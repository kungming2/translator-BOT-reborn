#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
Main script to fetch posts and act upon them.
"""
import time

from config import logger, SETTINGS
from connection import REDDIT
from database import db
from models import ajo
from models.ajo import ajo_loader


def ziwen_posts():
    """
    The main top-level post filtering runtime for r/translator.
    It removes posts that do not meet the subreddit's guidelines.
    It also assigns flair to posts, saves them as Ajos, and determines
    what to pass to the notification system.

    :return: Nothing.
    """
    subreddit_object = REDDIT.subreddit(SETTINGS['subreddit'])
    fetch_amount = SETTINGS['max_posts']

    current_time = int(time.time())  # This is the current time.
    logger.debug(f'[ZW] Fetching new r/{subreddit_object} posts at {current_time}.')
    posts = []

    # We get the last X new posts.
    posts += list(subreddit_object.new(limit=fetch_amount))
    posts.reverse()  # Reverse it so that we start processing the older ones first. Newest ones last.

    for post in posts:
        # Anything that needs to happen every loop goes here.
        post_ajo = None
        post_id = post.id

        try:
            post_author = post.author.name
        except AttributeError:
            # Author is deleted. We skip.
            logger.debug(f"> u/{post.author} does not exist.")
            continue

        # Skip if post has already been processed
        if db.cursor_main.execute('SELECT 1 FROM old_posts WHERE ID = ?', (post_id,)).fetchone():
            logger.debug(f"[ZW] Posts: This post {post_id} already exists in the processed database.")

            # Try to load the associated Ajo object
            post_ajo = ajo_loader(post_id)
            if post_ajo:
                logger.debug(f"[ZW] Posts: Loaded existing Ajo for post {post_id}.")
            else:
                logger.warning(f"[ZW] Posts: Post {post_id} is in `old_posts` database but has no Ajo stored.")
            continue

        # TODO load ajo here

        # Mark post as processed
        db.cursor_main.execute('INSERT INTO old_posts (ID) VALUES (?)', (post_id,))
        db.conn_main.commit()

        # Check on ajo status. We only want to deal with untranslated new posts.
        if post_ajo is not None and post_ajo.status in ["translated", "doublecheck", "missing", "inprogress"]:
            logger.info(f"[ZW] Posts: Skipping post {post_id} because status is '{post_ajo.status}'.")
            continue
