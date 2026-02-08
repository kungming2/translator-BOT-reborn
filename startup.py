#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
Initializes Ziwen's runtime state and caches key data on startup.
"""

import time
from dataclasses import dataclass
from typing import Any

from config import logger, SETTINGS
from connection import REDDIT, USERNAME
from tasks.data_maintenance import points_worth_cacher


@dataclass
class State:
    """A simple state container for Ziwen constants that are called
    upon startup."""

    post_templates: dict[str, Any]
    recent_submitters: list[str]


def template_retriever() -> dict[str, str]:
    """
    Retrieve the current link flair templates on r/translator.

    :return: A dictionary keyed by preferred codes with template IDs as values.
             Returns an empty dictionary if no templates are found.
    """
    return {
        template["css_class"]: template["id"]
        for template in REDDIT.subreddit(SETTINGS["subreddit"]).flair.link_templates
        if template.get("css_class") and template.get("id")
    }


def most_recent_submitters() -> list[str]:
    """
    Return a list of usernames who submitted to r/translator in the
    last 24 hours.

    Ignores deleted users and the bot account.
    """
    cutoff: float = time.time() - 86400
    return [
        post.author.name
        for post in REDDIT.subreddit(SETTINGS["subreddit"]).new(limit=100)
        if post.created_utc > cutoff and post.author and post.author.name != USERNAME
    ]


def ziwen_startup() -> State:
    """
    Group together common activities that need to be run on an occasional basis.
    Usually activated at start-up. This is used in ajo.py.

    :return: A State object containing the current tasks state.
    """
    post_templates: dict[str, str] = template_retriever()
    logger.debug(
        "[ZW] # Current post templates retrieved: %d templates", len(post_templates)
    )

    recent_submitters: list[str] = most_recent_submitters()

    # Does not return anything. Run just to make sure there's data in
    # the points cache.
    points_worth_cacher()
    logger.debug("[ZW] # Points cache updated.")

    return State(post_templates=post_templates, recent_submitters=recent_submitters)


STATE: State = ziwen_startup()


if __name__ == "__main__":
    start_time = time.time()
    print(template_retriever())
    print(round(time.time() - start_time, 2))
