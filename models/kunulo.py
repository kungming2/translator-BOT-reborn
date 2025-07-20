#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
Defines the Kunolo class, which was formerly called "Komento" in
earlier versions of the bot. Given a Reddit post, it tracks pre-existing
comments that the bot has posted on it so that the bot can take action
on them. The bot uses invisible Markdown anchors embedded in the
comments, like: [](#anchor)

This is a companion to the Ajo class, as it tells the bot quickly what
actions that are public-facing can be done.
"""
import re

from config import SETTINGS
from connection import REDDIT_HELPER


class Kunulo:
    """
    To use: kunulo = Kunulo.from_submission(reddit_submission)
    """
    anchor_pattern = re.compile(r"\[]\(#([a-zA-Z0-9_]+)\)")

    def __init__(self, tag_to_comment_ids=None, op_thanks=False):
        self._tag_to_comment_ids = tag_to_comment_ids or {}
        self._op_thanks = op_thanks

    def __repr__(self):
        return f"<Kunulo: ({self._tag_to_comment_ids}) | {self._op_thanks}>"

    @classmethod
    def from_submission(cls, submission):  # This is how it is usually called.
        thanks_keywords = SETTINGS['thanks_keywords']
        tag_to_comment_ids = {}
        op_thanks = False

        op_author = submission.author.name if submission.author else None
        submission.comments.replace_more(limit=None)
        for comment in submission.comments.list():
            comment_author = comment.author.name if comment.author else None
            comment_body = comment.body.lower()  # for easier matching
            # Gather bot's anchor tags as before
            if comment_author == 'translator-BOT':
                for tag in cls.anchor_pattern.findall(comment.body):
                    tag_to_comment_ids.setdefault(tag, []).append(comment.id)
            # Check for OP thanking (case-insensitive)
            if not op_thanks and comment_author == op_author and any(
                    kw in comment_body.lower() for kw in thanks_keywords):
                op_thanks = True

        return cls(tag_to_comment_ids, op_thanks)

    def __getattr__(self, name):
        if name == 'op_thanks':
            return self._op_thanks
        if name in self._tag_to_comment_ids:
            return self._tag_to_comment_ids[name]
        raise AttributeError(f"'Kunulo' object has no attribute '{name}'")

    def first(self, name):
        return self._tag_to_comment_ids.get(name, [None])[0]


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
