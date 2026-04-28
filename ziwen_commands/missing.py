#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
This handles the !missing command, which designates a post as missing
content to be translated and messages the OP about it.
...

Logger tag: [ZW:MISSING]
"""

import logging

from praw.models import Comment

from config import logger as _base_logger
from models.ajo import Ajo
from models.instruo import Instruo
from models.komando import Komando
from reddit.connection import REDDIT
from reddit.reddit_sender import message_send
from responses import RESPONSE

from . import update_status

logger = logging.LoggerAdapter(_base_logger, {"tag": "ZW:MISSING"})


# ─── Command handler ──────────────────────────────────────────────────────────


def handle(comment: Comment, _instruo: Instruo, komando: Komando, ajo: Ajo) -> None:
    """Command handler called by ziwen_commands()."""
    status_type: str = "missing"
    logger.info("Missing handler initiated.")
    logger.info(f"!{status_type}, from u/{comment.author} on `{ajo.id}`.")

    if ajo.author is None:
        logger.warning(
            f"Post `{ajo.id}` has no author (deleted/removed). Skipping missing handler."
        )
        return

    original_poster = REDDIT.redditor(ajo.author)

    update_status(ajo, komando, status_type)

    total_message: str = RESPONSE.MSG_MISSING_ASSETS.format(
        author=original_poster, permalink=ajo.submission.permalink
    )
    message_send(
        original_poster,
        subject=RESPONSE.MSG_MISSING_ASSETS_SUBJECT,
        body=total_message,
    )

    logger.info(
        f"> Marked post `{ajo.id}` by u/{original_poster} "
        f"as missing assets and messaged them."
    )
