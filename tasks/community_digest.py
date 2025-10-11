#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
import json
import time
from datetime import date, datetime

from config import logger
from connection import REDDIT
from database import db
from main_wenju import task
from notifications import notifier_internal
from responses import RESPONSE


@task(schedule='daily')
def send_internal_post_digest():
    """
    Check for new posts in the last 24 hours and send
    notifications for unprocessed ones.
    """
    # Calculate timestamp for 24 hours ago
    cutoff_time = int(time.time()) - (24 * 60 * 60)

    # Fetch all posts from the last 24 hours
    query = """
        SELECT id, created_utc, content 
        FROM internal_posts 
        WHERE created_utc >= ?
    """
    posts = db.fetchall_main(query, (cutoff_time,))

    for post in posts:
        post_id = post['id']
        content_str = post['content']

        # Parse the content JSON
        try:
            content = json.loads(content_str)
        except json.JSONDecodeError:
            logger.warning(f"Warning: Could not parse content for post {post_id}")
            continue

        # Skip if already processed
        if content.get('processed', False):
            continue

        # Get the post_type and submission ID
        post_type = content.get('post_type')
        submission_id = content.get('id')

        if not post_type or not submission_id:
            logger.warning(f"Warning: Missing post_type or id for post {post_id}")
            continue

        # Get the Reddit submission object
        try:
            submission = REDDIT.submission(id=submission_id)
        except Exception as e:
            logger.error(f"Error fetching submission {submission_id}: {e}")
            continue

        # Send notifications
        notifier_internal(post_type, submission)

        # Update the processed flag in the database
        content['processed'] = True
        updated_content = json.dumps(content)

        update_query = """
            UPDATE internal_posts 
            SET content = ? 
            WHERE id = ?
        """
        cursor = db.cursor_main
        cursor.execute(update_query, (updated_content, post_id))
        db.conn_main.commit()

    return


@task(schedule='weekly')
def weekly_unknown_thread():
    """
    Posts the Weekly 'Unknown' thread: a round-up of all posts from the last
    seven days still marked as "Unknown".
    """
    r = REDDIT.subreddit('translator')
    today_str = date.today().strftime("%Y-%m-%d")

    # Get the current week number for the post title
    current_week = datetime.now().strftime("%U")

    unknown_entries = []

    # Retrieve 'Unknown' posts from the past week
    for item in r.search('flair:"Unknown"', sort="new", time_filter="week"):
        if item.link_flair_css_class == "unknown":
            title_safe = item.title.replace("|", " ")  # Avoid Markdown table conflicts
            post_date = datetime.fromtimestamp(item.created_utc).strftime("%Y-%m-%d")
            unknown_entries.append(f"| {post_date} | **[{title_safe}]({item.permalink})** | u/{item.author} |")

    if not unknown_entries:
        logger.debug("[WJ] unknown_thread: No 'Unknown' posts found this week.")
        return

    # Prepare the thread content
    unknown_entries.reverse()  # Oldest first
    unknown_content = "\n".join(unknown_entries)

    thread_title = f'[META] Weekly "Unknown" Identification Thread — {today_str} (Week {current_week})'
    body = RESPONSE.WEEKLY_UNKNOWN_THREAD.format(unknown_content=unknown_content)

    # Submit and distinguish the post
    submission = r.submit(title=thread_title, selftext=body, send_replies=False)
    submission.mod.distinguish()
    logger.info(f"[WJ] unknown_thread: Posted weekly 'Unknown' thread (Week {current_week}).")

    return
