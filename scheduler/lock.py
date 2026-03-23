# scheduler/lock.py
"""File-based exclusive locking for bot scripts using fcntl."""

# ─── Imports ──────────────────────────────────────────────────────────────────

import fcntl
import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from config import SCHEDULER_SETTINGS

# ─── Module-level constants ───────────────────────────────────────────────────

LOCK_DIR = Path(SCHEDULER_SETTINGS["locks_directory"])


# ─── Exceptions ───────────────────────────────────────────────────────────────


class AlreadyRunningError(Exception):
    """Raised when a script lock cannot be acquired because the script is already running."""


# ─── Lock context manager ─────────────────────────────────────────────────────


@contextmanager
def script_lock(name: str) -> Iterator[None]:
    """
    Acquire an exclusive lock for the named script.
    Raises AlreadyRunningError if already running.
    """
    LOCK_DIR.mkdir(parents=True, exist_ok=True)
    lock_path = LOCK_DIR / f"{name}.lock"

    with open(lock_path, "w") as f:
        try:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)  # type: ignore[attr-defined]
        except BlockingIOError:
            raise AlreadyRunningError(f"{name} is already running")
        try:
            f.write(str(os.getpid()))
            yield
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)  # type: ignore[attr-defined]
