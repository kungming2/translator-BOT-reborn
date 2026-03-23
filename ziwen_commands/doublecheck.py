#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
Allows posts to be set as "Needs Review".
This is generally used when asking for reviews of one's work.
...

Logger tag: [ZW:DBLCHK]
"""

import logging

from praw.models import Comment

from config import logger as _base_logger
from models.ajo import Ajo
from models.instruo import Instruo
from models.komando import Komando
from models.kunulo import Kunulo

from . import update_status

logger = logging.LoggerAdapter(_base_logger, {"tag": "ZW:DBLCHK"})


# ─── Command handler ──────────────────────────────────────────────────────────


def handle(comment: Comment, _instruo: Instruo, komando: Komando, ajo: Ajo) -> None:
    """
    Command handler called by ziwen_commands().

    Marks a post as needing review by updating its status to 'doublecheck'
    and removes any existing claim comments.

    Args:
        comment: The Reddit comment that triggered this command.
        _instruo: Instruction object (unused in this handler).
        komando: Command object containing parsed command data.
        ajo: The Ajo object representing the post to be marked for review.

    Side effects:
        - Updates the post status to 'doublecheck' (Needs Review)
        - Deletes any previously claimed comment on the submission
        - Logs the status change operation
    """
    logger.info("Doublecheck handler initiated.")
    status_type: str = "doublecheck"
    logger.info(f"!{status_type}, from u/{comment.author}.")

    update_status(ajo, komando, status_type)
    logger.info(f"> Marked post `{ajo.id}` as 'Needs Review.' (`{status_type}`)")

    kunulo_object: Kunulo = Kunulo.from_submission(ajo.submission)
    kunulo_object.delete("comment_claim")
