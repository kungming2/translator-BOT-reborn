#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
Handles regular functions to keep things tidy.
"""
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Any

import yaml

from config import logger, SETTINGS, Paths
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


def validate_all_yaml_files():
    """
    Scans the given Paths class for all attributes containing YAML file paths
    and validates them.

    :return: True if all YAML files are valid, False otherwise.
    """
    yaml_files = []
    paths_class = Paths

    # Collect all paths ending with .yaml from dictionaries in the Paths class
    for attr_name in dir(paths_class):
        attr_value = getattr(paths_class, attr_name)
        if isinstance(attr_value, dict):
            for key, path in attr_value.items():
                if isinstance(path, str) and path.lower().endswith(".yaml"):
                    yaml_files.append(path)

    if not yaml_files:
        logger.warning("[YAML Validation] No YAML files found in Paths.")
        return True

    logger.info(f"[YAML Validation] Found {len(yaml_files)} YAML files to check.")

    all_valid = True
    for file_path in yaml_files:
        path_obj = Path(file_path)

        if not path_obj.exists():
            logger.error(f"[YAML Validation] File not found: {file_path}")
            all_valid = False
            continue

        try:
            with open(path_obj, "r", encoding="utf-8") as f:
                yaml.safe_load(f)
            logger.debug(f"[YAML Validation] Valid YAML: {file_path}")
        except yaml.YAMLError as e:
            logger.error(f"[YAML Validation] Invalid YAML in {file_path}: {e}")
            all_valid = False
        except Exception as e:
            logger.error(f"[YAML Validation] Error reading {file_path}: {e}")
            all_valid = False

    return all_valid


def clean_processed_database():
    """
    Cleans up the processed comments and posts in the database by
    pruning old entries from the 'old_comments' and 'old_posts' tables,
    keeping only the most recent ones.

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


def ziwen_startup() -> State:
    """
    Group together common activities that need to be run on an occasional basis.
    Usually activated at start-up. This is used in ajo.py.

    :return: A State object containing the current tasks state.
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


STATE = ziwen_startup()


if __name__ == "__main__":
    start_time = time.time()
    print(validate_all_yaml_files())
    print(round(time.time() - start_time, 2))
