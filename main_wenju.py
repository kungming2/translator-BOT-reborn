#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
Scheduled Task Runner

This module provides a decorator-based system for scheduling tasks tasks.

HOW TO ADD A NEW TASK:
1. Create or open a task file in tasks/
2. Import the decorator: `from main_wenju import task`
3. Decorate your function with the schedule:

   @task(schedule='hourly')  # or 'daily', 'weekly', 'monthly'
   def your_task_name():
       # Your task logic here
       pass

4. Make sure the task module is imported at the top of this file

AVAILABLE SCHEDULES:
- 'hourly': Runs every hour
- 'daily': Runs once per day
- 'weekly': Runs once per week
- 'monthly': Runs once per month

EXAMPLE TASK FILE (tasks/database.py):
    from main_wenju import task

    @task(schedule='hourly')
    def cleanup_temp_tables():
        pass

    @task(schedule='daily')
    def optimize_indexes():
        pass
"""
import sys
from tasks import status_report


_tasks = {}


def task(schedule):
    """Decorator to register a task with a schedule"""
    def decorator(func):
        if schedule not in _tasks:
            _tasks[schedule] = []
        _tasks[schedule].append(func)
        return func
    return decorator


def run_schedule(schedule_name):
    """Run all tasks for a given schedule"""
    tasks_to_run = _tasks.get(schedule_name, [])
    for task_func in tasks_to_run:
        print(f"Running {task_func.__name__}...")
        try:
            task_func()
        except Exception as e:
            print(f"Error in {task_func.__name__}: {e}")


if __name__ == '__main__':
    if len(sys.argv) > 1:
        run_schedule(sys.argv[1])
