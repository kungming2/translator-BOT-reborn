#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
This module contains tasks related to gathering and presenting
information that is public-facing (that is, towards the community).
Functions placed here generally will generate a report viewable by the
public.
...

Logger tag: [WJ:DIGEST]
"""

# ─── Imports ──────────────────────────────────────────────────────────────────

import logging
import time
from datetime import datetime

from config import SETTINGS
from config import logger as _base_logger
from database import db
from models.diskuto import diskuto_loader, diskuto_writer
from reddit.connection import REDDIT, USERNAME, submit_translatorbot_post
from reddit.notifications import notifier_internal
from wenju import task

# ─── Module-level constants ───────────────────────────────────────────────────

logger = logging.LoggerAdapter(_base_logger, {"tag": "WJ:DIGEST"})

# ─── Internal post digest ─────────────────────────────────────────────────────


@task(schedule="daily")
def send_internal_post_digest() -> None:
    """
    Check for new internal posts in the last 24 hours and send
    notifications for unprocessed ones. This is usually meta/community,
    and this allows for messages to be sent en masse at once.
    """
    cutoff_time = int(time.time()) - (24 * 60 * 60)

    query = """
        SELECT id
        FROM internal_posts 
        WHERE created_utc >= ?
    """
    posts = db.fetchall_main(query, (cutoff_time,))

    post_type_counts: dict[str, int] = {}

    for post in posts:
        post_id = post["id"]
        diskuto = diskuto_loader(post_id)
        if diskuto is None:
            continue

        if diskuto.processed:
            continue

        post_type = diskuto.post_type
        submission_id = diskuto.id
        logger.info(
            f"Post {post_id}: post_type={post_type!r}, submission_id={submission_id!r}"
        )

        if not post_type or not submission_id:
            logger.warning(f"Warning: Missing post_type or id for post {post_id}")
            continue

        try:
            submission = REDDIT.submission(id=submission_id)
        except Exception as e:
            logger.error(f"Error fetching submission {submission_id}: {e}")
            continue

        notifier_internal(post_type, submission)
        post_type_counts[post_type] = post_type_counts.get(post_type, 0) + 1

        diskuto.mark_processed()
        diskuto_writer(diskuto)

    if post_type_counts:
        counts_summary = ", ".join(
            f"{post_type}: {count} post(s)"
            for post_type, count in sorted(post_type_counts.items())
        )
        logger.info(
            f"Processed {sum(post_type_counts.values())} internal post(s) — {counts_summary}"
        )

    return


# ─── Bot action reporting ─────────────────────────────────────────────────────


def _analyze_bot_mod_log(start_time: int, end_time: int) -> dict[str, int]:
    """
    Analyze mod log actions performed by u/translator-BOT in r/translator.

    Args:
        start_time: Unix timestamp for the start of the time range
        end_time: Unix timestamp for the end of the time range

    Returns:
        Mapping of action type (e.g. 'removelink') to occurrence count.
    """
    subreddit = REDDIT.subreddit(SETTINGS["subreddit"])
    action_counts: dict[str, int] = {}

    for log_entry in subreddit.mod.log(mod=USERNAME, limit=None):
        if start_time <= log_entry.created_utc <= end_time:
            action_type = log_entry.action
            action_counts[action_type] = action_counts.get(action_type, 0) + 1
        elif log_entry.created_utc < start_time:
            # Logs are returned newest first — stop once past our range.
            break

    return action_counts


@task(schedule="weekly")
def weekly_bot_action_report() -> None:
    """
    Generate a weekly report of u/translator-BOT mod actions and post to r/translatorBOT.
    """
    end_time = int(time.time())
    start_time = end_time - (7 * 24 * 60 * 60)

    action_data = _analyze_bot_mod_log(start_time, end_time)

    start_date = datetime.fromtimestamp(start_time).strftime("%Y-%m-%d")
    end_date = datetime.fromtimestamp(end_time).strftime("%Y-%m-%d")

    end_datetime = datetime.fromtimestamp(end_time)
    week_number: int = end_datetime.isocalendar()[1]

    total_actions = sum(action_data.values())
    avg_actions_per_day = total_actions / 7

    report_sections: list[str] = []

    summary = f"""## Summary

- **Analyzed Period**: {start_date} to {end_date}
- **Total Reddit Actions**: {total_actions:,}
- **Average Actions per Day**: {avg_actions_per_day:,.1f}
- **Unique Action Types**: {len(action_data)}
    """
    report_sections.append(summary)

    if action_data:
        breakdown = [
            "## Action Breakdown",
            "| Action | Count | Percentage |",
            "|--------|-------|------------|",
        ]
        for action in sorted(action_data.keys()):
            count = action_data[action]
            percentage = (count / total_actions * 100) if total_actions > 0 else 0
            breakdown.append(f"| {action} | {count:,} | {percentage:.1f}% |")
        report_sections.append("\n".join(breakdown))
    else:
        report_sections.append("## Action Breakdown\nNo actions found in this period.")

    report_content = "\n\n".join(report_sections)

    title = f"u/translator-BOT Mod Action Statistics — {end_date} (Week {week_number})"

    submission = submit_translatorbot_post(
        title,
        selftext=report_content,
        reddit=REDDIT,
    )
    logger.info(f"Report posted: {submission.url}")

    return
