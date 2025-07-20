#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
Defines the Instruo comment structure and class, along with related functions.
"""
import re

from config import SETTINGS

from connection import REDDIT_HELPER
from models.komando import extract_commands_from_text


class Instruo:
    """
    Defines a class that is derived from a PRAW comment with commands.
    Note that you CAN derive an Instruo from any comment; however
    it will not have any commands as properties. comment_has_command
    should therefore be called first to prevent initialization of
    empty Instruos.

    instruo = Instruo.from_comment(comment)
    """
    def __init__(self, id_comment, id_post, created_utc, author_comment, commands, languages, body=None, author_post=None):
        self.id_comment = id_comment
        self.id_post = id_post
        self.created_utc = created_utc  # integer Unix timestamp
        self.author_comment = author_comment  # String, not a PRAW object
        self.author_post = author_post  # String, not a PRAW object
        self.commands = commands  # List of Komando objects
        self.languages = languages  # List of Lingvo objects
        self.body = body  # Raw comment text, optional if not created from PRAW

    def __repr__(self):
        return f"Instruo (id={self.id_comment!r}, commands={self.commands!r})"

    def to_dict(self):
        return {
            "id_comment": self.id_comment,
            "id_post": self.id_post,
            "created_utc": self.created_utc,
            "author_comment": self.author_comment,
            "author_post": self.author_post,
            "commands": [cmd.to_dict() for cmd in self.commands],
            "languages": [str(lang) for lang in self.languages],
            "body": self.body
        }

    @classmethod
    def from_comment(cls, comment, parent_languages=None):
        text = comment.body
        id_comment = comment.id
        id_post = comment.submission.id
        created_utc = int(comment.created_utc)
        author_comment = str(comment.author) if comment.author else "[deleted]"
        author_post = str(comment.submission.author) if comment.submission.author else "[deleted]"
        commands = extract_commands_from_text(text)
        return cls(
            id_comment=id_comment,
            id_post=id_post,
            created_utc=created_utc,
            author_comment=author_comment,
            author_post=author_post,
            commands=commands,
            languages=parent_languages or [],
            body=text
        )


def comment_has_command(comment):
    """
    Returns True if the comment contains any recognized command,
    False otherwise. This is used to skip comments which have no
    actionable content.

    Args:
        comment: A PRAW comment object or a plain string.

    Returns:
        bool
    """
    if isinstance(comment, str):
        text = comment.lower()
    else:
        text = comment.body.lower()

    # Remove inline and multiline backtick content
    # This allows people to quote the commands (`!doublecheck`)
    # without triggering it.
    text = re.sub(r'`[^`]*`', '', text)

    # Check commands with required arguments (e.g. !identify:lang)
    for cmd in SETTINGS['commands_with_args']:
        if cmd in text:
            return True

    # Check commands with optional arguments (e.g. !translated or !translated:fr)
    for cmd in SETTINGS['commands_optional_args']:
        if cmd in text:
            return True
        try_colon = cmd + ":"
        if try_colon in text:
            return True

    # Check commands with no arguments
    for cmd in SETTINGS['commands_no_args']:
        if cmd in text:
            return True

    return False


'''TESTING FUNCTIONS'''


def test_instruo_on_r_translator_recent_comments(limit=100):
    """Testing function only. To be moved in final version."""
    subreddit = REDDIT_HELPER.subreddit("translator")
    print(f"Fetching the last {limit} comments from r/translator...")
    count = 0
    for comment in subreddit.comments(limit=limit):
        if comment_has_command(comment):
            try:
                instruo = Instruo.from_comment(comment)
                if instruo.author_comment == "translator-BOT":
                    print("skipped own comment")
                    continue

                print(f"Comment ID: {instruo.id_comment}, Comment Author: {instruo.author_comment}, Commands: {instruo.commands}")
                print(f"Comment body: {comment.body[0:50]}")
                print(f"Comment permalink: https://www.reddit.com{comment.permalink}")
                print(vars(instruo))
                count += 1
                print('------------------')
            except Exception as e:
                print(f"Error processing comment {comment.id if hasattr(comment, 'id') else '[unknown]'}: {e}")
                print(f"Error Comment permalink: https://www.reddit.com{comment.permalink}")
    print(f"Processed {count} comments.")


if '__main__' == __name__:
    test_instruo_on_r_translator_recent_comments()
