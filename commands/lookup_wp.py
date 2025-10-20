#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""Simple command wrapper for Wikipedia lookup."""

from config import logger
from lookup.wp_utils import wikipedia_lookup
from reddit_sender import comment_reply
from responses import RESPONSE


def handle(comment, _instruo, komando, _ajo) -> None:
    """
    Command handler called by ziwen_commands().
    Example of data:
        Komando(name='wikipedia_lookup', data=['Sanxing (deities)'])]
    """
    logger.info("Wikipedia Lookup handler initiated.")
    logger.info(f"[ZW] Bot: COMMAND: Wikipedia Lookup, from u/{comment.author}.")

    wikipedia_data: str | None = wikipedia_lookup(komando.data)

    if wikipedia_data:
        # Add comment anchor.
        wikipedia_data += RESPONSE.ANCHOR_WIKIPEDIA
        comment_reply(comment, wikipedia_data)
        logger.info(f"[ZW] Bot: COMMAND: Replied to comment `{comment.id}`.")
