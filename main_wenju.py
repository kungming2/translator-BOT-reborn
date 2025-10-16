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
     - cron: 3 */1 * * * (At minute 3 past every hour)
- 'daily': Runs once per day
     - cron: 47 23 * * * (At 23:47 every day)
- 'weekly': Runs once per week
     - cron: 13 8 * * 3 (At 08:13 on Wednesday)
- 'monthly': Runs once per month
     - cron: 13 8 10 * * (At 08:13 on day-of-month 10)
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

from config import logger
from tasks import get_tasks, run_schedule


def wenju_runner():
    if len(sys.argv) > 1:
        schedule_name = sys.argv[1]
        run_schedule(schedule_name)
    else:
        logger.info("Usage: python main_wenju.py <schedule_name>")
        logger.info("Available schedules:", list(get_tasks().keys()))
        sys.exit(1)


if __name__ == '__main__':
    wenju_runner()
