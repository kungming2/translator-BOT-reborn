#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
Main script to fetch posts and act upon them.
...

Logger tag: [ZW:P]
"""

import logging
import pprint
import time

from praw.models import Submission

from config import SETTINGS
from config import logger as _base_logger
from database import db, record_filter_log
from models.ajo import Ajo
from models.diskuto import Diskuto, diskuto_exists, diskuto_writer
from monitoring.dupe_detector import check_image_duplicate, duplicate_detector
from monitoring.request_closeout import closeout_posts
from monitoring.usage_statistics import action_counter
from reddit.connection import REDDIT, is_internal_post, is_mod, remove_content
from reddit.notifications import is_user_over_submission_limit, notifier
from reddit.reddit_sender import reddit_reply
from reddit.startup import STATE
from reddit.wiki import update_wiki_page
from responses import RESPONSE
from time_handling import get_current_utc_date
from title.title_ai import format_title_correction_comment
from title.title_handling import is_english_only, main_posts_filter, process_title
from utility import fetch_youtube_length

logger = logging.LoggerAdapter(_base_logger, {"tag": "ZW:P"})


# ─── Internal helpers ─────────────────────────────────────────────────────────


def _assign_internal_post_flair(
    post: Submission, internal_post_type: str | None
) -> bool:
    """
    Assign the appropriate flair template to an internal post based on its type.

    :param post: Reddit submission object
    :param internal_post_type: Type of internal post (e.g., 'meta', 'community'), or None
    :return: True if flair was successfully assigned, False otherwise
    """
    if not internal_post_type:
        logger.warning(
            f"Internal post `{post.id}` has no post_type, cannot assign flair."
        )
        return False

    template_id = STATE.post_templates.get(internal_post_type)

    if not template_id:
        logger.warning(
            f"No flair template found for internal post type '{internal_post_type}' "
            f"on post `{post.id}`"
        )
        return False

    try:
        post.flair.select(
            flair_template_id=template_id, text=internal_post_type.title()
        )
        logger.info(
            f"Assigned '{internal_post_type}' flair to internal post `{post.id}`"
        )
        return True
    except Exception as e:
        logger.error(f"Failed to assign flair to internal post `{post.id}`: {e}")
        return False


# ─── Main post processing loop ────────────────────────────────────────────────


def ziwen_posts(post_limit: int | None = None) -> None:
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

    current_time = int(time.time())
    logger.debug(f"Fetching new r/{subreddit_object} posts at {current_time}.")

    # Fetch and reverse so we process oldest posts first, newest last.
    posts = list(subreddit_object.new(limit=fetch_amount))
    posts.reverse()
    logger.debug(f"Fetched {len(posts)} posts to process.")

    # ── Duplicate detection ────────────────────────────────────────────────────

    logger.info("Running duplicate detection...")
    detection_limit = int(fetch_amount // 4)
    dupes_removed = duplicate_detector(
        list_posts=posts[-detection_limit:],
        reddit_instance=REDDIT,
        testing_mode=SETTINGS["testing_mode"],
    )
    if dupes_removed:
        logger.info(f"Completed duplicate detection. Removed {dupes_removed} posts.")
    else:
        logger.info("No duplicate posts found.")

    for post in posts:
        post_ajo = None
        post_id = post.id
        post_age = current_time - post.created_utc  # Age of this post, in seconds
        post_title = str(post.title)
        post_long_comment = False  # Whether to warn user the post is long.

        # ── Pre-flight checks ──────────────────────────────────────────────────

        # Skip posts with deleted authors.
        try:
            post_author = post.author.name
        except AttributeError:
            logger.debug(f"> u/{post.author} does not exist.")
            continue

        # Handle internal posts (meta, community, etc.) separately.
        if is_internal_post(post):
            if diskuto_exists(post_id):
                logger.debug(f"> Internal post `{post_id}` has already been processed.")
                continue
            else:
                diskuto_output = Diskuto.process_post(post)
                diskuto_writer(diskuto_output)
                _assign_internal_post_flair(post, diskuto_output.post_type)
                logger.info(
                    f"> `{post.id}` post saved as an internal post for later processing."
                )
                continue  # Do not write to regular Ajo database.

        # Skip already-processed posts.
        if db.cursor_main.execute(
            "SELECT 1 FROM old_posts WHERE id = ?", (post_id,)
        ).fetchone():
            logger.debug(
                f"This post {post_id} already exists in the processed database."
            )
            continue

        # Mark post as processed.
        logger.info(f"Now processing `{post_id}`: {post_title}...")
        db.cursor_main.execute(
            "INSERT INTO old_posts (id, created_utc, filtered) VALUES (?, ?, ?)",
            (post_id, int(post.created_utc), 0),
        )
        db.conn_main.commit()

        # ── Title filtration ───────────────────────────────────────────────────

        logger.info(
            f"About to assess filtration for post `{post_id}` with title: "
            f"{post_title} | `{post_id}`"
        )
        post_okay, filtered_title, filter_reason = main_posts_filter(post_title)
        logger.info(f"Filter result for `{post_id}`: {post_okay}, {filter_reason}")

        if not post_okay:
            if not SETTINGS["testing_mode"]:
                remove_content(
                    post, "title", "Removed: Failed all title filtration routines."
                )
            suggested_title_replacement = format_title_correction_comment(
                title_text=post_title, author=post_author
            )
            removal_suggestion = suggested_title_replacement + RESPONSE.BOT_DISCLAIMER
            reddit_reply(post, removal_suggestion)

            record_filter_log(
                post_title, post.created_utc, filter_reason or "Unknown filter reason"
            )
            db.cursor_main.execute(
                "UPDATE old_posts SET filtered = 1 WHERE id = ?", (post_id,)
            )
            db.conn_main.commit()

            action_counter(1, "Removed posts")
            logger.info(
                f"Removed post that violated formatting guidelines. Title: {post_title} | `{post.id}`"
            )
            continue

        # ── Ajo creation ───────────────────────────────────────────────────────

        if not post_ajo:
            logger.info(
                f"No Ajo stored in existing database for `{post.id}`. Creating new Ajo..."
            )
            titolo_content = process_title(post)
            post_ajo = Ajo.from_titolo(titolo_content, post)

        # Check for English-only posts.
        if is_english_only(titolo_content):
            if not SETTINGS["testing_mode"]:
                remove_content(post, "title", "Removed: English-only post.")
            reddit_reply(post, RESPONSE.COMMENT_ENGLISH_ONLY.format(author=post_author))

            record_filter_log(post_title, post.created_utc, "EE")
            db.cursor_main.execute(
                "UPDATE old_posts SET filtered = 1 WHERE id = ?", (post_id,)
            )
            db.conn_main.commit()

            action_counter(1, "Removed posts")
            logger.info(f"Removed an English-only post. | `{post.id}`")
            continue

        # Skip posts that are already in a non-untranslated state.
        if post_ajo is not None and post_ajo.status in [
            "translated",
            "doublecheck",
            "missing",
            "inprogress",
        ]:
            logger.info(
                f"Skipping post {post_id} because status is '{post_ajo.status}'."
            )
            continue

        # ── Image duplicate check ──────────────────────────────────────────────

        if post_ajo and post_ajo.image_hash:
            duplicate_result = check_image_duplicate(
                post=post,
                ajo=post_ajo,
                days_lookback=90,
                max_distance=5,
                testing_mode=SETTINGS["testing_mode"],
            )

            if duplicate_result and duplicate_result["found"]:
                logger.info(
                    f"Image duplicate detected for `{post_id}`. "
                    f"Distance: {duplicate_result['distance']}, "
                    f"Same author: {duplicate_result['same_author']}"
                )

        # ── Notification eligibility ───────────────────────────────────────────

        if post_ajo.lingvo:
            logger.info(
                f"New {post_ajo.language_name} post submitted by "
                f"u/{post_author} | `{post_id}`."
            )
        else:
            logger.warning(f"Post with ID `{post_id}` has no language name.")

        # Skip posts that are too old to act on (e.g. after a long downtime).
        if post_age > valid_period:
            logger.info(
                f"Post `{post_id}` is too old for my action parameters. Skipping..."
            )
            continue

        # Only send notifications for recent posts; older ones are caught up
        # silently. notification_cutoff_age is in MINUTES, converted to seconds.
        notifications_cutoff = SETTINGS["notification_cutoff_age"] * 60
        messages_send_okay = post_age < notifications_cutoff
        if not messages_send_okay:
            logger.info(f"Post `{post_id}` is too old to send notifications for.")

        # Disable notifications for moderator test posts.
        if messages_send_okay and SETTINGS.get("mod_test_emoji"):
            mod_test_emoji = SETTINGS["mod_test_emoji"]
            if mod_test_emoji in post_title and is_mod(post_author):
                messages_send_okay = False
                logger.info(
                    f"Post `{post_id}` is a moderator test post. Notifications disabled."
                )

        # ── Length checks ──────────────────────────────────────────────────────

        if len(post.selftext) > SETTINGS["post_long_characters"]:
            logger.info("This is a long piece of text.")
            post_long_comment = True
        elif "youtube.com" in post.url or "youtu.be" in post.url:
            logger.debug(f"Analyzing YouTube video link at: {post.url}")
            video_length = fetch_youtube_length(post.url)

            if (
                video_length is not None
                and video_length > SETTINGS["video_long_seconds"]
                and "t=" not in post.url
            ):
                logger.info(f"This is a long YouTube video ({video_length} seconds).")
                post_long_comment = True
            elif video_length is None:
                logger.warning(f"Could not fetch YouTube video length for {post.url}")

        # ── Notifications and replies ──────────────────────────────────────────

        user_posted_too_much = is_user_over_submission_limit(post_author)

        if messages_send_okay and not user_posted_too_much:
            action_counter(1, "New posts")
            already_contacted: set[str] = set()

            if titolo_content and hasattr(titolo_content, "notify_languages"):
                for lingvo in titolo_content.notify_languages:
                    notified = notifier(
                        lingvo, post, already_contacted=list(already_contacted)
                    )
                    post_ajo.add_notified(notified)
                    already_contacted.update(notified)
            else:
                logger.warning(
                    f"Cannot send notifications for post {post_id} -"
                    f" titolo_content is None or missing notify_languages."
                )

        # Leave a long-post comment if required.
        if post_long_comment:
            post_ajo.is_long = True
            long_comment = RESPONSE.COMMENT_LONG + RESPONSE.BOT_DISCLAIMER
            reddit_reply(post, long_comment)
            logger.info(f"Left a comment informing that the post `{post_id}` is long.")

        # Leave an informative comment for unknown-language posts.
        if post_ajo.preferred_code == "unknown":
            unknown_comment = RESPONSE.COMMENT_UNKNOWN + RESPONSE.BOT_DISCLAIMER
            reddit_reply(post, unknown_comment)
            logger.info(f"Left an informative 'unknown' comment on post `{post_id}`.")

        # ── Ajo finalization ───────────────────────────────────────────────────

        # Save to the wiki if this is not a commonly requested language.
        if post_ajo.lingvo is None or not post_ajo.lingvo.supported:
            language_name = (
                post_ajo.lingvo.name if post_ajo.lingvo is not None else None
            ) or "*Unparsed*"
            update_wiki_page(
                "save",
                get_current_utc_date(),
                post_title,
                post_id,
                language_name,
            )

        logger.debug(
            f"Created Ajo for new post and saved to local database. | `{post.id}`"
        )
        logger.info(f"Post Title: `{post.title}`")
        logger.info(f"Post Link: `https://www.reddit.com{post.permalink}`")
        logger.info(f"Post Ajo ID: `{post_ajo.id}`")
        logger.info(f"Post Ajo initial data:\n{pprint.pformat(vars(post_ajo))}")

        # Write the Ajo to disk and update Reddit flair.
        if not SETTINGS["testing_mode"]:
            post_ajo.update_reddit(initial_update=True)

    # Run request closeout once per polling cycle.
    closeout_posts()
    return
