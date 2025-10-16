#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
Handles the top-level functions that go through posts, messages, and
comments. This is the actual module that is run.
"""

import os
import sys
import time
import traceback

import psutil

from config import logger
from connection import REDDIT, credentials_source
from database import record_activity_csv
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
            probe = REDDIT.redditor(credentials_source["USERNAME"]).created_utc
            used_calls = REDDIT.auth.limits["used"]

            # Record memory usage at the end of a run.
            mem_num = psutil.Process(os.getpid()).memory_info().rss
            mem_usage = "{:.2f} MB".format(mem_num / (1024 * 1024))
            logger.info(
                f"[ZW] Run complete. Calls used: {used_calls}. {mem_usage} used."
            )

        except Exception as e:  # The bot encountered an error/exception.
            logger.error(f"[ZW] Main: Encountered error {e}.")

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
    except KeyboardInterrupt:  # Manual termination of the script with Ctrl-C.
        logger.info("Manual user shutdown.")
        sys.exit()
