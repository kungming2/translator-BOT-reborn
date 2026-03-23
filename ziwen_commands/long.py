#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
This handles the !long command, which toggles a post as being marked
quite long for translators. This command can be used by the original
poster of a submission or mods.
...

Logger tag: [ZW:LONG]
"""

import logging

from praw.models import Comment

from config import logger as _base_logger
from models.ajo import Ajo
from models.instruo import Instruo
from models.komando import Komando
from models.kunulo import Kunulo
from reddit.connection import is_mod

logger = logging.LoggerAdapter(_base_logger, {"tag": "ZW:LONG"})


# ─── Command handler ──────────────────────────────────────────────────────────


def handle(comment: Comment, _instruo: Instruo, _komando: Komando, ajo: Ajo) -> None:
    """Command handler called by ziwen_commands()."""
    logger.info("Long handler initiated.")

    original_poster = comment.submission.author

    if is_mod(comment.author) or original_poster == comment.author:
        logger.info(f"!long, from user u/{comment.author} on `{ajo.id}`.")

        # Toggle the long state.
        current_status: bool = ajo.is_long
        new_status: bool = not current_status

        # If toggled off, delete any existing long informational comment.
        if not new_status:
            kunulo_object: Kunulo = Kunulo.from_submission(ajo.submission)
            kunulo_object.delete("comment_long")

        ajo.set_is_long(new_status)
        logger.info(f"Changed post `{ajo.id}`'s long state to '{new_status}.'")
