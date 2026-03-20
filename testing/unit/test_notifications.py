#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
Unit tests for notifications.py

Run with:
    pytest test_notifications.py -v
"""

from unittest.mock import MagicMock, patch

import orjson

# noinspection PyProtectedMember
from reddit.notifications import (
    _notification_rate_limiter,
    _notifier_duplicate_checker,
    _notifier_title_cleaner,
    _prune_deleted_user_notifications,
    _should_send_language_notification,
    _update_user_notification_count,
    fetch_usernames_for_lingvo,
    is_user_over_submission_limit,
    notifier_internal,
    notifier_language_list_editor,
    notifier_language_list_retriever,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_lingvo(
    *,
    name: str = "Spanish",
    preferred_code: str = "es",
    country: str | None = None,
    script_code: str | None = None,
    rate_monthly: float = 85.0,
    greetings: str = "Hola",
) -> MagicMock:
    lingvo = MagicMock()
    lingvo.name = name
    lingvo.preferred_code = preferred_code
    lingvo.country = country
    lingvo.script_code = script_code
    lingvo.rate_monthly = rate_monthly
    lingvo.greetings = greetings
    return lingvo


def make_submission(
    *,
    post_id: str = "abc123",
    title: str = "[Spanish > English] Help please",
    permalink: str = "/r/translator/comments/abc123/",
    author_name: str = "some_user",
    over_18: bool = False,
    url: str = "https://www.reddit.com/r/translator/comments/abc123/",
) -> MagicMock:
    sub = MagicMock()
    sub.id = post_id
    sub.title = title
    sub.permalink = permalink
    sub.author.name = author_name
    sub.over_18 = over_18
    sub.url = url
    return sub


# ===========================================================================
# _process_language_code  (tested indirectly via notifier_language_list_editor)
# ===========================================================================


class TestProcessLanguageCode:
    """Tested via notifier_language_list_editor since the function is private."""

    def test_english_code_skipped(self):
        # Items with preferred_code == "en" should be silently skipped
        lingvo = MagicMock()
        lingvo.preferred_code = "en"
        with (
            patch("reddit.notifications.db") as mock_db,
            patch(
                "reddit.notifications.SETTINGS",
                {"internal_post_types": ["meta", "community"]},
            ),
            patch(
                "reddit.notifications._notifier_duplicate_checker", return_value=False
            ),
        ):
            notifier_language_list_editor([lingvo], "user1", mode="insert")
            mock_db.cursor_main.execute.assert_not_called()

    def test_script_code_gets_prefix(self):
        # A 4-character code should be stored as "unknown-XXXX"
        lingvo = MagicMock()
        lingvo.preferred_code = "Cyrl"
        captured = {}

        def fake_checker(code, _username, **_kwargs):
            captured["code"] = code
            return False

        with (
            patch("reddit.notifications.db") as mock_db,
            patch(
                "reddit.notifications.SETTINGS",
                {"internal_post_types": ["meta", "community"]},
            ),
            patch(
                "reddit.notifications._notifier_duplicate_checker",
                side_effect=fake_checker,
            ),
        ):
            mock_db.conn_main.__enter__ = MagicMock(return_value=mock_db.conn_main)
            mock_db.conn_main.__exit__ = MagicMock(return_value=False)
            notifier_language_list_editor([lingvo], "user1", mode="insert")
        assert captured.get("code") == "unknown-Cyrl"


# ===========================================================================
# _notifier_duplicate_checker
# ===========================================================================


class TestNotifierDuplicateChecker:
    @staticmethod
    def _run(code, username, internal=False, db_result=None):
        with patch("reddit.notifications.db") as mock_db:
            mock_db.conn_main.__enter__ = MagicMock(return_value=mock_db.conn_main)
            mock_db.conn_main.__exit__ = MagicMock(return_value=False)
            mock_db.cursor_main.execute.return_value.fetchone.return_value = db_result
            return _notifier_duplicate_checker(code, username, internal=internal)

    def test_returns_true_when_record_exists(self):
        assert self._run("es", "user1", db_result=(1,)) is True

    def test_returns_false_when_no_record(self):
        assert self._run("es", "user1", db_result=None) is False

    def test_internal_flag_uses_notify_internal_table(self):
        with patch("reddit.notifications.db") as mock_db:
            mock_db.conn_main.__enter__ = MagicMock(return_value=mock_db.conn_main)
            mock_db.conn_main.__exit__ = MagicMock(return_value=False)
            mock_db.cursor_main.execute.return_value.fetchone.return_value = None
            _notifier_duplicate_checker("meta", "user1", internal=True)
            query = mock_db.cursor_main.execute.call_args[0][0]
            assert "notify_internal" in query

    def test_language_flag_uses_notify_users_table(self):
        with patch("reddit.notifications.db") as mock_db:
            mock_db.conn_main.__enter__ = MagicMock(return_value=mock_db.conn_main)
            mock_db.conn_main.__exit__ = MagicMock(return_value=False)
            mock_db.cursor_main.execute.return_value.fetchone.return_value = None
            _notifier_duplicate_checker("es", "user1", internal=False)
            query = mock_db.cursor_main.execute.call_args[0][0]
            assert "notify_users" in query

    def test_four_char_code_gets_unknown_prefix(self):
        with patch("reddit.notifications.db") as mock_db:
            mock_db.conn_main.__enter__ = MagicMock(return_value=mock_db.conn_main)
            mock_db.conn_main.__exit__ = MagicMock(return_value=False)
            mock_db.cursor_main.execute.return_value.fetchone.return_value = None
            _notifier_duplicate_checker("Cyrl", "user1", internal=False)
            params = mock_db.cursor_main.execute.call_args[0][1]
            assert params[0] == "unknown-cyrl"


# ===========================================================================
# _prune_deleted_user_notifications
# ===========================================================================


class TestPruneDeletedUserNotifications:
    def test_valid_user_returns_none(self):
        with patch("reddit.notifications.is_valid_user", return_value=True):
            result = _prune_deleted_user_notifications("activeuser")
        assert result is None

    def test_deleted_user_with_subscriptions_deletes_and_returns_codes(self):
        cursor = MagicMock()
        conn = MagicMock()
        cursor.fetchall.return_value = [("es",), ("fr",)]
        with (
            patch("reddit.notifications.is_valid_user", return_value=False),
            patch("reddit.notifications.db") as mock_db,
        ):
            mock_db.cursor_main = cursor
            mock_db.conn_main = conn
            result = _prune_deleted_user_notifications("deleteduser")
        assert result == ["es", "fr"]
        conn.commit.assert_called_once()

    def test_deleted_user_with_no_subscriptions_returns_empty_list(self):
        cursor = MagicMock()
        cursor.fetchall.return_value = []
        with (
            patch("reddit.notifications.is_valid_user", return_value=False),
            patch("reddit.notifications.db") as mock_db,
        ):
            mock_db.cursor_main = cursor
            mock_db.conn_main = MagicMock()
            result = _prune_deleted_user_notifications("deleteduser")
        assert result == []

    def test_internal_flag_uses_notify_internal_table(self):
        cursor = MagicMock()
        cursor.fetchall.return_value = []
        with (
            patch("reddit.notifications.is_valid_user", return_value=False),
            patch("reddit.notifications.db") as mock_db,
        ):
            mock_db.cursor_main = cursor
            mock_db.conn_main = MagicMock()
            _prune_deleted_user_notifications("deleteduser", internal_posts=True)
            query = cursor.execute.call_args_list[0][0][0]
            assert "notify_internal" in query


# ===========================================================================
# notifier_language_list_editor
# ===========================================================================


class TestNotifierLanguageListEditor:
    BASE_SETTINGS = {"internal_post_types": ["meta", "community"]}

    @staticmethod
    def _make_lingvo(code):
        lingvo_mock = MagicMock()
        lingvo_mock.preferred_code = code
        return lingvo_mock

    def test_purge_deletes_from_both_tables(self):
        with (
            patch("reddit.notifications.db") as mock_db,
            patch("reddit.notifications.SETTINGS", self.BASE_SETTINGS),
        ):
            mock_db.conn_main.__enter__ = MagicMock(return_value=mock_db.conn_main)
            mock_db.conn_main.__exit__ = MagicMock(return_value=False)
            notifier_language_list_editor([], "user1", mode="purge")
            queries = [c[0][0] for c in mock_db.cursor_main.execute.call_args_list]
            assert any("notify_users" in q for q in queries)
            assert any("notify_internal" in q for q in queries)

    def test_insert_new_language(self):
        lingvo = self._make_lingvo("es")
        with (
            patch("reddit.notifications.db") as mock_db,
            patch("reddit.notifications.SETTINGS", self.BASE_SETTINGS),
            patch(
                "reddit.notifications._notifier_duplicate_checker", return_value=False
            ),
        ):
            mock_db.conn_main.__enter__ = MagicMock(return_value=mock_db.conn_main)
            mock_db.conn_main.__exit__ = MagicMock(return_value=False)
            notifier_language_list_editor([lingvo], "user1", mode="insert")
            queries = [c[0][0] for c in mock_db.cursor_main.execute.call_args_list]
            assert any("INSERT" in q for q in queries)

    def test_insert_skips_existing(self):
        lingvo = self._make_lingvo("es")
        with (
            patch("reddit.notifications.db") as mock_db,
            patch("reddit.notifications.SETTINGS", self.BASE_SETTINGS),
            patch(
                "reddit.notifications._notifier_duplicate_checker", return_value=True
            ),
        ):
            notifier_language_list_editor([lingvo], "user1", mode="insert")
            mock_db.cursor_main.execute.assert_not_called()

    def test_delete_existing_language(self):
        lingvo = self._make_lingvo("es")
        with (
            patch("reddit.notifications.db") as mock_db,
            patch("reddit.notifications.SETTINGS", self.BASE_SETTINGS),
            patch(
                "reddit.notifications._notifier_duplicate_checker", return_value=True
            ),
        ):
            mock_db.conn_main.__enter__ = MagicMock(return_value=mock_db.conn_main)
            mock_db.conn_main.__exit__ = MagicMock(return_value=False)
            notifier_language_list_editor([lingvo], "user1", mode="delete")
            queries = [c[0][0] for c in mock_db.cursor_main.execute.call_args_list]
            assert any("DELETE" in q for q in queries)

    def test_delete_skips_nonexistent(self):
        lingvo = self._make_lingvo("es")
        with (
            patch("reddit.notifications.db") as mock_db,
            patch("reddit.notifications.SETTINGS", self.BASE_SETTINGS),
            patch(
                "reddit.notifications._notifier_duplicate_checker", return_value=False
            ),
        ):
            notifier_language_list_editor([lingvo], "user1", mode="delete")
            mock_db.cursor_main.execute.assert_not_called()

    def test_internal_post_type_uses_notify_internal(self):
        with (
            patch("reddit.notifications.db") as mock_db,
            patch("reddit.notifications.SETTINGS", self.BASE_SETTINGS),
            patch(
                "reddit.notifications._notifier_duplicate_checker", return_value=False
            ),
        ):
            mock_db.conn_main.__enter__ = MagicMock(return_value=mock_db.conn_main)
            mock_db.conn_main.__exit__ = MagicMock(return_value=False)
            notifier_language_list_editor(["meta"], "user1", mode="insert")
            queries = [c[0][0] for c in mock_db.cursor_main.execute.call_args_list]
            assert any("notify_internal" in q for q in queries)

    def test_empty_list_does_nothing(self):
        with (
            patch("reddit.notifications.db") as mock_db,
            patch("reddit.notifications.SETTINGS", self.BASE_SETTINGS),
        ):
            notifier_language_list_editor([], "user1", mode="insert")
            mock_db.cursor_main.execute.assert_not_called()

    def test_accepts_string_username(self):
        lingvo = self._make_lingvo("es")
        with (
            patch("reddit.notifications.db") as mock_db,
            patch("reddit.notifications.SETTINGS", self.BASE_SETTINGS),
            patch(
                "reddit.notifications._notifier_duplicate_checker", return_value=False
            ),
        ):
            mock_db.conn_main.__enter__ = MagicMock(return_value=mock_db.conn_main)
            mock_db.conn_main.__exit__ = MagicMock(return_value=False)
            # Should not raise
            notifier_language_list_editor([lingvo], "stringuser", mode="insert")


# ===========================================================================
# _update_user_notification_count
# ===========================================================================


class TestUpdateUserNotificationCount:
    def test_inserts_new_user(self):
        lingvo = make_lingvo(preferred_code="es")
        cursor = MagicMock()
        cursor.fetchone.return_value = None
        with patch("reddit.notifications.db") as mock_db:
            mock_db.cursor_main = cursor
            mock_db.conn_main = MagicMock()
            _update_user_notification_count("newuser", lingvo)
            queries = [c[0][0] for c in cursor.execute.call_args_list]
            assert any("INSERT" in q for q in queries)

    def test_updates_existing_user(self):
        lingvo = make_lingvo(preferred_code="es")
        cursor = MagicMock()
        cursor.fetchone.return_value = {"received": orjson.dumps({"es": 3})}
        with patch("reddit.notifications.db") as mock_db:
            mock_db.cursor_main = cursor
            mock_db.conn_main = MagicMock()
            _update_user_notification_count("existinguser", lingvo)
            queries = [c[0][0] for c in cursor.execute.call_args_list]
            assert any("UPDATE" in q for q in queries)

    def test_increments_existing_count(self):
        lingvo = make_lingvo(preferred_code="es")
        cursor = MagicMock()
        cursor.fetchone.return_value = {"received": orjson.dumps({"es": 5})}
        written = {}

        def capture_execute(query, params=None):
            if params and "UPDATE" in query:
                written["data"] = orjson.loads(params[0])

        cursor.execute.side_effect = capture_execute
        with patch("reddit.notifications.db") as mock_db:
            mock_db.cursor_main = cursor
            mock_db.conn_main = MagicMock()
            _update_user_notification_count("user1", lingvo)
        assert written.get("data", {}).get("es") == 6

    def test_script_code_appended_to_language_code(self):
        lingvo = make_lingvo(preferred_code="und", script_code="Cyrl")
        cursor = MagicMock()
        cursor.fetchone.return_value = None
        written = {}

        def capture_execute(query, params=None):
            if params and "INSERT" in query:
                written["data"] = orjson.loads(params[1])

        cursor.execute.side_effect = capture_execute
        with patch("reddit.notifications.db") as mock_db:
            mock_db.cursor_main = cursor
            mock_db.conn_main = MagicMock()
            _update_user_notification_count("user1", lingvo)
        assert "und-Cyrl" in written.get("data", {})

    def test_corrupt_json_resets_to_empty(self):
        lingvo = make_lingvo(preferred_code="es")
        cursor = MagicMock()
        cursor.fetchone.return_value = {"received": b"not json{{"}
        with patch("reddit.notifications.db") as mock_db:
            mock_db.cursor_main = cursor
            mock_db.conn_main = MagicMock()
            # Should not raise
            _update_user_notification_count("user1", lingvo)


# ===========================================================================
# _notification_rate_limiter
# ===========================================================================


class TestNotificationRateLimiter:
    BASE_SETTINGS = {
        "notifications_user_limit": 50,
        "notifications_api_limiter_on": False,
        "unknown_language_default_rate": 10,
    }

    def _run(self, users, lingvo, monthly_limit=5, contacted=None, settings=None):
        with patch("reddit.notifications.SETTINGS", settings or self.BASE_SETTINGS):
            return _notification_rate_limiter(users, lingvo, monthly_limit, contacted)

    def test_empty_list_returns_empty(self):
        lingvo = make_lingvo(rate_monthly=10.0)
        assert self._run([], lingvo) == []

    def test_zero_limit_returns_empty(self):
        lingvo = make_lingvo(rate_monthly=10.0)
        assert self._run(["user1"], lingvo, monthly_limit=0) == []

    def test_already_contacted_users_excluded(self):
        lingvo = make_lingvo(rate_monthly=100.0)
        result = self._run(["user1", "user2"], lingvo, contacted=["user1"])
        assert "user1" not in result

    def test_rare_language_returns_all_users_sorted(self):
        # rate_monthly < 5 and api_limiter_on = False -> return all sorted
        lingvo = make_lingvo(rate_monthly=2.0)
        users = ["charlie", "alice", "bob"]
        result = self._run(users, lingvo)
        assert result == sorted(users, key=lambda u: u.lower())

    def test_common_language_limits_notifications(self):
        # 10 users, monthly_limit=5, rate=100 -> 10*5/100 = 0.5 -> rounds to 1 (min 1)
        lingvo = make_lingvo(rate_monthly=100.0)
        users = [f"user{i}" for i in range(10)]
        result = self._run(users, lingvo, monthly_limit=5)
        assert len(result) >= 1
        assert len(result) <= len(users)

    def test_result_does_not_exceed_user_limit(self):
        settings = {**self.BASE_SETTINGS, "notifications_user_limit": 3}
        lingvo = make_lingvo(rate_monthly=100.0)
        users = [f"user{i}" for i in range(20)]
        result = self._run(users, lingvo, monthly_limit=50, settings=settings)
        assert len(result) <= 3

    def test_unknown_language_uses_default_rate(self):
        lingvo = make_lingvo(
            name="Unknown",
            preferred_code="unknown",
            rate_monthly=None,  # type: ignore[arg-type]
        )
        # Should not raise; default rate of 10 applies
        result = self._run(["user1"], lingvo)
        assert isinstance(result, list)


# ===========================================================================
# _should_send_language_notification
# ===========================================================================


class TestShouldSendLanguageNotification:
    def test_empty_history_always_sends(self):
        lingvo = make_lingvo(preferred_code="es", name="Spanish")
        assert _should_send_language_notification(lingvo, []) is True

    def test_language_not_in_history_sends(self):
        lingvo = make_lingvo(preferred_code="es", name="Spanish")
        assert _should_send_language_notification(lingvo, ["fr", "de"]) is True

    def test_language_is_last_in_history_sends(self):
        lingvo = make_lingvo(preferred_code="es", name="Spanish")
        assert _should_send_language_notification(lingvo, ["fr", "es"]) is True

    def test_language_in_history_but_not_last_blocks(self):
        lingvo = make_lingvo(preferred_code="es", name="Spanish")
        assert _should_send_language_notification(lingvo, ["es", "fr"]) is False

    def test_matches_by_name_as_well_as_code(self):
        lingvo = make_lingvo(preferred_code="es", name="Spanish")
        # History uses names instead of codes (legacy format)
        assert _should_send_language_notification(lingvo, ["French", "Spanish"]) is True

    def test_name_in_history_but_not_last_blocks(self):
        lingvo = make_lingvo(preferred_code="es", name="Spanish")
        assert (
            _should_send_language_notification(lingvo, ["Spanish", "French"]) is False
        )


# ===========================================================================
# is_user_over_submission_limit
# ===========================================================================


class TestIsUserOverSubmissionLimit:
    def test_under_limit_returns_false(self):
        with (
            patch("reddit.notifications.SETTINGS", {"user_submission_limit": 3}),
            patch("reddit.notifications.STATE") as mock_state,
        ):
            mock_state.recent_submitters = ["user1", "user2", "user1"]
            assert is_user_over_submission_limit("user1") is False  # count=2, limit=3

    def test_over_limit_returns_true(self):
        with (
            patch("reddit.notifications.SETTINGS", {"user_submission_limit": 2}),
            patch("reddit.notifications.STATE") as mock_state,
        ):
            mock_state.recent_submitters = ["user1", "user1", "user1"]
            assert is_user_over_submission_limit("user1") is True  # count=3 > limit=2

    def test_user_not_in_list_returns_false(self):
        with (
            patch("reddit.notifications.SETTINGS", {"user_submission_limit": 1}),
            patch("reddit.notifications.STATE") as mock_state,
        ):
            mock_state.recent_submitters = ["other_user"]
            assert is_user_over_submission_limit("user1") is False


# ===========================================================================
# _notifier_title_cleaner
# ===========================================================================


class TestNotifierTitleCleaner:
    def test_brackets_escaped(self):
        result = _notifier_title_cleaner("[Spanish > English]")
        assert "\\[" in result
        assert "\\]" in result

    def test_parentheses_escaped(self):
        result = _notifier_title_cleaner("Some (title)")
        assert "\\(" in result
        assert "\\)" in result

    def test_asterisk_escaped(self):
        assert "\\*" in _notifier_title_cleaner("bold *word*")

    def test_underscore_escaped(self):
        assert "\\_" in _notifier_title_cleaner("some_word")

    def test_tilde_escaped(self):
        assert "\\~" in _notifier_title_cleaner("~~strikethrough~~")

    def test_backtick_escaped(self):
        assert "\\`" in _notifier_title_cleaner("`code`")

    def test_plain_title_unchanged(self):
        assert _notifier_title_cleaner("Hello world") == "Hello world"

    def test_real_world_title(self):
        title = "[Spanish > English] What does my grandparents' carpet say?"
        result = _notifier_title_cleaner(title)
        assert "\\[" in result
        assert "\\]" in result
        assert ">" in result  # > is not in the sensitive list


# ===========================================================================
# fetch_usernames_for_lingvo
# ===========================================================================


class TestFetchUsernamesForLingvo:
    def test_returns_usernames_for_code(self):
        lingvo = make_lingvo(preferred_code="es", country=None)
        cursor = MagicMock()
        cursor.fetchall.return_value = [{"username": "user1"}, {"username": "user2"}]
        with patch("reddit.notifications.db") as mock_db:
            mock_db.conn_main.cursor.return_value = cursor
            result = fetch_usernames_for_lingvo(lingvo)
        assert "user1" in result
        assert "user2" in result

    def test_max_num_limits_results(self):
        lingvo = make_lingvo(preferred_code="es", country=None)
        cursor = MagicMock()
        cursor.fetchall.return_value = [{"username": f"user{i}"} for i in range(20)]
        with patch("reddit.notifications.db") as mock_db:
            mock_db.conn_main.cursor.return_value = cursor
            result = fetch_usernames_for_lingvo(lingvo, max_num=5)
        assert len(result) == 5

    def test_attribute_error_returns_empty(self):
        bad_lingvo = MagicMock(spec=[])  # no preferred_code attribute
        result = fetch_usernames_for_lingvo(bad_lingvo)
        assert result == []

    def test_script_code_gets_unknown_prefix(self):
        lingvo = make_lingvo(preferred_code="Cyrl", country=None)
        cursor = MagicMock()
        cursor.fetchall.return_value = []
        with patch("reddit.notifications.db") as mock_db:
            mock_db.conn_main.cursor.return_value = cursor
            fetch_usernames_for_lingvo(lingvo)
            params = cursor.execute.call_args[0][1]
            assert params == ("unknown-Cyrl",)


# ===========================================================================
# notifier_language_list_retriever
# ===========================================================================


class TestNotifierLanguageListRetriever:
    def test_returns_internal_post_types_as_strings(self):
        cursor = MagicMock()
        cursor.fetchall.return_value = [("meta",), ("community",)]
        with patch("reddit.notifications.db") as mock_db:
            mock_db.cursor_main = cursor
            result = notifier_language_list_retriever("user1", internal=True)
        assert result == ["meta", "community"]

    def test_returns_lingvo_objects_for_languages(self):
        cursor = MagicMock()
        cursor.fetchall.return_value = [("es",), ("fr",)]
        mock_lingvo = MagicMock()
        with (
            patch("reddit.notifications.db") as mock_db,
            patch("reddit.notifications.converter", return_value=mock_lingvo),
        ):
            mock_db.cursor_main = cursor
            result = notifier_language_list_retriever("user1", internal=False)
        assert all(r is mock_lingvo for r in result)
        assert len(result) == 2


# ===========================================================================
# notifier_internal
# ===========================================================================


class TestNotifierInternal:
    BASE_SETTINGS = {"internal_post_types": ["meta", "community"]}

    def _run(self, post_type, targets=None, author_name="mod_user"):
        sub = make_submission()
        sub.author.name = author_name
        sub.title = f"[{post_type.title()}] Weekly thread"
        sub.permalink = "/r/translator/comments/abc123/"

        targets = (
            targets if targets is not None else [("meta", "user1"), ("meta", "user2")]
        )
        cursor = MagicMock()
        cursor.fetchall.return_value = targets

        with (
            patch("reddit.notifications.SETTINGS", self.BASE_SETTINGS),
            patch("reddit.notifications.db") as mock_db,
            patch("reddit.notifications.REDDIT") as _mock_reddit,
            patch("reddit.notifications.message_send") as mock_send,
            patch("reddit.notifications.RESPONSE") as mock_resp,
            patch("reddit.notifications._prune_deleted_user_notifications"),
        ):
            mock_db.conn_main.cursor.return_value = cursor
            mock_resp.MSG_NOTIFY.format.return_value = "Body"
            mock_resp.BOT_DISCLAIMER = ""
            mock_resp.MSG_UNSUBSCRIBE_BUTTON = ""
            result = notifier_internal(post_type, sub)
            return result, mock_send

    def test_unsupported_post_type_returns_empty(self):
        sub = make_submission()
        with patch("reddit.notifications.SETTINGS", self.BASE_SETTINGS):
            result = notifier_internal("unknown_type", sub)
        assert result == []

    def test_no_author_returns_empty(self):
        sub = make_submission()
        sub.author = None
        with patch("reddit.notifications.SETTINGS", self.BASE_SETTINGS):
            result = notifier_internal("meta", sub)
        assert result == []

    def test_no_subscribers_returns_empty(self):
        result, mock_send = self._run("meta", targets=[])
        assert result == []
        mock_send.assert_not_called()

    def test_messages_sent_to_all_subscribers(self):
        targets = [("meta", "user1"), ("meta", "user2")]
        result, mock_send = self._run("meta", targets=targets)
        assert mock_send.call_count == 2

    def test_returns_target_list(self):
        targets = [("meta", "user1")]
        result, _ = self._run("meta", targets=targets)
        assert result == targets

    def test_user_not_found_triggers_prune(self):
        from reddit.reddit_sender import UserNotFoundException

        sub = make_submission()
        sub.author.name = "mod_user"
        cursor = MagicMock()
        cursor.fetchall.return_value = [("meta", "ghost_user")]
        with (
            patch("reddit.notifications.SETTINGS", self.BASE_SETTINGS),
            patch("reddit.notifications.db") as mock_db,
            patch("reddit.notifications.REDDIT"),
            patch(
                "reddit.notifications.message_send", side_effect=UserNotFoundException
            ),
            patch("reddit.notifications.RESPONSE") as mock_resp,
            patch(
                "reddit.notifications._prune_deleted_user_notifications"
            ) as mock_prune,
        ):
            mock_db.conn_main.cursor.return_value = cursor
            mock_resp.MSG_NOTIFY.format.return_value = "Body"
            mock_resp.BOT_DISCLAIMER = ""
            mock_resp.MSG_UNSUBSCRIBE_BUTTON = ""
            notifier_internal("meta", sub)
        mock_prune.assert_called_once_with("ghost_user", True)
