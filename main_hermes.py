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
from dataclasses import dataclass

from praw.exceptions import PRAWException

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


@dataclass
class HermesRunStats:
    posts_seen: int = 0
    new_posts: int = 0
    parsed: int = 0
    parse_failed: int = 0
    db_upserts: int = 0
    replies_sent: int = 0
    replies_skipped: int = 0
    expired_pruned: int = 0
    deleted_pruned: int = 0
    verified_posts: int = 0
    raw_candidates: int = 0


# ─── Core routines ────────────────────────────────────────────────────────────


def get_submissions(stats: HermesRunStats | None = None) -> None:
    """
    Fetch the most recent posts from r/Language_Exchange (oldest first),
    store/update author entries, then post match replies where appropriate.
    """
    if stats is None:
        stats = HermesRunStats()

    posts = list(REDDIT_HERMES.subreddit("language_exchange").new(limit=FETCH_AMOUNT))
    posts.reverse()  # Process oldest first for chronological ordering
    stats.posts_seen += len(posts)

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
        stats.new_posts += 1

        # Parse languages from title
        offering, seeking, levels = title_parser(post.title, include_iso_639_3=True)
        logger.info(
            f"Parsed title for `{post.id}`: offering={offering}, "
            f"seeking={seeking}, levels={levels}."
        )

        if not offering and not seeking:
            stats.parse_failed += 1
            logger.info(f"Skipped post `{post.id}`: reason=parse_failed.")
            continue
        if not offering or not seeking:
            missing_side = "offering" if not offering else "seeking"
            logger.info(
                f"Parsed title for `{post.id}` with warning: empty_{missing_side}."
            )
        stats.parsed += 1

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
        stats.db_upserts += 1

        # Respect heavily-commented posts (they don't need the bot)
        if post.num_comments > CUT_OFF_COMMENTS_MIN:
            stats.replies_skipped += 1
            logger.info(
                f"Skipped reply for `{post.id}`: reason=too_many_comments, "
                f"comments={post.num_comments}, threshold={CUT_OFF_COMMENTS_MIN}."
            )
            continue

        # Find and post matches
        greeting = get_language_greeting(offering, seeking)
        match_data = language_matcher(offering, seeking)
        if match_data:
            stats.raw_candidates += len(match_data)
            match_body = format_matches(match_data, REDDIT_HERMES)
            if match_body:
                reply_body = (
                    f"{greeting}I found the following users who may fit your language exchange criteria:\n\n"
                    + match_body
                    + HERMES_BOT_DISCLAIMER
                )
                try:
                    post.reply(reply_body)
                except TRANSIENT_ERRORS:
                    logger.warning(
                        f"Reply result for `{post.id}`: sent=false, error=transient."
                    )
                    raise
                except PRAWException as reply_exc:
                    stats.replies_skipped += 1
                    logger.warning(
                        f"Reply result for `{post.id}`: sent=false, "
                        f"error={type(reply_exc).__name__}: {reply_exc}"
                    )
                else:
                    stats.replies_sent += 1
                    logger.info(f"Reply result for `{post.id}`: sent=true.")
            else:
                stats.replies_skipped += 1
                logger.info(
                    f"Skipped reply for `{post.id}`: reason=no_formatted_matches, "
                    f"raw_candidates={len(match_data)}."
                )
        else:
            stats.replies_skipped += 1
            logger.info(f"Skipped reply for `{post.id}`: reason=no_matches.")


def database_maintenance(stats: HermesRunStats | None = None) -> None:
    """
    Remove entries that have exceeded the 90-day retention window and
    purge entries whose original posts have since been deleted or removed.
    """
    if stats is None:
        stats = HermesRunStats()

    # 1. Prune by age
    pruned_ids = hermes_db.prune_old_entries(CUT_OFF)
    if pruned_ids:
        stats.expired_pruned += len(pruned_ids)

    # 2. Verify remaining posts still exist on Reddit
    entries = hermes_db.get_all_entries()
    if not entries:
        logger.info(
            "Maintenance summary: expired_pruned=%s, deleted_pruned=0, verified=0.",
            stats.expired_pruned,
        )
        return

    full_names = [f"t3_{data['id']}" for _, data, _ in entries if data.get("id")]
    author_by_post: dict[str, str] = {
        data["id"]: username for username, data, _ in entries if data.get("id")
    }

    for i in range(0, len(full_names), 100):
        for submission in REDDIT_HERMES.info(fullnames=full_names[i : i + 100]):
            try:
                author_name = submission.author.name  # raises AttributeError if deleted
                stats.verified_posts += 1
                logger.debug(
                    f"Verified post by u/{author_name} at {submission.permalink}"
                )
            except AttributeError:
                logger.debug(
                    f"Post {submission.id} deleted/removed. Removing from database."
                )
                user_to_delete = author_by_post.get(submission.id)
                if user_to_delete:
                    hermes_db.delete_entry(user_to_delete)
                    stats.deleted_pruned += 1

    logger.info(
        "Maintenance summary: expired_pruned=%s, deleted_pruned=%s, verified=%s.",
        stats.expired_pruned,
        stats.deleted_pruned,
        stats.verified_posts,
    )


# ─── Entry point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    start_time = time.time()
    run_stats = HermesRunStats()

    logger.info(
        f"Hermes cycle start: fetch_limit={FETCH_AMOUNT}, "
        f"reply_cutoff={CUT_OFF_REPLY}, comment_cutoff={CUT_OFF_COMMENTS_MIN}."
    )
    logger.debug(f"Settings: {HERMES_SETTINGS}")

    initialize_hermes_db()

    try:
        database_maintenance(run_stats)
        get_submissions(run_stats)

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
        logger.info(
            "Run complete: "
            f"posts_seen={run_stats.posts_seen}, "
            f"new_posts={run_stats.new_posts}, "
            f"parsed={run_stats.parsed}, "
            f"parse_failed={run_stats.parse_failed}, "
            f"db_upserts={run_stats.db_upserts}, "
            f"replies_sent={run_stats.replies_sent}, "
            f"replies_skipped={run_stats.replies_skipped}, "
            f"expired_pruned={run_stats.expired_pruned}, "
            f"deleted_pruned={run_stats.deleted_pruned}, "
            f"verified={run_stats.verified_posts}, "
            f"raw_candidates={run_stats.raw_candidates}, "
            f"duration={elapsed_time:.2f}m."
        )
        hermes_db.close_all()
