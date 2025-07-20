#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
This handles the !missing command, which designates a post as missing
content to be translated and messages the OP about it.
"""
import time

from connection import REDDIT
from config import logger
from reddit_sender import message_send
from responses import RESPONSE


def handle(comment, instruo, komando, ajo):
    print("Missing handler initiated.")
    logger.info(f"[ZW] Bot: COMMAND: !missing, from u/{comment.author} on `{ajo.id}`.")
    current_time = time.time()
    original_poster = REDDIT.redditor(ajo.author)

    total_message = RESPONSE['MSG_MISSING_ASSETS'].format(oauthor=original_poster, opermalink=ajo.permalink)
    message_send(original_poster,
                 subject='A message from r/translator regarding your translation request',
                 body=total_message)

    ajo.set_status("missing")
    ajo.set_time('missing', current_time)

    logger.info(f"[ZW] Bot: > Marked post `{ajo.id}` by u/{original_poster} as missing assets and messaged them.")
    ajo.update_reddit()
