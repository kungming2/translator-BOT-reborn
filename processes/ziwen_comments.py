#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
Main script to fetch and handle commands called via comments.
...

Logger tag: [ZW:C]
"""

import logging
import time

from praw.models import Comment
from prawcore import exceptions

from config import SETTINGS
from config import logger as _base_logger
from database import db
from models.ajo import Ajo, ajo_loader
from models.diskuto import diskuto_exists
from models.instruo import Instruo, comment_has_command
from monitoring.points import points_tabulator
from monitoring.usage_statistics import action_counter, user_statistics_writer
from reddit.connection import REDDIT, credentials_source, is_internal_post
from reddit.reddit_sender import message_send
from reddit.verification import VERIFIED_POST_ID
from responses import RESPONSE
from title.title_handling import process_title
from ziwen_commands import HANDLERS

logger = logging.LoggerAdapter(_base_logger, {"tag": "ZW:C"})


# ─── Internal helpers ─────────────────────────────────────────────────────────


def _mark_short_thanks_as_translated(comment: Comment, ajo: Ajo) -> None:
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
        f"COMMAND: Short thanks from u/{author_name}. Sending user a message..."
    )
    ajo.set_status("translated")
    ajo.set_time("translated", current_time)

    # Notify the user.
    message_body = RESPONSE.MSG_SHORT_THANKS_TRANSLATED.format(
        comment.author, f"https://redd.it/{ajo.id}"
    )
    message_send(
        comment.author,
        "A message about your translation request",
        message_body,
    )

    return


# ─── Main comment processing loop ────────────────────────────────────────────


def ziwen_commands() -> None:
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
        logger.error(f"Encountered a server error: {ex}")
        return
    else:
        logger.debug(f"Fetched {len(comments)} comments to process.")

    for comment in comments:
        comment_id = comment.id
        original_post = comment.submission
        comment_body = comment.body.lower()  # lowercase for ease of command matching

        # ── Pre-flight checks ──────────────────────────────────────────────────

        # Skip comments with deleted authors.
        try:
            author_name = comment.author.name
        except AttributeError:
            continue

        # Skip internal posts (e.g. meta/community), but allow the verified thread.
        if original_post.id != VERIFIED_POST_ID and (
            diskuto_exists(original_post.id) or is_internal_post(original_post)
        ):
            continue

        # Skip already-processed comments; mark new ones immediately.
        if db.cursor_main.execute(
            "SELECT 1 FROM old_comments WHERE id = ?", (comment_id,)
        ).fetchone():
            logger.debug(f"Comment `{comment_id}` has already been processed.")
            continue
        else:
            db.cursor_main.execute(
                "INSERT INTO old_comments (id, created_utc) VALUES (?, ?)",
                (comment_id, int(comment.created_utc)),
            )
            db.conn_main.commit()
            logger.debug(f"Comment `{comment_id}` is now being processed.")

        # Skip the bot's own comments and AutoModerator comments.
        logger.debug(f"Checking author: '{author_name}' against bot: '{username}'")
        if author_name.lower() in [
            username.lower(),
            "automoderator",
            "translator-modteam",
        ]:
            logger.debug(f"`{comment_id}` is from bot u/{author_name}. Skipping...")
            continue

        # Skip comments on filtered posts.
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

        # ── Ajo loading ────────────────────────────────────────────────────────

        is_verified_post = original_post.id == VERIFIED_POST_ID
        original_ajo = ajo_loader(original_post.id)
        if not original_ajo:
            if is_verified_post:
                logger.debug("Verified post has no Ajo — skipping Ajo creation.")
            else:
                logger.warning(
                    f"Ajo for `{original_post.id}` does not exist. Creating..."
                )
                original_ajo = Ajo.from_titolo(
                    process_title(original_post), original_post
                )
        logger.debug(
            f"> Ajo lingvo is {original_ajo.lingvo if original_ajo else None}"
        )  # loaded lazily

        # ── Command dispatch ───────────────────────────────────────────────────

        instruo = None
        if comment_has_command(comment_body):
            parent_languages = [original_ajo.lingvo] if original_ajo else []
            instruo = Instruo.from_comment(comment, parent_languages=parent_languages)

            logger.info(
                f"> Derived instruo and ajo for `{comment.id}` on "
                f"post `{original_post.id}` as: `{instruo}`."
            )
            logger.info(
                f"> Comment can be viewed at https://www.reddit.com{comment.permalink}."
            )

            # If this is the verified thread, only allow !verify commands.
            if original_post.id == VERIFIED_POST_ID:
                allowed_commands = [
                    k for k in instruo.commands if k.name.lower() == "verify"
                ]
                if not allowed_commands:
                    logger.info(
                        f"Non-verify command attempted on verified thread `{original_post.id}`. "
                        f"Skipping comment `{comment_id}`."
                    )
                    continue
                instruo.commands = allowed_commands

            for komando in instruo.commands:
                handler = HANDLERS.get(komando.name.lower())

                if handler:
                    logger.info(
                        f"Command `{komando}` detected for `{comment_id}` on "
                        f"post `{original_post.id}`. Passing to handler."
                    )
                    handler(comment, instruo, komando, original_ajo)
                    action_counter(1, komando.name)
                else:
                    logger.error(f"No handler for command: {komando.name}")

            user_statistics_writer(instruo)
            logger.debug("Recorded user commands in database.")

            if (
                not diskuto_exists(original_post.id)
                and original_ajo
                and original_ajo.lingvo
            ):
                points_tabulator(comment, original_post, original_ajo.lingvo)
        else:
            # Non-command comment on the verified thread — skip silently.
            if original_post.id == VERIFIED_POST_ID:
                logger.debug(
                    "Non-command comment on verified thread "
                    f"`{original_post.id}`. Skipping."
                )
                continue

            logger.debug(
                f"Post `{original_post.id}` does not contain "
                "any operational keywords and commands."
            )

        # ── Post-command processing ────────────────────────────────────────────

        # Process THANKS keywords from original posters.
        if original_ajo and any(keyword in comment_body for keyword in thanks_keywords):
            _mark_short_thanks_as_translated(comment, original_ajo)

        # Check if there was a 'set' command in this comment.
        moderator_set = False
        skip_update = False
        if instruo:
            moderator_set = any(
                komando.name.lower() == "set" for komando in instruo.commands
            )
            # Skip update if the only command is 'verify'.
            if (
                len(instruo.commands) == 1
                and instruo.commands[0].name.lower() == "verify"
            ):
                skip_update = True

        # Update the Ajo flair and database — skip in testing mode
        # and skip if the only command was 'verify'.
        if not SETTINGS["testing_mode"] and not skip_update and original_ajo:
            original_ajo.update_reddit(moderator_set=moderator_set)
