#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
Handler for the !search command, which looks for strings in other posts
on r/translator and can also handle frequently requested translation
lookups.
"""

from config import logger
from connection import REDDIT_HELPER
from models.instruo import Instruo
from reddit_sender import message_reply
from responses import RESPONSE
from search_handling import fetch_search_reddit_posts, build_search_results
from wiki import search_integration


def handle(comment, _instruo, komando, _ajo):
    """Sample input: [Komando(name='search', data=['allergy'])]"""
    logger.info("Search handler initiated.")
    search_terms = komando.data  # This is a list of strings

    # Join search terms into a single query string
    search_query = " ".join(search_terms)

    # Check for frequently-translated text and return advisories first
    frequently_translated_info = search_integration(search_query)
    if frequently_translated_info and "Advisory" in frequently_translated_info:
        message_reply(comment, frequently_translated_info + RESPONSE.BOT_DISCLAIMER)
        return

    # Fetch Google search results for r/translator
    post_ids = fetch_search_reddit_posts(search_query)
    if not post_ids:
        logger.info(f"[ZW] Bot: > No results found for '{search_query}'.")
        return

    logger.info(f"[ZW] Bot: > Results found for '{search_query}'...")

    # Build reply from Reddit submissions
    search_results_body = build_search_results(post_ids, search_query)

    # Format final reply with optional frequently-translated information
    results_header = f'## Search results on r/translator for "{search_query}":\n\n'
    full_reply = (
        f"{frequently_translated_info}\n\n{results_header}{search_results_body}"
        if frequently_translated_info
        else f"{results_header}{search_results_body}"
    )
    message_reply(comment, full_reply + RESPONSE.BOT_DISCLAIMER)


if "__main__" == __name__:
    while True:
        # Get comment URL from user
        comment_url = input("Enter Reddit comment URL (or 'quit' to exit): ").strip()

        # Check for exit
        if comment_url.lower() in ["quit", "exit", "q"]:
            break

        # Get comment from URL and process
        test_comment = REDDIT_HELPER.comment(url=comment_url)
        test_instruo = Instruo.from_comment(test_comment)
        print(f"Instruo created: {test_instruo}\n")
        print(handle(test_comment, test_instruo, test_instruo.commands[0], None))
