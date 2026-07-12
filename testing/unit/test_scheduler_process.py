#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""Tests for bounded scheduler subprocess execution."""

import signal
import subprocess
from unittest.mock import MagicMock, call, patch

from scheduler.process import run_bounded_process, terminate_process_group


def test_run_bounded_process_returns_exit_code() -> None:
    process = MagicMock(pid=123)
    process.wait.return_value = 0

    with patch("scheduler.process.subprocess.Popen", return_value=process) as popen:
        result = run_bounded_process(
            ["python", "bot.py"], MagicMock(), 30, 5, "bot", MagicMock()
        )

    assert result == 0
    popen.assert_called_once_with(
        ["python", "bot.py"],
        stdout=popen.call_args.kwargs["stdout"],
        stderr=popen.call_args.kwargs["stderr"],
        start_new_session=True,
    )
    process.wait.assert_called_once_with(timeout=30)


def test_run_bounded_process_terminates_after_timeout() -> None:
    process = MagicMock(pid=123)
    process.wait.side_effect = subprocess.TimeoutExpired("bot", 30)
    logger = MagicMock()

    with (
        patch("scheduler.process.subprocess.Popen", return_value=process),
        patch("scheduler.process.terminate_process_group") as terminate,
    ):
        result = run_bounded_process(
            ["python", "bot.py"], MagicMock(), 30, 5, "bot", logger
        )

    assert result is None
    terminate.assert_called_once_with(process, 5, logger)


def test_terminate_process_group_escalates_to_sigkill() -> None:
    process = MagicMock(pid=123)
    process.wait.side_effect = [subprocess.TimeoutExpired("bot", 5), 0]

    with (
        patch("scheduler.process._kill_process_group") as killpg,
    ):
        terminate_process_group(process, 5, MagicMock())

    assert killpg.call_args_list == [
        call(123, signal.SIGTERM),
        call(123, 9),
    ]
    assert process.wait.call_args_list == [call(timeout=5), call()]


def test_terminate_process_group_stops_after_sigterm() -> None:
    process = MagicMock(pid=123)
    process.wait.return_value = 0

    with patch("scheduler.process._kill_process_group") as killpg:
        terminate_process_group(process, 5, MagicMock())

    killpg.assert_called_once_with(123, signal.SIGTERM)
    process.wait.assert_called_once_with(timeout=5)
