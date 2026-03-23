#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
Simple command wrapper for Wikipedia lookup.
...

Logger tag: [ZW:WP]
"""

import logging

from praw.models import Comment

from config import logger as _base_logger
from models.ajo import Ajo
from models.instruo import Instruo
from models.komando import Komando
from reddit.reddit_sender import reddit_reply
from responses import RESPONSE
from ziwen_lookup.wp_utils import wikipedia_lookup

logger = logging.LoggerAdapter(_base_logger, {"tag": "ZW:WP"})


# ─── Command handler ──────────────────────────────────────────────────────────


def handle(comment: Comment, _instruo: Instruo, komando: Komando, _ajo: Ajo) -> None:
    """
    Command handler called by ziwen_commands().
    Example of data:
        Komando(name='lookup_wp', data=['Sanxing (deities)'])]
    """
    logger.info("Wikipedia Lookup handler initiated.")
    logger.info(f"Wikipedia Lookup, from u/{comment.author}.")

    if not komando.data:
        logger.info("> No lookup terms provided. Ignoring.")
        return

    wikipedia_data: str | None = wikipedia_lookup(komando.data)

    if wikipedia_data:
        wikipedia_data += RESPONSE.ANCHOR_WIKIPEDIA
        reddit_reply(comment, wikipedia_data)
        logger.info(f"> Replied to comment `{comment.id}`.")
