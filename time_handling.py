#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
Handles time-related conversion tasks.
Adherence to ISO 8601 or timestamps is strongly emphasized.
"""

from datetime import date, datetime, timezone


def get_current_utc_time() -> str:
    """Returns the current UTC time as a string"""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def time_convert_to_string(unix_integer: int | float) -> str:
    """
    Converts a UNIX timestamp to an ISO 8601 UTC time string.

    :param unix_integer: UNIX time as an int or float.
    :return: ISO 8601 formatted UTC time string
             (e.g., '2025-07-11T03:21:00Z').
    """
    return datetime.fromtimestamp(int(unix_integer), tz=timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )


def time_convert_to_utc(iso_str: str) -> str:
    """Convert an ISO-8601 timestamp (with offset) to UTC ISO string."""
    try:
        dt = datetime.fromisoformat(iso_str)
        return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except (TypeError, ValueError, AttributeError):
        return iso_str  # fallback if malformed or missing


def convert_to_day(unix_integer: int | float) -> str:
    """
    Converts a UNIX timestamp to a UTC date string (YYYY-MM-DD).

    :param unix_integer: UNIX time as an int or float.
    :return: UTC date string, e.g., '2025-07-11'.
    """
    return datetime.fromtimestamp(int(unix_integer), tz=timezone.utc).strftime(
        "%Y-%m-%d"
    )


def get_current_local_date() -> str:
    """Return the current local date in YYYY-MM-DD format. Unused."""
    return datetime.now().strftime("%Y-%m-%d")


def get_current_utc_date() -> str:
    """Return the current UTC date in YYYY-MM-DD format."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def get_current_month() -> str:
    """Return the current UTC month in YYYY-MM format."""
    return datetime.now(timezone.utc).strftime("%Y-%m")


def get_previous_month(year_month: str) -> str:
    """Give this function a year-month string, and it will return the
    previous month as a string in the same format."""

    year, month = year_month.split("-", 1)
    if month == "01":
        previous_year = int(year) - 1
        previous_month = 12
    else:
        previous_year = int(year)
        previous_month = int(month) - 1
        if previous_month < 10:
            previous_month = f"0{previous_month}"

    previous = f"{previous_year}-{previous_month}"

    return previous


def messaging_months_elapsed() -> int:
    """
    Returns the number of months of statistics since May 2016,
    when the r/translator redesign was implemented. This is used
    to assess average posts per language for notifications.

    :return: Number of months since May 2016.
    """
    # May 2016 corresponds to 2016 * 12 + 5 = 24197 (January = 1)
    month_beginning = 2016 * 12 + 5

    today = date.today()
    total_current_months = today.year * 12 + today.month

    return total_current_months - month_beginning
