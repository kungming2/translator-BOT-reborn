#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
Provides the hourly public statistics snapshot.
...

Logger tag: [WJ:PUBSTATS]
"""

# ─── Imports ──────────────────────────────────────────────────────────────────

import base64
import json
import logging
import os
import secrets
import time
from datetime import UTC, date, datetime
from pathlib import Path
from typing import TypedDict

from config import Paths
from config import logger as _base_logger
from monitoring.action_statistics import ActionAverage, get_action_daily_averages
from time_handling import get_current_utc_date
from wenju import WENJU_SETTINGS, task
from wenyuan.period_statistics import build_period_stats_data

# ─── Module-level constants ───────────────────────────────────────────────────

logger = logging.LoggerAdapter(_base_logger, {"tag": "WJ:PUBSTATS"})


class _FilterStatistics(TypedDict):
    """Structured title-filter statistics exposed on the public dashboard."""

    ratePerDay: float
    startDate: str
    endDate: str


class _PublicStatistics(TypedDict):
    """Allowlisted statistics used by the public dashboard."""

    filter_data: _FilterStatistics | None
    actions: list[ActionAverage]
    new_posts: float
    notifications: float
    wenyuan_data: dict[str, object] | None


# ─── Data collectors ──────────────────────────────────────────────────────────


def _filter_entries_by_date_range(
    entries: list[str],
    start_date: date | int | float,
    end_date: date | int | float,
) -> tuple[list[str], date, date]:
    """
    Filter log entries to those within the specified date range.

    Args:
        entries: List of log entry strings
        start_date: datetime.date or Unix timestamp
        end_date: datetime.date or Unix timestamp

    Returns:
        tuple: (filtered_entries, start_date_obj, end_date_obj)
    """
    if isinstance(start_date, (int, float)):
        start_date = datetime.fromtimestamp(start_date, tz=UTC).date()
    if isinstance(end_date, (int, float)):
        end_date = datetime.fromtimestamp(end_date, tz=UTC).date()

    filtered = []
    for line_num, entry in enumerate(entries, start=1):
        try:
            parts = [p.strip() for p in entry.split("|") if p.strip()]

            if not parts:
                raise ValueError("No valid parts found in entry")

            entry_date_str = parts[0]
            entry_date = datetime.strptime(entry_date_str, "%Y-%m-%d").date()

        except Exception as e:
            logger.error(f"Encountered entry error at line {line_num}: {e}")
            logger.error(f"ENTRY: {entry}")
            continue

        if entry_date is not None and start_date <= entry_date <= end_date:
            filtered.append(entry)

    return filtered, start_date, end_date


def _collect_filter_statistics(
    start_date: date | int | float,
    end_date: date | int | float,
) -> _FilterStatistics | None:
    """Calculate the title-filter rate for an explicit date range."""
    try:
        with open(Paths.LOGS["FILTER"], encoding="utf-8") as f:
            filter_logs = f.read().strip()
    except FileNotFoundError:
        logger.warning("Filter log file not found.")
        return None

    all_entries = filter_logs.splitlines()[2:]

    if len(all_entries) < 2:
        logger.info("Not enough data in filter log.")
        return None

    entries, period_start, period_end = _filter_entries_by_date_range(
        all_entries, start_date, end_date
    )
    if not entries:
        logger.warning("No entries found in specified date range.")
        return None

    days_elapsed = (period_end - period_start).days or 1
    entry_count = len(entries)
    rate_per_day = round(entry_count / days_elapsed, 2)

    logger.debug(
        f"Average filtered posts: {rate_per_day}/day "
        f"over {days_elapsed} days ({entry_count} entries)."
    )

    return {
        "ratePerDay": rate_per_day,
        "startDate": str(period_start),
        "endDate": str(period_end),
    }


def _wenyuan_period_stats(days: int = 30) -> dict[str, object] | None:
    """Collect Wenyuan period statistics for the public dashboard."""
    try:
        stats_data = build_period_stats_data(days, include_comparison=True)
    except Exception as e:
        logger.error("Failed to collect Wenyuan period statistics — %s", e)
        return None

    return stats_data


def _collect_public_statistics(
    today_date: date, current_time: int, days_ago: int
) -> _PublicStatistics:
    """Collect the allowlisted statistics for the hourly public dashboard."""
    back_start_date = current_time - (86400 * days_ago)
    filter_data = _collect_filter_statistics(
        start_date=back_start_date, end_date=today_date
    )
    actions = get_action_daily_averages(back_start_date, current_time, days_ago)
    wenyuan_data = _wenyuan_period_stats(30)

    return {
        "filter_data": filter_data,
        "actions": actions,
        "new_posts": next(
            (
                action["count"]
                for action in actions
                if action["name"].lower() == "new posts"
            ),
            0.0,
        ),
        "notifications": next(
            (
                action["count"]
                for action in actions
                if action["name"].lower() == "notifications"
            ),
            0.0,
        ),
        "wenyuan_data": wenyuan_data,
    }


# ─── Public HTML rendering ────────────────────────────────────────────────────


def _json_for_html(data: dict) -> str:
    """Serialize JSON for safe inclusion in an HTML script-data element."""
    return (
        json.dumps(data, indent=2)
        .replace("&", "\\u0026")
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )


def _build_public_dashboard_data(
    date_str: str, statistics: _PublicStatistics
) -> dict[str, object]:
    """Return the explicit allowlist of shared statistics safe to publish."""
    return {
        "date": date_str,
        "generatedAt": datetime.now(UTC).isoformat(timespec="seconds"),
        "filter": statistics["filter_data"]
        or {"ratePerDay": 0, "startDate": date_str, "endDate": date_str},
        "newPosts": statistics["new_posts"],
        "notifications": statistics["notifications"],
        "actions": statistics["actions"],
        "wenyuanPeriodStats": statistics["wenyuan_data"],
    }


def _render_public_stats_dashboard(date_str: str, data: dict) -> str:
    """Render the allowlisted public statistics as a self-contained HTML page."""
    with open(Paths.TEMPLATES["PUBLIC_STATS"], encoding="utf-8") as f:
        template = f.read()
    with open(Paths.ICONS["PUBLIC_STATS_FAVICON"], "rb") as f:
        favicon_base64 = base64.b64encode(f.read()).decode("ascii")

    csp_nonce = secrets.token_urlsafe(24)
    return (
        template.replace("__DATE_STR__", date_str)
        .replace('"__DATA_JSON__"', _json_for_html(data))
        .replace("__FAVICON_BASE64__", favicon_base64)
        .replace("__CSP_NONCE__", csp_nonce)
    )


def _atomic_write_text(path: Path, content: str) -> None:
    """Replace a generated page atomically so readers never see a partial file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        temporary_path.write_text(content, encoding="utf-8")
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)


def _atomic_write_bytes(path: Path, content: bytes) -> None:
    """Replace a generated binary asset atomically."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        temporary_path.write_bytes(content)
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)


# ─── Scheduled tasks ──────────────────────────────────────────────────────────


@task(schedule="hourly")
def generate_public_statistics() -> None:
    """Generate the isolated public statistics snapshot without notifications."""
    logger.info("Generating public statistics snapshot...")
    today_date_str = get_current_utc_date()
    today_date = datetime.strptime(today_date_str, "%Y-%m-%d").date()
    statistics = _collect_public_statistics(
        today_date,
        int(time.time()),
        WENJU_SETTINGS["report_command_average"],
    )
    public_data = _build_public_dashboard_data(today_date_str, statistics)
    public_html = _render_public_stats_dashboard(today_date_str, public_data)
    public_html_path = Path(Paths.PUBLIC["STATS"])
    public_touch_icon_path = Path(Paths.PUBLIC["TOUCH_ICON"])
    touch_icon = Path(Paths.ICONS["PUBLIC_STATS_TOUCH_ICON"]).read_bytes()
    _atomic_write_bytes(public_touch_icon_path, touch_icon)
    _atomic_write_text(public_html_path, public_html)
    logger.info(
        "Public statistics snapshot saved to %s with touch icon %s",
        public_html_path,
        public_touch_icon_path,
    )
