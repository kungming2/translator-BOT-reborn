#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
Main script to fetch and handle commands called via comments.
"""

import time
import traceback

from prawcore import exceptions
from wasabi import msg

from commands import HANDLERS
from config import SETTINGS, logger
from connection import REDDIT, credentials_source
from database import db
from error import error_log_extended
from models.ajo import Ajo, ajo_loader
from models.diskuto import diskuto_exists
from models.instruo import Instruo, comment_has_command
from points import points_tabulator
from usage_statistics import action_counter, user_statistics_writer
from reddit_sender import message_send
from responses import RESPONSE
from title_handling import Titolo


def _mark_short_thanks_as_translated(comment, ajo):
    """Looks at the content of a comment and determines if the
    submission author's thank you is sufficient to mark it as
    translated, according to specific criteria.
    """
    author_name = comment.author.name
    comment_body = comment.body.lower()
    has_translated = "!translated" in comment_body
    exceptions_list = ["but", "however", "no"]
    short_body = len(comment.body) <= 20

    # Exit if it doesn't meet our criteria for assessing.
    if has_translated or not short_body:
        return

    # Is the author of the comment the author of the post?
    if author_name != ajo.author:
        return  # If not, we don't care about this.

    if ajo.status != "untranslated":
        return

    # This should only be marked if it's not in an identified state,
    # in case people respond to that command.
    if ajo.is_identified:
        return

    # Did the OP have reservations?
    if any(exception in comment_body for exception in exceptions_list):
        return

    # Here, this means that the criteria has been met to mark the Ajo
    # and the post as being translated.
    current_time = int(time.time())
    logger.info(
        f"[ZW] Bot: COMMAND: Short thanks from u/{author_name}. Sending user a message..."
    )
    ajo.set_status("translated")
    ajo.set_time("translated", current_time)

    # Notify the user.
    message_body = RESPONSE.MSG_SHORT_THANKS_TRANSLATED.format(
        comment.author, f"https://redd.it/{ajo.id}"
    )
    message_send(
        comment.author,
        "[Notification] A message about your translation request",
        message_body,
    )

    return


def ziwen_commands():
    """
    Main runtime for r/translator that checks for keywords and commands.

    :return: Nothing.
    """
    subreddit = SETTINGS["subreddit"]
    thanks_keywords = SETTINGS["thanks_keywords"]
    username = credentials_source["USERNAME"]
    logger.debug(f"Fetching new r/{subreddit} comments...")
    r = REDDIT.subreddit(subreddit)

    try:
        comments = list(r.comments(limit=SETTINGS["max_posts"]))
    except exceptions.ServerError:
        # Server issues.
        logger.error("Encountered a server error.")
        return

    # Start processing comments.
    for comment in comments:
        comment_id = comment.id
        # Returns a submission object of the parent to work with
        original_post = comment.submission
        comment_body = comment.body.lower()  # lowercase for ease of command matching

        # Skip comments with deleted authors.
        try:
            author_name = comment.author.name
        except AttributeError:
            continue

        # Skip the bot's own comments.
        if author_name == username:
            continue

        # Skip internal posts (e.g. meta/community).
        if diskuto_exists(original_post.id):
            continue

        # Check to see if the comment has already been acted upon.
        if db.cursor_main.execute(
            "SELECT 1 FROM old_comments WHERE ID = ?", (comment_id,)
        ).fetchone():
            # Comment already processed
            logger.debug(f"Comment `{comment_id}` has already been processed.")
            continue
        else:  # Mark comment as processed in the database
            db.cursor_main.execute(
                "INSERT INTO old_comments (ID) VALUES (?)", (comment_id,)
            )
            db.conn_main.commit()
            logger.debug(f"Comment `{comment_id}` is now being processed.")

        # Load the ajo for the post from the database.
        original_ajo = ajo_loader(original_post.id)
        if not original_ajo:
            # On the off-chance that there is no Ajo associated...
            logger.warning(f"Ajo for `{original_post.id}` does not exist. Creating...")
            original_ajo = Ajo.from_titolo(
                Titolo.process_title(original_post), original_post
            )

        # Derive an Instruo, and act on it if there are commands.
        # It's basically a class that represents a comment which has
        # subreddit-specific commands and instructions in it.
        # Note that an Instruo can have multiple commands associated
        # with it.
        if comment_has_command(comment_body):
            # Initialize the variables the command handlers will require.
            instruo = Instruo.from_comment(comment)

            logger.info(f"> Derived instruo and ajo for `comment.id` as: `{instruo}`.")
            logger.info(f"> Comment can be viewed at `{comment.permalink}`.")

            # Pass off to handling functions depending on the command.
            # e.g. an identify command will pass off to the handler
            # function located in identify.py

            # Iterate over the commands in the comment.
            for komando in instruo.commands:
                handler = HANDLERS.get(komando.name.lower())

                # A matching handler for the command is found.
                # Pass off the information for it to handle.
                if handler:
                    logger.info(
                        f"Command `{komando}` detected for `{comment_id}`. Passing to handler."
                    )
                    handler(comment, instruo, komando, original_ajo)
                    # Record this action to the counter log
                    action_counter(1, komando.name)
                else:
                    # This is unlikely to happen - basically happens when
                    # there is a command listed to be acted upon, but
                    # there is no code to actually process it.
                    logger.error(f"No handler for command: {komando.name}")

            # Record data on user commands.
            user_statistics_writer(instruo)
            logger.debug("[ZW] Bot: Recorded user commands in database.")

            # Calculate points for the comment and write to database.
            points_tabulator(comment, original_post, original_ajo.lingvo)
        else:
            logger.debug(
                f"[ZW] Bot: Post `{original_post.id}` does not contain any operational keywords."
            )

        # Process THANKS keywords from original posters.
        if any(keyword in comment_body for keyword in thanks_keywords):
            # Assess whether a thank-you comment can mark the post as translated.
            _mark_short_thanks_as_translated(comment, original_ajo)

        # Update the ajo if NOT in testing mode.
        if not SETTINGS["testing_mode"]:
            original_ajo.update_reddit()


if __name__ == "__main__":
    msg.good("Launching Ziwen commands...")
    # noinspection PyBroadException
    try:
        ziwen_commands()
    except Exception:  # intentionally broad: catch all exceptions for logging
        error_entry = traceback.format_exc()
        error_log_extended(error_entry, "Ziwen Commands")
    msg.info("Ziwen commands routine completed.")
