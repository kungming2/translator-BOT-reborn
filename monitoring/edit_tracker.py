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
   - Triggers reprocessing when new commands are added via edits, or
     when lookup_cjk / lookup_wp backtick/brace content changes even
     if the set of command names stays the same (e.g. switching from
     `七転八起` to `七転八起`! to disable tokenization)
   - Uses a three-phase approach:
     * Phase 1: Cache all recent comments (with their parsed command names
       and resolved lookup content)
     * Phase 2: Check edited comments for genuinely new commands or
       changed lookup content
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

# ─── Imports ──────────────────────────────────────────────────────────────────

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

# ─── Module-level constants ───────────────────────────────────────────────────

logger = logging.LoggerAdapter(_base_logger, {"tag": "MN:EDIT"})

# Sentinel used when a comment has no commands at all.
_NO_COMMANDS = ""

# Separators used when serializing lookup_content to a single DB column.
# _LOOKUP_CONTENT_SEP divides individual terms within a block.
# _LOOKUP_SECTION_SEP divides the cjk block from the wp block.
# Neither character appears in CJK text, Wikipedia titles, or language codes.
_LOOKUP_CONTENT_SEP = "|"
_LOOKUP_SECTION_SEP = "§"


# ─── Cache helpers ────────────────────────────────────────────────────────────


def _is_comment_within_edit_window(comment: "Comment") -> bool:
    """Return True if the comment is young enough to still be monitored.
    The age limit is defined in settings as hours."""
    time_diff = time.time() - comment.created_utc
    age_in_seconds = SETTINGS["comment_edit_age_max"] * 3600
    return not time_diff > age_in_seconds


def _serialize_komandos(text: str) -> str:
    """
    Parse *text* for commands and return a comma-separated string of the
    unique command names found (e.g. ``"identify,translated"``).

    Returns an empty string when no commands are present, which is stored
    as-is so callers can distinguish "cached with no commands" from
    "not in cache at all" (the latter returns None from _get_cached_comment).
    """
    commands = extract_commands_from_text(text)
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


# ─── Lookup content serialization ─────────────────────────────────────────────


def _serialize_lookup_content(commands: list) -> str:
    """
    Serialize lookup_cjk and lookup_wp data from a parsed command list into
    a compact string for storage in the lookup_content column.

    Format: ``<cjk_block>§<wp_block>``

    cjk_block: ``lang:term|lang:term|...``
        - lang is the 2/3-char code; term is the post-tokenization token.
        - The explicit flag and disable_tokenization flag are excluded;
          only the resolved terms matter for change detection.

    wp_block: ``term@lang|term@lang|...``
        - lang is the 2/3-char Wikipedia language code, or empty string
          for the default English Wikipedia (``{{Mesa}}`` → ``Mesa@``,
          ``{{Mesa}}:es`` → ``Mesa@es``).
        - ``@`` is used as the intra-entry separator because Wikipedia
          article titles can contain colons but not ``@``.

    Returns an empty string when no lookup commands are present, so that
    comments with no backtick or brace content do not get a stray ``§``
    stored in the database.
    """
    cjk_parts: list[str] = []
    wp_parts: list[str] = []

    for cmd in commands:
        if cmd.name == "lookup_cjk" and cmd.data:
            for entry in cmd.data:
                if isinstance(entry, tuple) and len(entry) >= 2:
                    lang, term = entry[0], entry[1]
                    cjk_parts.append(f"{lang}:{term}")
        elif cmd.name == "lookup_wp" and cmd.data:
            for entry in cmd.data:
                if isinstance(entry, tuple):
                    term, lang = entry  # (str, str | None)
                    wp_parts.append(f"{term}@{lang or ''}")

    if not cjk_parts and not wp_parts:
        return ""

    cjk_block = _LOOKUP_CONTENT_SEP.join(cjk_parts)
    wp_block = _LOOKUP_CONTENT_SEP.join(wp_parts)
    return f"{cjk_block}{_LOOKUP_SECTION_SEP}{wp_block}"


def _deserialize_lookup_content(s: str) -> tuple[set[str], set[str]]:
    """
    Inverse of ``_serialize_lookup_content``.

    Returns ``(cjk_terms, wp_terms)`` as sets of opaque strings suitable
    for equality comparison. The internal encoding (``lang:term`` and
    ``term@lang``) is treated as opaque; callers should not parse the
    individual fields.
    """
    if _LOOKUP_SECTION_SEP in s:
        cjk_block, wp_block = s.split(_LOOKUP_SECTION_SEP, 1)
    else:
        cjk_block, wp_block = s, ""

    cjk_terms = {t for t in cjk_block.split(_LOOKUP_CONTENT_SEP) if t}
    wp_terms = {t for t in wp_block.split(_LOOKUP_CONTENT_SEP) if t}
    return cjk_terms, wp_terms


# ─── Cached comment container ─────────────────────────────────────────────────


class _CachedComment:
    """Thin container for what we read back from comment_cache."""

    __slots__ = ("body", "_komandos_str", "_komando_set", "lookup_content")

    def __init__(self, body: str, komandos: str, lookup_content: str = ""):
        """Store the cached comment body, raw komandos string, and lookup content."""
        self.body = body
        self._komandos_str = komandos
        self._komando_set: set[str] | None = None
        self.lookup_content = lookup_content

    @property
    def command_names(self) -> set[str]:
        """Deserialized set of command names; parsed lazily on first access."""
        if self._komando_set is None:
            self._komando_set = _deserialize_komandos(self._komandos_str)
        return self._komando_set

    @property
    def cjk_terms(self) -> set[str]:
        """Deserialized CJK term set from lookup_content."""
        return _deserialize_lookup_content(self.lookup_content)[0]

    @property
    def wp_terms(self) -> set[str]:
        """Deserialized Wikipedia term set from lookup_content."""
        return _deserialize_lookup_content(self.lookup_content)[1]


def _get_cached_comment(comment_id: str) -> "_CachedComment | None":
    """Retrieve cached body, komandos, and lookup_content for *comment_id*.
    Returns None if the comment is not in the cache."""
    cursor = db.cursor_cache
    cursor.execute(
        "SELECT content, komandos, lookup_content FROM comment_cache WHERE id = ?",
        (comment_id,),
    )
    result = cursor.fetchone()
    if result is None:
        return None
    body, komandos, lookup_content = result
    return _CachedComment(
        body=body,
        komandos=komandos or _NO_COMMANDS,
        lookup_content=lookup_content or "",
    )


def _update_comment_cache(
    comment_id: str,
    comment_body: str,
    created_utc: int,
    komandos: str | None = None,
    lookup_content: str | None = None,
) -> None:
    """Replace old cache entry with the new body, komandos, and lookup_content.

    If *komandos* or *lookup_content* are None they are derived from a single
    parse of *comment_body*, so callers that have already parsed the commands
    can pass both in to avoid double-parsing.
    """
    if komandos is None or lookup_content is None:
        parsed_commands = extract_commands_from_text(comment_body)
        if komandos is None:
            komandos = ",".join(dict.fromkeys(cmd.name for cmd in parsed_commands))
        if lookup_content is None:
            lookup_content = _serialize_lookup_content(parsed_commands)

    cursor = db.cursor_cache
    cursor.execute("DELETE FROM comment_cache WHERE id = ?", (comment_id,))
    cursor.execute(
        "INSERT INTO comment_cache VALUES (?, ?, ?, ?, ?)",
        (comment_id, comment_body, created_utc, komandos, lookup_content),
    )
    db.conn_cache.commit()


def _remove_from_processed(comment_id: str) -> None:
    """Force a reprocess by removing from the processed comment database."""
    cursor = db.cursor_main
    cursor.execute("DELETE FROM old_comments WHERE id = ?", (comment_id,))
    db.conn_main.commit()
    logger.debug(f"Removed comment '{comment_id}' from processed database.")


def _cleanup_comment_cache(limit: int) -> None:
    """Remove oldest entries beyond the comment limit."""
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


# ─── Edit tracker ─────────────────────────────────────────────────────────────


def edit_tracker() -> None:
    """
    Detect edited r/translator comments that introduce new commands or
    change the content of lookup_cjk / lookup_wp queries.

    Reprocessing is triggered when either of the following is true:

    - The edited version contains command names not present in the cached
      (pre-edit) version (e.g. a new !translated is added).
    - The resolved lookup_cjk or lookup_wp content has changed even though
      the command names are identical (e.g. switching `七転八起` to
      `七転八起`! to disable tokenization, which changes the
      post-tokenization tokens that would actually be looked up).

    The comparison is command-set and lookup-content aware, so purely
    cosmetic edits (rewording surrounding prose without changing commands
    or backtick/brace content) do not trigger unnecessary reprocessing.
    """
    # Phase 1: Iterate over recent comments to seed / refresh the cache.
    # This catches "ninja edits" made within Reddit's 3-minute no-flag
    # window before they appear in the mod.edited queue.
    total_fetch_num = SETTINGS["comment_edit_num_limit"] * 2
    total_keep_num = total_fetch_num * 5
    for comment in REDDIT_HELPER.subreddit(SETTINGS["subreddit"]).comments(
        limit=total_fetch_num
    ):
        if not _is_comment_within_edit_window(comment):
            continue

        comment_id = comment.id
        comment_body = comment.body.strip()

        # Only insert; never overwrite in Phase 1 (we want the *original*
        # body to stay cached so Phase 2 can diff against it later).
        cached = _get_cached_comment(comment_id)
        if not cached:
            # Don't record komandos or lookup_content for the bot's own
            # comments — they would produce false positives in Phase 2.
            author = str(comment.author) if comment.author else ""
            if author.lower() == USERNAME.lower():
                komandos = _NO_COMMANDS
                lookup_content = ""
            else:
                parsed = extract_commands_from_text(comment_body)
                komandos = ",".join(dict.fromkeys(cmd.name for cmd in parsed))
                lookup_content = _serialize_lookup_content(parsed)
            logger.debug(
                f"Cached new comment `{comment_id}` "
                f"(komandos: {komandos if komandos else 'none'})"
            )
            _update_comment_cache(
                comment_id,
                comment_body,
                int(comment.created_utc),
                komandos,
                lookup_content,
            )

    # Phase 2: Fetch only the edited comments from the subreddit.
    # This produces a generator that includes both comments and submissions.
    for item in REDDIT.subreddit(SETTINGS["subreddit"]).mod.edited(
        limit=SETTINGS["comment_edit_num_limit"]
    ):
        if isinstance(item, models.Submission):
            continue

        comment_id = item.id
        comment_new_body = item.body.strip()

        if not _is_comment_within_edit_window(item):
            continue

        # Fast pre-check: if the new version has no commands at all,
        # there is nothing to reprocess regardless of what the old
        # version contained.
        if not comment_has_command(item):
            continue

        cached = _get_cached_comment(comment_id)
        comment_old_body = cached.body if cached else ""

        if comment_old_body == comment_new_body:
            logger.debug(f"Comment `{comment_id}`: body unchanged, skipping.")
            continue

        old_command_names: set[str] = cached.command_names if cached else set()
        new_commands = extract_commands_from_text(comment_new_body)
        new_command_names: set[str] = {cmd.name for cmd in new_commands}

        added_commands = new_command_names - old_command_names

        # Also check whether lookup content changed even if command names
        # did not. This catches the case where the user edits the backtick
        # content (e.g. toggling the tokenization-disable ``!`` suffix, or
        # changing the looked-up term or Wikipedia language code) without
        # adding a new command keyword.
        new_lookup_content = _serialize_lookup_content(new_commands)
        old_cjk, old_wp = _deserialize_lookup_content(
            cached.lookup_content if cached else ""
        )
        new_cjk, new_wp = _deserialize_lookup_content(new_lookup_content)
        lookup_content_changed = (old_cjk != new_cjk) or (old_wp != new_wp)

        if added_commands or lookup_content_changed:
            if added_commands:
                reason = f"new command(s) {sorted(added_commands)} detected"
            else:
                reason = (
                    f"lookup content changed "
                    f"(cjk: {old_cjk!r} → {new_cjk!r}, "
                    f"wp: {old_wp!r} → {new_wp!r})"
                )
            logger.info(
                f"[Edit_Tracker] Reprocessing triggered for `{comment_id}`: "
                f"{reason}. "
                f"https://www.reddit.com{item.permalink}"
            )
            _remove_from_processed(comment_id)
        else:
            logger.debug(
                f"Comment `{comment_id}` edited but no new commands or lookup "
                f"content changes detected "
                f"(had={sorted(old_command_names)}, now={sorted(new_command_names)})."
            )

        new_komandos = ",".join(
            dict.fromkeys(cmd.name for cmd in new_commands)  # ordered dedup
        )
        _update_comment_cache(
            comment_id,
            comment_new_body,
            int(item.created_utc),
            new_komandos,
            new_lookup_content,
        )

    # Phase 3: Cache cleanup.
    _cleanup_comment_cache(total_keep_num)

    return


# ─── Progress tracker ─────────────────────────────────────────────────────────


def progress_tracker() -> None:
    """
    Check Reddit for posts marked as "In Progress" and determine
    if their claim period has expired. If expired, reset them to the
    'Untranslated' state. Supports both single and defined multiple posts.
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

        ajo = ajo_loader(post_id)
        if ajo is None:
            logger.debug("Couldn't find Ajo in local database. Loading from Reddit.")
            ajo = Ajo.from_titolo(process_title(post.title))

        if (ajo.type in ("single", "multiple")) and not ajo.is_defined_multiple:
            if ajo.status != "inprogress":
                continue
        else:
            has_inprogress = (
                isinstance(ajo.status, dict) and "inprogress" in ajo.status.values()
            )
            if not has_inprogress:
                continue

        kunulo_object = Kunulo.from_submission(post)
        comment_claim_id = kunulo_object.get_tag("comment_claim")

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

        if time_diff is None or time_diff <= SETTINGS["claim_period"]:
            continue

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
            for key in inprogress_keys:
                if claim_comment_data["language"].preferred_code == key:
                    kunulo_object.delete("comment_claim")
                    ajo.set_defined_multiple_status(key, "untranslated")

        ajo.update_reddit()

    logger.debug(f"Checked {posts_checked} in-progress post(s)")

    return


# ─── Entry point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    start_time = time.time()
    logger.info("Running Edit Tracker...")
    edit_tracker()
    logger.info(f"Finished. {round(time.time() - start_time, 2)} seconds elapsed.")
