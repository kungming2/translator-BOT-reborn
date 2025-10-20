#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
Tracks changes in comments' edits. This works by caching comments and
checking against them later.

This module provides two main tracking functions:

1. edit_tracker():
   - Monitors recent comments for edits that add new commands
   - Detects both "ninja edits" (within 3 minutes, no edit flag) and
     regular edits (with edit flag)
   - Caches comment content and compares against new versions
   - Triggers reprocessing when new commands are added via edits
   - Uses a three-phase approach:
     * Phase 1: Cache all recent comments
     * Phase 2: Check edited comments for new commands
     * Phase 3: Clean up old cache entries

2. progress_tracker():
   - Monitors posts marked as "In Progress"
   - Checks if claim periods have expired (based on settings)
   - Automatically resets expired claims to "Untranslated" status
   - Supports both single-language and multi-language posts
   - Removes claim comments when resetting posts

Both functions help maintain data integrity by catching changes that
might otherwise be missed in normal processing.
"""

import time
from typing import TYPE_CHECKING

from praw import models
from wasabi import msg

from commands.claim import parse_claim_comment
from config import SETTINGS, logger
from connection import REDDIT, REDDIT_HELPER
from database import db
from models.ajo import Ajo, ajo_loader
from models.instruo import comment_has_command
from models.kunulo import Kunulo
from title_handling import Titolo

if TYPE_CHECKING:
    from praw.models import Comment


def _is_comment_within_edit_window(comment: "Comment") -> bool:
    """Skip comments that are too old and unedited.
    The limit is defined in settings as hours."""
    time_diff = time.time() - comment.created_utc
    age_in_seconds = SETTINGS["comment_edit_age_max"] * 3600

    return not time_diff > age_in_seconds


def _get_cached_comment(comment_id: str) -> str | None:
    """Retrieve comment text from cache."""
    cursor = db.cursor_cache
    cursor.execute("SELECT content FROM comment_cache WHERE id = ?", (comment_id,))
    result = cursor.fetchone()
    return result[0] if result else None  # Just the body text, or None


def _update_comment_cache(comment_id: str, comment_body: str) -> None:
    """Replace old comment text with new version."""
    cursor = db.cursor_cache
    cursor.execute("DELETE FROM comment_cache WHERE id = ?", (comment_id,))
    cursor.execute(
        "INSERT INTO comment_cache VALUES (?, ?)", (comment_id, comment_body)
    )
    db.conn_cache.commit()


def _remove_from_processed(comment_id: str) -> None:
    """Force a reprocess by removing from the processed comment database."""
    cursor = db.cursor_main
    cursor.execute("DELETE FROM old_comments WHERE id = ?", (comment_id,))
    db.conn_main.commit()
    logger.debug(
        f"[ZW] Edit Tracker: Removed comment '{comment_id}' from processed database."
    )


def _cleanup_comment_cache(limit: int) -> None:
    """Remove oldest entries beyond comment limit."""
    cursor = db.cursor_cache
    cleanup = """
        DELETE FROM comment_cache 
        WHERE id NOT IN (
            SELECT id FROM comment_cache ORDER BY id DESC LIMIT ?
        )
    """
    cursor.execute(cleanup, (limit,))
    db.conn_cache.commit()
    logger.debug("[ZW] Edit Finder: Cleaned up the edited comments cache.")


def edit_tracker() -> None:
    """
    Detects edited r/translator comments that involve commands or
    lookup items. If a meaningful change is detected, the comment is
    removed from the processed database for reprocessing.
    """
    # Phase 1: Iterate over comments. This only needs to get the comments
    # which may have been "ninja-edited"; that is, they were edited in
    # the last 3 minutes and therefore do not have an 'edited' flag.
    total_fetch_num = SETTINGS["comment_edit_num_limit"] * 2
    total_keep_num = total_fetch_num * 5
    for comment in REDDIT_HELPER.subreddit(SETTINGS["subreddit"]).comments(
        limit=total_fetch_num
    ):
        # Comment is beyond our time span for monitoring.
        if not _is_comment_within_edit_window(comment):
            continue

        comment_id = comment.id
        comment_body = comment.body.strip()

        # Check against the pre-existing cache.
        cached = _get_cached_comment(comment_id)

        # If not in cache, insert it
        if not cached:
            _update_comment_cache(comment_id, comment_body)
            continue

    # Phase 2: Fetch only the edited comments from the subreddit.
    # This produces a generator that includes both comments and
    # submissions.
    for item in REDDIT.subreddit(SETTINGS["subreddit"]).mod.edited(
        limit=SETTINGS["comment_edit_num_limit"]
    ):
        # Skip submissions, keep only comments
        if isinstance(item, models.Submission):
            continue

        comment_id = item.id
        comment_new_body = item.body.strip()

        # Check the comment's age.
        if not _is_comment_within_edit_window(item):
            continue

        # Comment has no actionable command.
        if not comment_has_command(item):
            continue

        # Fetch the old stored information.
        cached = _get_cached_comment(comment_id)
        comment_old_body = cached if cached else ""
        if comment_old_body == comment_new_body:
            logger.debug("The comment stored is the same.")
            continue

        # Compare command relevance between old and new versions
        old_had_command = (
            comment_has_command(comment_old_body) if comment_old_body else False
        )
        new_has_command = comment_has_command(item)

        # There's a new command in the new comment text.
        if new_has_command and not old_had_command:
            logger.info(
                f"[Edit_Tracker] Reprocessing triggered: "
                f"{comment_id} at https://www.reddit.com{item.permalink}"
            )
            # Remove the comment ID from the database so that
            # ziwen_commands will reprocess it.
            _remove_from_processed(comment_id)

        # Update the cache.
        _update_comment_cache(comment_id, comment_new_body)

    # Phase 3: Cache cleanup
    _cleanup_comment_cache(total_keep_num)

    return


def progress_tracker() -> None:
    """
    Checks Reddit for posts marked as "In Progress" and determines
    if their claim period has expired. If expired, resets them to the
    'Untranslated' state. This supports both single and defined multiple
    posts.
    """
    current_time = int(time.time())
    search_query = 'flair:"in progress"'
    search_results = REDDIT_HELPER.subreddit(SETTINGS["subreddit"]).search(
        search_query, time_filter="week", sort="new"
    )

    for post in search_results:
        post_id = post.id
        permalink = post.permalink

        # Load Ajo object from local cache or create from Reddit
        ajo = ajo_loader(post_id)
        if ajo is None:  # Unlikely to happen, but just in case.
            logger.debug(
                "[ZW] progress_tracker: Couldn't find Ajo in "
                "local database. Loading from Reddit."
            )
            ajo = Ajo.from_titolo(Titolo.process_title(post.title))

        # Skip if the data doesn't match an in progress post for some reason.
        if (
            ajo.type == "single"
            or ajo.type == "multiple"
            and not ajo.is_defined_multiple
        ):
            if ajo.status != "inprogress":
                continue  # Skip posts without the correct flair
        else:  # Defined multiple
            has_inprogress = "inprogress" in ajo.status.values()
            if not has_inprogress:
                continue  # No inprogress marking in any of the dictionary's items.

        kunulo_object = Kunulo.from_submission(post)
        claim_comment = REDDIT_HELPER.comment(kunulo_object.get_tag("comment_claim"))
        claim_comment_data = parse_claim_comment(claim_comment.body, current_time)
        time_diff = claim_comment_data.get("claim_time_diff")

        # Skip if there's no claim time data, or if the time difference
        # is still within the allowable amount.
        if time_diff is None or time_diff <= SETTINGS["claim_period"]:
            continue

        # Claim expired: remove claim comment and reset post
        logger.info(
            f"[ZW] progress_tracker: Post exceeded claim period. Resetting. {permalink}"
        )
        if ajo.type == "single":
            kunulo_object.delete("comment_claim")
            ajo.set_status("untranslated")
        elif ajo.is_defined_multiple:
            inprogress_keys = [
                key for key, value in ajo.status.items() if value == "inprogress"
            ]
            # Iterate over only the languages which are still marked
            # in progress.
            for key in inprogress_keys:
                if claim_comment_data["language"].preferred_code == key:
                    kunulo_object.delete("comment_claim")
                    ajo.set_defined_multiple_status("untranslated")

        ajo.update_reddit()

    return


if __name__ == "__main__":
    start_time = time.time()
    with msg.loading("Running Edit Tracker..."):
        edit_tracker()
    msg.info(f"Finished. {round(time.time() - start_time, 2)} seconds elapsed.")
