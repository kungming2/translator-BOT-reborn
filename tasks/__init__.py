#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
from config import Paths, load_settings, logger
from discord_utils import send_discord_alert

_tasks = {}


def _fetch_wenju_settings():
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


def run_schedule(schedule_name):
    """Run all tasks for a given schedule"""

    # Import task modules here, in order to register them. Everything in
    # tasks/ should be placed here.
    from . import (
        community_digest,
        data_maintenance,
        moderator_digest,
        status_report,
        iso_updates,
    )

    tasks_to_run = _tasks.get(schedule_name, [])
    executed_tasks = []

    for task_func in tasks_to_run:
        print(f"Running {task_func.__name__}...")
        try:
            task_func()
            executed_tasks.append(task_func.__name__)
        except Exception as e:
            print(f"Error in {task_func.__name__}: {e}")

    # Send Discord alert after all tasks have completed
    if executed_tasks:
        task_list = ", ".join(executed_tasks)
        notify_message = (
            f"The following functions on the **{schedule_name}** schedule have been run:\n"
            f"> `{task_list}`"
        )
    else:
        notify_message = f"No tasks were executed for the **{schedule_name}** schedule."

    send_discord_alert(
        f"{schedule_name.title()} Actions Completed",
        notify_message,
        "alert",
    )
    logger.info(f"[WJ] Discord notification sent for ({schedule_name}).")

    return


def get_tasks():
    """Get all registered tasks"""
    return _tasks


WENJU_SETTINGS = _fetch_wenju_settings()
