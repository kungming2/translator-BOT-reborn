#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
Main script to fetch posts and act upon them.
"""

import re
import time
import traceback

from wasabi import msg

from config import SETTINGS, logger
from connection import REDDIT
from database import db, record_filter_log
# from dupe_detector import duplicate_detector
from error import error_log_extended
from models.ajo import Ajo, ajo_loader
from models.diskuto import Diskuto, diskuto_writer
from notifications import is_user_over_submission_limit, notifier
from reddit_sender import message_reply
from request_closeout import closeout_posts
from responses import RESPONSE
from usage_statistics import action_counter
from time_handling import get_current_utc_date
from title_handling import (
    Titolo,
    format_title_correction_comment,
    is_english_only,
    main_posts_filter,
)
from utility import fetch_youtube_length
from wiki import update_wiki_page


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
    valid_period = SETTINGS["claim_period"] * 3  # Window to act on posts
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
        # by Wenju
        diskuto_pattern = r"^\s*\[(" + "|".join(SETTINGS["internal_post_types"]) + r")]"
        if re.match(diskuto_pattern, post_title, flags=re.I):
            diskuto_output = Diskuto.process_post(post)
            diskuto_writer(diskuto_output)
            logger.info(
                "> `post.id` post saved as an internal post for later processing."
            )
            continue  # Do not write to regular Ajo database.

        # Skip if post has already been processed
        if db.cursor_main.execute(
            "SELECT 1 FROM old_posts WHERE ID = ?", (post_id,)
        ).fetchone():
            logger.debug(
                f"[ZW] Posts: This post {post_id} already exists in the processed database."
            )

            # Try to load the associated Ajo object
            post_ajo = ajo_loader(post_id)
            if post_ajo:
                logger.debug(f"[ZW] Posts: Loaded existing Ajo for post {post_id}.")
            else:
                logger.warning(
                    f"[ZW] Posts: Post {post_id} is in `old_posts` database but has no Ajo stored."
                )
            continue

        # Create a new Ajo here into memory if it doesn't already exist.
        if not post_ajo:
            logger.info(
                "[ZW] Posts: No Ajo stored in existing database. Creating new Ajo..."
            )
            titolo_content = Titolo.process_title(post)
            post_ajo = Ajo.from_titolo(titolo_content, post)

        # Mark post as processed
        db.cursor_main.execute("INSERT INTO old_posts (ID) VALUES (?)", (post_id,))
        db.conn_main.commit()

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
        if post_ajo.language_name:
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
        messages_send_okay = post_age < 3600
        if not messages_send_okay:
            logger.info(
                f"[ZW] Posts: Post `{post_id}` is too old to send notifications for."
            )

        # Apply a filtration test to make sure this post is valid.
        post_okay, filtered_title, filter_reason = main_posts_filter(post_title)

        # If it fails this test, write to `record_filter_log`
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
            action_counter(1, "Removed posts")  # Write to the counter log
            logger.info(
                f"[ZW] Posts: Removed post that violated formatting guidelines. Title: {post_title} | `{post.id}`"
            )
            continue

        # Check for English-only content.
        if is_english_only(titolo_content):
            # Remove this post, as it is English-only.
            if not SETTINGS["testing_mode"]:
                post.mod.remove()
            message_reply(
                post, RESPONSE.COMMENT_ENGLISH_ONLY.format(author=post_author)
            )

            record_filter_log(post_title, post.created_utc, "EE")
            action_counter(1, "Removed posts")  # Write to the counter log
            logger.info("[ZW] Posts: Removed an English-only post. | `{post.id}`")
            continue

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
            if video_length > SETTINGS["video_long_seconds"] and "t=" not in post.url:
                logger.info(
                    f"[ZW] Posts: This is a long YouTube video ({video_length} seconds)."
                )
                post_long_comment = True

        # This is a boolean that is True if the user has posted too much
        # in a short period of time and False if they haven't.
        user_posted_too_much = is_user_over_submission_limit(post_author)

        # Get the Titolo and send notifications to users.
        if messages_send_okay and not user_posted_too_much:
            action_counter(1, "New posts")  # Write to the counter log
            for lingvo in titolo_content.notify_languages:
                notified = notifier(
                    lingvo, post
                )  # Returns a list of messaged individuals.

                # Add the list of notified users to the Ajo.
                post_ajo.add_notified(notified)

        # Leave a long comment if required.
        if post_long_comment:
            # Add attribute to Ajo
            post_ajo.is_long = True

            long_comment = RESPONSE.COMMENT_LONG + RESPONSE.BOT_DISCLAIMER
            message_reply(post, long_comment)
            logger.info("[ZW] Posts: Left a comment informing that the post is long.")

        # Add to the saved wiki page if it's not a commonly requested language.
        if not post_ajo.lingvo.supported:
            update_wiki_page(
                "save",
                get_current_utc_date(),
                post_title,
                post_id,
                post_ajo.lingvo.name,
            )

        # Update the Ajo with the Titolo data. This takes care of writing
        # the Ajo to the local database as well as updating the Reddit
        # flair.
        logger.debug(
            f"[ZW] Posts: Created Ajo for new post and saved to local database. | `{post.id}`"
        )
        logger.info(f"[ZW] Post Ajo ID: `{post_ajo.id}`")
        logger.info(f"[ZW] Post Ajo initial data: `{vars(post_ajo)}`")

        # Only update if we're not in testing mode.
        if not SETTINGS["testing_mode"]:
            post_ajo.update_reddit()

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
