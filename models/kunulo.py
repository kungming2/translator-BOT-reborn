#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
Defines the Kunulo ("companion") class, which was formerly called "Komento" in
earlier versions of the bot. Given a Reddit post, it tracks pre-existing
comments that the bot has posted on it so that the bot can take action
on them. The bot uses invisible Markdown anchors embedded in the
comments, like: [](#tag)

This is a companion to the Ajo class, as it tells the bot quickly what
actions that are public-facing can be done.
...

Logger tag: [M:KUNULO]
"""

import logging
import re
from typing import Any

from praw.models import Comment, Submission

from config import SETTINGS
from config import logger as _base_logger
from reddit.connection import REDDIT, REDDIT_HELPER, USERNAME

logger = logging.LoggerAdapter(_base_logger, {"tag": "M:KUNULO"})

EntryData = list[str] | None
KunuloEntry = tuple[str, EntryData]


# ─── Main Kunulo class ────────────────────────────────────────────────────────


class Kunulo:
    """
    This class generally contains a dictionary keyed by the comment type
    and the comment ID it is linked to, along with optional associated data.
    Another Boolean stores whether the OP has thanked people.

    Internal storage format: Each tag maps to a list of (comment_id, data) tuples.
    Legacy format (just comment IDs) is automatically converted for compatibility.

    For ``comment_cjk`` and ``comment_wikipedia`` entries, ``data`` is a dict
    with two keys:

    - ``"terms"``: list of looked-up strings extracted from the reply body
    - ``"parent_id"``: Reddit comment ID of the user comment that triggered this
      bot reply (extracted from the ``[](#cjk_parent_XXXX)`` or
      ``[](#wp_parent_XXXX)`` anchor embedded in the reply body by
      ``lookup_cjk._format_reply`` / ``lookup_wp._format_wp_reply``).
      May be ``None`` for replies posted before this feature was introduced.

    For all other tags, ``data`` remains a plain ``list[str] | None``.

    To use: kunulo = Kunulo.from_submission(reddit_submission)
    Example output:
    <Kunulo: ({'comment_unknown': [('nijg7y3', None)]}) | OP Thanks: False>
    """

    anchor_pattern = re.compile(r"\[]\(#([a-zA-Z0-9_]+)\)")
    # Matches the parent-comment anchor embedded by lookup_cjk._format_reply,
    # e.g. [](#cjk_parent_abc123) → group 1 = "abc123"
    cjk_parent_pattern = re.compile(r"\[]\(#cjk_parent_([a-zA-Z0-9]+)\)")
    # Matches the parent-comment anchor embedded by lookup_wp._format_wp_reply,
    # e.g. [](#wp_parent_abc123) → group 1 = "abc123"
    wp_parent_pattern = re.compile(r"\[]\(#wp_parent_([a-zA-Z0-9]+)\)")

    # ── Construction ──────────────────────────────────────────────────────────

    def __init__(self, data: dict | None = None, op_thanks: bool = False) -> None:
        """Initialize all Kunulo attributes from keyword arguments."""
        self._data: dict[str, list] = data or {}
        self._op_thanks = op_thanks
        self._submission: Any = None  # Store submission for delete functionality

    def __repr__(self) -> str:
        return f"<Kunulo: ({self._data}) | OP Thanks: {self._op_thanks}>"

    @classmethod
    def from_submission(cls, submission: Submission) -> "Kunulo":
        """
        Create a Kunulo instance from a PRAW submission object.

        Args:
            submission: PRAW submission object

        Returns:
            Kunulo: Instance populated with comment data from the submission
        """
        thanks_keywords = SETTINGS["thanks_keywords"]
        thanks_negation_keywords = SETTINGS["thanks_negation_keywords"]
        instance = cls()
        op_thanks = False

        op_author = submission.author.name if submission.author else None
        submission.comments.replace_more(limit=None)

        for comment in submission.comments.list():
            comment_author = comment.author.name if comment.author else None
            comment_body = comment.body.lower()  # for easier matching

            # Gather bot's anchor tags
            if comment_author == USERNAME:
                for tag in cls.anchor_pattern.findall(comment.body):
                    if tag == "comment_cjk":
                        # For CJK replies, store a dict with terms and the ID
                        # of the user comment that triggered this bot reply.
                        # The parent ID is embedded in the reply body as
                        # [](#cjk_parent_XXXX) by lookup_cjk._format_reply.
                        terms = cls._extract_cjk_characters(comment.body)
                        parent_match = cls.cjk_parent_pattern.search(comment.body)
                        parent_id = parent_match.group(1) if parent_match else None
                        associated_data: Any = {
                            "terms": terms,
                            "parent_id": parent_id,
                        }
                    elif tag == "comment_wikipedia":
                        # Same structure as comment_cjk: store terms and the
                        # triggering comment's ID so lookup_wp can edit in place.
                        # The parent ID is embedded as [](#wp_parent_XXXX) by
                        # lookup_wp._format_wp_reply.
                        wp_terms = cls._extract_wikipedia_terms(comment.body)
                        wp_parent_match = cls.wp_parent_pattern.search(comment.body)
                        wp_parent_id = (
                            wp_parent_match.group(1) if wp_parent_match else None
                        )
                        associated_data = {
                            "terms": wp_terms,
                            "parent_id": wp_parent_id,
                        }
                    else:
                        associated_data = None
                    instance._add_entry(tag, comment.id, associated_data)

            # Check for OP thanking (case-insensitive)
            # Don't count as thanks if negation keywords are present
            if not op_thanks and comment_author == op_author:
                has_thanks = any(kw in comment_body for kw in thanks_keywords)
                has_negation = any(
                    kw in comment_body for kw in thanks_negation_keywords
                )
                if has_thanks and not has_negation:
                    op_thanks = True

        instance._op_thanks = op_thanks
        instance._submission = submission  # Store submission reference
        return instance

    # ── Internal entry helpers ─────────────────────────────────────────────────

    @staticmethod
    def _normalize_entry(entry: "KunuloEntry | str") -> "KunuloEntry":
        """
        Convert entry to (comment_id, data) format for internal consistency.
        Handles legacy format where entries might be just strings.

        Args:
            entry: Either a string (comment_id) or tuple (comment_id, data)

        Returns:
            tuple: (comment_id, data) format
        """
        if isinstance(entry, tuple):
            return entry
        return entry, None  # Legacy format: just ID, no associated data

    @staticmethod
    def _extract_cjk_characters(comment_body: str) -> list[str]:
        """
        Extract CJK characters from markdown headers in comment body.

        Parses lines starting with '# [' and extracts the CJK characters
        before any parentheses. For example:
        - "# [夜](url)" -> "夜"
        - "# [國 / 国](url)" -> "國"  (traditional char only)

        Args:
            comment_body: The raw Markdown text of the comment

        Returns:
            list: List of CJK character strings found in headers
        """
        cjk_chars = []
        # Pattern to match: # [characters (optional)](url)
        # Captures text between [ and either ( or ]
        header_pattern = re.compile(r"^#\s+\[([^](\[]+?)(?:\s*\(|])", re.MULTILINE)

        for match in header_pattern.finditer(comment_body):
            char = match.group(1).strip()
            if char:
                # If format is "國 / 国", extract only the traditional character (before " / ")
                if " / " in char:
                    char = char.split(" / ")[0].strip()
                cjk_chars.append(char)

        return cjk_chars

    @staticmethod
    def _extract_wikipedia_terms(comment_body: str) -> list[str]:
        """
        Extract Wikipedia search terms from bold Markdown links in comment body.

        Parses lines with **[term](url) pattern and extracts the term.
        For example:
        - "**[error](https://en.wikipedia.org/wiki/error)**" -> "error"

        Args:
            comment_body: The raw Markdown text of the comment

        Returns:
            list: List of Wikipedia search terms found
        """
        terms = []
        # Pattern to match: **[term](url)** or **[term]
        # Captures text between [ and ]
        wiki_pattern = re.compile(r"\*\*\[([^]]+)]")

        for match in wiki_pattern.finditer(comment_body):
            term = match.group(1).strip()
            if term:
                terms.append(term)

        return terms

    def _add_entry(self, tag: str, comment_id: str, data: EntryData = None) -> None:
        """
        Add an entry, storing as tuple (comment_id, data).

        Args:
            tag: The tag identifier
            comment_id: The Reddit comment ID
            data: Optional associated data (e.g., words, characters)
        """
        self._data.setdefault(tag, []).append((comment_id, data))

    # ── Serialization ─────────────────────────────────────────────────────────

    def to_dict(self) -> dict[str, Any]:
        """
        Convert Kunulo instance to a dictionary representation.

        Returns:
            dict: Dictionary with 'data' (tags and their entries) and 'op_thanks' flag
        """

        def _entry_to_dict(entry: "KunuloEntry | str") -> dict[str, Any]:
            comment_id, associated_data = self._normalize_entry(entry)
            return {"comment_id": comment_id, "associated_data": associated_data}

        return {
            "data": {
                tag: [_entry_to_dict(entry) for entry in entries]
                for tag, entries in self._data.items()
            },
            "op_thanks": self._op_thanks,
        }

    # ── Tag lookup / access ────────────────────────────────────────────────────

    def __getattr__(self, tag: str) -> Any:
        """
        Allow attribute-style access to tags.
        Returns list of (comment_id, data) tuples for backward compatibility.
        """
        if tag.startswith("__") and tag.endswith("__"):
            raise AttributeError(tag)
        if tag == "op_thanks":
            return self._op_thanks
        if tag in self._data:
            return self._data[tag]
        raise AttributeError(f"'Kunulo' object has no attribute '{tag}'")

    def get_tag(self, tag: str) -> str | None:
        """
        Get the first comment ID associated with a tag (backward compatible).

        Args:
            tag: The tag identifier to look up

        Returns:
            str or None: The first comment ID if the tag exists, None otherwise
        """
        entries = self._data.get(tag, [])
        if not entries:
            return None
        entry = self._normalize_entry(entries[0])
        return entry[0]  # Return just the comment ID

    def get_tag_with_data(
        self, tag: str, index: int = 0
    ) -> KunuloEntry | tuple[None, None]:
        """
        Get the comment ID and its associated data for a tag.

        Args:
            tag: The tag identifier to look up
            index: Which entry to retrieve if multiple exist (default: 0)

        Returns:
            tuple or (None, None): (comment_id, data) if the tag exists, (None, None) otherwise
        """
        entries = self._data.get(tag, [])
        if not entries or index >= len(entries):
            return None, None
        entry = self._normalize_entry(entries[index])
        return entry  # Return (comment_id, data) tuple

    def get_all_entries(self, tag: str) -> list[KunuloEntry]:
        """
        Get all entries for a tag as a list of (comment_id, data) tuples.

        Args:
            tag: The tag identifier to look up

        Returns:
            list: List of (comment_id, data) tuples, or empty list if tag doesn't exist
        """
        entries = self._data.get(tag, [])
        return [self._normalize_entry(e) for e in entries]

    def get_comment_ids(self, tag: str) -> list[str]:
        """
        Get all comment IDs for a tag (without associated data).

        Args:
            tag: The tag identifier to look up

        Returns:
            list: List of comment IDs, or empty list if tag doesn't exist
        """
        entries = self._data.get(tag, [])
        return [self._normalize_entry(e)[0] for e in entries]

    def find_cjk_reply_for_comment(self, triggering_comment_id: str) -> str | None:
        """
        Find the bot's existing CJK reply that was triggered by a specific
        user comment.

        Searches all ``comment_cjk`` entries for one whose ``parent_id``
        matches *triggering_comment_id*.  Returns ``None`` if no match is
        found, or if the entry predates the parent-tracking feature (i.e.
        ``parent_id`` is ``None``).

        Args:
            triggering_comment_id: The Reddit comment ID of the user comment
                whose edit is being reprocessed.

        Returns:
            str or None: The bot's comment ID to edit, or None if not found.
        """
        for bot_comment_id, data in self.get_all_entries("comment_cjk"):
            if isinstance(data, dict) and data.get("parent_id") == triggering_comment_id:
                return bot_comment_id
        return None

    def find_wp_reply_for_comment(self, triggering_comment_id: str) -> str | None:
        """
        Find the bot's existing Wikipedia reply that was triggered by a specific
        user comment.

        Searches all ``comment_wikipedia`` entries for one whose ``parent_id``
        matches *triggering_comment_id*.  Returns ``None`` if no match is
        found, or if the entry predates the parent-tracking feature (i.e.
        ``parent_id`` is ``None``).

        Args:
            triggering_comment_id: The Reddit comment ID of the user comment
                whose edit is being reprocessed.

        Returns:
            str or None: The bot's comment ID to edit, or None if not found.
        """
        for bot_comment_id, data in self.get_all_entries("comment_wikipedia"):
            if isinstance(data, dict) and data.get("parent_id") == triggering_comment_id:
                return bot_comment_id
        return None

    def check_existing_cjk_lookups(
        self, requested_characters: list[str], exact_match: bool = True
    ) -> dict[str, Any] | None:
        """
        Check if requested CJK characters have already been looked up.

        Args:
            requested_characters: List of CJK characters to check
            exact_match: If True, requires exact same set of characters.
                        If False, checks if requested chars are subset of any existing lookup.

        Returns:
            dict or None: If matches found, returns {'comment_id': str, 'matched_terms': list}
                         If no matches, returns None
        """
        if not requested_characters:
            return None

        # Get all comment_cjk entries
        cjk_entries = self.get_all_entries("comment_cjk")

        if not cjk_entries:
            return None

        # Convert requested characters to a set for comparison
        requested_set = set(requested_characters)

        # Check each existing comment for matches.
        # associated_data is now a dict {"terms": [...], "parent_id": "..."}
        # for replies posted after the parent-tracking feature was introduced,
        # and a plain list for older replies.
        for comment_id, associated_data in cjk_entries:
            if associated_data is None:
                continue

            existing_chars: list[str]
            if isinstance(associated_data, dict):
                existing_chars = associated_data.get("terms") or []
            else:
                # Legacy format: plain list
                existing_chars = associated_data

            existing_set = set(existing_chars)

            if exact_match:
                if requested_set == existing_set:
                    return {
                        "comment_id": comment_id,
                        "matched_terms": list(requested_set),
                    }
            else:
                if requested_set.issubset(existing_set):
                    return {
                        "comment_id": comment_id,
                        "matched_terms": list(requested_set),
                    }

        return None

    # ── Reddit actions ────────────────────────────────────────────────────────

    def get_comment_permalink(self, comment_id: str) -> str:
        """
        Generate a Reddit permalink for a comment.

        Args:
            comment_id: The Reddit comment ID

        Returns:
            str: Reddit permalink URL

        Raises:
            RuntimeError: If no submission is associated with this Kunulo instance
        """
        if self._submission is None:
            raise RuntimeError(
                "Cannot generate permalink: No submission associated with this Kunulo instance."
            )

        return f"https://www.reddit.com{self._submission.permalink}{comment_id}"

    def delete(self, tag: str) -> int:
        """
        Delete all comments associated with the given tag from Reddit.

        Args:
            tag: The tag identifier for comments to delete

        Returns:
            int: Number of comments successfully deleted

        Raises:
            RuntimeError: If no submission is associated with this Kunulo instance
        """
        if self._submission is None:
            raise RuntimeError(
                "Cannot delete comments: No submission associated with this Kunulo instance. "
                "Use Kunulo.from_submission() to create an instance with delete capability."
            )

        entries = self._data.get(tag, [])
        if not entries:
            return 0

        deleted_count = 0
        for entry in entries:
            comment_id = self._normalize_entry(entry)[0]
            try:
                # Use instead of self._submission.reddit
                comment = REDDIT.comment(id=comment_id)
                comment.delete()
                deleted_count += 1
                logger.info(f"Deleted comment `{comment_id}` associated with {tag}.")
            except Exception as e:
                # Log the error but continue trying to delete other comments
                logger.warning(f"Warning: Failed to delete comment {comment_id}: {e}")

        # Remove the tag from data if any comments were deleted
        if deleted_count > 0:
            del self._data[tag]

        return deleted_count


# ─── Module-level utilities ───────────────────────────────────────────────────


def get_submission_from_comment(comment_reference: Comment | str) -> Submission:
    """
    Retrieves the parent submission of a Reddit comment.
    Accepts either a comment ID string or a PRAW Comment object.

    Args:
        comment_reference: Either a comment ID (str) or a PRAW Comment object.

    Returns:
        The parent Submission object.

    Raises:
        praw.exceptions.PRAWException: If Reddit API request fails.
        ValueError: If input is invalid.
    """
    # Get comment object if input is an ID string
    if isinstance(comment_reference, str):
        comment = REDDIT_HELPER.comment(id=comment_reference)
    elif hasattr(comment_reference, "link_id"):  # Check if it's a Comment-like object
        comment = comment_reference
    else:
        raise ValueError("Input must be comment ID or Comment object")

    # Extract submission ID (removes 't3_' prefix)
    try:
        return REDDIT_HELPER.submission(id=comment.link_id[3:])
    except AttributeError as err:
        raise ValueError("Invalid comment reference - missing link_id") from err
