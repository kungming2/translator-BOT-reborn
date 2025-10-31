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
"""

import sys
import traceback

from config import logger
from error import error_log_extended
from tasks import get_tasks, run_schedule


def wenju_runner() -> None:
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
        # Don’t treat intentional exits or Ctrl+C as "errors"
        raise
    except Exception as e:
        # Log all other unexpected exceptions
        error_text = f"{type(e).__name__}: {e}\n\n{traceback.format_exc()}"
        error_log_extended(error_text, "Wenju")
