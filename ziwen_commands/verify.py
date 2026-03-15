#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""Simple wrapper for the !verify command, which automatically
will verify someone for a language and change their flair accordingly.
...

Logger tag: [ZW:VERIFY]
"""

import logging

from config import logger as _base_logger
from reddit.verification import process_verification

logger = logging.LoggerAdapter(_base_logger, {"tag": "ZW:VERIFY"})


def handle(comment, _instruo, _komando, _ajo) -> None:
    """Command handler called by ziwen_commands()."""

    logger.info(f"!verify, from u/{comment.author}.")

    process_verification(comment)
