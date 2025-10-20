#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
Handles search tasks for frequently requested translations.
"""

import re
from datetime import datetime, timezone
from typing import TYPE_CHECKING

import ddgs

from config import SETTINGS
from connection import REDDIT_HELPER, credentials_source, logger

if TYPE_CHECKING:
    from praw.models import Comment


def fetch_search_reddit_posts(search_term: str) -> list[str]:
    """Extract Reddit post IDs from Reddit/DuckDuckGo search."""
    post_ids = []
    search_engine = SETTINGS["search_engine"]

    if search_engine == "Reddit":
        logger.info(f"Searching Reddit for: {search_term}")

        try:
            # Use Reddit's search directly
            subreddit = REDDIT_HELPER.subreddit(SETTINGS["subreddit"])
            search_results = subreddit.search(search_term, limit=5)

            for submission in search_results:
                post_ids.append(submission.id)
                logger.debug(f"Found post: {submission.title} (ID: {submission.id})")

        except Exception as e:
            logger.error(f"Error during Reddit search: {type(e).__name__}: {e}")

        logger.debug(f"Total post IDs extracted: {len(post_ids)}")
    elif search_engine == "DDG":
        search_query = f"{search_term} site:reddit.com/r/{SETTINGS['subreddit']}"
        logger.info(f"Searching DDG for: {search_term}")

        try:
            searcher = ddgs.DDGS()
            results = list(searcher.text(search_query, max_results=5))
            logger.info(f"Number of URLs returned in DDG results: {len(results)}")

            for i, result in enumerate(results):
                url = result["href"]
                if "comments" in url:
                    logger.debug(f"URL {i + 1} contains 'comments'")
                    match = re.search(r"comments/(.*?)/\w", url)
                    if match:
                        post_id = match.group(1)
                        logger.debug(f"Extracted post ID: {post_id}")
                        post_ids.append(post_id)
                    else:
                        logger.debug(f"Regex did not match for URL {i + 1}")
                else:
                    logger.debug(f"URL {i + 1} does not contain 'comments'")

        except Exception as e:
            logger.error(f"Error during search: {type(e).__name__}: {e}")

        logger.debug(f"Total post IDs extracted: {len(post_ids)}")
        logger.debug(f"Post IDs: {post_ids}")

    return post_ids


def build_search_results(post_ids: list[str], search_term: str) -> str:
    """Build formatted search results from Reddit submissions."""
    result_sections = []

    for post_id in post_ids[:6]:  # Limit to 6 posts to avoid excessive length
        submission = REDDIT_HELPER.submission(id=post_id)
        submission_date = datetime.fromtimestamp(
            submission.created_utc, tz=timezone.utc
        ).strftime("%Y-%m-%d")
        result_sections.append(
            f"**[{submission.title}](https://www.reddit.com{submission.permalink})** ({submission_date})\n"
        )

        # Process comments in submission
        submission.comments.replace_more(limit=None)
        for comment in submission.comments.list():
            formatted_comment = _extract_relevant_comment(comment, search_term)
            if formatted_comment:
                result_sections.append(formatted_comment)

    return "\n\n".join(result_sections)


def _extract_relevant_comment(comment: "Comment", search_term: str) -> str | None:
    """Extract and format a comment if it contains the search term."""
    try:
        comment_author = comment.author.name
    except AttributeError:
        return None  # Author deleted

    if (
        comment_author == credentials_source["USERNAME"]
        or "!search" in comment.body.lower()
    ):
        return None

    # Clean and format comment body
    non_empty_lines = [line for line in comment.body.split("\n") if line]
    quoted_body = "\n> ".join(non_empty_lines)

    if search_term.lower() in quoted_body.lower():
        return f"*Comment by u/{comment_author}* (+{comment.score}):\n\n>{quoted_body}"

    return None


if __name__ == "__main__":
    while True:
        my_search = input("Please enter your search term: ")
        searched_posts = fetch_search_reddit_posts(my_search)
        print(build_search_results(searched_posts, my_search))
