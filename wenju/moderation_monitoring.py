#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""Monitor moderation signals and alert r/translator moderators."""

import logging

from config import SETTINGS
from config import logger as _base_logger
from database import db
from integrations.discord_utils import send_discord_alert
from reddit.connection import REDDIT, create_mod_note
from wenju import WENJU_SETTINGS, task

logger = logging.LoggerAdapter(_base_logger, {"tag": "WJ:MODMON"})


@task(schedule="hourly")
def monitor_controversial_comments() -> None:
    """
    Check r/translator hourly for heavily downvoted comments
    and flag them for review via a Discord alert.

    :return: None
    """
    for comment in REDDIT.subreddit(SETTINGS["subreddit"]).comments(limit=100):
        score = comment.score
        removed = comment.removed
        mod_reports = comment.mod_reports
        permalink = comment.permalink
        comment_id = comment.id
        created_utc = int(comment.created_utc)
        author_name = comment.author.name if comment.author else "[deleted]"

        query = "SELECT comment_id FROM acted_comments WHERE comment_id = ?"
        already_acted = db.fetch_main(query, (comment_id,))

        score_threshold = WENJU_SETTINGS["controversial_score_threshold"]
        if (
            score <= score_threshold
            and not removed
            and not mod_reports
            and not already_acted
        ):
            create_mod_note(
                "ABUSE_WARNING",
                author_name,
                f"Authored heavily downvoted comment at https://www.reddit.com/{permalink}",
            )

            send_discord_alert(
                "Comment with Excessive Downvotes",
                f"[This comment](https://www.reddit.com{permalink}) "
                f"has many downvotes (`{score}`). Please check the thread.",
                "alert",
            )

            logger.info(
                f"Flagged controversial comment `{comment_id}` by "
                f"u/{author_name} (score: {score}) — Discord alert sent."
            )

            insert_query = """
                           INSERT INTO acted_comments (comment_id, created_utc, comment_author_username, action_type)
                           VALUES (?, ?, ?, ?) \
                           """
            cursor = db.cursor_main
            cursor.execute(
                insert_query,
                (comment_id, created_utc, author_name, "controversial_comment"),
            )
            db.conn_main.commit()

    return


@task(schedule="daily")
def modqueue_assessor() -> None:
    """
    Check how many items are in the modqueue and alert Discord
    if the count exceeds a certain threshold.
    """
    modqueue_items = list(
        REDDIT.subreddit(SETTINGS["subreddit"]).mod.modqueue(limit=None)
    )
    total_items = len(modqueue_items)

    comment_count = sum(1 for item in modqueue_items if item.fullname.startswith("t1_"))
    submission_count = sum(
        1 for item in modqueue_items if item.fullname.startswith("t3_")
    )

    markdown_summary = (
        f"\n\n- **Total Items**: {total_items}\n"
        f"- **Comments**: {comment_count}\n"
        f"- **Submissions**: {submission_count}"
    )

    if total_items >= WENJU_SETTINGS["max_queue"]:
        send_discord_alert(
            subject=f"{total_items} items in r/translator Modqueue",
            message=(
                f"There are now **{total_items} items** in [the modqueue]"
                f"(https://www.reddit.com/r/translator/about/modqueue). "
                f"Please help clear some of these items if you can."
                f"{markdown_summary}"
            ),
            webhook_name="alert",
        )

    return
