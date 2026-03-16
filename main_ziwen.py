#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
Handles the top-level functions that go through posts, messages, and
comments. This is the actual module that is run.
...

Logger tag: [ZW]
"""

import logging
import os
import time
import traceback

import psutil

from config import SETTINGS, TRANSIENT_ERRORS
from config import logger as _base_logger
from database import record_activity_csv
from error import error_log_extended
from integrations.discord_utils import send_discord_alert
from monitoring.edit_tracker import edit_tracker, progress_tracker
from processes.ziwen_comments import ziwen_commands
from processes.ziwen_messages import ziwen_messages
from processes.ziwen_posts import ziwen_posts
from reddit.connection import REDDIT, USERNAME
from reddit.verification import verification_parser
from time_handling import time_convert_to_string

logger = logging.LoggerAdapter(_base_logger, {"tag": "ZW"})


def _maybe_alert_slow_run(elapsed_minutes, run_start, api_calls, memory_usage):
    if elapsed_minutes <= SETTINGS["cycle_time"]:
        return
    send_discord_alert(
        subject="Excessive Run Time Alert",
        message=(
            f"Run took {elapsed_minutes:.2f} minutes (> {SETTINGS['cycle_time']} minutes)\n\n"
            f"* **Run start time**: {run_start}\n"
            f"* **API calls used**: {api_calls}\n"
            f"* **Memory usage**: {memory_usage}"
        ),
        webhook_name="alert",
    )
    logger.warning(
        f"Discord alert sent for overly-long run time: {elapsed_minutes:.2f} minutes."
    )


if __name__ == "__main__":
    start_time = time.time()

    try:
        logger.info("Starting cycle run.")

        # First it processes the titles of new posts.
        ziwen_posts()

        # Then it checks for any edits to comments.
        edit_tracker()
        progress_tracker()

        # Process comments and acts on commands.
        ziwen_commands()

        # Then it checks its messages (generally for new
        # subscriptions for language notifications).
        ziwen_messages()

        # Process verification requests.
        verification_parser()

        # Record API usage limit.
        probe = REDDIT.redditor(USERNAME).created_utc
        used_calls = REDDIT.auth.limits["used"]

        # Record memory usage at the end of a run.
        mem_bytes = psutil.Process(os.getpid()).memory_info().rss
        mem_usage = f"{mem_bytes / (1024**2):.2f} MB"
        logger.info(f"Run complete. Calls used: {used_calls}. {mem_usage} used.")

    except (KeyboardInterrupt, SystemExit):
        # Don't treat intentional exits or Ctrl+C as "errors"
        logger.info("Manual user shutdown.")
        raise

    except TRANSIENT_ERRORS as e:
        # Just log transient errors at WARNING level, don't save to error log
        logger.warning(f"Transient error encountered: {type(e).__name__}: {e}")
        logger.info("Will retry on next cycle.")

    except Exception as e:  # The bot encountered a major error/exception.
        logger.critical(f"Encountered critical error: {e}.")
        error_log_extended(traceback.format_exc(), "Ziwen Main")

    else:
        elapsed_time = (time.time() - start_time) / 60
        run_time = time_convert_to_string(start_time)

        # run_information fields: run_time, label, used_calls, mem_usage, elapsed_time, pid
        run_information = (
            run_time,
            "Cycle run",
            used_calls,
            mem_usage,
            elapsed_time,
            os.getpid(),
        )
        record_activity_csv("cycle", run_information)
        logger.info(f"Run {elapsed_time:.2f} minutes.")

        _maybe_alert_slow_run(elapsed_time, run_time, used_calls, mem_usage)
