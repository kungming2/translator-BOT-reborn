#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
main_hermes.py — Hermes runtime entry point.

Run from the project root:

    python Hermes/main_hermes.py

Hermes monitors r/Language_Exchange, stores one entry per author, and
replies to new posts with a ranked table of language-exchange partners.

Runtime flow
────────────
1. Initialise the hermes.db tables (no-op if they already exist).
2. Log in to REDDIT_HERMES via the shared connection module.
3. Loop:
   a. database_maintenance() — prune old / deleted entries.
   b. get_submissions()      — process new posts and post matches.

Logger tag: [HM]
"""

import sys
import time
import traceback

from config import TRANSIENT_ERRORS, Paths, get_specific_logger
from error import error_log_basic
from hermes import HERMES_SETTINGS
from hermes.hermes_database import hermes_db, initialize_hermes_db
from hermes.matching import (
    HERMES_BOT_DISCLAIMER,
    format_matches,
    get_language_greeting,
    language_matcher,
    title_parser,
)
from hermes.tools import get_statistics, test_parser
from reddit.connection import REDDIT_HERMES

logger = get_specific_logger("HM", log_path=Paths.HERMES["HERMES_EVENTS"])

# How old a post must be before Hermes will reply
# (avoids pre-empting organic replies by people)
CUT_OFF_REPLY: int = HERMES_SETTINGS["cut_off_reply"]
# Maximum comments already on a post before Hermes skips it
CUT_OFF_COMMENTS_MIN: int = HERMES_SETTINGS["cut_off_comments_min"]
# 90-day retention window
CUT_OFF: int = HERMES_SETTINGS["cut_off"]
# Post fetch limit
FETCH_AMOUNT: int = HERMES_SETTINGS["fetch_limit"]


# ─── Core routines ────────────────────────────────────────────────────────────


def get_submissions() -> None:
    """
    Fetch the most recent posts from r/Language_Exchange (oldest first),
    store/update author entries, then post match replies where appropriate.
    """
    posts = list(REDDIT_HERMES.subreddit("language_exchange").new(limit=FETCH_AMOUNT))
    posts.reverse()  # Process oldest first for chronological ordering

    current_time = time.time()

    for post in posts:
        post_created = int(post.created_utc)

        # Allow time for organic discussion before the bot weighs in
        if current_time - post_created < CUT_OFF_REPLY:
            continue

        # Skip if already processed
        if hermes_db.is_processed(post.id):
            logger.debug(f"Post {post.id} already processed. Skipping.")
            continue

        # Record immediately so a crash/restart doesn't double-process
        hermes_db.mark_processed(post.id, post_created)

        # Skip deleted authors
        try:
            post_author = post.author.name.lower()
        except AttributeError:
            logger.info("> Author deleted. Skipped.")
            continue

        logger.info(f"New post: '{post.title}' by u/{post_author}")

        # Parse languages from title
        offering, seeking, levels = title_parser(post.title, include_iso_639_3=True)

        if not offering and not seeking:
            logger.info("> Could not parse languages from title. Skipped.")
            continue

        user_data = {
            "id": post.id,
            "title": post.title,
            "posted": post_created,
            "offering": offering,
            "seeking": seeking,
            "level": levels,
        }

        # Upsert the author's entry in the database
        hermes_db.upsert_entry(post_author, user_data, post_created)

        # Respect heavily-commented posts (they don't need the bot)
        if len(post.num_comments) > CUT_OFF_COMMENTS_MIN:
            logger.info(
                f">{CUT_OFF_COMMENTS_MIN} comments on post. Skipping match reply."
            )
            continue

        # Find and post matches
        greeting = get_language_greeting(offering, seeking)
        match_data = language_matcher(offering, seeking)
        if match_data:
            match_body = format_matches(match_data, REDDIT_HERMES)
            if match_body:
                reply_body = (
                    f"{greeting}I found the following users who may fit your language exchange criteria:\n\n"
                    + match_body
                    + HERMES_BOT_DISCLAIMER
                )
                post.reply(reply_body)
                logger.info(f"> Replied to u/{post_author}.")


def database_maintenance() -> None:
    """
    Remove entries that have exceeded the 90-day retention window and
    purge entries whose original posts have since been deleted or removed.
    """
    # 1. Prune by age
    pruned_ids = hermes_db.prune_old_entries(CUT_OFF)
    if pruned_ids:
        logger.info(f"Pruned {len(pruned_ids)} expired entries: {pruned_ids}")

    # 2. Verify remaining posts still exist on Reddit
    entries = hermes_db.get_all_entries()
    if not entries:
        return

    full_names = [f"t3_{data['id']}" for _, data, _ in entries if data.get("id")]
    author_by_post: dict[str, str] = {
        data["id"]: username for username, data, _ in entries if data.get("id")
    }

    for i in range(0, len(full_names), 100):
        for submission in REDDIT_HERMES.info(fullnames=full_names[i:i + 100]):
            try:
                author_name = submission.author.name  # raises AttributeError if deleted
                logger.debug(f"Verified post by u/{author_name} at {submission.permalink}")
            except AttributeError:
                logger.info(
                    f"Post {submission.id} deleted/removed. Removing from database."
                )
                user_to_delete = author_by_post.get(submission.id)
                if user_to_delete:
                    hermes_db.delete_entry(user_to_delete)


# ─── Entry point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    start_time = time.time()

    logger.info("Hermes starting up. Logged in...")
    logger.debug(f"Settings: {HERMES_SETTINGS}")

    initialize_hermes_db()

    if "--test" in sys.argv:
        # Parse the optional numeric argument after --test
        idx = sys.argv.index("--test")
        try:
            test_limit = int(sys.argv[idx + 1])
        except (IndexError, ValueError):
            test_limit = 100
        logger.info(f"Running in parser test mode (limit={test_limit}).")
        test_parser(REDDIT_HERMES, test_limit)

    elif len(sys.argv) > 1:
        logger.info("Running in statistics mode.")
        get_statistics()

    else:
        try:
            database_maintenance()
            get_submissions()

        except KeyboardInterrupt:
            logger.info("Hermes stopped by user (KeyboardInterrupt).")
            sys.exit(0)

        except TRANSIENT_ERRORS as e:
            logger.warning(f"Transient error encountered: {type(e).__name__}: {e}")
            logger.info("Will retry on next cycle.")

        except Exception as exc:
            entry = f"### {exc}\n\n{traceback.format_exc()}"
            logger.critical(entry)
            error_log_basic(entry, "Hermes")

        finally:
            elapsed_time = round((time.time() - start_time) / 60, 2)
            logger.info(f"Run {elapsed_time:.2f} minutes.")
            hermes_db.close_all()
