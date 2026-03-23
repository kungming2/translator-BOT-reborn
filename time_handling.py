#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
Handles time-related conversion tasks.
Adherence to ISO 8601 or timestamps is strongly emphasized.
...

Logger tag: [TIME]
"""

# ─── Imports ──────────────────────────────────────────────────────────────────

from datetime import date, datetime, timezone

# ─── Current time & date ──────────────────────────────────────────────────────


def get_current_utc_time() -> str:
    """Return the current UTC time as an ISO 8601 string."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def get_current_utc_date() -> str:
    """Return the current UTC date in YYYY-MM-DD format."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def get_current_local_date() -> str:
    """Return the current local date in YYYY-MM-DD format. Unused."""
    return datetime.now().strftime("%Y-%m-%d")


def get_current_month() -> str:
    """Return the current UTC month in YYYY-MM format."""
    return datetime.now(timezone.utc).strftime("%Y-%m")


# ─── Timestamp conversion ─────────────────────────────────────────────────────


def time_convert_to_string(unix_integer: int | float) -> str:
    """
    Convert a UNIX timestamp to an ISO 8601 UTC time string.

    :param unix_integer: UNIX time as an int or float.
    :return: ISO 8601 formatted UTC time string
             (e.g., '2025-07-11T03:21:00Z').
    """
    return datetime.fromtimestamp(int(unix_integer), tz=timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )


def time_convert_to_utc(iso_str: str) -> str:
    """
    Convert an ISO 8601 timestamp (with offset) to a UTC ISO string.
    Returns the original string unchanged if it is malformed or missing.
    """
    try:
        dt = datetime.fromisoformat(iso_str)
        return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except (TypeError, ValueError, AttributeError):
        return iso_str


def convert_to_day(unix_integer: int | float) -> str:
    """
    Convert a UNIX timestamp to a UTC date string (YYYY-MM-DD).

    :param unix_integer: UNIX time as an int or float.
    :return: UTC date string, e.g., '2025-07-11'.
    """
    return datetime.fromtimestamp(int(unix_integer), tz=timezone.utc).strftime(
        "%Y-%m-%d"
    )


def time_convert_to_string_seconds(seconds: int) -> str:
    """
    Convert a duration in seconds to a human-readable time string.

    Args:
        seconds: Time in seconds.

    Returns:
        Formatted time string (e.g., '2 hours, 15 minutes').
    """
    if seconds < 60:
        return f"{seconds} seconds"
    elif seconds < 3600:
        minutes = seconds // 60
        return f"{minutes} minutes"
    elif seconds < 86400:
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        return f"{hours} hours, {minutes} minutes"
    else:
        days = seconds // 86400
        hours = (seconds % 86400) // 3600
        return f"{days} days, {hours} hours"


# ─── Month arithmetic ─────────────────────────────────────────────────────────


def get_previous_month(year_month: str) -> str:
    """
    Return the month preceding *year_month* as a YYYY-MM string.

    :param year_month: A year-month string in YYYY-MM format.
    :return: The previous month in YYYY-MM format.
    """
    year, month = year_month.split("-", 1)
    if month == "01":
        previous_year = int(year) - 1
        previous_month = 12
    else:
        previous_year = int(year)
        previous_month = int(month) - 1

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

    today = date.today()
    total_current_months = today.year * 12 + today.month

    return total_current_months - month_beginning
