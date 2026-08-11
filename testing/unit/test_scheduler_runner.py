#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""Tests for scheduler registration and shared Reddit-client locking."""

import importlib.util
import sys
import types
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


class _AlreadyRunningError(Exception):
    """Test double for a busy scheduler file lock."""


class _Scheduler:
    """Minimal APScheduler double that records registered jobs."""

    def __init__(self, *, timezone: str) -> None:
        self.timezone = timezone
        self.jobs: list[dict[str, object]] = []

    def add_listener(self, *_args: object) -> None:
        pass

    def add_job(self, func: object, trigger: str, **kwargs: object) -> None:
        self.jobs.append({"func": func, "trigger": trigger, **kwargs})

    def start(self) -> None:
        pass


@pytest.fixture
def runner_module(tmp_path: Path):
    """Load scheduler.runner with platform-neutral dependency doubles."""
    scheduler_settings = {
        "main_bot_directory": str(tmp_path),
        "main_log_directory": str(tmp_path),
        "locks_directory": str(tmp_path / "locks"),
        "job_timeouts_seconds": {
            "ziwen": 170,
            "chinese_reference": 540,
            "hermes": 1500,
            "wenju_hourly": 3000,
            "wenju_daily": 3600,
            "wenju_weekly": 3600,
            "wenju_monthly": 7200,
        },
        "termination_grace_seconds": 60,
    }
    config_stub = types.ModuleType("config")
    config_stub.SCHEDULER_SETTINGS = scheduler_settings

    @contextmanager
    def placeholder_lock(_name: str, *, blocking: bool = False) -> Iterator[None]:
        del blocking
        yield

    lock_stub = types.ModuleType("scheduler.lock")
    lock_stub.AlreadyRunningError = _AlreadyRunningError
    lock_stub.script_lock = placeholder_lock

    events_stub = types.ModuleType("apscheduler.events")
    events_stub.EVENT_JOB_ERROR = 1
    events_stub.EVENT_JOB_MISSED = 2
    events_stub.JobExecutionEvent = object

    blocking_stub = types.ModuleType("apscheduler.schedulers.blocking")
    blocking_stub.BlockingScheduler = _Scheduler

    module_path = Path(__file__).resolve().parents[2] / "scheduler" / "runner.py"
    spec = importlib.util.spec_from_file_location("_scheduler_runner_test", module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)

    stubs = {
        "config": config_stub,
        "scheduler.lock": lock_stub,
        "apscheduler.events": events_stub,
        "apscheduler.schedulers.blocking": blocking_stub,
    }
    with patch.dict(sys.modules, stubs):
        spec.loader.exec_module(module)
    return module


def test_monthly_job_is_separated_and_waits_for_primary_reddit_lock(
    runner_module,
) -> None:
    monthly_job = next(
        job for job in runner_module.scheduler.jobs if job["id"] == "wenju_monthly"
    )

    assert monthly_job["hour"] == 0
    assert monthly_job["minute"] == 10
    assert monthly_job["kwargs"] == {
        "script": "main_wenju.py",
        "args": ["monthly"],
        "lock_name": "wenju_monthly",
        "coordination_lock_name": "reddit_primary",
        "wait_for_coordination_lock": True,
    }


def test_ziwen_skips_when_monthly_holds_primary_reddit_lock(
    runner_module, tmp_path: Path
) -> None:
    acquired_locks: list[tuple[str, bool]] = []

    @contextmanager
    def busy_primary_lock(name: str, *, blocking: bool = False) -> Iterator[None]:
        acquired_locks.append((name, blocking))
        if name == "reddit_primary":
            raise _AlreadyRunningError
        yield

    run_process = MagicMock(return_value=0)
    runner_module.script_lock = busy_primary_lock
    runner_module.run_bounded_process = run_process
    runner_module.LOG_DIR = tmp_path

    runner_module.run_script(
        "main_ziwen.py",
        lock_name="ziwen",
        coordination_lock_name="reddit_primary",
    )

    assert acquired_locks == [("ziwen", False), ("reddit_primary", False)]
    run_process.assert_not_called()


def test_monthly_waits_for_primary_reddit_lock_then_runs(
    runner_module, tmp_path: Path
) -> None:
    acquired_locks: list[tuple[str, bool]] = []

    @contextmanager
    def available_lock(name: str, *, blocking: bool = False) -> Iterator[None]:
        acquired_locks.append((name, blocking))
        yield

    run_process = MagicMock(return_value=0)
    runner_module.script_lock = available_lock
    runner_module.run_bounded_process = run_process
    runner_module.LOG_DIR = tmp_path
    runner_module.BOT_DIR = tmp_path

    runner_module.run_script(
        "main_wenju.py",
        args=["monthly"],
        lock_name="wenju_monthly",
        coordination_lock_name="reddit_primary",
        wait_for_coordination_lock=True,
    )

    assert acquired_locks == [
        ("wenju_monthly", False),
        ("reddit_primary", True),
    ]
    run_process.assert_called_once()
