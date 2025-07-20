#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
Handles regular functions to keep things tidy.
"""
import time
from dataclasses import dataclass
from typing import Dict, Any


from config import logger, SETTINGS
from connection import REDDIT, credentials_source
from database import db
from points import points_worth_cacher


@dataclass
class State:
    """A simple state container for Ziwen constants that are called
    upon startup."""
    post_templates: Dict[str, Any]
    recent_submitters: list


def template_retriever():
    """
    Retrieve the current link flair templates on r/translator.

    :return: A dictionary keyed by preferred codes with template IDs as values.
             Returns an empty dictionary if no templates are found.
    """
    return {
        template["css_class"]: template["id"]
        for template in REDDIT.subreddit('translator').flair.link_templates
        if template.get("css_class") and template.get("id")
    }


def most_recent_submitters():
    """
    Return a list of usernames who submitted to r/translator in the
    last 24 hours.

    Ignores deleted users and the bot account.
    """
    cutoff = time.time() - 86400
    return [
        post.author.name
        for post in REDDIT.subreddit("translator").new(limit=100)
        if post.created_utc > cutoff
        and post.author
        and post.author.name != credentials_source['USERNAME']
    ]


def clean_processed_database():
    """
    Cleans up the processed comments and posts in the database by pruning
    old entries from the 'old_comments' and 'old_posts' tables, keeping only the most recent.
    # TODO to be called by the upcoming Wenju rewrite
    :return: None
    """
    max_posts = SETTINGS["max_posts"]

    cursor = db.cursor_main

    # Clean old_comments
    logger.info("Starting cleanup of 'old_comments' table...")
    query_comments = '''
        DELETE FROM old_comments
        WHERE id NOT IN (
            SELECT id FROM old_comments ORDER BY id DESC LIMIT ?
        )
    '''
    cursor.execute(query_comments, (max_posts * 10,))
    logger.info(f"Cleanup complete. Kept latest {max_posts * 10} entries in 'old_comments'.")

    # Clean old_posts
    logger.info("Starting cleanup of 'old_posts' table...")
    query_posts = '''
        DELETE FROM old_posts
        WHERE id NOT IN (
            SELECT id FROM old_posts ORDER BY id DESC LIMIT ?
        )
    '''
    cursor.execute(query_posts, (max_posts * 10,))
    logger.info(f"Cleanup complete. Kept latest {max_posts * 10} entries in 'old_posts'.")

    # Commit once after both operations
    db.conn_main.commit()


def ziwen_maintenance() -> State:
    """
    Group together common activities that need to be run on an occasional basis.
    Usually activated at start-up.

    :return: A State object containing the current maintenance state.
    """
    post_templates = template_retriever()
    logger.debug("[ZW] # Current post templates retrieved: %d templates", len(post_templates))

    recent_submitters = most_recent_submitters()

    points_worth_cacher()  # Does not return anything.
    logger.debug("[ZW] # Points cache updated.")

    return State(
        post_templates=post_templates,
        recent_submitters=recent_submitters
    )


STATE = ziwen_maintenance()


if __name__ == "__main__":
    start_time = time.time()
    print(ziwen_maintenance())
    print(round(time.time() - start_time, 2))
