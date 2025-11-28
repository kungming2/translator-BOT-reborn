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
from connection import REDDIT, credentials_source, is_internal_post
from database import db
from error import error_log_extended
from models.ajo import Ajo, ajo_loader
from models.diskuto import diskuto_exists
from models.instruo import Instruo, comment_has_command
from points import points_tabulator
from reddit_sender import message_send
from responses import RESPONSE
from title_handling import Titolo
from usage_statistics import action_counter, user_statistics_writer
from verification import VERIFIED_POST_ID


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
        f"[ZW] Commands: COMMAND: Short thanks from u/{author_name}. Sending user a message..."
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

    This function processes comments in the subreddit, looking for bot commands
    and keywords. It handles command execution, user statistics, points calculation,
    and flair updates based on comment content.

    The function performs the following operations:
    - Fetches recent comments from the subreddit
    - Skips already processed, deleted, or internal post comments
    - Loads or creates Ajo objects for each post
    - Detects and processes bot commands (e.g., !identify, !set, !claim)
    - Records user statistics and calculates translation points
    - Processes thank-you keywords from original posters
    - Updates post flairs based on status changes

    Special handling for the !set command:
    When a moderator uses the !set command to change a post's language, the
    flair update will not include the "(Identified)" suffix, as this indicates
    a direct moderator action rather than community identification.

    Special handling for the verified thread:
    The verified thread (retrieved via get_verified_thread()) is exempted from
    internal post filtering. Only !verify commands are allowed on this thread;
    all other commands are blocked.

    :return: Nothing.
    """
    subreddit = SETTINGS["subreddit"]
    thanks_keywords = SETTINGS["thanks_keywords"]
    username = credentials_source["USERNAME"]
    logger.debug(f"Fetching new r/{subreddit} comments...")
    r = REDDIT.subreddit(subreddit)

    try:
        comments = list(r.comments(limit=SETTINGS["max_posts"]))
    except exceptions.ServerError as ex:
        # Server issues.
        logger.error(f"Encountered a server error: {ex}")
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

        # Skip internal posts (e.g. meta/community), but allow the verified thread
        if original_post.id != VERIFIED_POST_ID and (
            diskuto_exists(original_post.id) or is_internal_post(original_post)
        ):
            continue

        # Check to see if the comment has already been acted upon.
        if db.cursor_main.execute(
            "SELECT 1 FROM old_comments WHERE id = ?", (comment_id,)
        ).fetchone():
            # Comment already processed
            logger.debug(f"Comment `{comment_id}` has already been processed.")
            continue
        else:  # Mark comment as processed in the database
            db.cursor_main.execute(
                "INSERT INTO old_comments (id, created_utc) VALUES (?, ?)",
                (comment_id, int(comment.created_utc)),
            )
            db.conn_main.commit()
            logger.debug(f"Comment `{comment_id}` is now being processed.")

        # Skip the bot's own comments and AutoModerator comments.
        logger.debug(
            f"[ZW] Commands: Checking author: '{author_name}' against bot: '{username}'"
        )
        if author_name.lower() in [
            username.lower(),
            "automoderator",
            "translator-modteam",
        ]:
            logger.info(
                f"[ZW] Commands: `{comment_id}` is from bot u/{author_name}. Skipping..."
            )
            continue

        # Skip comments on filtered posts
        filtered_result = db.cursor_main.execute(
            "SELECT filtered FROM old_posts WHERE id = ?", (original_post.id,)
        ).fetchone()
        # Note: filtered_result[0] accesses the filtered column directly since
        # we're only SELECTing that one column (not SELECT *)
        if filtered_result and filtered_result[0] == 1:
            logger.info(
                f"Comment `{comment_id}` is on already-filtered post `{original_post.id}`. Skipping."
            )
            continue

        # Load the ajo for the post from the database.
        original_ajo = ajo_loader(original_post.id)
        if not original_ajo:
            # On the off-chance that there is no Ajo associated...
            logger.warning(
                f"[ZW] Commands: Ajo for `{original_post.id}` does not exist. Creating..."
            )
            original_ajo = Ajo.from_titolo(
                Titolo.process_title(original_post), original_post
            )
        logger.debug(
            f"[ZW] Commands: > Ajo lingvo is {original_ajo.lingvo}"
        )  # loaded lazily

        # Derive an Instruo, and act on it if there are commands.
        # It's basically a class that represents a comment which has
        # subreddit-specific commands and instructions in it.
        # Note that an Instruo can have multiple commands associated
        # with it.
        instruo = None
        if comment_has_command(comment_body):
            # Initialize the variables the command handlers will require.
            instruo = Instruo.from_comment(comment)

            logger.info(
                f"[ZW] Commands: > Derived instruo and ajo for `{comment.id}` on "
                f"post `{original_post.id}` as: `{instruo}`."
            )
            logger.info(
                f"[ZW] Commands: > Comment can be viewed at https://www.reddit.com{comment.permalink}."
            )

            # If this is the verified thread, only allow !verify commands
            if original_post.id == VERIFIED_POST_ID:
                # Filter to only allow 'verify' commands on the verified thread
                allowed_commands = [
                    k for k in instruo.commands if k.name.lower() == "verify"
                ]
                if not allowed_commands:
                    logger.info(
                        f"[ZW] Commands: Non-verify command attempted on verified thread `{original_post.id}`. "
                        f"Skipping comment `{comment_id}`."
                    )
                    continue
                # Replace commands with only the allowed ones
                instruo.commands = allowed_commands

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
                        f"[ZW] Commands: Command `{komando}` detected for `{comment_id}` on "
                        f"post `{original_post.id}`. Passing to handler."
                    )
                    handler(comment, instruo, komando, original_ajo)
                    # Record this action to the counter log
                    action_counter(1, komando.name)
                else:
                    # This is unlikely to happen - basically happens when
                    # there is a command listed to be acted upon, but
                    # there is no code to actually process it.
                    logger.error(
                        f"[ZW] Commands: No handler for command: {komando.name}"
                    )

            # Record data on user commands.
            user_statistics_writer(instruo)
            logger.debug("[ZW] Commands: Recorded user commands in database.")

            # Calculate points for the comment and write them to database.
            # This is obviously skipped if the post is an internal post.
            if not diskuto_exists(original_post.id):
                points_tabulator(comment, original_post, original_ajo.lingvo)
        else:
            # If this is the verified thread and there are no commands, skip
            if original_post.id == VERIFIED_POST_ID:
                logger.debug(
                    "Non-command comment on verified thread "
                    f"`{original_post.id}`. Skipping."
                )
                continue

            logger.debug(
                f"[ZW] Commands: Post `{original_post.id}` does not contain "
                "any operational keywords and commands."
            )

        # Process THANKS keywords from original posters.
        if any(keyword in comment_body for keyword in thanks_keywords):
            # Assess whether a thank-you comment can mark the post as translated.
            _mark_short_thanks_as_translated(comment, original_ajo)

        # Check if there was a 'set' command in this comment
        moderator_set = False
        skip_update = False
        if instruo and comment_has_command(comment_body):
            moderator_set = any(
                komando.name.lower() == "set" for komando in instruo.commands
            )
            # Skip update if the only command is 'verify'
            if (
                len(instruo.commands) == 1
                and instruo.commands[0].name.lower() == "verify"
            ):
                skip_update = True

        # Update the ajo if NOT in testing mode. This updates both the
        # flair on the site as well as the local database.
        # Also skip if the only command was 'verify'.
        if not SETTINGS["testing_mode"] and not skip_update:
            original_ajo.update_reddit(moderator_set=moderator_set)


if __name__ == "__main__":
    msg.good("Launching Ziwen commands...")
    # noinspection PyBroadException
    try:
        ziwen_commands()
    except Exception:  # intentionally broad: catch all exceptions for logging
        error_entry = traceback.format_exc()
        error_log_extended(error_entry, "Ziwen Commands")
    msg.info("Ziwen commands routine completed.")
