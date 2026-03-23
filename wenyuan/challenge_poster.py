#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
Handles posting the translation challenge.
...

Logger tag: [WY:POSTER]
"""

import logging
from datetime import datetime, timezone

from config import SETTINGS, Paths
from config import logger as _base_logger
from integrations.discord_utils import send_discord_alert
from reddit.connection import REDDIT

logger = logging.LoggerAdapter(_base_logger, {"tag": "WY:POSTER"})


# ─── Reddit operations ────────────────────────────────────────────────────────


def translation_challenge_poster() -> None:
    """
    Post the weekly translation challenge as a stickied post.

    Reads the challenge content from file, creates a Reddit post with
    the current date, stickies it, and sends a Discord notification.
    """
    with open(Paths.TEMPLATES["TRANSLATION_CHALLENGE"], "r", encoding="utf-8") as f:
        weekly_challenge_md = f.read()

    timestamp_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    weekly_title = f"[Community] Translation Challenge — {timestamp_utc}"

    submission = REDDIT.subreddit(SETTINGS["subreddit"]).submit(
        title=weekly_title, selftext=weekly_challenge_md, send_replies=False
    )
    submission.mod.sticky(bottom=False)

    logger.info(
        "[WY] translation_challenge_poster: Submitted the weekly challenge to r/translator."
    )

    subject = "New Translation Challenge on r/translator"
    message = f"A new translation challenge has been posted [here](https://www.reddit.com{submission.permalink})."
    send_discord_alert(subject, message, "notification")
