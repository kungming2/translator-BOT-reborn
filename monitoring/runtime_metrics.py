#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""Lightweight per-cycle counters for runtime logging."""

from collections import Counter

_COUNTERS: Counter[str] = Counter()


def reset_runtime_metrics() -> None:
    """Clear counters at the start of a Ziwen cycle."""
    _COUNTERS.clear()


def increment_runtime_metric(name: str, amount: int = 1) -> None:
    """Increment one named runtime counter."""
    _COUNTERS[name] += amount


def runtime_metrics_snapshot() -> dict[str, int]:
    """Return a plain dictionary of current runtime counters."""
    return dict(_COUNTERS)
