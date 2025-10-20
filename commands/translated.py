#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
Allows posts to be set as "Translated".
This is generally used when a translator believes the post's
request to be fulfilled.
"""

from config import logger
from messaging import notify_op_translated_post
from models.kunulo import Kunulo

from . import update_status


def handle(comment, _instruo, komando, ajo) -> None:
    """Command handler called by ziwen_commands()."""
    logger.info("Translated handler initiated.")
    status_type: str = "translated"
    logger.info(f"[ZW] Bot: COMMAND: !{status_type}, from u/{comment.author}.")

    # Handler logic to update the post status.
    update_status(ajo, komando, status_type)

    # Update the Ajo and post.
    logger.info(f"[ZW] Bot: > Marked post `{ajo.id}` as {status_type}.")

    # Delete the claimed and long comments if present
    delete_comments: list[str] = ["comment_long", "comment_claim"]
    kunulo_object: Kunulo = Kunulo.from_submission(ajo.submission)
    for tag in delete_comments:
        kunulo_object.delete(tag)

    # OP has not yet thanked people.
    if not kunulo_object.op_thanks:
        # Message the OP, letting them know that their request has been
        # fulfilled.
        notify_op_translated_post(ajo.author, ajo.submission.permalink)
