#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
Handles posting the translation challenge.
"""

from datetime import datetime, timezone

from config import SETTINGS, Paths
from connection import logger, REDDIT
from discord_utils import send_discord_alert


def translation_challenge_poster():
    """
    Post the weekly translation challenge as a stickied post.

    Reads the challenge content from file, creates a Reddit post with
    the current date, stickies it, and sends a Discord notification.
    """
    # Read challenge content from file
    with open(Paths.WENYUAN["TRANSLATION_CHALLENGE"], "r", encoding="utf-8") as f:
        weekly_challenge_md = f.read()

    # Format title with current date (UTC)
    timestamp_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    weekly_title = f"[English > Any] Translation Challenge — {timestamp_utc}"

    # Submit and sticky the post
    submission = REDDIT.subreddit(SETTINGS["subreddit"]).submit(
        title=weekly_title, selftext=weekly_challenge_md, send_replies=False
    )
    submission.mod.sticky(bottom=False)

    logger.info(
        "[WY] translation_challenge_poster: Submitted the weekly challenge to r/translator."
    )

    # Send Discord notification
    subject = "New Translation Challenge on r/translator"
    message = f"A new translation challenge has been posted [here](https://www.reddit.com{submission.permalink})."
    send_discord_alert(subject, message, "notification")
