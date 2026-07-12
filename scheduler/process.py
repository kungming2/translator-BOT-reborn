#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""Bounded subprocess execution for scheduled bot jobs."""

import logging
import os
import signal
import subprocess
from collections.abc import Sequence
from contextlib import suppress
from typing import IO

SIGKILL = getattr(signal, "SIGKILL", 9)


def _kill_process_group(pid: int, sig: int) -> None:
    """Call the POSIX process-group signal API used by the Linux scheduler."""
    killpg = getattr(os, "killpg", None)
    if killpg is None:
        raise RuntimeError("Process-group termination requires a POSIX host")
    killpg(pid, sig)


def terminate_process_group(
    process: subprocess.Popen, grace_seconds: int, logger: logging.Logger
) -> None:
    """Terminate a child process group and reap its leader."""
    try:
        _kill_process_group(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        process.wait()
        return

    try:
        process.wait(timeout=grace_seconds)
        return
    except subprocess.TimeoutExpired:
        logger.error(
            "Process group PID %s ignored SIGTERM for %s seconds; sending SIGKILL",
            process.pid,
            grace_seconds,
        )

    with suppress(ProcessLookupError):
        _kill_process_group(process.pid, SIGKILL)
    process.wait()


def run_bounded_process(
    command: Sequence[str],
    output: IO[str],
    timeout_seconds: int,
    grace_seconds: int,
    job_name: str,
    logger: logging.Logger,
) -> int | None:
    """Run a command, returning its code or ``None`` after a timeout."""
    process = subprocess.Popen(
        command,
        stdout=output,
        stderr=output,
        start_new_session=True,
    )
    try:
        return process.wait(timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        logger.error(
            "%s exceeded its %s-second runtime limit; terminating process group PID %s",
            job_name,
            timeout_seconds,
            process.pid,
        )
        terminate_process_group(process, grace_seconds, logger)
        return None
