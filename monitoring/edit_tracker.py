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
     * Phase 1: Cache all recent comments (with their parsed command names)
     * Phase 2: Check edited comments for genuinely new commands
     * Phase 3: Clean up old cache entries

2. progress_tracker():
   - Monitors posts marked as "In Progress"
   - Checks if claim periods have expired (based on settings)
   - Automatically resets expired claims to "Untranslated" status
   - Supports both single-language and multi-language posts
   - Removes claim comments when resetting posts

Both functions help maintain data integrity by catching changes that
might otherwise be missed in normal processing.
...

Logger tag: [MN:EDIT]
"""

import logging
import time
from typing import TYPE_CHECKING

from praw import models

from config import SETTINGS
from config import logger as _base_logger
from database import db
from models.ajo import Ajo, ajo_loader
from models.instruo import comment_has_command
from models.komando import extract_commands_from_text
from models.kunulo import Kunulo
from reddit.connection import REDDIT, REDDIT_HELPER, USERNAME
from title.title_handling import process_title
from ziwen_commands.claim import parse_claim_comment

if TYPE_CHECKING:
    from praw.models import Comment

logger = logging.LoggerAdapter(_base_logger, {"tag": "MN:EDIT"})

# Sentinel used when a comment has no commands at all.
_NO_COMMANDS = ""


def _is_comment_within_edit_window(comment: "Comment") -> bool:
    """Skip comments that are too old and unedited.
    The limit is defined in settings as hours."""
    time_diff = time.time() - comment.created_utc
    age_in_seconds = SETTINGS["comment_edit_age_max"] * 3600

    return not time_diff > age_in_seconds


# ---------------------------------------------------------------------------
# Cache helpers
# ---------------------------------------------------------------------------


def _serialize_komandos(text: str) -> str:
    """
    Parse *text* for commands and return a comma-separated string of the
    unique command names found (e.g. ``"identify,translated"``).

    Returns an empty string when no commands are present, which is stored
    as-is so callers can distinguish "cached with no commands" from
    "not in cache at all" (the latter returns None from _get_cached_comment).
    """
    commands = extract_commands_from_text(text)
    # Preserve order while deduplicating, matching _deduplicate_args behaviour.
    seen: set[str] = set()
    names: list[str] = []
    for cmd in commands:
        if cmd.name not in seen:
            seen.add(cmd.name)
            names.append(cmd.name)
    return ",".join(names)


def _deserialize_komandos(komandos_str: str) -> set[str]:
    """
    Convert a stored komandos string back into a set of command names.
    Returns an empty set for the empty-string sentinel.
    """
    if not komandos_str:
        return set()
    return set(komandos_str.split(","))


class _CachedComment:
    """Thin container for what we read back from comment_cache."""

    __slots__ = ("body", "_komandos_str", "_komando_set")

    def __init__(self, body: str, komandos: str):
        """Store the cached comment body and raw komandos string."""
        self.body = body
        # Parsed lazily on first access via property below.
        self._komandos_str = komandos
        self._komando_set: set[str] | None = None

    @property
    def command_names(self) -> set[str]:
        """Deserialised set of command names; parsed lazily on first access."""
        if self._komando_set is None:
            self._komando_set = _deserialize_komandos(self._komandos_str)
        return self._komando_set


def _get_cached_comment(comment_id: str) -> "_CachedComment | None":
    """Retrieve cached body and komandos for *comment_id*.
    Returns None if the comment is not in the cache."""
    cursor = db.cursor_cache
    cursor.execute(
        "SELECT content, komandos FROM comment_cache WHERE id = ?", (comment_id,)
    )
    result = cursor.fetchone()
    if result is None:
        return None
    body, komandos = result
    return _CachedComment(body=body, komandos=komandos or _NO_COMMANDS)


def _update_comment_cache(
    comment_id: str,
    comment_body: str,
    created_utc: int,
    komandos: str | None = None,
) -> None:
    """Replace old cache entry with the new body and komandos string.

    If *komandos* is None the column is derived from *comment_body* here,
    so callers that have already parsed the commands can pass them in to
    avoid double-parsing.
    """
    if komandos is None:
        komandos = _serialize_komandos(comment_body)

    cursor = db.cursor_cache
    cursor.execute("DELETE FROM comment_cache WHERE id = ?", (comment_id,))
    cursor.execute(
        "INSERT INTO comment_cache VALUES (?, ?, ?, ?)",
        (comment_id, comment_body, created_utc, komandos),
    )
    db.conn_cache.commit()


def _remove_from_processed(comment_id: str) -> None:
    """Force a reprocess by removing from the processed comment database."""
    cursor = db.cursor_main
    cursor.execute("DELETE FROM old_comments WHERE id = ?", (comment_id,))
    db.conn_main.commit()
    logger.debug(f"Removed comment '{comment_id}' from processed database.")


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
    logger.debug("Cleaned up the edited comments cache.")


# ---------------------------------------------------------------------------
# Main tracker
# ---------------------------------------------------------------------------


def edit_tracker() -> None:
    """
    Detects edited r/translator comments that introduce new commands.
    If a meaningful change is detected, the comment is removed from the
    processed database so ziwen_commands will reprocess it.

    The comparison is command-set aware: reprocessing is only triggered
    when the edited version contains command names that were not present
    in the cached (pre-edit) version.  This correctly handles the case
    where a comment already had one command (e.g. !identify) and the
    user edits in a second one (e.g. !translated) — something the old
    boolean comment_has_command() check would have missed.
    """
    # Phase 1: Iterate over recent comments to seed / refresh the cache.
    # This catches "ninja edits" made within Reddit's 3-minute no-flag
    # window before they appear in the mod.edited queue.
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

        # Only insert; never overwrite in Phase 1 (we want the *original*
        # body to stay cached so Phase 2 can diff against it later).
        cached = _get_cached_comment(comment_id)
        if not cached:
            # Don't record komandos for the bot's own comments — they would
            # produce false positives when the edit diff runs in Phase 2.
            author = str(comment.author) if comment.author else ""
            komandos = (
                _NO_COMMANDS
                if author.lower() == USERNAME.lower()
                else _serialize_komandos(comment_body)
            )
            logger.debug(
                f"Cached new comment `{comment_id}` "
                f"(komandos: {komandos if komandos else 'none'})"
            )
            _update_comment_cache(
                comment_id, comment_body, int(comment.created_utc), komandos
            )

    # Phase 2: Fetch only the edited comments from the subreddit.
    # This produces a generator that includes both comments and submissions.
    for item in REDDIT.subreddit(SETTINGS["subreddit"]).mod.edited(
        limit=SETTINGS["comment_edit_num_limit"]
    ):
        # Skip submissions, keep only comments.
        if isinstance(item, models.Submission):
            continue

        comment_id = item.id
        comment_new_body = item.body.strip()

        # Comment is beyond our monitoring window.
        if not _is_comment_within_edit_window(item):
            continue

        # Fast pre-check: if the new version has no commands at all,
        # there is nothing to reprocess regardless of what the old
        # version contained.
        if not comment_has_command(item):
            continue

        # Read the cached (pre-edit) state.
        cached = _get_cached_comment(comment_id)
        comment_old_body = cached.body if cached else ""

        if comment_old_body == comment_new_body:
            logger.debug(f"Comment `{comment_id}`: body unchanged, skipping.")
            continue

        # Determine which command names are genuinely new.
        old_command_names: set[str] = cached.command_names if cached else set()
        new_commands = extract_commands_from_text(comment_new_body)
        new_command_names: set[str] = {cmd.name for cmd in new_commands}

        added_commands = new_command_names - old_command_names

        if added_commands:
            logger.info(
                f"[Edit_Tracker] Reprocessing triggered for `{comment_id}`: "
                f"new command(s) {sorted(added_commands)} detected. "
                f"https://www.reddit.com{item.permalink}"
            )
            _remove_from_processed(comment_id)
        else:
            logger.debug(
                f"Comment `{comment_id}` edited but no new commands added "
                f"(had={sorted(old_command_names)}, now={sorted(new_command_names)})."
            )

        # Persist the updated body and freshly-parsed komandos.
        new_komandos = ",".join(
            dict.fromkeys(cmd.name for cmd in new_commands)  # ordered dedup
        )
        _update_comment_cache(
            comment_id, comment_new_body, int(item.created_utc), new_komandos
        )

    # Phase 3: Cache cleanup.
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
    posts_checked = 0
    search_results = REDDIT_HELPER.subreddit(SETTINGS["subreddit"]).search(
        search_query, time_filter="week", sort="new"
    )

    for post in search_results:
        post_id = post.id
        permalink = post.permalink
        posts_checked += 1

        # Load Ajo object from local cache or create from Reddit
        ajo = ajo_loader(post_id)
        if ajo is None:  # Unlikely to happen, but just in case.
            logger.debug("Couldn't find Ajo in local database. Loading from Reddit.")
            ajo = Ajo.from_titolo(process_title(post.title))

        # Skip if the data doesn't match an in progress post for some reason.
        if (ajo.type in ("single", "multiple")) and not ajo.is_defined_multiple:
            if ajo.status != "inprogress":
                continue  # Skip posts without the correct flair
        else:  # Defined multiple
            has_inprogress = (
                isinstance(ajo.status, dict) and "inprogress" in ajo.status.values()
            )
            if not has_inprogress:
                continue  # No inprogress marking in any of the dictionary's items.

        kunulo_object = Kunulo.from_submission(post)
        comment_claim_id = kunulo_object.get_tag("comment_claim")

        # Skip if there's no claim comment ID
        if not comment_claim_id:
            logger.warning(
                f"No comment_claim found for post {post_id}. Skipping. {permalink}"
            )
            continue

        try:
            claim_comment = REDDIT_HELPER.comment(comment_claim_id)
            claim_comment_data = parse_claim_comment(claim_comment.body, current_time)
            time_diff = claim_comment_data.get("claim_time_diff")
        except Exception as e:
            logger.warning(
                f"Failed to fetch/parse claim comment for post {post_id}. "
                f"Error: {e}. Skipping. {permalink}"
            )
            continue

        # Skip if there's no claim time data, or if the time difference
        # is still within the allowable amount.
        if time_diff is None or time_diff <= SETTINGS["claim_period"]:
            continue

        # Claim expired: remove claim comment and reset post
        logger.info(f"Post exceeded claim period. Resetting. {permalink}")
        if ajo.type == "single":
            kunulo_object.delete("comment_claim")
            ajo.set_status("untranslated")
        elif ajo.is_defined_multiple:
            inprogress_keys = (
                [key for key, value in ajo.status.items() if value == "inprogress"]
                if isinstance(ajo.status, dict)
                else []
            )
            # Iterate over only the languages which are still marked
            # in progress.
            for key in inprogress_keys:
                if claim_comment_data["language"].preferred_code == key:
                    kunulo_object.delete("comment_claim")
                    ajo.set_defined_multiple_status(key, "untranslated")

        ajo.update_reddit()

    logger.debug(f"Checked {posts_checked} in-progress post(s)")

    return


if __name__ == "__main__":
    start_time = time.time()
    logger.info("Running Edit Tracker...")
    edit_tracker()
    logger.info(f"Finished. {round(time.time() - start_time, 2)} seconds elapsed.")
