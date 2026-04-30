#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
Unit tests for time_handling.py
"""

import pytest

from time_handling import (
    get_previous_month,
    time_convert_to_string_seconds,
    time_convert_to_utc,
)


def test_time_convert_to_utc_accepts_z_suffix():
    assert time_convert_to_utc("2024-01-15T12:30:00Z") == "2024-01-15T12:30:00Z"


def test_time_convert_to_utc_returns_naive_input_unchanged():
    naive = "2024-01-15T12:30:00"
    assert time_convert_to_utc(naive) == naive


def test_time_convert_to_string_seconds_handles_pluralization_and_negative():
    assert time_convert_to_string_seconds(1) == "1 second"
    assert time_convert_to_string_seconds(61) == "1 minute"
    assert time_convert_to_string_seconds(3600) == "1 hour"
    assert time_convert_to_string_seconds(3661) == "1 hour, 1 minute"
    assert time_convert_to_string_seconds(86400) == "1 day"
    assert time_convert_to_string_seconds(-5) == "0 seconds"


def test_get_previous_month_valid_and_invalid_inputs():
    assert get_previous_month("2024-01") == "2023-12"
    assert get_previous_month("2024-12") == "2024-11"

    with pytest.raises(ValueError):
        get_previous_month("2024-00")

    with pytest.raises(ValueError):
        get_previous_month("2024-13")

    with pytest.raises(ValueError):
        get_previous_month("2024-1")
