import unittest

from monitoring.usage_statistics import _canonical_notification_language_code


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
