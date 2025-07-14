#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
Handles time-related conversion tasks.
Adherence to ISO 8601 or timestamps is strongly emphasized.
"""
import time
from datetime import datetime, timezone


def time_convert_to_string(unix_integer):
    """
    Converts a UNIX timestamp to an ISO 8601 UTC time string.

    :param unix_integer: UNIX time as an int or float.
    :return: ISO 8601 formatted UTC time string
             (e.g., '2025-07-11T03:21:00Z').
    """
    return datetime.fromtimestamp(int(unix_integer), tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def get_previous_month(year_month):
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


YEAR_MONTH_NOW = time.strftime("%Y-%m")
