import importlib
import sqlite3
import sys
import types
import unittest
from unittest.mock import patch

sys.modules.setdefault("isodate", types.ModuleType("isodate"))

points = importlib.import_module("monitoring.points")


class _FakeDb:
    def __init__(self) -> None:
        self.conn_main = sqlite3.connect(":memory:")
        self.cursor_main = self.conn_main.cursor()
        self.cursor_main.execute(
            """
            CREATE TABLE total_points (
                year_month TEXT,
                comment_id TEXT,
                username TEXT,
                points INTEGER,
                post_id TEXT
            )
            """
        )
        self.conn_main.commit()

    def fetchall_main(self, query: str, params: tuple = ()) -> list[dict]:
        cursor = self.conn_main.execute(query, params)
        columns = [description[0] for description in cursor.description]
        return [dict(zip(columns, row, strict=True)) for row in cursor.fetchall()]


class TestMonthPointsSummary(unittest.TestCase):
    def test_formats_ranked_points_and_applies_existing_filters(self) -> None:
        fake_db = _FakeDb()
        fake_db.cursor_main.executemany(
            "INSERT INTO total_points VALUES (?, ?, ?, ?, ?)",
            [
                ("2026-05", "c1", "helper_one", 5, "post1"),
                ("2026-05", "c2", "helper_one", 7, "post2"),
                ("2026-04", "c3", "helper_one", 3, "post3"),
                ("2026-05", "c4", "other", 8, "post4"),
                ("2026-05", "c5", "below_threshold", 4, "post5"),
                ("2026-05", "c6", "AutoModerator", 100, "post6"),
            ],
        )
        fake_db.conn_main.commit()

        with (
            patch.object(points, "db", fake_db),
            patch.object(
                points,
                "WENJU_SETTINGS",
                {
                    "minimum_points_display_threshold": 5,
                    "points_exclude_usernames": ["AutoModerator"],
                },
            ),
        ):
            summary = points.get_month_points_summary("2026-05")

        helper_row = "| u\\/helper\\_one | 12 | 15 | 2 posts | 3 posts |"
        other_row = "| u\\/other | 8 | 8 | 1 posts | 1 posts |"
        self.assertIn("| Username | Points in 2026-05 |", summary)
        self.assertIn(helper_row, summary)
        self.assertIn(other_row, summary)
        self.assertLess(summary.index(helper_row), summary.index(other_row))
        self.assertNotIn("below_threshold", summary)
        self.assertNotIn("AutoModerator", summary)


class TestPointRecordReplacement(unittest.TestCase):
    def test_replaces_existing_comment_rows_instead_of_appending(self) -> None:
        fake_db = _FakeDb()
        fake_db.cursor_main.executemany(
            "INSERT INTO total_points VALUES (?, ?, ?, ?, ?)",
            [
                ("2026-04", "abc123", "translator_a", 5, "post1"),
                ("2026-04", "abc123", "translator_a", 5, "post1"),
                ("2026-04", "other", "translator_b", 2, "post2"),
            ],
        )
        fake_db.conn_main.commit()

        with (
            patch.object(points, "db", fake_db),
            patch.object(points, "get_current_month", return_value="2026-05"),
        ):
            points._replace_comment_point_records(
                "abc123", [["translator_a", 7], ["helper", 1]], "post1"
            )

        rows = fake_db.cursor_main.execute(
            """
            SELECT year_month, comment_id, username, points, post_id
            FROM total_points
            ORDER BY comment_id, username
            """
        ).fetchall()

        self.assertEqual(
            rows,
            [
                ("2026-05", "abc123", "helper", 1, "post1"),
                ("2026-05", "abc123", "translator_a", 7, "post1"),
                ("2026-04", "other", "translator_b", 2, "post2"),
            ],
        )

    def test_skips_excluded_usernames_when_writing_comment_rows(self) -> None:
        fake_db = _FakeDb()

        with (
            patch.object(points, "db", fake_db),
            patch.object(points, "get_current_month", return_value="2026-05"),
            patch.object(
                points,
                "WENJU_SETTINGS",
                {"points_exclude_usernames": ["AutoModerator", "translator-BOT"]},
            ),
        ):
            points._replace_comment_point_records(
                "abc123",
                [["helper", 1], ["automoderator", 7], ["translator-BOT", 20]],
                "post1",
            )

        rows = fake_db.cursor_main.execute(
            """
            SELECT year_month, comment_id, username, points, post_id
            FROM total_points
            """
        ).fetchall()

        self.assertEqual(rows, [("2026-05", "abc123", "helper", 1, "post1")])


class TestPointsPolicySettings(unittest.TestCase):
    def test_unknown_language_value_uses_primary_settings(self) -> None:
        lingvo = types.SimpleNamespace(preferred_code="unknown")

        with patch.dict(points.SETTINGS, {"points_unknown_language_value": 9}):
            result = points.points_worth_determiner(lingvo)

        self.assertEqual(result, 9)


if __name__ == "__main__":
    unittest.main()
