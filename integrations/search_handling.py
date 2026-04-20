#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
Handles search tasks for frequently requested translations.
...

Logger tag: [I:SEARCH]
"""

from __future__ import annotations

# ─── Imports ──────────────────────────────────────────────────────────────────
import logging
import re
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import ddgs

from config import SETTINGS
from config import logger as _base_logger
from reddit.connection import REDDIT_HELPER, credentials_source

if TYPE_CHECKING:
    from praw.models import Comment

# ─── Module-level constants ───────────────────────────────────────────────────

logger = logging.LoggerAdapter(_base_logger, {"tag": "I:SEARCH"})


# ─── Post ID retrieval ────────────────────────────────────────────────────────


def _search_reddit_native(search_term: str) -> list[str]:
    """
    Search the configured subreddit via Reddit's own search API and return
    a list of matching post IDs.
    """
    post_ids: list[str] = []
    logger.info(f"Searching Reddit for: {search_term}")

    try:
        subreddit = REDDIT_HELPER.subreddit(SETTINGS["subreddit"])
        for submission in subreddit.search(search_term, limit=5):
            post_ids.append(submission.id)
            logger.debug(f"Found post: {submission.title} (ID: {submission.id})")
    except Exception as e:
        logger.error(f"Error during Reddit search: {type(e).__name__}: {e}")

    logger.debug(f"Total post IDs extracted: {len(post_ids)}")
    return post_ids


def _search_ddg(search_term: str) -> list[str]:
    """
    Search via DuckDuckGo restricted to the configured subreddit and return
    a list of post IDs extracted from result URLs.
    """
    post_ids: list[str] = []
    search_query = f"{search_term} site:reddit.com/r/{SETTINGS['subreddit']}"
    logger.info(f"Searching DDG for: {search_term}")

    try:
        results = list(ddgs.DDGS().text(search_query, max_results=5))
        logger.info(f"Number of URLs returned in DDG results: {len(results)}")

        for i, result in enumerate(results):
            url = result["href"]
            if "comments" not in url:
                logger.debug(f"URL {i + 1} does not contain 'comments'")
                continue

            logger.debug(f"URL {i + 1} contains 'comments'")
            match = re.search(r"comments/(.*?)/\w", url)
            if match:
                post_id = match.group(1)
                logger.debug(f"Extracted post ID: {post_id}")
                post_ids.append(post_id)
            else:
                logger.debug(f"Regex did not match for URL {i + 1}")

    except Exception as e:
        logger.error(f"Error during search: {type(e).__name__}: {e}")

    logger.debug(f"Total post IDs extracted: {len(post_ids)}")
    logger.debug(f"Post IDs: {post_ids}")
    return post_ids


def fetch_search_reddit_posts(search_term: str) -> list[str]:
    """
    Extract Reddit post IDs matching *search_term* using whichever search
    engine is configured in settings (``"Reddit"`` or ``"DDG"``).

    :param search_term: The term to search for.
    :return: List of Reddit post ID strings.
    """
    search_engine = SETTINGS["search_engine"]

    if search_engine == "Reddit":
        return _search_reddit_native(search_term)
    elif search_engine == "DDG":
        return _search_ddg(search_term)

    logger.warning(
        f"Unknown search engine configured: {search_engine!r}. Returning []."
    )
    return []


# ─── Comment filtering ────────────────────────────────────────────────────────


def _extract_relevant_comment(comment: Comment, search_term: str) -> str | None:
    """
    Return a formatted Markdown block for *comment* if it contains
    *search_term*, or None if it should be skipped.
    """
    try:
        comment_author = comment.author.name
    except AttributeError:
        logger.debug(f"Skipping comment {comment.id} — author deleted.")
        return None

    if (
        comment_author == credentials_source["USERNAME"]
        or "!search" in comment.body.lower()
    ):
        return None

    non_empty_lines = [line for line in comment.body.split("\n") if line]
    quoted_body = "\n> ".join(non_empty_lines)

    if search_term.lower() not in quoted_body.lower():
        return None

    return f"*Comment by u/{comment_author}* (+{comment.score}):\n\n>{quoted_body}"


# ─── Result formatting ────────────────────────────────────────────────────────


def build_search_results(post_ids: list[str], search_term: str) -> str:
    """
    Build a formatted Markdown string of search results from a list of
    Reddit post IDs, including any comments that contain *search_term*.

    :param post_ids: List of Reddit submission IDs to process.
    :param search_term: The original search term (used for comment filtering).
    :return: Markdown-formatted results string.
    """
    result_sections: list[str] = []
    logger.info(
        f"Building search results for {len(post_ids)} post(s), term: {search_term!r}."
    )

    for post_id in post_ids[:6]:  # Cap at 6 posts to avoid excessive length.
        submission = REDDIT_HELPER.submission(id=post_id)
        submission_date = datetime.fromtimestamp(
            submission.created_utc, tz=UTC
        ).strftime("%Y-%m-%d")

        result_sections.append(
            f"**[{submission.title}]"
            f"(https://www.reddit.com{submission.permalink})** "
            f"({submission_date})\n"
        )

        submission.comments.replace_more(limit=None)
        for comment in submission.comments.list():
            formatted = _extract_relevant_comment(comment, search_term)
            if formatted:
                result_sections.append(formatted)

    return "\n\n".join(result_sections)
