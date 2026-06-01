import unittest

from calendar_handling import convert_calendar_payload


class TestConvertCalendarPayload(unittest.TestCase):
    def test_chinese_cycle_year_alias_matches_bare_cycle_year(self) -> None:
        self.assertEqual(
            convert_calendar_payload("chinese:乙巳"),
            convert_calendar_payload("乙巳"),
        )

    def test_chinese_cycle_year_alias_accepts_pinyin(self) -> None:
        self.assertEqual(
            convert_calendar_payload("chinese:yisi"),
            convert_calendar_payload("yisi"),
        )

    def test_lunar_cycle_year_alias_matches_bare_cycle_year(self) -> None:
        self.assertEqual(
            convert_calendar_payload("lunar:乙巳"),
            convert_calendar_payload("乙巳"),
        )


if __name__ == "__main__":
    unittest.main()
