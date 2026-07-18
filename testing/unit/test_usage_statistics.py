import unittest
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import orjson

import monitoring.action_statistics as action_statistics
import monitoring.language_frequency as language_frequency
import monitoring.user_statistics as user_statistics

# noinspection PyProtectedMember
from monitoring.user_statistics import _canonical_notification_language_code


class TestActionCounter(unittest.TestCase):
    def test_records_action_and_sends_discord_log(self) -> None:
        with TemporaryDirectory() as temp_dir:
            counter_path = Path(temp_dir) / "counter.json"

            with (
                patch.object(
                    action_statistics.Paths,
                    "LOGS",
                    {"COUNTER": str(counter_path)},
                ),
                patch.object(
                    action_statistics,
                    "get_current_utc_date",
                    return_value="2026-05-03",
                ),
                patch.object(action_statistics, "send_discord_alert") as alert_mock,
            ):
                action_statistics.action_counter(2, "Notifications")

            self.assertEqual(
                orjson.loads(counter_path.read_bytes()),
                {"2026-05-03": {"Notifications": 2}},
            )
            alert_mock.assert_called_once_with(
                "Ziwen Logging",
                ("**Action:** `Notifications`\n**Recorded:** `2`\n"),
                "logs",
            )

    def test_skipped_action_does_not_send_discord_log(self) -> None:
        with (
            patch.object(action_statistics.Paths, "LOGS", {"COUNTER": "unused.json"}),
            patch.object(action_statistics, "send_discord_alert") as alert_mock,
        ):
            action_statistics.action_counter(0, "Notifications")

        alert_mock.assert_not_called()


class TestActionDailyAverages(unittest.TestCase):
    def test_returns_sorted_structured_averages(self) -> None:
        with TemporaryDirectory() as temp_dir:
            counter_path = Path(temp_dir) / "counter.json"
            counter_path.write_bytes(
                orjson.dumps(
                    {
                        "2026-05-01": {"Notifications": 6, "New posts": 3},
                        "2026-05-02": {"Notifications": 3, "New posts": 1},
                        "2026-04-30": {"Notifications": 100},
                        "malformed": {"Notifications": 100},
                    }
                )
            )
            start = int(datetime(2026, 5, 1, tzinfo=UTC).timestamp())
            end = int(datetime(2026, 5, 2, 23, 59, tzinfo=UTC).timestamp())

            with patch.object(
                action_statistics.Paths, "LOGS", {"COUNTER": str(counter_path)}
            ):
                result = action_statistics.get_action_daily_averages(start, end, 2)

        self.assertEqual(
            result,
            [
                {"name": "New posts", "count": 2.0},
                {"name": "Notifications", "count": 4.5},
            ],
        )

    def test_rejects_nonpositive_period(self) -> None:
        with self.assertRaisesRegex(ValueError, "greater than zero"):
            action_statistics.get_action_daily_averages(0, 1, 0)


class TestNotificationStatsFormatting(unittest.TestCase):
    def test_duplicate_script_key_is_canonicalized(self) -> None:
        self.assertEqual(
            _canonical_notification_language_code("teng-teng"), "unknown-teng"
        )

    def test_regional_language_key_is_preserved(self) -> None:
        self.assertEqual(_canonical_notification_language_code("pt-pt"), "pt-pt")

    def test_existing_unknown_script_key_is_preserved(self) -> None:
        self.assertEqual(
            _canonical_notification_language_code("unknown-teng"), "unknown-teng"
        )


class TestUserStatistics(unittest.TestCase):
    def test_loader_formats_commands_and_merges_canonical_notifications(self) -> None:
        cursor = MagicMock()
        cursor.fetchone.side_effect = [
            ("example_user", b'{"!translated:":2,"Notifications":99,"`":1}'),
            ("example_user", b'{"teng-teng":2,"unknown-teng":3}'),
        ]

        with patch.object(
            user_statistics,
            "db",
            SimpleNamespace(cursor_main=cursor),
        ):
            result = user_statistics.user_statistics_loader("example_user")

        self.assertEqual(
            result,
            (
                "| Commands/Notifications | Times |\n"
                "|--------|------|\n"
                "| lookup_cjk | 1 |\n"
                "| translated | 2 |\n"
                "| Notifications (`unknown-teng`) | 5 |"
            ),
        )

    def test_writer_inserts_serialized_command_counts(self) -> None:
        cursor = MagicMock()
        cursor.fetchone.return_value = None
        connection = MagicMock()
        instruo = SimpleNamespace(
            author_comment="example_user",
            commands=[
                SimpleNamespace(name="identify"),
                SimpleNamespace(name="identify"),
                SimpleNamespace(name="translated"),
            ],
        )

        with patch.object(
            user_statistics,
            "db",
            SimpleNamespace(cursor_main=cursor, conn_main=connection),
        ):
            user_statistics.user_statistics_writer(instruo)

        insert_call = cursor.execute.call_args_list[1]
        self.assertIn("INSERT INTO total_commands", insert_call.args[0])
        self.assertEqual(insert_call.args[1][0], "example_user")
        self.assertEqual(
            orjson.loads(insert_call.args[1][1]),
            {"identify": 2, "translated": 1},
        )
        connection.commit.assert_called_once_with()


class TestLanguageFrequencyMarkdown(unittest.TestCase):
    def test_frequency_table_includes_language_code_in_linked_name(self) -> None:
        language = SimpleNamespace(
            name="Volapuk",
            preferred_code="vo",
            link_statistics="https://example.test/vo",
            rate_daily=0.0003,
            rate_monthly=0.01,
            rate_yearly=0.12,
        )

        markdown = language_frequency.generate_language_frequency_markdown([language])

        self.assertIn(
            "| [Volapuk (`vo`)](https://example.test/vo)        | 0.12 posts              | year |",
            markdown,
        )

    def test_frequency_table_includes_language_code_without_statistics(self) -> None:
        language = SimpleNamespace(
            name="Example",
            preferred_code="ex",
            link_statistics=None,
            rate_daily=None,
            rate_monthly=None,
            rate_yearly=None,
        )

        markdown = language_frequency.generate_language_frequency_markdown([language])

        self.assertIn(
            "| Example (`ex`)        | No recorded statistics     | ---   |",
            markdown,
        )


if __name__ == "__main__":
    unittest.main()
