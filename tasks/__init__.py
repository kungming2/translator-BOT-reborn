#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
from config import Paths, load_settings

_tasks = {}


def fetch_wenju_settings():
    return load_settings(Paths.SETTINGS['WENJU_SETTINGS'])


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
    # Import task modules here to ensure they're registered
    from . import (community_digest, data_maintenance, moderator_digest,
                   status_report)

    tasks_to_run = _tasks.get(schedule_name, [])
    for task_func in tasks_to_run:
        print(f"Running {task_func.__name__}...")
        try:
            task_func()
        except Exception as e:
            print(f"Error in {task_func.__name__}: {e}")


def get_tasks():
    """Get all registered tasks"""
    return _tasks


WENJU_SETTINGS = fetch_wenju_settings()
