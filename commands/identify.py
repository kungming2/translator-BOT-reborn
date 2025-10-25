#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
!identify is a public means of setting the post flair. This is also
known by the short form !id, which is treated as a synonym.
"""

from config import logger
from models.kunulo import Kunulo
from notifications import notifier
from reddit_sender import comment_reply
from responses import RESPONSE
from wiki import update_wiki_page

from . import update_language


def _send_notifications_okay(instruo, ajo) -> bool:
    """Simple function that checks to see if the comment also
    includes another Komando that sets the setting to translated
    or needs review.
    Returns True if it's okay to send messages, False otherwise."""

    if ajo.status in ["translated", "doublecheck"]:
        return False

    for command in instruo.commands:
        if command.name in ["translated", "doublecheck"]:
            return False

    return True


def handle(comment, instruo, komando, ajo) -> None:
    """Command handler called by ziwen_commands()."""
    logger.info("Identify handler initiated.")
    original_post = comment.submission

    # Check against !translated or doublecheck also in the Instruo.
    # We don't want to alert people if the comment already included
    # a translation.
    permission_to_send: bool = _send_notifications_okay(instruo, ajo)

    # Invalid identification data.
    if not komando.data:
        logger.error("No Komando data found!")
        return

    logger.info(f"[ZW] Bot: COMMAND: !identify, from u/{comment.author} on `{ajo.id}`.")
    logger.info(f"[ZW] Bot: !identify data is: {komando.data}")

    # Update the Ajo's language(s) post.
    try:
        update_language(ajo, komando)
    except ValueError as e:
        logger.error(f"[ZW] Bot: !identify data is invalid: {e}")
        invalid_text = RESPONSE.COMMENT_LANGUAGE_NO_RESULTS
        comment_reply(comment, invalid_text)
        logger.info("[ZW] Bot: Replied letting them know identification is invalid.")
        return

    # Handle notifications.
    if ajo.type == "single" or (ajo.type == "multiple" and not ajo.is_defined_multiple):
        original_language = ajo.lingvo
        new_language = komando.data[0]  # Lingvo

        # Assuming the two languages are different, we can obtain a
        # list of people to notify for.
        if original_language != new_language:
            # Update the 'identified' wiki page for single languages.
            if ajo.type == "single":
                update_wiki_page(
                    action="identify",
                    formatted_date=ajo.created_utc,
                    title=ajo.title_original,
                    post_id=ajo.id,
                    flair_text=original_language,
                    new_flair=komando.data[0].name,
                    user=ajo.author,
                )
            if permission_to_send:
                logger.info("Now sending notifications...")
                contacted = notifier(new_language, original_post, "identify")
                ajo.add_notified(contacted)
    else:  # Defined multiple post.
        if ajo.is_defined_multiple:
            logger.info("Handling defined multiple post...")
            # For a defined multiple post, iterate over the new
            # languages that are listed.
            new_languages = komando.data
            for language in new_languages:
                if permission_to_send:
                    logger.info(f"Now sending notifications for {language.name}...")
                    contacted = notifier(language, original_post, "identify")
                    ajo.add_notified(contacted)

    # Delete the 'Unknown' placeholder comment left by the bot.
    kunulo: Kunulo = Kunulo.from_submission(original_post)
    kunulo.delete("comment_unknown")
