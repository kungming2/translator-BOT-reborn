#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
Handles time-related conversion tasks.
Adherence to ISO 8601 or timestamps is strongly emphasized.
...

Logger tag: [TIME]
"""

# ─── Imports ──────────────────────────────────────────────────────────────────

from datetime import UTC, datetime

# ─── Current time & date ──────────────────────────────────────────────────────


def get_current_utc_time() -> str:
    """Return the current UTC time as an ISO 8601 string."""
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def get_current_utc_date() -> str:
    """Return the current UTC date in YYYY-MM-DD format."""
    return datetime.now(UTC).strftime("%Y-%m-%d")


def get_current_month() -> str:
    """Return the current UTC month in YYYY-MM format."""
    return datetime.now(UTC).strftime("%Y-%m")


# ─── Timestamp conversion ─────────────────────────────────────────────────────


def time_convert_to_string(unix_integer: int | float) -> str:
    """
    Convert a UNIX timestamp to an ISO 8601 UTC time string.

    :param unix_integer: UNIX time as an int or float.
    :return: ISO 8601 formatted UTC time string
             (e.g., '2025-07-11T03:21:00Z').
    """
    return datetime.fromtimestamp(int(unix_integer), tz=UTC).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )


def time_convert_to_utc(iso_str: str) -> str:
    """
    Convert an ISO 8601 timestamp (with offset) to a UTC ISO string.
    Returns the original string unchanged if it is malformed or missing.
    """
    try:
        normalized = (
            iso_str.replace("Z", "+00:00") if isinstance(iso_str, str) else iso_str
        )
        dt = datetime.fromisoformat(normalized)
        if dt.tzinfo is None:
            return iso_str
        return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    except (TypeError, ValueError, AttributeError):
        return iso_str


def convert_to_day(unix_integer: int | float) -> str:
    """
    Convert a UNIX timestamp to a UTC date string (YYYY-MM-DD).

    :param unix_integer: UNIX time as an int or float.
    :return: UTC date string, e.g., '2025-07-11'.
    """
    return datetime.fromtimestamp(int(unix_integer), tz=UTC).strftime("%Y-%m-%d")


def time_convert_to_string_seconds(seconds: int) -> str:
    """
    Convert a duration in seconds to a human-readable time string.

    :param seconds: Time in seconds.
    :return: Formatted time string (e.g., '2 hours, 15 minutes').
    """
    seconds = max(0, int(seconds))

    def _unit(value: int, label: str) -> str:
        suffix = "" if value == 1 else "s"
        return f"{value} {label}{suffix}"

    if seconds < 60:
        return _unit(seconds, "second")
    elif seconds < 3600:
        minutes = seconds // 60
        return _unit(minutes, "minute")
    elif seconds < 86400:
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        return f"{_unit(hours, 'hour')}, {_unit(minutes, 'minute')}"
    else:
        days = seconds // 86400
        hours = (seconds % 86400) // 3600
        return f"{_unit(days, 'day')}, {_unit(hours, 'hour')}"


# ─── Month arithmetic ─────────────────────────────────────────────────────────


def get_previous_month(year_month: str) -> str:
    """
    Return the month preceding *year_month* as a YYYY-MM string.

    :param year_month: A year-month string in YYYY-MM format.
    :return: The previous month in YYYY-MM format.
    """
    parts = year_month.split("-", 1)
    if (
        len(parts) != 2
        or len(parts[0]) != 4
        or len(parts[1]) != 2
        or not parts[0].isdigit()
        or not parts[1].isdigit()
    ):
        raise ValueError(
            f"Invalid year_month format: {year_month!r}. Expected YYYY-MM."
        )

    year, month = parts
    month_int = int(month)
    if not 1 <= month_int <= 12:
        raise ValueError(f"Invalid month in year_month: {year_month!r}.")

    if month == "01":
        previous_year = int(year) - 1
        previous_month = 12
    else:
        previous_year = int(year)
        previous_month = month_int - 1

    return f"{previous_year}-{previous_month:02d}"


def messaging_months_elapsed() -> int:
    """
    Return the number of months elapsed since May 2016, when the
    r/translator redesign was implemented. Used to assess average
    posts per language for notifications.

    :return: Number of months since May 2016.
    """
    # May 2016 corresponds to 2016 * 12 + 5 = 24197 (January = 1)
    month_beginning = 2016 * 12 + 5

    today = datetime.now(UTC).date()
    total_current_months = today.year * 12 + today.month

    return total_current_months - month_beginning
