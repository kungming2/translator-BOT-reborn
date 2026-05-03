import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import orjson

from monitoring.usage_statistics import (
    _canonical_notification_language_code,
    action_counter,
)


class TestActionCounter(unittest.TestCase):
    def test_records_action_and_sends_discord_log(self) -> None:
        with TemporaryDirectory() as temp_dir:
            counter_path = Path(temp_dir) / "counter.json"

            with (
                patch(
                    "monitoring.usage_statistics.Paths.LOGS",
                    {"COUNTER": str(counter_path)},
                ),
                patch(
                    "monitoring.usage_statistics.get_current_utc_date",
                    return_value="2026-05-03",
                ),
                patch(
                    "monitoring.usage_statistics.send_discord_alert"
                ) as alert_mock,
            ):
                action_counter(2, "Notifications")

            self.assertEqual(
                orjson.loads(counter_path.read_bytes()),
                {"2026-05-03": {"Notifications": 2}},
            )
            alert_mock.assert_called_once_with(
                "Action Counter",
                (
                    "Action: `Notifications`\n"
                    "Recorded: `2`\n"
                    "Daily total: `2`\n"
                    "Date: `2026-05-03`"
                ),
                "logs",
            )

    def test_skipped_action_does_not_send_discord_log(self) -> None:
        with (
            patch("monitoring.usage_statistics.Paths.LOGS", {"COUNTER": "unused.json"}),
            patch("monitoring.usage_statistics.send_discord_alert") as alert_mock,
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


if __name__ == "__main__":
    unittest.main()
