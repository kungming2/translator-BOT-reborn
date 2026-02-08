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
"""

import pprint
import re

from config import SETTINGS, logger
from connection import REDDIT, REDDIT_HELPER, USERNAME


class Kunulo:
    """
    This class generally contains a dictionary keyed by the comment type
    and the comment ID it is linked to, along with optional associated data.
    Another Boolean stores whether the OP has thanked people.

    Internal storage format: Each tag maps to a list of (comment_id, data) tuples.
    Legacy format (just comment IDs) is automatically converted for compatibility.

    To use: kunulo = Kunulo.from_submission(reddit_submission)
    Example output:
    <Kunulo: ({'comment_unknown': [('nijg7y3', None)]}) | OP Thanks: False>
    """

    anchor_pattern = re.compile(r"\[]\(#([a-zA-Z0-9_]+)\)")

    def __init__(self, data=None, op_thanks=False):
        self._data = data or {}
        self._op_thanks = op_thanks
        self._submission = None  # Store submission for delete functionality

    def __repr__(self):
        return f"<Kunulo: ({self._data}) | OP Thanks: {self._op_thanks}>"

    def to_dict(self):
        """
        Convert Kunulo instance to a dictionary representation.

        Returns:
            dict: Dictionary with 'data' (tags and their entries) and 'op_thanks' flag
        """
        return {
            "data": {
                tag: [
                    {
                        "comment_id": self._normalize_entry(entry)[0],
                        "associated_data": self._normalize_entry(entry)[1],
                    }
                    for entry in entries
                ]
                for tag, entries in self._data.items()
            },
            "op_thanks": self._op_thanks,
        }

    @staticmethod
    def _normalize_entry(entry):
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
    def _extract_cjk_characters(comment_body):
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
    def _extract_wikipedia_terms(comment_body):
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

    def _add_entry(self, tag, comment_id, data=None):
        """
        Add an entry, storing as tuple (comment_id, data).

        Args:
            tag: The tag identifier
            comment_id: The Reddit comment ID
            data: Optional associated data (e.g., words, characters)
        """
        self._data.setdefault(tag, []).append((comment_id, data))

    @classmethod
    def from_submission(cls, submission):
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
                    # Extract associated data based on tag type
                    associated_data = None
                    if tag == "comment_cjk":
                        associated_data = cls._extract_cjk_characters(comment.body)
                    elif tag == "comment_wikipedia":
                        associated_data = cls._extract_wikipedia_terms(comment.body)
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

    def __getattr__(self, tag):
        """
        Allow attribute-style access to tags.
        Returns list of (comment_id, data) tuples for backward compatibility.
        """
        if tag == "op_thanks":
            return self._op_thanks
        if tag in self._data:
            return self._data[tag]
        raise AttributeError(f"'Kunulo' object has no attribute '{tag}'")

    def get_tag(self, tag):
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

    def get_tag_with_data(self, tag, index=0):
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

    def get_all_entries(self, tag):
        """
        Get all entries for a tag as a list of (comment_id, data) tuples.

        Args:
            tag: The tag identifier to look up

        Returns:
            list: List of (comment_id, data) tuples, or empty list if tag doesn't exist
        """
        entries = self._data.get(tag, [])
        return [self._normalize_entry(e) for e in entries]

    def get_comment_ids(self, tag):
        """
        Get all comment IDs for a tag (without associated data).

        Args:
            tag: The tag identifier to look up

        Returns:
            list: List of comment IDs, or empty list if tag doesn't exist
        """
        entries = self._data.get(tag, [])
        return [self._normalize_entry(e)[0] for e in entries]

    def check_existing_cjk_lookups(self, requested_characters, exact_match=True):
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

        # Check each existing comment for matches
        for comment_id, existing_chars in cjk_entries:
            if existing_chars:
                existing_set = set(existing_chars)

                if exact_match:
                    # Check for exact match (same characters, order doesn't matter)
                    if requested_set == existing_set:
                        return {
                            "comment_id": comment_id,
                            "matched_terms": list(requested_set),
                        }
                else:
                    # Check if requested is subset of existing
                    if requested_set.issubset(existing_set):
                        return {
                            "comment_id": comment_id,
                            "matched_terms": list(requested_set),
                        }

        return None

    def get_comment_permalink(self, comment_id):
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

    def delete(self, tag):
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
                logger.info(
                    f"[ZW] Kunulo: Deleted comment `{comment_id}` associated with {tag}."
                )
            except Exception as e:
                # Log the error but continue trying to delete other comments
                logger.warning(f"Warning: Failed to delete comment {comment_id}: {e}")

        # Remove the tag from data if any comments were deleted
        if deleted_count > 0:
            del self._data[tag]

        return deleted_count


def get_submission_from_comment(comment_reference):
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
    except AttributeError:
        raise ValueError("Invalid comment reference - missing link_id")


if __name__ == "__main__":
    while True:
        test_url = input("Enter the URL of the Reddit post with comments to test: ")
        submission_id = test_url.split("comments/")[1].split("/")[0]
        test_post = REDDIT.submission(id=submission_id)
        test_kunulo = Kunulo.from_submission(test_post)
        pprint.pprint(test_kunulo)
