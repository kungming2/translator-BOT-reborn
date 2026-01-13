#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
Handles the top-level functions that go through posts, messages, and
comments. This is the actual module that is run.
"""

import os
import time
import traceback

import psutil

from config import SETTINGS, TRANSIENT_ERRORS, logger
from connection import REDDIT, USERNAME
from database import record_activity_csv
from discord_utils import send_discord_alert
from edit_tracker import edit_tracker, progress_tracker
from error import error_log_extended
from processes.ziwen_commands import ziwen_commands
from processes.ziwen_messages import ziwen_messages
from processes.ziwen_posts import ziwen_posts
from time_handling import time_convert_to_string
from verification import verification_parser

if __name__ == "__main__":
    start_time = time.time()

    try:
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
        mem_num = psutil.Process(os.getpid()).memory_info().rss
        mem_usage = "{:.2f} MB".format(mem_num / (1024 * 1024))
        logger.info(f"[ZW] Run complete. Calls used: {used_calls}. {mem_usage} used.")

    except (KeyboardInterrupt, SystemExit):
        # Don't treat intentional exits or Ctrl+C as "errors"
        logger.info("Manual user shutdown.")
        raise

    except TRANSIENT_ERRORS as e:
        # Just log transient errors at WARNING level, don't save to error log
        logger.warning(
            f"[ZW] Main: Transient error encountered: {type(e).__name__}: {e}"
        )
        logger.info("[ZW] Main: Will retry on next cycle.")

    except Exception as e:  # The bot encountered a major error/exception.
        logger.critical(f"[ZW] Main: Encountered critical error {e}.")

        # Format the error text.
        error_entry = traceback.format_exc()
        error_log_extended(error_entry, "Ziwen Main")
    else:
        # Package data for this run and write it to a record.
        elapsed_time = round((time.time() - start_time) / 60, 2)
        run_time = time_convert_to_string(start_time)
        run_information = (
            run_time,
            "Cycle run",
            used_calls,
            None,
            mem_usage,
            None,
            elapsed_time,
        )
        record_activity_csv(run_information)
        logger.info(f"[ZW] Main: Run {elapsed_time:.2f} minutes.")

        # Send Discord alert if run took longer than 5 minutes
        cycle_time = SETTINGS["cycle_time"]
        if elapsed_time > cycle_time:
            alert_subject = "Long Run Time Alert"
            alert_message = (
                f"Run took {elapsed_time:.2f} minutes (> {cycle_time} minutes)\n"
                f"API calls used: {used_calls}\n"
                f"Memory usage: {mem_usage}"
            )
            send_discord_alert(
                subject=alert_subject,
                message=alert_message,
                webhook_name="alert",
            )
            logger.warning(
                f"[ZW] Discord alert sent for overly-long run time: {elapsed_time:.2f} minutes."
            )
