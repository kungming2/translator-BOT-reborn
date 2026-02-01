#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
!set is a mod-accessible means of setting the post flair. The mod's
comment is removed by AutoModerator so it looks like nothing happened.
"""

from config import logger
from connection import is_mod
from models.kunulo import Kunulo
from reddit_sender import message_send
from responses import RESPONSE

from . import update_language


def handle(comment, _instruo, komando, ajo) -> None:
    """Command handler called by ziwen_commands()."""
    logger.info("Set handler initiated.")

    # Check to see if the person calling this command is a moderator
    if not is_mod(comment.author):
        logger.debug(f"u/{comment.author} is not a mod. Skipping...")
        return

    logger.info(
        f"[ZW] Bot: COMMAND: !set, from moderator u/{comment.author} on `{ajo.id}`."
    )

    # Invalid identification data.
    if not komando.data or None in komando.data:
        logger.error(f"Invalid or missing Komando data: {komando.data}")
        message_send(
            comment.author,
            "[Notification] Invalid !set language",
            RESPONSE.COMMENT_LANGUAGE_NO_RESULTS.format(id_comment_body=comment.body),
        )
        logger.info("[ZW] Bot: Replied letting the mod know setting is invalid.")
        return

    # Update the Ajo's language(s) post.
    try:
        update_language(ajo, komando)
    except ValueError as e:
        logger.error(f"[ZW] Bot: !set data is invalid: {e}")
        message_send(
            comment.author,
            "[Notification] Invalid !set language",
            RESPONSE.COMMENT_LANGUAGE_NO_RESULTS.format(id_comment_body=comment.body),
        )
        logger.info("[ZW] Bot: Replied letting the mod know setting is invalid.")
        return

    # Delete any pre-existing defined multiple or "Unknown" comment.
    delete_tags: list[str] = ["comment_defined_multiple", "comment_unknown"]
    kunulo_object: Kunulo = Kunulo.from_submission(ajo.submission)
    for tag in delete_tags:
        kunulo_object.delete(tag)

    # Message the mod who called this command.
    languages = komando.data  # List of Lingvo objects
    logger.info(
        f"[ZW] Bot: Building !set success message for {len(languages)} language(s)."
    )

    if len(languages) == 1:
        new_language = languages[0]
        set_msg: str = (
            f"{new_language.greetings}, moderator u/{comment.author},\n\n"
            f"The [post](https://www.reddit.com{ajo.submission.permalink}) has been set to the language "
            f"{new_language.name} (`{new_language.preferred_code}`)."
        )
        logger.info(
            f"[ZW] Bot: Single-language message built for {new_language.preferred_code}."
        )
    else:
        # Multiple languages - collate greetings (excluding "Hello")
        greetings = [lang.greetings for lang in languages if lang.greetings != "Hello"]
        greeting_string = " / ".join(greetings) if greetings else "Hello"

        # Build the language list string
        lang_parts = [f"{lang.name} (`{lang.preferred_code}`)" for lang in languages]
        lang_string = ", ".join(lang_parts[:-1]) + f", and {lang_parts[-1]}"

        set_msg: str = (
            f"{greeting_string}, moderator u/{comment.author},\n\n"
            f"The [post](https://www.reddit.com{ajo.submission.permalink}) has been set to the languages "
            f"{lang_string}."
        )
        logger.info("[ZW] Bot: Multi-language message built.")

    logger.info(f"[ZW] Bot: Sending !set success message to u/{comment.author}.")
    try:
        message_send(
            comment.author,
            subject="[Notification] !set command successful",
            body=set_msg,
        )
        logger.info(
            f"[ZW] Bot: Successfully informed moderator u/{comment.author} of command success."
        )
    except Exception as e:
        logger.error(
            f"[ZW] Bot: Failed to send message to u/{comment.author}: {type(e).__name__}: {e}"
        )
