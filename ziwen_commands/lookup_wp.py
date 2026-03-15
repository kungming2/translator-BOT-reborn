#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
Simple command wrapper for Wikipedia lookup.
...

Logger tag: [ZW:WP]
"""

import logging

from config import logger as _base_logger
from reddit.reddit_sender import reddit_reply
from responses import RESPONSE
from ziwen_lookup.wp_utils import wikipedia_lookup

logger = logging.LoggerAdapter(_base_logger, {"tag": "ZW:WP"})


def handle(comment, _instruo, komando, _ajo) -> None:
    """
    Command handler called by ziwen_commands().
    Example of data:
        Komando(name='lookup_wp', data=['Sanxing (deities)'])]
    """
    logger.info("Wikipedia Lookup handler initiated.")
    logger.info(f"Wikipedia Lookup, from u/{comment.author}.")

    wikipedia_data: str | None = wikipedia_lookup(komando.data)

    if wikipedia_data:
        # Add comment anchor.
        wikipedia_data += RESPONSE.ANCHOR_WIKIPEDIA
        reddit_reply(comment, wikipedia_data)
        logger.info(f"> Replied to comment `{comment.id}`.")
