#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
Unit tests for edit_tracker.py

Run with:
    pytest test_edit_tracker.py -v
"""

import time
from unittest.mock import MagicMock, patch

# noinspection PyProtectedMember
from monitoring.edit_tracker import (
    _CachedComment,
    _cleanup_comment_cache,
    _deserialize_komandos,
    _get_cached_comment,
    _is_comment_within_edit_window,
    _remove_from_processed,
    _serialize_komandos,
    _update_comment_cache,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_comment(
    *,
    comment_id: str = "abc123",
    body: str = "!translated",
    created_utc: float | None = None,
    author_name: str = "some_user",
    edited: bool = True,
    permalink: str = "/r/translator/comments/abc123/post/abc123/",
) -> MagicMock:
    comment = MagicMock()
    comment.id = comment_id
    comment.body = body
    comment.created_utc = created_utc or time.time()
    comment.author.name = author_name
    comment.edited = edited
    comment.permalink = permalink
    return comment


# ===========================================================================
# _serialize_komandos / _deserialize_komandos
# ===========================================================================


class TestSerializeKomandos:
    def test_empty_text_returns_empty_string(self):
        with patch(
            "monitoring.edit_tracker.extract_commands_from_text", return_value=[]
        ):
            assert _serialize_komandos("no commands here") == ""

    def test_single_command(self):
        cmd = MagicMock()
        cmd.name = "translated"
        with patch(
            "monitoring.edit_tracker.extract_commands_from_text", return_value=[cmd]
        ):
            assert _serialize_komandos("!translated") == "translated"

    def test_multiple_commands_joined_with_comma(self):
        cmds = [MagicMock(name=None), MagicMock(name=None)]
        cmds[0].name = "translated"
        cmds[1].name = "identify"
        with patch(
            "monitoring.edit_tracker.extract_commands_from_text", return_value=cmds
        ):
            result = _serialize_komandos("!translated !identify")
        assert result == "translated,identify"

    def test_duplicate_commands_deduplicated(self):
        cmds = [MagicMock(name=None), MagicMock(name=None)]
        cmds[0].name = "translated"
        cmds[1].name = "translated"
        with patch(
            "monitoring.edit_tracker.extract_commands_from_text", return_value=cmds
        ):
            result = _serialize_komandos("!translated !translated")
        assert result == "translated"


class TestDeserializeKomandos:
    def test_empty_string_returns_empty_set(self):
        assert _deserialize_komandos("") == set()

    def test_single_command(self):
        assert _deserialize_komandos("translated") == {"translated"}

    def test_multiple_commands(self):
        assert _deserialize_komandos("translated,identify") == {
            "translated",
            "identify",
        }


# ===========================================================================
# _CachedComment
# ===========================================================================


class TestCachedComment:
    def test_command_names_parsed_from_komandos_string(self):
        c = _CachedComment(body="!translated", komandos="translated,identify")
        assert c.command_names == {"translated", "identify"}

    def test_empty_komandos_gives_empty_set(self):
        c = _CachedComment(body="just a comment", komandos="")
        assert c.command_names == set()

    def test_command_names_lazily_parsed(self):
        c = _CachedComment(body="!translated", komandos="translated")
        assert c._komando_set is None
        _ = c.command_names
        assert c._komando_set is not None

    def test_command_names_cached_after_first_access(self):
        c = _CachedComment(body="!translated", komandos="translated")
        first = c.command_names
        second = c.command_names
        assert first is second


# ===========================================================================
# _is_comment_within_edit_window
# ===========================================================================


class TestIsCommentWithinEditWindow:
    def test_recent_comment_is_within_window(self):
        comment = make_comment(created_utc=time.time() - 60)  # 1 minute old
        with patch("monitoring.edit_tracker.SETTINGS", {"comment_edit_age_max": 1}):
            assert _is_comment_within_edit_window(comment) is True

    def test_old_comment_is_outside_window(self):
        comment = make_comment(created_utc=time.time() - 7200)  # 2 hours old
        with patch("monitoring.edit_tracker.SETTINGS", {"comment_edit_age_max": 1}):
            assert _is_comment_within_edit_window(comment) is False


# ===========================================================================
# _get_cached_comment
# ===========================================================================


class TestGetCachedComment:
    def test_returns_none_when_not_cached(self):
        cursor = MagicMock()
        cursor.fetchone.return_value = None
        with patch("monitoring.edit_tracker.db") as mock_db:
            mock_db.cursor_cache = cursor
            assert _get_cached_comment("missing_id") is None

    def test_returns_cached_comment_object(self):
        cursor = MagicMock()
        cursor.fetchone.return_value = ("Some body text", "translated")
        with patch("monitoring.edit_tracker.db") as mock_db:
            mock_db.cursor_cache = cursor
            result = _get_cached_comment("abc123")
        assert isinstance(result, _CachedComment)
        assert result.body == "Some body text"
        assert result.command_names == {"translated"}

    def test_none_komandos_stored_as_empty_sentinel(self):
        cursor = MagicMock()
        cursor.fetchone.return_value = ("Body text", None)
        with patch("monitoring.edit_tracker.db") as mock_db:
            mock_db.cursor_cache = cursor
            result = _get_cached_comment("abc123")
        assert result.command_names == set()


# ===========================================================================
# _update_comment_cache
# ===========================================================================


class TestUpdateCommentCache:
    def test_deletes_then_inserts(self):
        cursor = MagicMock()
        with (
            patch("monitoring.edit_tracker.db") as mock_db,
            patch(
                "monitoring.edit_tracker._serialize_komandos", return_value="translated"
            ),
        ):
            mock_db.cursor_cache = cursor
            mock_db.conn_cache = MagicMock()
            _update_comment_cache("abc123", "!translated", 1772409600)
        calls = [c[0][0] for c in cursor.execute.call_args_list]
        assert any("DELETE" in c for c in calls)
        assert any("INSERT" in c for c in calls)

    def test_commit_called(self):
        cursor = MagicMock()
        conn = MagicMock()
        with (
            patch("monitoring.edit_tracker.db") as mock_db,
            patch("monitoring.edit_tracker._serialize_komandos", return_value=""),
        ):
            mock_db.cursor_cache = cursor
            mock_db.conn_cache = conn
            _update_comment_cache("abc123", "no commands", 1772409600)
        conn.commit.assert_called_once()

    def test_provided_komandos_not_reparsed(self):
        cursor = MagicMock()
        with (
            patch("monitoring.edit_tracker.db") as mock_db,
            patch("monitoring.edit_tracker._serialize_komandos") as mock_ser,
        ):
            mock_db.cursor_cache = cursor
            mock_db.conn_cache = MagicMock()
            _update_comment_cache(
                "abc123", "!translated", 1772409600, komandos="translated"
            )
        mock_ser.assert_not_called()

    def test_komandos_derived_from_body_when_not_provided(self):
        cursor = MagicMock()
        with (
            patch("monitoring.edit_tracker.db") as mock_db,
            patch(
                "monitoring.edit_tracker._serialize_komandos", return_value="translated"
            ) as mock_ser,
        ):
            mock_db.cursor_cache = cursor
            mock_db.conn_cache = MagicMock()
            _update_comment_cache("abc123", "!translated", 1772409600)
        mock_ser.assert_called_once_with("!translated")


# ===========================================================================
# _remove_from_processed
# ===========================================================================


class TestRemoveFromProcessed:
    def test_deletes_from_old_comments(self):
        cursor = MagicMock()
        conn = MagicMock()
        with patch("monitoring.edit_tracker.db") as mock_db:
            mock_db.cursor_main = cursor
            mock_db.conn_main = conn
            _remove_from_processed("abc123")
        query = cursor.execute.call_args[0][0]
        assert "DELETE" in query
        assert "old_comments" in query
        conn.commit.assert_called_once()


# ===========================================================================
# _cleanup_comment_cache
# ===========================================================================


class TestCleanupCommentCache:
    def test_executes_delete_with_limit(self):
        cursor = MagicMock()
        with patch("monitoring.edit_tracker.db") as mock_db:
            mock_db.cursor_cache = cursor
            mock_db.conn_cache = MagicMock()
            _cleanup_comment_cache(100)
        query, params = cursor.execute.call_args[0]
        assert "DELETE" in query
        assert params == (100,)

    def test_commit_called(self):
        conn = MagicMock()
        with patch("monitoring.edit_tracker.db") as mock_db:
            mock_db.cursor_cache = MagicMock()
            mock_db.conn_cache = conn
            _cleanup_comment_cache(50)
        conn.commit.assert_called_once()
