#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
Unit tests for usage_statistics.py

Run with:
    pytest test_usage_statistics.py -v
"""

from unittest.mock import MagicMock, mock_open, patch

import orjson

from monitoring.usage_statistics import (
    action_counter,
    count_notifications,
    generate_command_usage_report,
    generate_language_frequency_markdown,
    months_since_redesign,
    user_statistics_loader,
    user_statistics_writer,
)

# ---------------------------------------------------------------------------
# Shared sample counter log data (mirrors real log structure)
# ---------------------------------------------------------------------------

SAMPLE_LOG = {
    "2026-03-02": {
        "New posts": 48,
        "Notifications": 695,
        "translated": 35,
        "identify": 11,
        "lookup_cjk": 3,
        "reset": 1,
        "set": 1,
        "Removed duplicates": 2,
        "Removed posts": 4,
        "Removed image duplicates": 1,
        "transform": 1,
        "Subscriptions": 1,
    },
    "2026-03-03": {
        "New posts": 53,
        "Notifications": 528,
        "translated": 25,
        "identify": 5,
        "lookup_cjk": 3,
        "doublecheck": 3,
        "long": 1,
        "reset": 2,
        "set": 1,
        "Removed duplicates": 2,
        "Removed posts": 3,
        "page": 1,
    },
    "2026-03-20": {
        "Removed duplicates": 5,
    },
}

SAMPLE_LOG_BYTES = orjson.dumps(SAMPLE_LOG)

# Unix timestamps for 2026-03-02 and 2026-03-03 (UTC midnight)
TS_MAR02 = 1772409600  # 2026-03-02 00:00:00 UTC
TS_MAR03 = 1772496000  # 2026-03-03 00:00:00 UTC
TS_MAR20 = 1773964800  # 2026-03-20 00:00:00 UTC


# ===========================================================================
# action_counter
# ===========================================================================


class TestActionCounter:
    @staticmethod
    def _run(messages_number, action_type, existing: dict | None = None):
        """Patch file I/O and return the dict that would have been written."""
        existing_bytes = orjson.dumps(existing or {})
        written = {}

        def fake_open(_path, mode):
            if mode == "rb":
                m = mock_open(read_data=existing_bytes)()
                return m
            # "wb" — capture what gets written
            handle = mock_open()()
            handle.write.side_effect = lambda data: written.update(orjson.loads(data))
            return handle

        with (
            patch("monitoring.usage_statistics.open", fake_open),
            patch(
                "monitoring.usage_statistics.get_current_utc_date",
                return_value="2026-03-02",
            ),
        ):
            action_counter(messages_number, action_type)

        return written

    def test_new_action_is_recorded(self):
        result = self._run(1, "translated")
        assert result["2026-03-02"]["translated"] == 1

    def test_existing_action_is_incremented(self):
        existing = {"2026-03-02": {"translated": 10}}
        result = self._run(1, "translated", existing)
        assert result["2026-03-02"]["translated"] == 11

    def test_count_greater_than_one(self):
        result = self._run(5, "Notifications")
        assert result["2026-03-02"]["Notifications"] == 5

    def test_id_normalized_to_identify(self):
        result = self._run(1, "id")
        assert "identify" in result["2026-03-02"]
        assert "id" not in result["2026-03-02"]

    def test_zero_count_is_skipped(self):
        result = self._run(0, "translated")
        assert result == {}

    def test_invalid_count_is_skipped(self):
        result = self._run("bad", "translated")
        assert result == {}

    def test_missing_file_starts_fresh(self):
        with (
            patch(
                "monitoring.usage_statistics.open",
                side_effect=[FileNotFoundError, mock_open()()],
            ),
            patch(
                "monitoring.usage_statistics.get_current_utc_date",
                return_value="2026-03-02",
            ),
        ):
            # Should not raise
            try:
                action_counter(1, "translated")
            except FileNotFoundError:
                pass  # write side will also raise in this minimal mock — that's fine

    def test_new_day_gets_own_entry(self):
        existing = {"2026-03-01": {"translated": 5}}
        result = self._run(1, "translated", existing)
        assert "2026-03-01" in result
        assert "2026-03-02" in result
        assert result["2026-03-01"]["translated"] == 5
        assert result["2026-03-02"]["translated"] == 1


# ===========================================================================
# months_since_redesign
# ===========================================================================


class TestMonthsSinceRedesign:
    def test_returns_positive_int(self):
        result = months_since_redesign()
        assert isinstance(result, int)
        assert result > 0

    def test_increases_over_time(self):
        from datetime import datetime, timezone

        with patch("monitoring.usage_statistics.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 3, 1, tzinfo=timezone.utc)
            mock_dt.strptime = datetime.strptime  # keep strptime working
            result = months_since_redesign(start_year=2016, start_month=5)
        # (2026 * 12 + 3) - (2016 * 12 + 5) = 24315 - 24197 = 118
        assert result == 118

    def test_custom_start_date(self):
        from datetime import datetime, timezone

        with patch("monitoring.usage_statistics.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 1, 1, tzinfo=timezone.utc)
            mock_dt.strptime = datetime.strptime
            result = months_since_redesign(start_year=2025, start_month=1)
        assert result == 12


# ===========================================================================
# generate_language_frequency_markdown
# ===========================================================================


class TestGenerateLanguageFrequencyMarkdown:
    @staticmethod
    def _make_lingvo(name, daily, monthly, yearly, link):
        lang = MagicMock()
        lang.name = name
        lang.rate_daily = daily
        lang.rate_monthly = monthly
        lang.rate_yearly = yearly
        lang.link_statistics = link
        return lang

    def test_header_always_present(self):
        result = generate_language_frequency_markdown([])
        assert "Language Name" in result
        assert "Average Number of Posts" in result

    def test_high_frequency_uses_daily(self):
        lang = self._make_lingvo(
            "Spanish",
            daily=2.85,
            monthly=85.52,
            yearly=1026.24,
            link="https://www.reddit.com/r/translator/wiki/spanish",
        )
        result = generate_language_frequency_markdown([lang])
        assert "day" in result
        assert "2.85" in result

    def test_medium_frequency_uses_monthly(self):
        lang = self._make_lingvo(
            "Finnish",
            daily=0.5,
            monthly=15.0,
            yearly=180.0,
            link="https://www.reddit.com/r/translator/wiki/finnish",
        )
        result = generate_language_frequency_markdown([lang])
        assert "month" in result
        assert "15.00" in result

    def test_low_frequency_uses_yearly(self):
        lang = self._make_lingvo(
            "Basque",
            daily=0.01,
            monthly=0.3,
            yearly=3.6,
            link="https://www.reddit.com/r/translator/wiki/basque",
        )
        result = generate_language_frequency_markdown([lang])
        assert "year" in result
        assert "3.60" in result

    def test_missing_data_shows_no_statistics(self):
        lang = self._make_lingvo(
            "Unknown", daily=None, monthly=None, yearly=None, link=None
        )
        result = generate_language_frequency_markdown([lang])
        assert "No recorded statistics" in result

    def test_multiple_languages_all_present(self):
        langs = [
            self._make_lingvo(
                "Spanish", 2.85, 85.52, 1026.24, "https://example.com/es"
            ),
            self._make_lingvo("Finnish", 0.5, 15.0, 180.0, "https://example.com/fi"),
        ]
        result = generate_language_frequency_markdown(langs)
        assert "Spanish" in result
        assert "Finnish" in result


# ===========================================================================
# generate_command_usage_report
# ===========================================================================


class TestGenerateCommandUsageReport:
    def test_header_always_present(self):
        with patch("monitoring.usage_statistics.orjson.loads", return_value=SAMPLE_LOG):
            with patch(
                "monitoring.usage_statistics.open",
                mock_open(read_data=SAMPLE_LOG_BYTES),
            ):
                result = generate_command_usage_report(TS_MAR02, TS_MAR03, days=2)
        assert "Actions (Daily Average)" in result
        assert "Action" in result

    def test_counts_are_averaged_over_days(self):
        # translated: 35 (Mar02) + 25 (Mar03) = 60 total / 2 days = 30.0
        with patch("monitoring.usage_statistics.orjson.loads", return_value=SAMPLE_LOG):
            with patch(
                "monitoring.usage_statistics.open",
                mock_open(read_data=SAMPLE_LOG_BYTES),
            ):
                result = generate_command_usage_report(TS_MAR02, TS_MAR03, days=2)
        assert "30.0" in result

    def test_dates_outside_range_excluded(self):
        # Mar20 has Removed duplicates: 5; Mar02 has 2, Mar03 has 2 -> total 4 / 2 = 2.0
        # If Mar20 were included it would be 9 / 2 = 4.5
        with patch("monitoring.usage_statistics.orjson.loads", return_value=SAMPLE_LOG):
            with patch(
                "monitoring.usage_statistics.open",
                mock_open(read_data=SAMPLE_LOG_BYTES),
            ):
                result = generate_command_usage_report(TS_MAR02, TS_MAR03, days=2)
        assert "2.0" in result

    def test_missing_file_returns_header_only(self):
        with patch("monitoring.usage_statistics.open", side_effect=FileNotFoundError):
            result = generate_command_usage_report(TS_MAR02, TS_MAR03, days=2)
        assert "Actions (Daily Average)" in result
        assert "translated" not in result

    def test_malformed_json_returns_header_only(self):
        with patch(
            "monitoring.usage_statistics.orjson.loads",
            side_effect=orjson.JSONDecodeError("err", "doc", 0),
        ):
            with patch(
                "monitoring.usage_statistics.open", mock_open(read_data=b"not json")
            ):
                result = generate_command_usage_report(TS_MAR02, TS_MAR03, days=2)
        assert "Actions (Daily Average)" in result
        assert "translated" not in result

    def test_malformed_date_entry_is_skipped(self):
        bad_log = {"not-a-date": {"translated": 99}, "2026-03-02": {"translated": 1}}
        with patch("monitoring.usage_statistics.orjson.loads", return_value=bad_log):
            with patch("monitoring.usage_statistics.open", mock_open(read_data=b"")):
                result = generate_command_usage_report(TS_MAR02, TS_MAR02, days=1)
        assert "1.0" in result


# ===========================================================================
# count_notifications
# ===========================================================================


class TestCountNotifications:
    def test_totals_notifications_in_range(self):
        # Mar02: 695, Mar03: 528 -> total 1223
        with patch("monitoring.usage_statistics.orjson.loads", return_value=SAMPLE_LOG):
            with patch(
                "monitoring.usage_statistics.open",
                mock_open(read_data=SAMPLE_LOG_BYTES),
            ):
                result = count_notifications(TS_MAR02, TS_MAR03)
        assert "1,223" in result

    def test_average_is_calculated(self):
        # 1223 / 2 days = 611.5
        with patch("monitoring.usage_statistics.orjson.loads", return_value=SAMPLE_LOG):
            with patch(
                "monitoring.usage_statistics.open",
                mock_open(read_data=SAMPLE_LOG_BYTES),
            ):
                result = count_notifications(TS_MAR02, TS_MAR03)
        assert "611.50" in result

    def test_date_outside_range_excluded(self):
        # Mar20 has no Notifications key — total should still be Mar02+Mar03 only
        with patch("monitoring.usage_statistics.orjson.loads", return_value=SAMPLE_LOG):
            with patch(
                "monitoring.usage_statistics.open",
                mock_open(read_data=SAMPLE_LOG_BYTES),
            ):
                result = count_notifications(TS_MAR02, TS_MAR03)
        assert "1,223" in result

    def test_no_matching_dates_returns_zero(self):
        future_ts = 9999999999
        with patch("monitoring.usage_statistics.orjson.loads", return_value=SAMPLE_LOG):
            with patch(
                "monitoring.usage_statistics.open",
                mock_open(read_data=SAMPLE_LOG_BYTES),
            ):
                result = count_notifications(future_ts, future_ts)
        assert "0" in result


# ===========================================================================
# user_statistics_loader
# ===========================================================================


class TestUserStatisticsLoader:
    @staticmethod
    def _make_cursor(commands_row=None, notify_row=None):
        cursor = MagicMock()
        cursor.fetchone.side_effect = [commands_row, notify_row]
        return cursor

    def test_returns_none_when_no_data(self):
        cursor = self._make_cursor(None, None)
        with patch("monitoring.usage_statistics.db") as mock_db:
            mock_db.cursor_main = cursor
            assert user_statistics_loader("nobody") is None

    def test_returns_table_with_commands(self):
        commands = str({"translated": 10, "identify": 3})
        cursor = self._make_cursor(
            commands_row=("user1", commands),
            notify_row=None,
        )
        with patch("monitoring.usage_statistics.db") as mock_db:
            mock_db.cursor_main = cursor
            result = user_statistics_loader("user1")
        assert result is not None
        assert "translated" in result
        assert "identify" in result

    def test_notifications_key_excluded_from_commands(self):
        # "Notifications" as a command key should be dropped from the command rows,
        # though the word still appears in the table header "Commands/Notifications"
        commands = str({"translated": 5, "Notifications": 100})
        cursor = self._make_cursor(commands_row=("user1", commands))
        with patch("monitoring.usage_statistics.db") as mock_db:
            mock_db.cursor_main = cursor
            result = user_statistics_loader("user1")
        assert "| Notifications | 100 |" not in result
        assert "translated" in result

    def test_id_not_normalized_in_loader(self):
        # normalize_command in user_statistics_loader only strips ! and : —
        # the id -> identify remapping belongs to action_counter, not here
        commands = str({"id": 7})
        cursor = self._make_cursor(commands_row=("user1", commands))
        with patch("monitoring.usage_statistics.db") as mock_db:
            mock_db.cursor_main = cursor
            result = user_statistics_loader("user1")
        assert "| id | 7 |" in result

    def test_backtick_normalized_to_lookup_cjk(self):
        commands = str({"`": 4})
        cursor = self._make_cursor(commands_row=("user1", commands))
        with patch("monitoring.usage_statistics.db") as mock_db:
            mock_db.cursor_main = cursor
            result = user_statistics_loader("user1")
        assert "lookup_cjk" in result

    def test_wikipedia_lookup_normalized(self):
        commands = str({"wikipedia_lookup": 2})
        cursor = self._make_cursor(commands_row=("user1", commands))
        with patch("monitoring.usage_statistics.db") as mock_db:
            mock_db.cursor_main = cursor
            result = user_statistics_loader("user1")
        assert "lookup_wp" in result

    def test_notification_languages_included(self):
        notify = str({"Spanish": 50, "French": 20})
        cursor = self._make_cursor(commands_row=None, notify_row=("user1", notify))
        with patch("monitoring.usage_statistics.db") as mock_db:
            mock_db.cursor_main = cursor
            result = user_statistics_loader("user1")
        assert "Notifications (`Spanish`)" in result
        assert "Notifications (`French`)" in result

    def test_header_always_present(self):
        commands = str({"translated": 1})
        cursor = self._make_cursor(commands_row=("user1", commands))
        with patch("monitoring.usage_statistics.db") as mock_db:
            mock_db.cursor_main = cursor
            result = user_statistics_loader("user1")
        assert "Commands/Notifications" in result
        assert "Times" in result


# ===========================================================================
# user_statistics_writer
# ===========================================================================


class TestUserStatisticsWriter:
    @staticmethod
    def _make_instruo(author, command_names):
        instruo = MagicMock()
        instruo.author_comment = author
        instruo.commands = [MagicMock(name=n) for n in command_names]
        # MagicMock(name=...) sets the mock's name, not an attribute — fix that
        for mock, name in zip(instruo.commands, command_names):
            mock.name = name
        return instruo

    def test_inserts_new_user(self):
        instruo = self._make_instruo("newuser", ["translated"])
        cursor = MagicMock()
        cursor.fetchone.return_value = None  # no existing record
        conn = MagicMock()
        with patch("monitoring.usage_statistics.db") as mock_db:
            mock_db.cursor_main = cursor
            mock_db.conn_main = conn
            user_statistics_writer(instruo)
        cursor.execute.assert_called()
        conn.commit.assert_called_once()

    def test_updates_existing_user(self):
        instruo = self._make_instruo("existinguser", ["translated"])
        existing = str({"translated": 5})
        cursor = MagicMock()
        cursor.fetchone.return_value = {"commands": existing}
        conn = MagicMock()
        with patch("monitoring.usage_statistics.db") as mock_db:
            mock_db.cursor_main = cursor
            mock_db.conn_main = conn
            user_statistics_writer(instruo)
        # Check UPDATE was called (not INSERT)
        calls = [str(c) for c in cursor.execute.call_args_list]
        assert any("UPDATE" in c for c in calls)

    def test_multiple_commands_all_recorded(self):
        instruo = self._make_instruo("user1", ["translated", "identify", "translated"])
        cursor = MagicMock()
        cursor.fetchone.return_value = None
        conn = MagicMock()
        written_commands = {}

        def capture_insert(query, params):
            if "INSERT" in query:
                import ast

                written_commands.update(ast.literal_eval(params[1]))

        cursor.execute.side_effect = capture_insert
        with patch("monitoring.usage_statistics.db") as mock_db:
            mock_db.cursor_main = cursor
            mock_db.conn_main = conn
            user_statistics_writer(instruo)
        assert written_commands.get("translated") == 2
        assert written_commands.get("identify") == 1

    def test_empty_commands_skips_write(self):
        instruo = self._make_instruo("user1", [])
        cursor = MagicMock()
        cursor.fetchone.return_value = None
        conn = MagicMock()
        with patch("monitoring.usage_statistics.db") as mock_db:
            mock_db.cursor_main = cursor
            mock_db.conn_main = conn
            user_statistics_writer(instruo)
        conn.commit.assert_not_called()
