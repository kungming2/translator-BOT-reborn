#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
Request Closeout checks posts which are older than a week, have not been
marked as translated or needs review, and have above a certain amount of
comments/activity. It then messages the requester to remind them to mark
the post as translated if their request has been properly fulfilled.
"""

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from config import SETTINGS, logger
from connection import REDDIT
from database import db
from models.ajo import ajo_loader
from reddit_sender import message_send
from responses import RESPONSE

if TYPE_CHECKING:
    from praw.models import Submission

    from models.ajo import Ajo


def _send_closeout_messages(
    actionable_posts: list["Submission"],
    ajos_map: dict[str, "Ajo"],
    time_delta: float,
) -> None:
    """
    Send close-out notification messages to post authors.

    Args:
        actionable_posts: List of PRAW submission objects to close out.
        ajos_map: Dictionary mapping post IDs to their corresponding Ajo objects.
        time_delta: Days since post creation.
    """
    time_delta = round(time_delta, 1)

    for post_praw in actionable_posts:
        ajo = ajos_map[post_praw.id]
        language = ajo.lingvo.name

        # Build subject and message
        subject_line = RESPONSE.MSG_CLOSING_OUT_SUBJECT.format(language=language)
        closeout_message = RESPONSE.MSG_CLOSING_OUT.format(
            author=post_praw.author.name,
            days=time_delta,
            language=language,
            permalink=post_praw.permalink,
            num_comments=post_praw.num_comments,
        )
        closeout_message += RESPONSE.BOT_DISCLAIMER

        # Send the message
        message_send(
            redditor_obj=post_praw.author,
            subject=subject_line,
            body=closeout_message,
        )
        logger.info(
            f"Messaged u/{post_praw.author} about "
            f"closing out their post at {post_praw.permalink}."
        )

    return


def closeout_posts() -> None:
    """This functions looks back at posts, checks their age and their
    processed status, and reaches out to their posters if there's a
    minimum number of comments."""
    ajos_to_close = []
    actionable_posts = []
    ajos_map = {}  # Map post IDs to Ajo objects

    # Configurable close-out age (in days)
    days = SETTINGS["close_out_age"]

    # Define the time window: between N days ago + 1 hour and N days ago
    now = datetime.now(UTC)
    upper_dt = now - timedelta(days=days)
    lower_dt = upper_dt - timedelta(hours=1)

    # Convert to UNIX timestamps for SQLite
    upper = upper_dt.timestamp()
    lower = lower_dt.timestamp()

    query = """
            SELECT *
            FROM ajo_database
            WHERE created_utc BETWEEN ? AND ? \
            """
    rows = db.fetchall_ajo(query, (lower, upper))
    logger.debug(
        f"Fetching posts between {lower_dt.isoformat()} and {upper_dt.isoformat()}"
    )
    for row in rows:
        ajo = ajo_loader(row["id"])
        ajos_to_close.append(ajo)
        ajos_map[ajo.id] = ajo

    # Check to make sure the statuses match.
    posts_to_process = [
        post
        for post in ajos_to_close
        if post.status not in ["translated", "doublecheck"] and not post.closed_out
    ]

    if posts_to_process:
        logger.info(f"Found {len(posts_to_process)} posts to examine...")
    for post in posts_to_process:
        # Check number of comments. If there are more than our minimum required, take action.
        post_praw = REDDIT.submission(id=post.id)

        # Check if the post is deleted or removed
        if (
            post_praw.author is None
            or post_praw.selftext in ("[deleted]", "[removed]")
            or post_praw.removed_by_category is not None
        ):
            logger.info(
                f"Skipping post `{post.id}` for post closeout — deleted or removed."
            )
            post.set_closed_out(True)  # Mark it as closed.
            continue

        if post_praw.num_comments >= SETTINGS["close_out_comments_minimum"]:
            logger.info(
                f"Post `{post.id}` has {post_praw.num_comments} comments "
                f"(minimum: {SETTINGS['close_out_comments_minimum']}). "
                f"Adding to actionable posts and marking as closed out."
            )

            actionable_posts.append(post_praw)
            post.set_closed_out(True)
            post.update_reddit()

    # Send close-out messages to authors
    time_delta = (datetime.now(UTC) - lower_dt).days
    _send_closeout_messages(actionable_posts, ajos_map, time_delta)

    return


if __name__ == "__main__":
    print(closeout_posts())
