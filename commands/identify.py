#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
from config import logger
from models.kunulo import Kunulo
from notifications import notifier
from wiki import update_wiki_page


def send_notifications_okay(instruo, ajo):
    """Simple function that checks to see if the comment also
    includes another Komando that sets the setting to translated
    or needs review.
    Returns True if it's okay to send messages, False otherwise."""

    if ajo.status in ['translated', 'doublecheck']:
        return False

    for command in instruo.commands:
        if command.name in ['translated', 'doublecheck']:
            return False

    return True


def handle(comment, instruo, komando, ajo):
    print("Identify handler initiated.")
    original_post = comment.submission
    permission_to_send = send_notifications_okay(instruo, ajo)

    # Invalid identification data.
    if not komando.data:
        logger.error("No Komando data found!")
        return

    logger.info(f"[ZW] Bot: COMMAND: !identify, from u/{comment.author}.")
    logger.info(f'[ZW] Bot: !identify data is: {komando.data}')

    # Update the Ajo's language for a single-language post.
    if ajo.type == 'single':
        original_language = ajo.language_name
        new_language = komando.data[0]  # Lingvo
        ajo.set_language(new_language)
        update_wiki_page(
            save_or_identify=False,
            formatted_date=ajo.created_utc,
            title=ajo.title_original,
            post_id=ajo.id,
            flair_text=original_language,
            new_flair=komando.data[0].name,
            user=ajo.author
        )

        # Assuming the two languages are different, we can obtain a
        # list of people to notify for.
        if original_language != new_language and permission_to_send:
            logger.info("Now sending notifications...")
            contacted = notifier(new_language, original_post, 'identify')
            ajo.add_notified(contacted)

    else:  # Defined multiple post.
        logger.info("Handling defined multiple post...")
        # TODO fill out logic
        # TODO Notify others about the identification.
        logger.info("Now sending notifications...")
        # TODO check against !translated or doublecheck also in the Instruo.
        pass

    # TODO Delete the 'Unknown' placeholder comment left by the bot.
    kunulo = Kunulo.from_submission(original_post)

    # Update the Ajo and post.
    ajo.update_reddit()
