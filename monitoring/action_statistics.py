#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""Record global bot actions and calculate period averages."""

import logging
from datetime import UTC, datetime
from typing import TypedDict

import orjson

from config import Paths
from config import logger as _base_logger
from integrations.discord_utils import send_discord_alert
from time_handling import get_current_utc_date

logger = logging.LoggerAdapter(_base_logger, {"tag": "MN:ACTION"})


class ActionAverage(TypedDict):
    """One action and its average daily count for a requested period."""

    name: str
    count: float


def _send_action_counter_alert(action_type: str, count: int) -> None:
    """Send a verbose Discord log entry for a recorded action count."""
    message = f"**Action:** `{action_type}`\n**Recorded:** `{count}`\n"
    send_discord_alert("Ziwen Logging", message, "logs")


def action_counter(messages_number: int, action_type: str) -> None:
    """Record a number of bot actions by type and current UTC date."""
    try:
        count = int(messages_number)
        if count == 0:
            return
    except (ValueError, TypeError):
        logger.debug(
            f"action_counter: invalid messages_number {messages_number!r}, skipping."
        )
        return

    if action_type == "id":
        action_type = "identify"

    current_day = get_current_utc_date()
    try:
        with open(Paths.LOGS["COUNTER"], "rb") as file:
            current_actions = orjson.loads(file.read())
    except (FileNotFoundError, orjson.JSONDecodeError):
        current_actions = {}

    current_actions.setdefault(current_day, {})
    current_actions[current_day][action_type] = (
        current_actions[current_day].get(action_type, 0) + count
    )

    with open(Paths.LOGS["COUNTER"], "wb") as file:
        file.write(orjson.dumps(current_actions))

    _send_action_counter_alert(action_type, count)


def get_action_daily_averages(
    start_time: int, end_time: int, days: int
) -> list[ActionAverage]:
    """Return structured average daily action counts for a UTC time range."""
    if days <= 0:
        raise ValueError("days must be greater than zero")

    try:
        with open(Paths.LOGS["COUNTER"], "rb") as file:
            counter_data = orjson.loads(file.read())
    except (FileNotFoundError, orjson.JSONDecodeError):
        return []

    action_totals: dict[str, int] = {}
    for date_text, action_counts in counter_data.items():
        try:
            dt = datetime.strptime(date_text, "%Y-%m-%d").replace(tzinfo=UTC)
            unix_timestamp = int(dt.timestamp())
        except ValueError:
            logger.debug(f"Skipping malformed date entry: {date_text!r}.")
            continue

        if start_time <= unix_timestamp <= end_time:
            for action, count in action_counts.items():
                action_totals[action] = action_totals.get(action, 0) + int(count)

    return [
        {"name": action, "count": round(total / days, 2)}
        for action, total in sorted(action_totals.items())
    ]
