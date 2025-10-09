#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
The paging !page function contacts a number of people and asks them to
take a look at a post for a language that they're signed up for
notifications. This was the original function Ziwen was written for.
"""
import time

from config import SETTINGS, logger
from connection import REDDIT_HELPER
from notifications import notifier
from reddit_sender import comment_reply
from responses import RESPONSE


def handle(comment, _instruo, komando, ajo):
    logger.info("Page handler initiated.")
    replying_text = []
    current_time = time.time()
    original_poster = comment.author

    minimum_account_age_days = SETTINGS['user_age_page']
    minimum_account_age_seconds = minimum_account_age_days * 86400

    # Checks to see if the user account is old enough to use the
    # paging system.
    if current_time - int(original_poster.created_utc) < minimum_account_age_seconds:
        logger.debug(f"[ZW] Bot: > u/{original_poster}'s account is "
                     f"younger than {minimum_account_age_days} days.")
        reply_text = RESPONSE.COMMENT_PAGE_DISALLOWED + RESPONSE.BOT_DISCLAIMER
        comment_reply(comment, reply_text)
        return

    # Go through the paging languages
    paging_languages = komando.data
    for language in paging_languages:  # This will be a Lingvo.

        # Send messages out.
        original_post = REDDIT_HELPER.submission(ajo.id)
        people_messaged = notifier(language, original_post, mode='page')
        logger.info(f"[ZW] Bot: >> Messaged {len(people_messaged)} people for {language.name}.")

        # Check if there are people subscribed to the language in the
        # database. If there isn't, prep a reply.
        if not people_messaged:
            replying_text.append(
                RESPONSE.COMMENT_NO_LANGUAGE.format(
                    language_name=language.language_name,
                    language_code=language.preferred_code,
                )
            )
        else:
            # Add the notified users to the Ajo's list.
            ajo.add_notified(people_messaged)

    # Collate the languages for which there is nobody on file.
    if replying_text:
        lacking_page_languages_text = '\n\n'.join(replying_text)
        comment_reply(comment, lacking_page_languages_text + RESPONSE.BOT_DISCLAIMER)
        logger.info("Left a comment letting users know which languages "
                    "have no notifications coverage.")

    ajo.update_reddit()

    return
