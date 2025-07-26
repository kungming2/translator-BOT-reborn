#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
The paging !page function contacts a number of people and asks them to
take a look at a post for a language that they're signed up for
notifications. This was the original function Ziwen was written for.
"""
import time

from config import SETTINGS, logger
from reddit_sender import comment_reply
from responses import RESPONSE


def handle(comment, instruo, komando, ajo):
    print("Page handler initiated.")
    current_time = time.time()
    original_poster = comment.author

    minimum_account_age_days = SETTINGS['user_age_page']
    minimum_account_age_seconds = minimum_account_age_days * 86400

    # Checks to see if the user account is old enough to use the
    # paging system.
    if current_time - int(original_poster.created_utc) < minimum_account_age_seconds:
        logger.debug(f"[ZW] Bot: > u/{original_poster}'s account is younger than {minimum_account_age_days} days.")
        reply_text = RESPONSE.COMMENT_PAGE_DISALLOWED + RESPONSE.BOT_DISCLAIMER
        comment_reply(comment, reply_text)
        return

    # TODO go through the paging languages

    # TODO make sure to check if NSFW

    # Check if languages exist in database, if they do use notifier.

    # Use notifier

    # ajo.add_notified

    pass
