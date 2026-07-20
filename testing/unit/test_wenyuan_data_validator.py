#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""Unit tests for Wenyuan data-file validation."""

from wenyuan.data_validator import (
    _extract_date_from_text,
    _get_last_date_from_log,
)


def test_extract_date_from_iso_timestamp() -> None:
    assert _extract_date_from_text("2026-07-19T19:31:14Z") == "2026-07-19"


def test_events_log_uses_latest_timestamp_not_report_filename(tmp_path) -> None:
    events_log = tmp_path / "log_events.md"
    events_log.write_text(
        "\n".join(
            [
                (
                    "INFO: 2026-07-16T00:00:39Z - Report saved to "
                    "/reports/2026-07/2026-07-15.md"
                ),
                "INFO: 2026-07-19T19:31:14Z - Run complete.",
            ]
        ),
        encoding="utf-8",
    )

    assert _get_last_date_from_log(str(events_log), "EVENTS") == "2026-07-19"
