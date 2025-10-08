#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
Handler for the !search command, which looks for strings in other posts
on r/translator and can also handle frequently requested translation
lookups.
"""
import datetime

from config import logger
from connection import REDDIT_HELPER, credentials_source
from models.instruo import Instruo
from reddit_sender import message_reply
from responses import RESPONSE
from wiki import search_integration


def _extract_reddit_post_ids(search_term):
    """Extract Reddit post IDs from Reddit search.
    Note this has temporarily been changed from Google search;
    that may be changed back post-deployment."""
    post_ids = []

    print(f"DEBUG: Searching Reddit for: {search_term}")

    try:
        # Use Reddit's search directly
        subreddit = REDDIT_HELPER.subreddit('translator')
        search_results = subreddit.search(search_term, limit=5)

        for submission in search_results:
            post_ids.append(submission.id)
            print(f"DEBUG: Found post: {submission.title} (ID: {submission.id})")

    except Exception as e:
        print(f"DEBUG: Error during Reddit search: {type(e).__name__}: {e}")

    print(f"DEBUG: Total post IDs extracted: {len(post_ids)}")
    return post_ids


def _build_search_results(post_ids, search_term):
    """Build formatted search results from Reddit submissions."""
    result_sections = []

    for post_id in post_ids[:6]:  # Limit to 6 posts to avoid excessive length
        submission = REDDIT_HELPER.submission(id=post_id)
        submission_date = datetime.datetime.fromtimestamp(submission.created_utc).strftime('%Y-%m-%d')
        result_sections.append(f"**[{submission.title}]({submission.permalink})** ({submission_date})\n")

        # Process comments in submission
        submission.comments.replace_more(limit=None)
        for comment in submission.comments.list():
            formatted_comment = _extract_relevant_comment(comment, search_term)
            if formatted_comment:
                result_sections.append(formatted_comment)

    return '\n\n'.join(result_sections)


def _extract_relevant_comment(comment, search_term):
    """Extract and format a comment if it contains the search term."""
    try:
        comment_author = comment.author.name
    except AttributeError:
        return None  # Author deleted

    if comment_author == credentials_source['USERNAME'] or '!search' in comment.body.lower():
        return None

    # Clean and format comment body
    non_empty_lines = [line for line in comment.body.split("\n") if line]
    quoted_body = "\n> ".join(non_empty_lines)

    if search_term.lower() in quoted_body.lower():
        return f"*Comment by u/{comment_author}* (+{comment.score}):\n\n>{quoted_body}"

    return None


def handle(comment, _instruo, komando, _ajo):
    """Sample input: [Komando(name='search', data=['allergy'])]"""
    logger.info("Search handler initiated.")
    search_terms = komando.data  # This is a list of strings

    # Join search terms into a single query string
    search_query = ' '.join(search_terms)

    # Check for frequently-translated text and return advisories first
    frequently_translated_info = search_integration(search_query)
    if frequently_translated_info and 'Advisory' in frequently_translated_info:
        message_reply(comment, frequently_translated_info + RESPONSE.BOT_DISCLAIMER)
        return

    # Fetch Google search results for r/translator
    post_ids = _extract_reddit_post_ids(search_query)
    if not post_ids:
        logger.info(f"[ZW] Bot: > No results found for '{search_query}'.")
        return

    logger.info(f"[ZW] Bot: > Results found for '{search_query}'...")

    # Build reply from Reddit submissions
    search_results_body = _build_search_results(post_ids, search_query)

    # Format final reply with optional frequently-translated information
    results_header = f'## Search results on r/translator for "{search_query}":\n\n'
    full_reply = (f"{frequently_translated_info}\n\n{results_header}{search_results_body}"
                  if frequently_translated_info else f"{results_header}{search_results_body}")
    message_reply(comment, full_reply + RESPONSE.BOT_DISCLAIMER)


if '__main__' == __name__:
    while True:
        # Get comment URL from user
        comment_url = input("Enter Reddit comment URL (or 'quit' to exit): ").strip()

        # Check for exit
        if comment_url.lower() in ['quit', 'exit', 'q']:
            break

        # Get comment from URL and process
        test_comment = REDDIT_HELPER.comment(url=comment_url)
        test_instruo = Instruo.from_comment(test_comment)
        print(f"Instruo created: {test_instruo}\n")
        print(handle(test_comment, test_instruo, test_instruo.commands[0], None))
