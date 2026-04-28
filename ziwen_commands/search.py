#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
Handler for the !search command, which looks for strings in other posts
on r/translator and can also handle frequently requested translation
lookups.
...

Logger tag: [ZW:SEARCH]
"""

import logging

from praw.models import Comment

from config import logger as _base_logger
from integrations.search_handling import build_search_results, fetch_search_reddit_posts
from models.ajo import Ajo
from models.instruo import Instruo
from models.komando import Komando
from reddit.reddit_sender import reddit_reply
from reddit.wiki import search_integration
from responses import RESPONSE

logger = logging.LoggerAdapter(_base_logger, {"tag": "ZW:SEARCH"})


# ─── Command handler ──────────────────────────────────────────────────────────


def handle(comment: Comment, _instruo: Instruo, komando: Komando, _ajo: Ajo) -> None:
    """
    Command handler called by ziwen_commands().
    Example data:
        [Komando(name='search', data=['allergy'])]
    """
    logger.info("Search handler initiated.")
    if not komando.data:
        logger.info("> No search terms provided. Ignoring.")
        return

    search_terms: list[str] = komando.data
    search_query = " ".join(search_terms)

    # Return FRT advisories immediately if one matches.
    frequently_translated_info: str | None = search_integration(search_query)
    if frequently_translated_info and "Advisory" in frequently_translated_info:
        reddit_reply(comment, frequently_translated_info + RESPONSE.BOT_DISCLAIMER)
        return

    post_ids = fetch_search_reddit_posts(search_query)
    if not post_ids:
        logger.info(f"> No results found for '{search_query}'.")
        return

    logger.info(f"> Results found for '{search_query}'...")

    search_results_body: str = build_search_results(post_ids, search_query)

    results_header: str = RESPONSE.COMMENT_SEARCH_RESULTS_HEADER.format(
        search_query=search_query
    )
    results_header += "\n\n"
    full_reply: str = (
        f"{frequently_translated_info}\n\n{results_header}{search_results_body}"
        if frequently_translated_info
        else f"{results_header}{search_results_body}"
    )
    reddit_reply(comment, full_reply + RESPONSE.BOT_DISCLAIMER)
