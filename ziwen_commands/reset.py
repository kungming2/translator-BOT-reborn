#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
Handler for the !reset command, to revert a post back to as if it
were freshly processed. This command can only be called by a mod or the
original author of a post.
...

Logger tag: [ZW:RESET]
"""

import logging

from praw.models import Comment

from config import logger as _base_logger
from models.ajo import Ajo
from models.instruo import Instruo
from models.komando import Komando
from reddit.connection import is_mod
from reddit.reddit_sender import message_send
from responses import RESPONSE

logger = logging.LoggerAdapter(_base_logger, {"tag": "ZW:RESET"})


# ─── Command handler ──────────────────────────────────────────────────────────


def handle(comment: Comment, _instruo: Instruo, _komando: Komando, ajo: Ajo) -> None:
    """Command handler called by ziwen_commands()."""
    logger.info("Reset handler initiated.")
    original_poster = comment.submission.author

    if is_mod(comment.author) or original_poster == comment.author:
        logger.info(f"!reset, from user u/{comment.author} on `{ajo.id}`.")
        ajo.reset()

        reset_msg: str = RESPONSE.MSG_RESET_SUCCESS.format(
            post_id=ajo.id,
            permalink=comment.permalink,
        )
        message_send(
            comment.author,
            subject=RESPONSE.MSG_RESET_SUCCESS_SUBJECT,
            body=reset_msg,
        )

        logger.info(f"> Reset everything for the designated post `{ajo.id}`.")
