#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""Simple command wrapper for Wikipedia lookup."""
from config import logger
from lookup.wp_utils import wikipedia_lookup
from reddit_sender import comment_reply


def handle(comment, _instruo, komando, _ajo):
    """Example:
    Komando(name='wikipedia_lookup', data=['Sanxing (deities)'])]
    """
    logger.info("Wikipedia Lookup handler initiated.")
    logger.info(f"[ZW] Bot: COMMAND: Wikipedia Lookup, from u/{comment.author}.")

    wikipedia_data = wikipedia_lookup(komando.data)

    if wikipedia_data:
        comment_reply(comment, wikipedia_data)
        logger.info(f"[ZW] Bot: COMMAND: Replied to comment `{comment.id}`.")

    return
