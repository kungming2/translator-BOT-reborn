import unittest

from calendar_handling import convert_calendar_payload, format_calendar_query


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


class TestFormatCalendarQuery(unittest.TestCase):
    def test_pinyin_cycle_year_includes_characters(self) -> None:
        self.assertEqual(format_calendar_query("dingwei"), "dingwei (丁未)")

    def test_character_cycle_year_includes_pinyin(self) -> None:
        self.assertEqual(format_calendar_query("丁未"), "丁未 (dingwei)")

    def test_chinese_dated_payload_formats_cycle_year(self) -> None:
        self.assertEqual(
            format_calendar_query("chinese:dingwei:4:13"),
            "chinese:dingwei (丁未):4:13",
        )

    def test_non_chinese_payload_is_unchanged(self) -> None:
        self.assertEqual(
            format_calendar_query("hebrew:5784:Tishrei:1"),
            "hebrew:5784:Tishrei:1",
        )


if __name__ == "__main__":
    unittest.main()
