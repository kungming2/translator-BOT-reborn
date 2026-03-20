#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""Simple wrapper for the !verify command, which automatically
will verify someone for a language and change their flair accordingly.
...

Logger tag: [ZW:VERIFY]
"""

import logging

from praw.models import Comment

from config import logger as _base_logger
from models.ajo import Ajo
from models.instruo import Instruo
from models.komando import Komando
from reddit.verification import process_verification

logger = logging.LoggerAdapter(_base_logger, {"tag": "ZW:VERIFY"})


def handle(comment: Comment, _instruo: Instruo, _komando: Komando, _ajo: Ajo) -> None:
    """Command handler called by ziwen_commands()."""

    logger.info(f"!verify, from u/{comment.author}.")

    process_verification(comment)
