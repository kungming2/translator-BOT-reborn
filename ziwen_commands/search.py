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

from config import logger as _base_logger
from integrations.search_handling import build_search_results, fetch_search_reddit_posts
from reddit.reddit_sender import reddit_reply
from reddit.wiki import search_integration
from responses import RESPONSE

logger = logging.LoggerAdapter(_base_logger, {"tag": "ZW:SEARCH"})


def handle(comment, _instruo, komando, _ajo) -> None:
    """
    Command handler called by ziwen_commands().
    Example data:
        [Komando(name='search', data=['allergy'])]"""

    logger.info("Search handler initiated.")
    search_terms: list[str] = komando.data  # This is a list of strings

    # Join search terms into a single query string
    search_query = " ".join(search_terms)

    # Check for frequently-translated text and return advisories first
    frequently_translated_info: str | None = search_integration(search_query)
    if frequently_translated_info and "Advisory" in frequently_translated_info:
        reddit_reply(comment, frequently_translated_info + RESPONSE.BOT_DISCLAIMER)
        return

    # Fetch Google search results for r/translator
    post_ids = fetch_search_reddit_posts(search_query)
    if not post_ids:
        logger.info(f"> No results found for '{search_query}'.")
        return

    logger.info(f"> Results found for '{search_query}'...")

    # Build reply from Reddit submissions
    search_results_body: str = build_search_results(post_ids, search_query)

    # Format final reply with optional frequently-translated information
    results_header: str = f'## Search results on r/translator for "{search_query}":\n\n'
    full_reply: str = (
        f"{frequently_translated_info}\n\n{results_header}{search_results_body}"
        if frequently_translated_info
        else f"{results_header}{search_results_body}"
    )
    reddit_reply(comment, full_reply + RESPONSE.BOT_DISCLAIMER)
