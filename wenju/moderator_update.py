#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""Send a daily operational update to moderators through Discord."""

import csv
import logging
from datetime import datetime

import yaml

from config import Paths
from config import logger as _base_logger
from integrations.discord_utils import send_discord_alert
from time_handling import get_current_utc_date
from wenju import task

logger = logging.LoggerAdapter(_base_logger, {"tag": "WJ:MODUPDATE"})


def _activity_csv_summary() -> tuple[str, dict[str, object]]:
    """Read the activity log and summarize recent runtime performance."""
    csv_address = Paths.LOGS["ACTIVITY"]

    try:
        with open(csv_address, newline="") as f_input:
            reader = csv.reader(f_input)
            next(reader, None)
            main_lines = list(reader)
    except FileNotFoundError:
        logger.warning("Activity log file not found.")
        return "* **Activity log**: File missing", {}
    except Exception as e:
        logger.error(f"Failed to read CSV file — {e}")
        return "* **Activity log**: Error reading file", {}

    if not main_lines:
        logger.info("No data found in activity log.")
        return "* **Activity log**: No data available", {}

    api_calls = [int(row[2]) for row in main_lines if row[2].strip()]
    average_api_calls = round(sum(api_calls) / len(api_calls), 2) if api_calls else 0.0

    memory_data = []
    for row in main_lines:
        cell = row[3].strip()
        if cell.endswith(" MB"):
            cell = cell[:-3]
        if cell:
            try:
                memory_data.append(float(cell))
            except ValueError:
                continue
    average_memory = (
        round(sum(memory_data) / len(memory_data), 2) if memory_data else 0.0
    )

    cycle_times = [
        float(row[4]) for row in main_lines if len(row) > 4 and row[4].strip()
    ]
    average_cycle = (
        round(sum(cycle_times) / len(cycle_times), 2) if cycle_times else 0.0
    )
    longest_cycles = [
        round(value, 2) for value in sorted(cycle_times, reverse=True)[:3]
    ]
    longest_cycles_str = ", ".join(f"{value:.2f}" for value in longest_cycles)

    summary = (
        f"* **Average API Calls**: {average_api_calls}/cycle"
        f"\n* **Average Memory Used**: {average_memory} MB"
        f"\n* **Average Cycle Length**: {average_cycle} minutes"
        f"\n* **Longest Cycles**: {longest_cycles_str} minutes"
    )
    data = {
        "avgApiCalls": average_api_calls,
        "avgMemoryMB": average_memory,
        "avgCycleMin": average_cycle,
        "longestCycles": longest_cycles,
    }
    return summary, data


def _error_log_summary() -> tuple[str, dict[str, object]]:
    """Summarize the error-log count and most recent entry."""
    header = "# Error Log"

    try:
        with open(Paths.LOGS["ERROR"], encoding="utf-8") as f:
            error_logs: list[dict] | None = yaml.safe_load(f) or []
    except FileNotFoundError:
        logger.warning("Error log file not found.")
        return f"{header}\n* **Error log entries**: 0 (file missing)", {
            "count": 0,
            "lastEntry": "N/A",
            "resolved": True,
        }
    except yaml.YAMLError as e:
        logger.error(f"Failed to parse YAML — {e}")
        return f"{header}\n* **Error log entries**: Unknown (YAML parse error)", {
            "count": 0,
            "lastEntry": "N/A",
            "resolved": True,
        }

    if not isinstance(error_logs, list) or not error_logs:
        return f"{header}\n* **Error log entries**: 0", {
            "count": 0,
            "lastEntry": "N/A",
            "resolved": True,
        }

    last_entry = error_logs[-1]
    last_timestamp = last_entry.get("timestamp", "Unknown time")
    last_resolved = last_entry.get("resolved", False)
    resolved_suffix = " (resolved)" if last_resolved else ""

    try:
        last_entry_time = datetime.fromisoformat(
            last_timestamp.replace("Z", "+00:00")
        ).strftime("%Y-%m-%d %H:%M:%S UTC")
    except (ValueError, TypeError, AttributeError):
        last_entry_time = last_timestamp

    count = len(error_logs)
    summary = (
        f"{header}\n"
        f"* **Error log entries**: {count}\n"
        f"* **Last entry from**: {last_entry_time}{resolved_suffix}"
    )
    logger.debug(f"Found {count} entries in the error log.")

    return summary, {
        "count": count,
        "lastEntry": last_entry_time + resolved_suffix,
        "resolved": last_resolved,
    }


@task(schedule="daily")
def send_moderator_update() -> None:
    """Send error-log and runtime-performance information to moderators."""
    logger.info("Preparing moderator operational update...")
    today_date = get_current_utc_date()
    error_log_summary, _ = _error_log_summary()
    activity_summary, _ = _activity_csv_summary()
    notification_body = f"{error_log_summary}\n\n# Performance\n{activity_summary}"

    send_discord_alert(f"Moderator Update for {today_date}", notification_body, "alert")
    logger.info("Daily moderator operational update sent.")
