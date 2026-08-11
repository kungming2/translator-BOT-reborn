#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""Bounded retry helpers for transient Reddit API rate-limit responses."""

import logging
import time
from collections.abc import Callable, Sequence
from typing import TypeVar

from prawcore.exceptions import TooManyRequests

from config import logger as _base_logger

logger = logging.LoggerAdapter(_base_logger, {"tag": "R:RETRY"})

T = TypeVar("T")
DEFAULT_429_RETRY_DELAYS: tuple[float, ...] = (60.0, 120.0)


def _retry_delay(retry_after: str | None, fallback_delay: float) -> float:
    """Return a positive server-provided retry delay or the fallback delay."""
    if retry_after is not None:
        try:
            parsed_delay = float(retry_after)
        except ValueError:
            pass
        else:
            if parsed_delay > 0:
                return parsed_delay
    return fallback_delay


def call_with_429_retry(
    action: Callable[[], T],
    *,
    operation: str,
    fallback_delays: Sequence[float] = DEFAULT_429_RETRY_DELAYS,
    sleep: Callable[[float], None] = time.sleep,
) -> T:
    """Call ``action`` and retry bounded HTTP 429 failures after a delay."""
    for retry_number, fallback_delay in enumerate(fallback_delays, start=1):
        try:
            return action()
        except TooManyRequests as exc:
            wait_seconds = _retry_delay(exc.retry_after, fallback_delay)
            logger.warning(
                "%s received HTTP 429; retrying in %.1f seconds (%s/%s).",
                operation,
                wait_seconds,
                retry_number,
                len(fallback_delays),
            )
            sleep(wait_seconds)

    return action()
