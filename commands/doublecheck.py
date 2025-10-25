#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
Allows posts to be set as "Needs Review".
This is generally used when asking for reviews of one's work.
"""

from praw.models import Comment

from config import logger
from models.kunulo import Kunulo

from . import update_status


def handle(comment: Comment, _instruo, komando, ajo) -> None:
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
    logger.info(f"[ZW] Bot: COMMAND: !{status_type}, from u/{comment.author}.")

    # Handler logic to update the post status.
    update_status(ajo, komando, status_type)

    # Update the Ajo and post.
    logger.info(
        f"[ZW] Bot: > Marked post `{ajo.id}` as 'Needs Review.' (`{status_type}`)"
    )

    # Delete any previously claimed comment.
    kunulo_object: Kunulo = Kunulo.from_submission(ajo.submission)
    kunulo_object.delete("comment_claim")
