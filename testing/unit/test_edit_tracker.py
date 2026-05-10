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
    _deserialize_lookup_content,
    _get_cached_comment,
    _is_comment_within_edit_window,
    _is_processed_comment,
    _remove_from_processed,
    _serialize_komandos,
    _serialize_lookup_content,
    _update_comment_cache,
    edit_tracker,
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


def make_komando(name: str, data: list | None = None) -> MagicMock:
    """Return a minimal Komando-like mock with name and data attributes."""
    cmd = MagicMock()
    cmd.name = name
    cmd.data = data or []
    return cmd


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
# _serialize_lookup_content / _deserialize_lookup_content
# ===========================================================================


class TestSerializeLookupContent:
    def test_empty_command_list_gives_section_separator_only(self):
        result = _serialize_lookup_content([])
        assert result == ""

    def test_cjk_terms_encoded_as_lang_colon_term(self):
        cmd = make_komando("lookup_cjk", [("zh", "粽子", False), ("zh", "英雄", False)])
        result = _serialize_lookup_content([cmd])
        cjk, wp = _deserialize_lookup_content(result)
        assert cjk == {"zh:粽子", "zh:英雄"}
        assert wp == set()

    def test_explicit_flag_excluded_from_serialization(self):
        # explicit=True vs explicit=False should produce identical serialization
        cmd_explicit = make_komando("lookup_cjk", [("ja", "目的", True)])
        cmd_implicit = make_komando("lookup_cjk", [("ja", "目的", False)])
        assert _serialize_lookup_content([cmd_explicit]) == _serialize_lookup_content(
            [cmd_implicit]
        )

    def test_wp_english_default_encoded_with_empty_lang_suffix(self):
        cmd = make_komando("lookup_wp", [("Daruma doll", None)])
        result = _serialize_lookup_content([cmd])
        _, wp = _deserialize_lookup_content(result)
        assert wp == {"Daruma doll@"}

    def test_wp_with_language_code_encoded_correctly(self):
        cmd = make_komando("lookup_wp", [("Mesa", "es")])
        result = _serialize_lookup_content([cmd])
        _, wp = _deserialize_lookup_content(result)
        assert wp == {"Mesa@es"}

    def test_wp_english_and_spanish_are_distinct(self):
        cmd_en = make_komando("lookup_wp", [("Mesa", None)])
        cmd_es = make_komando("lookup_wp", [("Mesa", "es")])
        en_result = _serialize_lookup_content([cmd_en])
        es_result = _serialize_lookup_content([cmd_es])
        assert en_result != es_result

    def test_mixed_cjk_and_wp(self):
        cjk_cmd = make_komando("lookup_cjk", [("zh", "粽子", False)])
        wp_cmd = make_komando("lookup_wp", [("Daruma doll", None)])
        result = _serialize_lookup_content([cjk_cmd, wp_cmd])
        cjk, wp = _deserialize_lookup_content(result)
        assert cjk == {"zh:粽子"}
        assert wp == {"Daruma doll@"}

    def test_non_lookup_commands_ignored(self):
        cmd = make_komando("translated", [])
        result = _serialize_lookup_content([cmd])
        assert result == ""

    def test_disable_tokenization_changes_resolved_terms(self):
        # Tokenized version produces multiple tokens; disabling produces the full term.
        # This is the core bug scenario: edit tracker must detect this as a change.
        cmd_tokenized = make_komando(
            "lookup_cjk", [("ja", "七転", False), ("ja", "八", False)]
        )
        cmd_full = make_komando("lookup_cjk", [("ja", "七転八起", False)])
        assert _serialize_lookup_content([cmd_tokenized]) != _serialize_lookup_content(
            [cmd_full]
        )


class TestDeserializeLookupContent:
    def test_empty_string_returns_empty_sets(self):
        cjk, wp = _deserialize_lookup_content("")
        assert cjk == set()
        assert wp == set()

    def test_section_separator_only_returns_empty_sets(self):
        cjk, wp = _deserialize_lookup_content("§")
        assert cjk == set()
        assert wp == set()

    def test_cjk_only_returns_empty_wp(self):
        cjk, wp = _deserialize_lookup_content("zh:粽子§")
        assert cjk == {"zh:粽子"}
        assert wp == set()

    def test_wp_only_returns_empty_cjk(self):
        cjk, wp = _deserialize_lookup_content("§Mesa@es")
        assert cjk == set()
        assert wp == {"Mesa@es"}

    def test_round_trip_multiple_terms(self):
        cmd = make_komando(
            "lookup_cjk",
            [("zh", "天下", False), ("zh", "属于", False), ("zh", "壮士", False)],
        )
        serialized = _serialize_lookup_content([cmd])
        cjk, _ = _deserialize_lookup_content(serialized)
        assert cjk == {"zh:天下", "zh:属于", "zh:壮士"}


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

    def test_lookup_content_defaults_to_empty_string(self):
        c = _CachedComment(body="!translated", komandos="translated")
        assert c.lookup_content == ""

    def test_cjk_terms_parsed_from_lookup_content(self):
        c = _CachedComment(
            body="`粽子`", komandos="lookup_cjk", lookup_content="zh:粽子§"
        )
        assert c.cjk_terms == {"zh:粽子"}

    def test_wp_terms_parsed_from_lookup_content(self):
        c = _CachedComment(
            body="{{Mesa}}:es",
            komandos="lookup_wp",
            lookup_content="§Mesa@es",
        )
        assert c.wp_terms == {"Mesa@es"}

    def test_empty_lookup_content_gives_empty_term_sets(self):
        c = _CachedComment(body="!translated", komandos="translated", lookup_content="")
        assert c.cjk_terms == set()
        assert c.wp_terms == set()


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
        cursor.fetchone.return_value = ("Some body text", "translated", "")
        with patch("monitoring.edit_tracker.db") as mock_db:
            mock_db.cursor_cache = cursor
            result = _get_cached_comment("abc123")
        assert isinstance(result, _CachedComment)
        assert result.body == "Some body text"
        assert result.command_names == {"translated"}

    def test_none_komandos_stored_as_empty_sentinel(self):
        cursor = MagicMock()
        cursor.fetchone.return_value = ("Body text", None, "")
        with patch("monitoring.edit_tracker.db") as mock_db:
            mock_db.cursor_cache = cursor
            result = _get_cached_comment("abc123")
        assert result.command_names == set()

    def test_lookup_content_populated_from_row(self):
        cursor = MagicMock()
        cursor.fetchone.return_value = ("`粽子`", "lookup_cjk", "zh:粽子§")
        with patch("monitoring.edit_tracker.db") as mock_db:
            mock_db.cursor_cache = cursor
            result = _get_cached_comment("abc123")
        assert result.lookup_content == "zh:粽子§"
        assert result.cjk_terms == {"zh:粽子"}

    def test_none_lookup_content_normalised_to_empty_string(self):
        cursor = MagicMock()
        cursor.fetchone.return_value = ("Body text", "translated", None)
        with patch("monitoring.edit_tracker.db") as mock_db:
            mock_db.cursor_cache = cursor
            result = _get_cached_comment("abc123")
        assert result.lookup_content == ""


# ===========================================================================
# _update_comment_cache
# ===========================================================================


class TestUpdateCommentCache:
    @staticmethod
    def _make_mock_command(name: str = "translated") -> MagicMock:
        cmd = MagicMock()
        cmd.name = name
        cmd.data = []
        return cmd

    def test_deletes_then_inserts(self):
        cursor = MagicMock()
        mock_cmd = self._make_mock_command()
        with (
            patch("monitoring.edit_tracker.db") as mock_db,
            patch(
                "monitoring.edit_tracker.extract_commands_from_text",
                return_value=[mock_cmd],
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
        mock_cmd = self._make_mock_command()
        with (
            patch("monitoring.edit_tracker.db") as mock_db,
            patch(
                "monitoring.edit_tracker.extract_commands_from_text",
                return_value=[mock_cmd],
            ),
        ):
            mock_db.cursor_cache = cursor
            mock_db.conn_cache = conn
            _update_comment_cache("abc123", "no commands", 1772409600)
        conn.commit.assert_called_once()

    def test_both_provided_skips_parse(self):
        """Passing both komandos and lookup_content must not call extract_commands_from_text."""
        cursor = MagicMock()
        with (
            patch("monitoring.edit_tracker.db") as mock_db,
            patch("monitoring.edit_tracker.extract_commands_from_text") as mock_parse,
        ):
            mock_db.cursor_cache = cursor
            mock_db.conn_cache = MagicMock()
            _update_comment_cache(
                "abc123",
                "!translated",
                1772409600,
                komandos="translated",
                lookup_content="§",
            )
        mock_parse.assert_not_called()

    def test_neither_provided_triggers_single_parse(self):
        """Omitting both komandos and lookup_content calls extract_commands_from_text once."""
        cursor = MagicMock()
        mock_cmd = self._make_mock_command()
        with (
            patch("monitoring.edit_tracker.db") as mock_db,
            patch(
                "monitoring.edit_tracker.extract_commands_from_text",
                return_value=[mock_cmd],
            ) as mock_parse,
        ):
            mock_db.cursor_cache = cursor
            mock_db.conn_cache = MagicMock()
            _update_comment_cache("abc123", "!translated", 1772409600)
        mock_parse.assert_called_once_with("!translated")

    def test_only_komandos_provided_still_triggers_parse(self):
        """Passing komandos but not lookup_content must still parse to derive lookup_content."""
        cursor = MagicMock()
        mock_cmd = self._make_mock_command()
        with (
            patch("monitoring.edit_tracker.db") as mock_db,
            patch(
                "monitoring.edit_tracker.extract_commands_from_text",
                return_value=[mock_cmd],
            ) as mock_parse,
        ):
            mock_db.cursor_cache = cursor
            mock_db.conn_cache = MagicMock()
            _update_comment_cache(
                "abc123", "!translated", 1772409600, komandos="translated"
            )
        mock_parse.assert_called_once_with("!translated")

    def test_only_lookup_content_provided_still_triggers_parse(self):
        """Passing lookup_content but not komandos must still parse to derive komandos."""
        cursor = MagicMock()
        mock_cmd = self._make_mock_command()
        with (
            patch("monitoring.edit_tracker.db") as mock_db,
            patch(
                "monitoring.edit_tracker.extract_commands_from_text",
                return_value=[mock_cmd],
            ) as mock_parse,
        ):
            mock_db.cursor_cache = cursor
            mock_db.conn_cache = MagicMock()
            _update_comment_cache(
                "abc123", "!translated", 1772409600, lookup_content="§"
            )
        mock_parse.assert_called_once_with("!translated")

    def test_insert_receives_five_values(self):
        """The INSERT statement must bind five values matching the updated schema."""
        cursor = MagicMock()
        mock_cmd = self._make_mock_command()
        with (
            patch("monitoring.edit_tracker.db") as mock_db,
            patch(
                "monitoring.edit_tracker.extract_commands_from_text",
                return_value=[mock_cmd],
            ),
        ):
            mock_db.cursor_cache = cursor
            mock_db.conn_cache = MagicMock()
            _update_comment_cache("abc123", "!translated", 1772409600)

        insert_call = next(
            c for c in cursor.execute.call_args_list if "INSERT" in c[0][0]
        )
        bound_values = insert_call[0][1]
        assert len(bound_values) == 5


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
# _is_processed_comment
# ===========================================================================


class TestIsProcessedComment:
    def test_true_when_old_comments_has_row(self):
        cursor = MagicMock()
        cursor.execute.return_value.fetchone.return_value = (1,)
        with patch("monitoring.edit_tracker.db") as mock_db:
            mock_db.cursor_main = cursor
            assert _is_processed_comment("abc123") is True

    def test_false_when_old_comments_has_no_row(self):
        cursor = MagicMock()
        cursor.execute.return_value.fetchone.return_value = None
        with patch("monitoring.edit_tracker.db") as mock_db:
            mock_db.cursor_main = cursor
            assert _is_processed_comment("abc123") is False


# ===========================================================================
# edit_tracker
# ===========================================================================


class TestEditTracker:
    def test_phase_one_does_not_seed_already_edited_uncached_comment(self):
        comment = make_comment(body="`福`", edited=True)
        helper_subreddit = MagicMock()
        helper_subreddit.comments.return_value = [comment]
        reddit_subreddit = MagicMock()
        reddit_subreddit.mod.edited.return_value = []

        with (
            patch(
                "monitoring.edit_tracker.SETTINGS",
                {
                    "subreddit": "translator",
                    "comment_edit_num_limit": 1,
                    "comment_edit_age_max": 1,
                },
            ),
            patch("monitoring.edit_tracker.REDDIT_HELPER") as helper,
            patch("monitoring.edit_tracker.REDDIT") as reddit,
            patch("monitoring.edit_tracker._get_cached_comment", return_value=None),
            patch("monitoring.edit_tracker._update_comment_cache") as update_cache,
            patch("monitoring.edit_tracker._cleanup_comment_cache"),
        ):
            helper.subreddit.return_value = helper_subreddit
            reddit.subreddit.return_value = reddit_subreddit

            edit_tracker()

        update_cache.assert_not_called()

    def test_uncached_edited_command_removes_processed_marker(self):
        comment = make_comment(body="`福`", edited=True)
        reddit_subreddit = MagicMock()
        reddit_subreddit.mod.edited.return_value = [comment]
        cmd = make_komando("lookup_cjk", [("zh", "福", False)])

        with (
            patch(
                "monitoring.edit_tracker.SETTINGS",
                {
                    "subreddit": "translator",
                    "comment_edit_num_limit": 1,
                    "comment_edit_age_max": 1,
                },
            ),
            patch("monitoring.edit_tracker.REDDIT_HELPER") as helper,
            patch("monitoring.edit_tracker.REDDIT") as reddit,
            patch("monitoring.edit_tracker._get_cached_comment", return_value=None),
            patch(
                "monitoring.edit_tracker.extract_commands_from_text",
                return_value=[cmd],
            ),
            patch("monitoring.edit_tracker.comment_has_command", return_value=True),
            patch("monitoring.edit_tracker._is_processed_comment", return_value=True),
            patch("monitoring.edit_tracker._remove_from_processed") as remove,
            patch("monitoring.edit_tracker._update_comment_cache") as update_cache,
            patch("monitoring.edit_tracker._cleanup_comment_cache"),
        ):
            helper.subreddit.return_value.comments.return_value = []
            reddit.subreddit.return_value = reddit_subreddit

            edit_tracker()

        update_cache.assert_called_once()
        remove.assert_called_once_with("abc123")


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
