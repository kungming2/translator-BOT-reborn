#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
Main script to fetch posts and act upon them.
"""

import time
import traceback

from wasabi import msg

from config import SETTINGS, logger
from connection import REDDIT, is_internal_post
from database import db, record_filter_log

# from dupe_detector import duplicate_detector
from error import error_log_extended
from models.ajo import Ajo
from models.diskuto import Diskuto, diskuto_exists, diskuto_writer
from notifications import is_user_over_submission_limit, notifier
from reddit_sender import message_reply
from request_closeout import closeout_posts
from responses import RESPONSE
from startup import STATE
from time_handling import get_current_utc_date
from title_handling import (
    Titolo,
    format_title_correction_comment,
    is_english_only,
    main_posts_filter,
)
from usage_statistics import action_counter
from utility import fetch_youtube_length
from wiki import update_wiki_page


def _assign_internal_post_flair(post, internal_post_type: str | None) -> bool:
    """
    Assign the appropriate flair template to an internal post based on its type.

    :param post: Reddit submission object
    :param internal_post_type: Type of internal post (e.g., 'meta', 'community'), or None
    :return: True if flair was successfully assigned, False otherwise
    """
    if not internal_post_type:
        logger.warning(
            f"[ZW] Internal post `{post.id}` has no post_type, cannot assign flair."
        )
        return False

    # Get the template ID for this internal post type
    template_id = STATE.post_templates.get(internal_post_type)

    if not template_id:
        logger.warning(
            f"[ZW] No flair template found for internal post type '{internal_post_type}' "
            f"on post `{post.id}`"
        )
        return False

    try:
        post.flair.select(flair_template_id=template_id, text=internal_post_type)
        logger.info(
            f"[ZW] Assigned '{internal_post_type}' flair to internal post `{post.id}`"
        )
        return True
    except Exception as e:
        logger.error(f"[ZW] Failed to assign flair to internal post `{post.id}`: {e}")
        return False


def ziwen_posts(post_limit=None):
    """
    The primary top-level post filtering runtime for r/translator.
    It removes posts that do not meet the subreddit's guidelines.
    It also assigns flair to posts, saves them as Ajos, and determines
    what to pass to the notification system.

    :return: Nothing.
    """
    subreddit_object = REDDIT.subreddit(SETTINGS["subreddit"])
    fetch_amount = post_limit if post_limit is not None else SETTINGS["max_posts"]
    valid_period = SETTINGS["claim_period"] * 9  # Window to act on posts
    titolo_content = None

    current_time = int(time.time())  # This is the current time.
    logger.debug(f"[ZW] Fetching new r/{subreddit_object} posts at {current_time}.")
    posts = []

    # We get the last X new posts.
    posts += list(subreddit_object.new(limit=fetch_amount))
    # Reverse order so that we start processing the older posts, with
    # newest ones last.
    posts.reverse()

    # ========================================================================
    # DUPLICATE DETECTION - Run before main processing
    # ========================================================================
    """
    logger.info("[ZW] Running duplicate detection...")
    dupes_removed = duplicate_detector(
        list_posts=posts,
        reddit_instance=REDDIT,
        testing_mode=SETTINGS["testing_mode"],
    )
    if dupes_removed:
        logger.info(
            f"[ZW] Completed duplicate detection. Removed {dupes_removed} posts."
        )
    """

    # Main processing logic.
    for post in posts:
        # Anything that needs to happen every loop goes here.
        post_ajo = None
        post_id = post.id
        post_age = current_time - post.created_utc  # Age of this post, in seconds
        post_title = str(post.title)
        post_long_comment = False  # Whether to warn user the post is long.

        try:
            post_author = post.author.name
        except AttributeError:
            # Author is deleted. We skip.
            logger.debug(f"> u/{post.author} does not exist.")
            continue

        # Handle internal posts (such as meta or community ones).
        # Build regex dynamically from the list, then passes to external
        # handling for internal notifications at designated intervals
        # by Wenju.
        if is_internal_post(post):
            if diskuto_exists(post_id):  # Already saved
                logger.debug(f"> Internal post `{post_id}` has already been processed.")
                continue
            else:
                diskuto_output = Diskuto.process_post(post)
                diskuto_writer(diskuto_output)

                # Assign it a proper flair template.
                _assign_internal_post_flair(post, diskuto_output.post_type)

                logger.info(
                    f"> `{post.id}` post saved as an internal post for later processing."
                )
                continue  # Do not write to regular Ajo database.

        # Skip if post has already been processed
        if db.cursor_main.execute(
            "SELECT 1 FROM old_posts WHERE id = ?", (post_id,)
        ).fetchone():
            logger.debug(
                f"[ZW] Posts: This post {post_id} already exists in the processed database."
            )
            continue

        logger.info(f"[ZW] Posts: Now processing `{post_id}`: {post_title}...")
        # Mark post as processed.
        db.cursor_main.execute(
            "INSERT INTO old_posts (id, created_utc, filtered) VALUES (?, ?, ?)",
            (post_id, int(post.created_utc), 0),
        )
        db.conn_main.commit()

        # Apply a filtration test to make sure this post is valid.
        logger.info(
            f"[ZW] Posts: About to filter post `{post_id}` with title: {post_title} | `{post_id}`"
        )
        post_okay, filtered_title, filter_reason = main_posts_filter(post_title)
        logger.info(
            f"[ZW] Posts: Filter result for `{post_id}`: {post_okay}, {filter_reason}"
        )

        # If it fails this test, write to `record_filter_log` and then
        # skip processing it.
        if not post_okay:
            # Remove this post, it failed all routines.
            if not SETTINGS["testing_mode"]:
                post.mod.remove()
            suggested_title_replacement = format_title_correction_comment(
                title_text=post_title, author=post_author
            )
            removal_suggestion = suggested_title_replacement + RESPONSE.BOT_DISCLAIMER
            message_reply(post, removal_suggestion)

            # Write the title to the log.
            record_filter_log(post_title, post.created_utc, filter_reason)
            # Mark post as filtered in database
            db.cursor_main.execute(
                "UPDATE old_posts SET filtered = 1 WHERE id = ?", (post_id,)
            )
            db.conn_main.commit()

            action_counter(1, "Removed posts")  # Write to the counter log
            logger.info(
                f"[ZW] Posts: Removed post that violated formatting guidelines. Title: {post_title} | `{post.id}`"
            )
            continue

        # Create a new Ajo here into memory if it doesn't already exist.
        if not post_ajo:
            logger.info(
                f"[ZW] Posts: No Ajo stored in existing database for `{post.id}`. Creating new Ajo..."
            )
            titolo_content = Titolo.process_title(post)
            post_ajo = Ajo.from_titolo(titolo_content, post)

        # Check for English-only POSTS.
        if is_english_only(titolo_content):
            # Remove this post, as it is English-only.
            if not SETTINGS["testing_mode"]:
                post.mod.remove()
            message_reply(
                post, RESPONSE.COMMENT_ENGLISH_ONLY.format(author=post_author)
            )

            record_filter_log(post_title, post.created_utc, "EE")
            # Mark post as filtered in database
            db.cursor_main.execute(
                "UPDATE old_posts SET filtered = 1 WHERE id = ?", (post_id,)
            )
            db.conn_main.commit()

            action_counter(1, "Removed posts")  # Write to the counter log
            logger.info(f"[ZW] Posts: Removed an English-only post. | `{post.id}`")
            continue

        # Check on Ajo status. We only want to deal with untranslated new posts.
        if post_ajo is not None and post_ajo.status in [
            "translated",
            "doublecheck",
            "missing",
            "inprogress",
        ]:
            logger.info(
                f"[ZW] Posts: Skipping post {post_id} because status is '{post_ajo.status}'."
            )
            continue

        # Continue work on post.
        logger.info(f"[ZW] Posts: Processing post `{post_id}`.")
        if post_ajo.lingvo:
            logger.info(
                f"[ZW] Posts: New {post_ajo.language_name} post submitted by "
                f"u/{post_author} | `{post_id}`."
            )
        else:
            logger.warning(
                f"[ZW] Posts: Post with ID `{post_id}` has no language name."
            )

        # Check post age to be younger than a period of time.
        # This is to speed up rare cases where there is a huge backlog
        # of posts due to an extremely long downtime.
        if post_age > valid_period:
            logger.info(
                f"[ZW] Posts: Post `{post_id}` is too old for my action "
                f"parameters. Skipping..."
            )
            continue

        # If the post is under an hour, give permission to send
        # notifications to people. Otherwise, we won't.
        # This is mainly for catching up with older posts for downtime;
        # we want to process them, but we don't want to send notes.
        # notification_cutoff_age is in MINUTES, converted to seconds
        # for comparison
        notifications_cutoff = SETTINGS["notification_cutoff_age"] * 60
        messages_send_okay = post_age < notifications_cutoff
        if not messages_send_okay:
            logger.info(
                f"[ZW] Posts: Post `{post_id}` is too old to send notifications for."
            )

        # After this point, this post is something we can work with.
        # Length checks for overly long posts.
        if len(post.selftext) > SETTINGS["post_long_characters"]:
            logger.info("[ZW] Posts: This is a long piece of text.")
            post_long_comment = True
        # Check for YouTube length.
        elif "youtube.com" in post.url or "youtu.be" in post.url:
            logger.debug(f"[ZW] Posts: Analyzing YouTube video link at: {post.url}")
            video_length = fetch_youtube_length(post.url)

            # If the video is considered long by our settings,
            # but make an exception if someone posts the exact timestamp.
            # Also check if video_length is not None (API might fail)
            if (
                video_length is not None
                and video_length > SETTINGS["video_long_seconds"]
                and "t=" not in post.url
            ):
                logger.info(
                    f"[ZW] Posts: This is a long YouTube video ({video_length} seconds)."
                )
                post_long_comment = True
            elif video_length is None:
                logger.warning(
                    f"[ZW] Posts: Could not fetch YouTube video length for {post.url}"
                )

        # This is a boolean that is True if the user has posted too much
        # in a short period of time and False if they haven't.
        user_posted_too_much = is_user_over_submission_limit(post_author)

        # Get the Titolo and send notifications to users.
        if messages_send_okay and not user_posted_too_much:
            action_counter(1, "New posts")  # Write to the counter log

            # Add None check for titolo_content before accessing notify_languages
            if titolo_content and hasattr(titolo_content, "notify_languages"):
                for lingvo in titolo_content.notify_languages:
                    notified = notifier(
                        lingvo, post
                    )  # Returns a list of messaged individuals.

                    # Add the list of notified users to the Ajo.
                    post_ajo.add_notified(notified)
            else:
                logger.warning(
                    f"[ZW] Posts: Cannot send notifications for post {post_id} -"
                    f" titolo_content is None or missing notify_languages."
                )

        # Leave a long comment if required.
        if post_long_comment:
            # Add attribute to Ajo
            post_ajo.is_long = True

            long_comment = RESPONSE.COMMENT_LONG + RESPONSE.BOT_DISCLAIMER
            message_reply(post, long_comment)
            logger.info(
                f"[ZW] Posts: Left a comment informing that the post `{post_id}` is long."
            )

        # Leave an "unknown" comment if it's an unknown post.
        if post_ajo.preferred_code == "unknown":
            unknown_comment = RESPONSE.COMMENT_UNKNOWN + RESPONSE.BOT_DISCLAIMER
            message_reply(post, unknown_comment)
            logger.info(
                f"[ZW] Posts: Left an informative 'unknown' comment on post `{post_id}`."
            )

        # Add to the saved wiki page if it's not a commonly requested language.
        # Handle case where lingvo might be None
        if post_ajo.lingvo is None or not post_ajo.lingvo.supported:
            # Get language name, handling None case
            language_name = (
                post_ajo.lingvo.name if post_ajo.lingvo is not None else "Unparsed"
            )

            update_wiki_page(
                "save",
                get_current_utc_date(),
                post_title,
                post_id,
                language_name,
            )

        # Update the Ajo with the Titolo data. This takes care of writing
        # the Ajo to the local database as well as updating the Reddit
        # flair.
        logger.debug(
            f"[ZW] Posts: Created Ajo for new post and saved to local database. | `{post.id}`"
        )
        logger.info(f"[ZW] Post Title: `{post.title}`")
        logger.info(f"[ZW] Post Link: `https://www.reddit.com{post.permalink}`")
        logger.info(f"[ZW] Post Ajo ID: `{post_ajo.id}`")
        logger.info(f"[ZW] Post Ajo initial data: `{vars(post_ajo)}`")

        # Only update if we're not in testing mode. This also writes the
        # Ajo to disk.
        if not SETTINGS["testing_mode"]:
            post_ajo.update_reddit(initial_update=True)

        # Run request closeout.
        closeout_posts()

    return


# Primary runtime.
if __name__ == "__main__":
    msg.good("Launching Ziwen posts...")
    # noinspection PyBroadException
    try:
        ziwen_posts(15)
    except Exception:  # intentionally broad: catch all exceptions for logging
        error_entry = traceback.format_exc()
        error_log_extended(error_entry, "Ziwen Posts")
    msg.info("Ziwen posts routine completed.")
