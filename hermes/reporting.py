#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
Monthly reporting helpers for Hermes.

Logger tag: [HM:REPORT]
"""

# ─── Imports ──────────────────────────────────────────────────────────────────

from datetime import UTC, datetime

import praw

from config import TRANSLATORBOT_SUBREDDIT, Paths, get_specific_logger
from hermes.tools import format_statistics_for_reddit, get_statistics

# ─── Module-level constants ───────────────────────────────────────────────────

logger = get_specific_logger("HM:REPORT", log_path=Paths.HERMES["HERMES_EVENTS"])


# ─── Monthly statistics ───────────────────────────────────────────────────────


def previous_month_bounds(now: datetime | None = None) -> tuple[int, int, str]:
    """
    Return UTC start/end timestamps and YYYY-MM label for the previous month.
    """
    if now is None:
        now = datetime.now(UTC)
    elif now.tzinfo is None:
        now = now.replace(tzinfo=UTC)
    else:
        now = now.astimezone(UTC)

    current_month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if current_month_start.month == 1:
        previous_month_start = current_month_start.replace(
            year=current_month_start.year - 1,
            month=12,
        )
    else:
        previous_month_start = current_month_start.replace(
            month=current_month_start.month - 1,
        )

    return (
        int(previous_month_start.timestamp()),
        int(current_month_start.timestamp()),
        previous_month_start.strftime("%Y-%m"),
    )


def build_monthly_statistics_post(
    start_utc: int, end_utc: int, month_year: str
) -> tuple[str, str]:
    """Build the title and Markdown body for a Hermes monthly statistics post."""
    month_date = datetime.strptime(month_year, "%Y-%m").replace(tzinfo=UTC)
    month_label = month_date.strftime("%B %Y")
    stats = get_statistics(start_utc, end_utc)

    title = f"r/Language_Exchange Hermes Statistics - {month_label}"
    body = "\n\n".join(
        [
            f"# Hermes Statistics – {month_label}",
            format_statistics_for_reddit(stats),
            (
                "These figures summarize active Hermes database entries first "
                f"recorded from {month_year}-01 through the end of {month_label} UTC."
            ),
        ]
    )
    return title, body


def post_monthly_statistics(reddit: praw.Reddit | None = None) -> str | None:
    """
    Post the previous month's Hermes statistics to r/translatorBOT.

    Returns the new post URL, or None if a matching monthly post already exists.
    """
    if reddit is None:
        from reddit.connection import REDDIT_HERMES

        reddit = REDDIT_HERMES

    start_utc, end_utc, month_year = previous_month_bounds()
    title, body = build_monthly_statistics_post(start_utc, end_utc, month_year)
    subreddit = reddit.subreddit(TRANSLATORBOT_SUBREDDIT)

    for submission in subreddit.search(
        f'title:"{title}"', sort="new", time_filter="year"
    ):
        logger.info(
            f"Hermes monthly statistics post already exists: https://redd.it/{submission.id}"
        )
        return None

    submission = subreddit.submit(title=title, selftext=body, send_replies=False)
    logger.info(f"Posted Hermes monthly statistics: https://redd.it/{submission.id}")
    return f"https://www.reddit.com{submission.permalink}"
