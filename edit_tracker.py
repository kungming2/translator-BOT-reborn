#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
Tracks changes in comments' edits. This works by caching comments and

"""
import time

from praw import models
from wasabi import msg

from config import logger, SETTINGS
from connection import REDDIT, REDDIT_HELPER
from database import db
from models.ajo import ajo_writer, ajo_loader
from models.instruo import comment_has_command


def should_process_comment(comment):
    """Skip comments that are too old and unedited.
    The limit is defined in settings in hours."""
    time_diff = time.time() - comment.created_utc
    age_in_seconds = SETTINGS['comment_edit_age_max'] * 3600

    return not time_diff > age_in_seconds


def get_cached_comment(comment_id):
    """Retrieve comment text from cache."""
    cursor = db.cursor_cache
    cursor.execute("SELECT content FROM comment_cache WHERE id = ?", (comment_id,))
    result = cursor.fetchone()
    return result[0] if result else None  # Just the body text, or None


def update_comment_cache(comment_id, comment_body):
    """Replace old comment text with new version."""
    cursor = db.cursor_cache
    cursor.execute("DELETE FROM comment_cache WHERE id = ?", (comment_id,))
    cursor.execute("INSERT INTO comment_cache VALUES (?, ?)", (comment_id, comment_body))
    db.conn_cache.commit()


def remove_from_processed(comment_id):
    """Force a reprocess by removing from the processed comment database."""
    cursor = db.cursor_main
    cursor.execute("DELETE FROM old_comments WHERE id = ?", (comment_id,))
    db.conn_main.commit()
    logger.debug(f"[ZW] Edit Tracker: Removed comment '{comment_id}' from processed database.")


def cleanup_comment_cache(limit):
    """Remove oldest entries beyond comment limit."""
    cursor = db.cursor_cache
    cleanup = '''
        DELETE FROM comment_cache 
        WHERE id NOT IN (
            SELECT id FROM comment_cache ORDER BY id DESC LIMIT ?
        )
    '''
    cursor.execute(cleanup, (limit,))
    db.conn_cache.commit()
    logger.debug("[ZW] Edit Finder: Cleaned up the edited comments cache.")


def edit_tracker():
    """
    Detects edited r/translator comments that involve commands or
    lookup items.
    If a meaningful change is detected, the comment is removed from the
    processed database for reprocessing.
    """
    # Phase 1: Iterate over comments.
    total_fetch_num = SETTINGS['comment_edit_num_limit'] * 2
    total_keep_num = total_fetch_num * 5
    for comment in REDDIT_HELPER.subreddit("translator").comments(limit=total_fetch_num):

        # Comment is beyond our time span for monitoring.
        if not should_process_comment(comment):
            continue

        comment_id = comment.id
        comment_body = comment.body.strip()

        # Check against the pre-existing cache.
        cached = get_cached_comment(comment_id)

        # If not in cache, insert it
        if not cached:
            update_comment_cache(comment_id, comment_body)
            continue

    # Phase 2: Fetch only the edited comments from the subreddit.
    for item in REDDIT.subreddit("translator").mod.edited(limit=SETTINGS['comment_edit_num_limit']):

        # Skip submissions, keep only comments
        if isinstance(item, models.Submission):
            continue

        comment_id = item.id
        new_body = item.body.strip()

        if not should_process_comment(item):
            continue

        if not comment_has_command(item):
            continue

        # Fetch the old stored information.
        cached = get_cached_comment(comment_id)
        old_body = cached if cached else ""
        if old_body == new_body:
            logger.debug('The comment stored is the same.')
            continue

        # Compare command relevance between old and new versions
        old_had_command = comment_has_command(old_body) if old_body else False
        new_has_command = comment_has_command(item)

        if new_has_command and not old_had_command:
            logger.info(f"[Edit_Tracker] Reprocessing triggered: "
                        f"{comment_id} at https://www.reddit.com{item.permalink}")
            remove_from_processed(comment_id)  # This function must be defined

        # Update the cache.
        update_comment_cache(comment_id, new_body)

    # Phase 3: Cache cleanup
    cleanup_comment_cache(total_keep_num)


def progress_checker():
    """
    Checks Reddit for posts marked as "In Progress" and determines
    if their claim period has expired. If expired, resets them to the 'Untranslated' state.
    TODO when Ajos are done
    """
    search_results = r.search('flair:"in progress"', time_filter='month', sort='new')

    for post in search_results:
        if post.link_flair_css_class != 'inprogress':  # TODO change this to Ajo
            continue  # Skip posts without the correct flair

        post_id = post.id
        permalink = post.permalink

        # Load Ajo object from local cache or create from Reddit
        ajo = ajo_loader(post_id)
        if ajo is None:
            logger.debug("[ZW] progress_checker: Couldn't find Ajo in local database. Loading from Reddit.")
            ajo = Ajo(post)

        komento_data = komento_analyzer(post)
        time_diff = komento_data.get('claim_time_diff')

        # Skip if there's no claim time data
        if time_diff is None or time_diff <= CLAIM_PERIOD:
            continue

        # Claim expired: remove claim comment and reset post
        try:
            REDDIT.comment(id=komento_data['bot_claim_comment']).delete()
        except Exception as e:
            logger.warning(f"[ZW] progress_checker: Failed to delete claim comment for {permalink}: {e}")

        logger.info(f"[ZW] progress_checker: Post exceeded claim period. Resetting. {permalink}")
        ajo.set_status('untranslated')
        ajo.update_reddit()
        ajo_writer(ajo)


if __name__ == "__main__":
    start_time = time.time()
    with msg.loading("Running Edit Tracker..."):
        edit_tracker()
    msg.info(f"Finished. {round(time.time() - start_time, 2)} seconds elapsed.")
