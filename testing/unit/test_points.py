import sqlite3
import sys
import types
import unittest
from unittest.mock import patch

sys.modules.setdefault("isodate", types.ModuleType("isodate"))

import monitoring.points as points


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


if __name__ == "__main__":
    unittest.main()
