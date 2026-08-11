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
def script_lock(name: str, *, blocking: bool = False) -> Iterator[None]:
    """
    Acquire an exclusive lock for the named script.

    By default, raise ``AlreadyRunningError`` when the lock is busy. When
    ``blocking`` is true, wait until the current lock holder exits.
    """
    LOCK_DIR.mkdir(parents=True, exist_ok=True)
    lock_path = LOCK_DIR / f"{name}.lock"

    with open(lock_path, "w") as f:
        try:
            lock_flags = fcntl.LOCK_EX  # type: ignore[attr-defined]
            if not blocking:
                lock_flags |= fcntl.LOCK_NB  # type: ignore[attr-defined]
            fcntl.flock(f, lock_flags)  # type: ignore[attr-defined]
        except BlockingIOError as e:
            raise AlreadyRunningError(f"{name} is already running") from e
        try:
            f.write(str(os.getpid()))
            yield
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)  # type: ignore[attr-defined]
