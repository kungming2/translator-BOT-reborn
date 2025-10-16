#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
This handles the !missing command, which designates a post as missing
content to be translated and messages the OP about it.
"""

from config import logger
from connection import REDDIT
from reddit_sender import message_send
from responses import RESPONSE

from . import update_status


def handle(comment, _instruo, komando, ajo):
    status_type = "missing"
    logger.info("Missing handler initiated.")
    logger.info(
        f"[ZW] Bot: COMMAND: !{status_type}, from u/{comment.author} on `{ajo.id}`."
    )
    original_poster = REDDIT.redditor(ajo.author)

    # Handler logic to update the post status.
    update_status(ajo, komando, status_type)

    # Format and send the message to the OP letting them know.
    total_message = RESPONSE.MSG_MISSING_ASSETS.format(
        oauthor=original_poster, opermalink=ajo.permalink
    )
    message_send(
        original_poster,
        subject="A message from r/translator regarding your translation request",
        body=total_message,
    )

    logger.info(
        f"[ZW] Bot: > Marked post `{ajo.id}` by u/{original_poster} "
        f"as missing assets and messaged them."
    )

    return
