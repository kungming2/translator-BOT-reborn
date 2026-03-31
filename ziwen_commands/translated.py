#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
Allows posts to be set as "Translated".
This is generally used when a translator believes the post's
request to be fulfilled.
...

Logger tag: [ZW:TRANSLATED]
"""

import logging

from praw.models import Comment

from config import logger as _base_logger
from models.ajo import Ajo
from models.instruo import Instruo
from models.komando import Komando
from models.kunulo import Kunulo
from reddit.messaging import notify_op_translated_post

from . import update_status

logger = logging.LoggerAdapter(_base_logger, {"tag": "ZW:TRANSLATED"})


# ─── Command handler ──────────────────────────────────────────────────────────


def handle(comment: Comment, _instruo: Instruo, komando: Komando, ajo: Ajo) -> None:
    """Command handler called by ziwen_commands()."""
    logger.info("Translated handler initiated.")
    status_type: str = "translated"
    logger.info(f"!{status_type}, from u/{comment.author}.")

    update_status(ajo, komando, status_type)
    logger.info(f"> Marked post `{ajo.id}` as {status_type}.")

    # Delete any existing claim and long comments.
    kunulo_object: Kunulo = Kunulo.from_submission(ajo.submission)
    for tag in ["comment_long", "comment_claim"]:
        kunulo_object.delete(tag)

    # Message the OP if they haven't already thanked people.
    if (
        not kunulo_object.op_thanks
        and ajo.author is not None
        and comment.author.name != ajo.author
    ):
        logger.debug(f"Notifying OP u/{ajo.author} of translation.")
        notify_op_translated_post(ajo.author, ajo.submission.permalink)
