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
import re

import pprint

from config import SETTINGS, logger
from connection import REDDIT_HELPER


class Kunulo:
    """
    This class generally contains a dictionary keyed by the comment type
    and the comment ID it is linked to.
    Another Boolean stores whether the OP has thanked people.

    To use: kunulo = Kunulo.from_submission(reddit_submission)
    Example output:
    <Kunulo: ({'comment_unknown': ['nijg7y3']}) | OP Thanks: False>
    """
    anchor_pattern = re.compile(r"\[]\(#([a-zA-Z0-9_]+)\)")

    def __init__(self, data=None, op_thanks=False):
        self._data = data or {}
        self._op_thanks = op_thanks
        self._submission = None  # Store submission for delete functionality

    def __repr__(self):
        return f"<Kunulo: ({self._data}) | OP Thanks: {self._op_thanks}>"

    @classmethod
    def from_submission(cls, submission):
        # This is how it is usually called.
        # Accepts a PRAW submission object.
        thanks_keywords = SETTINGS['thanks_keywords']
        thanks_negation_keywords = SETTINGS['thanks_negation_keywords']
        data = {}
        op_thanks = False

        op_author = submission.author.name if submission.author else None
        submission.comments.replace_more(limit=None)
        for comment in submission.comments.list():
            comment_author = comment.author.name if comment.author else None
            comment_body = comment.body.lower()  # for easier matching
            # Gather bot's anchor tags as before
            if comment_author == 'translator-BOT':
                for tag in cls.anchor_pattern.findall(comment.body):
                    data.setdefault(tag, []).append(comment.id)
            # Check for OP thanking (case-insensitive)
            # Don't count as thanks if negation keywords are present
            if not op_thanks and comment_author == op_author:
                has_thanks = any(kw in comment_body for kw in thanks_keywords)
                has_negation = any(kw in comment_body for kw in thanks_negation_keywords)
                if has_thanks and not has_negation:
                    op_thanks = True

        instance = cls(data, op_thanks)
        instance._submission = submission  # Store submission reference
        return instance

    def __getattr__(self, tag):
        if tag == 'op_thanks':
            return self._op_thanks
        if tag in self._data:
            return self._data[tag]
        raise AttributeError(f"'Kunulo' object has no attribute '{tag}'")

    def get_tag(self, tag):
        """
        Get the first comment ID associated with a tag.

        Args:
            tag: The tag identifier to look up

        Returns:
            str or None: The first comment ID if the tag exists, None otherwise
        """
        return self._data.get(tag, [None])[0]

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

        comment_ids = self._data.get(tag, [])
        if not comment_ids:
            return 0

        deleted_count = 0
        for comment_id in comment_ids:
            try:
                comment = self._submission.reddit.comment(comment_id)
                comment.delete()
                deleted_count += 1
                logger.info(f"[ZW] Kunulo: Deleted comment `{comment_id}` associated with {tag}.")
            except Exception as e:
                # Log the error but continue trying to delete other comments
                print(f"Warning: Failed to delete comment {comment_id}: {e}")

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
    elif hasattr(comment_reference, 'link_id'):  # Check if it's a Comment-like object
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
        test_url = input("Enter the URL of the Reddit post to test: ")
        submission_id = test_url.split("comments/")[1].split("/")[0]
        test_post = REDDIT_HELPER.submission(id=submission_id)
        test_kunulo = Kunulo.from_submission(test_post)
        pprint.pprint(test_kunulo)
