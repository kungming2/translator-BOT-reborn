#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
Allows posts to be set as "Needs Review".
This is generally used when asking for reviews of one's work.
"""

from config import logger
from models.kunulo import Kunulo

from . import update_status


def handle(comment, _instruo, komando, ajo):
    logger.info("Doublecheck handler initiated.")
    status_type = 'doublecheck'
    logger.info(f"[ZW] Bot: COMMAND: !{status_type}, from u/{comment.author}.")

    # Handler logic to update the post status.
    update_status(ajo, komando, status_type)

    # Update the Ajo and post.
    logger.info(f"[ZW] Bot: > Marked post `{ajo.id}` as 'Needs Review.' "
                f"(`{status_type}`)")

    # Delete any previously claimed comment.
    kunulo_object = Kunulo.from_submission(ajo.submission)
    kunulo_object.delete('comment_claim')

    return
