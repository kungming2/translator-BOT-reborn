import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

import orjson

import monitoring.usage_statistics as usage_statistics
# noinspection PyProtectedMember
from monitoring.usage_statistics import (_canonical_notification_language_code,
                                         action_counter,
                                         generate_language_frequency_markdown)


class TestActionCounter(unittest.TestCase):
    def test_records_action_and_sends_discord_log(self) -> None:
        with TemporaryDirectory() as temp_dir:
            counter_path = Path(temp_dir) / "counter.json"

            with (
                patch.object(
                    usage_statistics.Paths,
                    "LOGS",
                    {"COUNTER": str(counter_path)},
                ),
                patch.object(
                    usage_statistics, "get_current_utc_date", return_value="2026-05-03"
                ),
                patch.object(usage_statistics, "send_discord_alert") as alert_mock,
            ):
                action_counter(2, "Notifications")

            self.assertEqual(
                orjson.loads(counter_path.read_bytes()),
                {"2026-05-03": {"Notifications": 2}},
            )
            alert_mock.assert_called_once_with(
                "Ziwen Logging",
                (
                    "**Action:** `Notifications`\n"
                    "**Recorded:** `2`\n"
                ),
                "logs",
            )

    def test_skipped_action_does_not_send_discord_log(self) -> None:
        with (
            patch.object(usage_statistics.Paths, "LOGS", {"COUNTER": "unused.json"}),
            patch.object(usage_statistics, "send_discord_alert") as alert_mock,
        ):
            action_counter(0, "Notifications")

        alert_mock.assert_not_called()


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

        markdown = generate_language_frequency_markdown([language])

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

        markdown = generate_language_frequency_markdown([language])

        self.assertIn(
            "| Example (`ex`)        | No recorded statistics     | ---   |",
            markdown,
        )


if __name__ == "__main__":
    unittest.main()
