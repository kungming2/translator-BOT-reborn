#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
Task registration and scheduling framework for the Wenju automation system.

This package provides the @task decorator used throughout the tasks/ directory
to register functions against a named schedule (e.g. 'hourly', 'daily', 'weekly').
Calling run_schedule() will auto-discover and import all sibling modules, then
execute every task registered under that schedule name.

Schedules
---------
    hourly   -- Runs frequently
    daily    -- Runs once per day
    weekly   -- Runs once per week

Usage
-----
    from tasks import task

    @task(schedule="daily")
    def my_task():
        ...

Logger tag: [WJ:I]
"""

import importlib
import logging
import traceback
from pathlib import Path

from config import Paths, load_settings
from config import logger as _base_logger
from error import error_log_basic
from integrations.discord_utils import send_discord_alert

logger = logging.LoggerAdapter(_base_logger, {"tag": "WJ:I"})

_tasks: dict[str, list] = {}


def _fetch_wenju_settings() -> dict:
    """Fetches Wenju-specific settings."""
    return load_settings(Paths.SETTINGS["WENJU_SETTINGS"])


def task(schedule):
    """Decorator to register a task with a schedule"""

    def decorator(func):
        if schedule not in _tasks:
            _tasks[schedule] = []
        _tasks[schedule].append(func)
        return func

    return decorator


def run_schedule(schedule_name) -> None:
    """Run all tasks for a given schedule"""

    # Dynamically import all task modules in the wenju/ directory
    # to register them. This automatically includes any .py files
    # without needing to manually list them.
    current_dir = Path(__file__).parent

    for file_path in current_dir.glob("*.py"):
        if file_path.name != "__init__.py":
            module_name = file_path.stem  # filename without .py extension
            importlib.import_module(f".{module_name}", package=__package__)

    tasks_to_run = _tasks.get(schedule_name, [])
    executed_tasks = []

    for task_func in tasks_to_run:
        logger.info(f"> Running {task_func.__name__}...")
        try:
            task_func()
            executed_tasks.append(task_func.__name__)
        except Exception as e:
            logger.exception(f"> Error in {task_func.__name__}: {e}")
            error_log_basic(f"{traceback.format_exc()}", f"Wenju ({schedule_name})")

    # Send Discord alert for some schedules after all tasks have completed
    if executed_tasks:
        task_list = "\n".join(f"* `{task_run}`" for task_run in sorted(executed_tasks))
        notify_message = (
            f"The following tasks on the **{schedule_name}** schedule have been run:\n"
            f"{task_list}"
        )
    else:
        notify_message = f"No tasks were executed for the **{schedule_name}** schedule."

    # Don't send hourly alerts, though.
    if schedule_name not in ["hourly", "daily"]:
        send_discord_alert(
            f"{schedule_name.title()} Tasks Completed",
            notify_message,
            "alert",
        )
        logger.info(f"Discord notification sent for ({schedule_name}).")

    return


def get_tasks() -> dict:
    """Get all registered tasks"""
    return _tasks


WENJU_SETTINGS = _fetch_wenju_settings()
