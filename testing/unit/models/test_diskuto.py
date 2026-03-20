#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
Unit tests for the Diskuto model class and its database helper functions.

Run with:
    pytest test_diskuto.py -v
"""

from unittest.mock import MagicMock, patch

import orjson
import pytest

from models.diskuto import Diskuto, diskuto_exists, diskuto_loader, diskuto_writer

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_praw_submission(
    *,
    post_id: str = "1rorpb8",
    title: str = "[Community] Translation Challenge — 2026-03-09",
    created_utc: float = 1773034258.0,
    author_name: str = "translatorbot",
    permalink: str = "/r/translator/comments/1rorpb8/community_translation_challenge/",
) -> MagicMock:
    """Return a minimal mock PRAW Submission."""
    sub = MagicMock()
    sub.id = post_id
    sub.title = title
    sub.created_utc = created_utc
    sub.author.name = author_name
    sub.permalink = permalink
    sub.comments.list.return_value = []
    return sub


# ===========================================================================
# Diskuto tests
# ===========================================================================


class TestDiskutoInit:
    def test_defaults(self):
        d = Diskuto()
        assert d.id is None
        assert d.title_original is None
        assert d.post_type is None
        assert d.created_utc is None
        assert d.processed is False

    def test_explicit_values(self):
        d = Diskuto(
            title_original="[META] r/translator Statistics – February 2026",
            post_type="meta",
            _id="1rp89hl",
            created_utc=1773080693,
            processed=True,
        )
        assert d.id == "1rp89hl"
        assert d.title_original == "[META] r/translator Statistics – February 2026"
        assert d.post_type == "meta"
        assert d.created_utc == 1773080693
        assert d.processed is True


class TestDiskutoReprStr:
    @staticmethod
    def _make():
        return Diskuto(
            title_original="[META] Weekly Thread",
            post_type="meta",
            _id="1rqmxid",
            created_utc=1773213188,
            processed=False,
        )

    def test_repr_contains_id(self):
        assert "1rqmxid" in repr(self._make())

    def test_repr_contains_type(self):
        assert "meta" in repr(self._make())

    def test_str_contains_all_fields(self):
        s = str(self._make())
        assert "1rqmxid" in s
        assert "meta" in s
        assert "1773213188" in s
        assert "False" in s


class TestDiskutoToDict:
    def test_keys_present(self):
        d = Diskuto(
            title_original="[Community] Challenge",
            post_type="community",
            _id="1rorpb8",
            created_utc=1773034258,
            processed=True,
        )
        assert set(d.to_dict().keys()) == {
            "id",
            "created_utc",
            "title_original",
            "post_type",
            "processed",
        }

    def test_values_match(self):
        d = Diskuto(
            title_original="[Community] Challenge",
            post_type="community",
            _id="1rorpb8",
            created_utc=1773034258,
            processed=True,
        )
        result = d.to_dict()
        assert result["id"] == "1rorpb8"
        assert result["post_type"] == "community"
        assert result["processed"] is True


class TestDiskutoToggleProcessed:
    def test_false_to_true(self):
        d = Diskuto(processed=False)
        d.toggle_processed()
        assert d.processed is True

    def test_true_to_false(self):
        d = Diskuto(processed=True)
        d.toggle_processed()
        assert d.processed is False

    def test_double_toggle_returns_original(self):
        d = Diskuto(processed=False)
        d.toggle_processed()
        d.toggle_processed()
        assert d.processed is False


class TestDiskutoProcessPost:
    def test_community_post(self):
        sub = make_praw_submission(
            post_id="1rorpb8",
            title="[Community] Translation Challenge — 2026-03-09",
            created_utc=1773034258.0,
        )
        d = Diskuto.process_post(sub)
        assert d.id == "1rorpb8"
        assert d.post_type == "community"
        assert d.title_original == "[Community] Translation Challenge — 2026-03-09"
        assert d.created_utc == 1773034258
        assert d.processed is False

    def test_meta_post(self):
        sub = make_praw_submission(
            post_id="1rp89hl",
            title="[META] r/translator Statistics – February 2026",
            created_utc=1773080693.0,
        )
        d = Diskuto.process_post(sub)
        assert d.id == "1rp89hl"
        assert d.post_type == "meta"

    def test_post_type_is_lowercased(self):
        d = Diskuto.process_post(make_praw_submission(title="[META] Some Post"))
        assert d.post_type == "meta"

    def test_no_tag_gives_none_post_type(self):
        d = Diskuto.process_post(make_praw_submission(title="No brackets here"))
        assert d.post_type is None

    def test_created_utc_is_int(self):
        d = Diskuto.process_post(make_praw_submission(created_utc=1773034258.9))
        assert isinstance(d.created_utc, int)
        assert d.created_utc == 1773034258

    def test_missing_title_raises(self):
        bad = MagicMock(spec=[])  # no .title, no .id attributes
        with pytest.raises(TypeError):
            Diskuto.process_post(bad)

    def test_missing_id_raises(self):
        bad = MagicMock(spec=["title"])  # has .title but not .id
        bad.title = "[META] Post"
        with pytest.raises(TypeError):
            Diskuto.process_post(bad)

    def test_tag_with_whitespace_stripped(self):
        d = Diskuto.process_post(make_praw_submission(title="[ Meta ] Weekly Thread"))
        assert d.post_type == "meta"


# ===========================================================================
# Diskuto database helpers
# ===========================================================================


class TestDiskutoExists:
    def test_returns_true_when_found(self):
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = (1,)
        with patch("models.diskuto.db") as mock_db:
            mock_db.cursor_main = mock_cursor
            assert diskuto_exists("1rorpb8") is True

    def test_returns_false_when_not_found(self):
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = None
        with patch("models.diskuto.db") as mock_db:
            mock_db.cursor_main = mock_cursor
            assert diskuto_exists("nonexistent") is False


class TestDiskutoWriter:
    @staticmethod
    def _make_diskuto():
        return Diskuto(
            title_original="[META] Test",
            post_type="meta",
            _id="abc123",
            created_utc=1773034258,
            processed=False,
        )

    def test_inserts_new_record(self):
        mock_cursor = MagicMock()
        mock_conn = MagicMock()
        mock_cursor.fetchone.return_value = None  # record does not exist yet
        with patch("models.diskuto.db") as mock_db:
            mock_db.cursor_main = mock_cursor
            mock_db.conn_main = mock_conn
            diskuto_writer(self._make_diskuto())
            mock_cursor.execute.assert_called()
            mock_conn.commit.assert_called_once()

    def test_updates_changed_record(self):
        mock_cursor = MagicMock()
        mock_conn = MagicMock()
        mock_cursor.fetchone.side_effect = [
            None,
            {"content": '{"id":"abc123","different":"data"}'},
        ]
        with patch("models.diskuto.db") as mock_db:
            mock_db.cursor_main = mock_cursor
            mock_db.conn_main = mock_conn
            diskuto_writer(self._make_diskuto())

    def test_invalid_object_raises(self):
        with pytest.raises(TypeError):
            diskuto_writer(object())  # type: ignore[arg-type]


class TestDiskutoLoader:
    def test_returns_none_when_missing(self):
        with patch("models.diskuto.db") as mock_db:
            mock_db.fetch_main.return_value = None
            assert diskuto_loader("missing_id") is None

    def test_returns_diskuto_object(self):
        payload = {
            "id": "1rorpb8",
            "created_utc": 1773034258,
            "title_original": "[Community] Translation Challenge — 2026-03-09",
            "post_type": "community",
            "processed": True,
        }
        with patch("models.diskuto.db") as mock_db:
            mock_db.fetch_main.return_value = {
                "content": orjson.dumps(payload).decode()
            }
            result = diskuto_loader("1rorpb8")
            assert isinstance(result, Diskuto)
            assert result.id == "1rorpb8"
            assert result.post_type == "community"
            assert result.processed is True

    def test_corrupt_json_returns_none(self):
        with patch("models.diskuto.db") as mock_db:
            mock_db.fetch_main.return_value = {"content": "not valid json{{"}
            assert diskuto_loader("bad_id") is None
