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

    def __init__(
        self,
        id_comment,
        id_post,
        created_utc,
        author_comment,
        commands,
        languages,
        body=None,
        author_post=None,
    ):
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
            "body": self.body,
        }

    @classmethod
    def from_comment(cls, comment, parent_languages=None):
        text = comment.body
        id_comment = comment.id
        id_post = comment.submission.id
        created_utc = int(comment.created_utc)
        author_comment = str(comment.author) if comment.author else "[deleted]"
        author_post = (
            str(comment.submission.author) if comment.submission.author else "[deleted]"
        )
        commands = extract_commands_from_text(text)
        return cls(
            id_comment=id_comment,
            id_post=id_post,
            created_utc=created_utc,
            author_comment=author_comment,
            author_post=author_post,
            commands=commands,
            languages=parent_languages or [],
            body=text,
        )

    @classmethod
    def from_text(cls, text, parent_languages=None):
        """
        Creates an Instruo instance from a plain text string for testing purposes only.

        WARNING: This method is NOT intended for production use. It creates an Instruo
        with placeholder values for all PRAW comment properties (IDs, timestamps, author
        information) since these cannot be obtained from raw text. Use this method only
        for unit tests, manual testing, or debugging command extraction logic.

        Args:
            text: A string containing the comment text to parse for commands.
            parent_languages: Optional list of Lingvo objects to associate with the Instruo.

        Returns:
            An Instruo instance with extracted commands and placeholder metadata.
        """
        commands = extract_commands_from_text(text)
        return cls(
            id_comment="TEST_ID",
            id_post="TEST_POST_ID",
            created_utc=0,
            author_comment="[test_user]",
            author_post="[test_post_author]",
            commands=commands,
            languages=parent_languages or [],
            body=text,
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
        text = comment.lower().strip()
    else:
        text = comment.body.lower().strip()

    # Remove multiline code blocks (triple backticks)
    text = re.sub(r"```[\s\S]*?```", "", text)  # non-greedy, removes across lines

    # Then remove inline *quoted* commands (like `!doublecheck`) —
    # but keep single backticks that look like CJK lookups (`享受`)
    # We'll only strip inline code *if* it contains a command marker inside.
    text = re.sub(r"`![^`]*`", "", text)

    # Detect lookup commands (e.g. `word` or {{term}})
    for lookup in SETTINGS.get("lookup_commands", []):
        if lookup in text:
            return True

    # Check commands with required arguments
    for cmd in SETTINGS["commands_with_args"]:
        if cmd in text:
            return True

    # Check commands with optional arguments
    for cmd in SETTINGS["commands_optional_args"]:
        if cmd in text:
            return True
        try_colon = cmd + ":"
        if try_colon in text:
            return True

    # Check commands with no arguments
    for cmd in SETTINGS["commands_no_args"]:
        if cmd in text:
            return True

    return False


def show_menu():
    print("\nSelect a query to run:")
    print("1. Enter Reddit comment URL to parse ")
    print("2. Enter text to parse for commands ")


if "__main__" == __name__:
    while True:
        show_menu()
        choice = input("Enter your choice (1-2): ")

        if choice == "x":
            print("Exiting...")
            break

        if choice not in ["1", "2"]:
            print("Invalid choice, please try again.")
            continue

        if choice == "1":
            # Get comment URL from user
            comment_url = input("Enter Reddit comment URL: ").strip()

            # Get comment from URL and process
            try:
                test_comment = REDDIT_HELPER.comment(url=comment_url)
                test_instruo = Instruo.from_comment(test_comment)
                print(f"Instruo created: {test_instruo}\n")
                print(vars(test_instruo))
            except Exception as ex:
                print(f"Error: {ex}\n")
        elif choice == "2":
            testing_text = input("Enter text to parse for commands: ")
            print(comment_has_command(testing_text.strip()))
