#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
Scheduled Task Runner

This module provides a decorator-based system for scheduling tasks.

HOW TO ADD A NEW TASK:
1. Create or open a task file in /tasks/
2. Import the decorator: `from main_wenju import task`
3. Decorate your function with the schedule:

   @task(schedule='hourly')  # or 'daily', 'weekly', 'monthly'
   def your_task_name():
       # Your task logic here
       pass

4. Make sure the task module is imported at the top of this file

AVAILABLE SCHEDULES (ALL IN LOCAL TIME):
- 'hourly': Runs every hour (e.g. python main_wenju.py hourly)
- 'daily': Runs once per day
- 'weekly': Runs once per week
- 'monthly': Runs once per month
Times are slightly irregular to avoid running when Ziwen is running.

EXAMPLE TASK FILE (tasks/task_category.py):
    from main_wenju import task

    @task(schedule='hourly')
    def placeholder():
        pass

    @task(schedule='daily')
    def placeholder_2():
        pass

MANUAL EXECUTION:
You can run any schedule manually for testing:
    python main_wenju.py hourly
    python main_wenju.py daily
...

Logger tag: [WJ]
"""

import logging
import sys
import traceback

from config import TRANSIENT_ERRORS
from config import logger as _base_logger
from error import error_log_extended
from wenju import get_tasks, run_schedule

logger = logging.LoggerAdapter(_base_logger, {"tag": "WJ"})


def wenju_runner() -> None:
    """
    Parse the command-line schedule argument and dispatch to the matching
    registered tasks.

    Reads ``sys.argv[1]`` for the schedule name (e.g. ``hourly``, ``daily``,
    ``weekly``, ``monthly``) and passes it to ``run_schedule()``. Exits with
    status 1 and prints usage hints if no argument is provided.

    Intended to be called from ``__main__`` only; error handling for transient
    and critical failures is managed by the enclosing ``try/except`` block.
    """
    if len(sys.argv) > 1:
        schedule_name: str = sys.argv[1]
        run_schedule(schedule_name)
    else:
        logger.warning("No time parameter specified as a system argument.")
        logger.info("Usage: python main_wenju.py <schedule_name>")
        logger.info("Available schedules: %s", list(get_tasks().keys()))
        sys.exit(1)


if __name__ == "__main__":
    try:
        wenju_runner()
    except (KeyboardInterrupt, SystemExit):
        # Don't treat intentional exits or Ctrl+C as "errors"
        logger.info("Manual user shutdown.")
        raise

    except TRANSIENT_ERRORS as e:
        # Just log transient errors at WARNING level, don't save to error log
        logger.warning(f"Transient error encountered: {type(e).__name__}: {e}")
        logger.info("Will retry on next cycle.")

    except Exception as e:
        # Log all other unexpected exceptions
        logger.critical(f"Encountered critical error: {e}.")

        error_text = f"{type(e).__name__}: {e}\n\n{traceback.format_exc()}"
        error_log_extended(error_text, "Wenju")
