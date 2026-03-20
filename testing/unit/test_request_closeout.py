#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
Unit tests for request_closeout.py

Run with:
    pytest test_request_closeout.py -v
"""

from unittest.mock import MagicMock, patch

# noinspection PyProtectedMember
from monitoring.request_closeout import _send_closeout_messages, closeout_posts

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_ajo(
    *,
    post_id: str = "abc123",
    status: str = "untranslated",
    closed_out: bool = False,
    language_name: str = "Spanish",
) -> MagicMock:
    ajo = MagicMock()
    ajo.id = post_id
    ajo.status = status
    ajo.closed_out = closed_out
    ajo.lingvo.name = language_name
    return ajo


def make_submission(
    *,
    post_id: str = "abc123",
    author_name: str = "some_user",
    num_comments: int = 10,
    selftext: str = "Please translate this.",
    removed_by_category: str | None = None,
    permalink: str = "/r/translator/comments/abc123/some_post/",
) -> MagicMock:
    sub = MagicMock()
    sub.id = post_id
    sub.author.name = author_name
    sub.num_comments = num_comments
    sub.selftext = selftext
    sub.removed_by_category = removed_by_category
    sub.permalink = permalink
    return sub


# ===========================================================================
# _send_closeout_messages
# ===========================================================================


class TestSendCloseoutMessages:
    @staticmethod
    def _run(posts, ajos_map, time_delta=7.0, valid_user=True):
        with (
            patch("monitoring.request_closeout.is_valid_user", return_value=valid_user),
            patch("monitoring.request_closeout.message_send") as mock_send,
            patch("monitoring.request_closeout.RESPONSE") as mock_resp,
        ):
            mock_resp.MSG_CLOSING_OUT_SUBJECT.format.return_value = "Subject"
            mock_resp.MSG_CLOSING_OUT.format.return_value = "Body"
            mock_resp.BOT_DISCLAIMER = "\n\n---\nBot"
            _send_closeout_messages(posts, ajos_map, time_delta)
            return mock_send

    def test_sends_message_for_valid_post(self):
        sub = make_submission()
        ajo = make_ajo()
        mock_send = self._run([sub], {sub.id: ajo})
        mock_send.assert_called_once()

    def test_skips_deleted_author(self):
        sub = make_submission()
        sub.author = None
        ajo = make_ajo()
        mock_send = self._run([sub], {sub.id: ajo})
        mock_send.assert_not_called()

    def test_skips_invalid_user(self):
        sub = make_submission()
        ajo = make_ajo()
        mock_send = self._run([sub], {sub.id: ajo}, valid_user=False)
        mock_send.assert_not_called()

    def test_sends_to_multiple_posts(self):
        subs = [make_submission(post_id="id1"), make_submission(post_id="id2")]
        ajos_map = {
            "id1": make_ajo(post_id="id1"),
            "id2": make_ajo(post_id="id2"),
        }
        mock_send = self._run(subs, ajos_map)
        assert mock_send.call_count == 2

    def test_uses_generic_language_when_lingvo_is_none(self):
        sub = make_submission()
        ajo = make_ajo()
        ajo.lingvo = None
        with (
            patch("monitoring.request_closeout.is_valid_user", return_value=True),
            patch("monitoring.request_closeout.message_send"),
            patch("monitoring.request_closeout.RESPONSE") as mock_resp,
        ):
            mock_resp.MSG_CLOSING_OUT_SUBJECT.format.return_value = "Subject"
            mock_resp.MSG_CLOSING_OUT.format.return_value = "Body"
            mock_resp.BOT_DISCLAIMER = ""
            _send_closeout_messages([sub], {sub.id: ajo}, 7.0)
            mock_resp.MSG_CLOSING_OUT_SUBJECT.format.assert_called_once_with(
                language="Generic"
            )

    def test_time_delta_is_rounded(self):
        sub = make_submission()
        ajo = make_ajo()
        with (
            patch("monitoring.request_closeout.is_valid_user", return_value=True),
            patch("monitoring.request_closeout.message_send"),
            patch("monitoring.request_closeout.RESPONSE") as mock_resp,
        ):
            mock_resp.MSG_CLOSING_OUT_SUBJECT.format.return_value = "Subject"
            mock_resp.MSG_CLOSING_OUT.format.return_value = "Body"
            mock_resp.BOT_DISCLAIMER = ""
            _send_closeout_messages([sub], {sub.id: ajo}, 7.456789)
            call_kwargs = mock_resp.MSG_CLOSING_OUT.format.call_args.kwargs
            assert call_kwargs["days"] == 7.5

    def test_bot_disclaimer_appended_to_message(self):
        sub = make_submission()
        ajo = make_ajo()
        sent_bodies = []
        with (
            patch("monitoring.request_closeout.is_valid_user", return_value=True),
            patch(
                "monitoring.request_closeout.message_send",
                side_effect=lambda **kw: sent_bodies.append(kw["body"]),
            ),
            patch("monitoring.request_closeout.RESPONSE") as mock_resp,
        ):
            mock_resp.MSG_CLOSING_OUT_SUBJECT.format.return_value = "Subject"
            mock_resp.MSG_CLOSING_OUT.format.return_value = "Body text"
            mock_resp.BOT_DISCLAIMER = "\n\n---\nZiwen"
            _send_closeout_messages([sub], {sub.id: ajo}, 7.0)
        assert sent_bodies[0] == "Body text\n\n---\nZiwen"


# ===========================================================================
# closeout_posts
# ===========================================================================


class TestCloseoutPosts:
    """
    Patches the full dependency surface of closeout_posts:
      - db.fetchall_ajo      — returns rows from the database query
      - ajo_loader           — converts rows to Ajo objects
      - REDDIT.submission    — fetches PRAW submission objects
      - _send_closeout_messages — verifies what gets forwarded for messaging
      - SETTINGS             — controls close_out_age and close_out_comments_minimum
    """

    BASE_SETTINGS = {
        "close_out_age": 7,
        "close_out_comments_minimum": 3,
    }

    def _run(
        self,
        *,
        db_rows=None,
        ajos=None,
        submissions=None,
        settings=None,
    ):
        """
        Wire up all mocks and call closeout_posts(), returning the
        mock_send spy so callers can inspect what was sent.
        """

        db_rows = db_rows or []
        ajos = ajos or []
        submissions = submissions or {}
        settings = settings or self.BASE_SETTINGS

        ajo_iter = iter(ajos)

        with (
            patch("monitoring.request_closeout.SETTINGS", settings),
            patch("monitoring.request_closeout.db") as mock_db,
            patch(
                "monitoring.request_closeout.ajo_loader",
                side_effect=lambda _: next(ajo_iter, None),
            ),
            patch("monitoring.request_closeout.REDDIT") as mock_reddit,
            patch("monitoring.request_closeout._send_closeout_messages") as mock_send,
        ):
            mock_db.fetchall_ajo.return_value = db_rows
            mock_reddit.submission.side_effect = lambda **kwargs: submissions.get(
                kwargs["id"], make_submission(post_id=kwargs["id"])
            )
            closeout_posts()
            return mock_send

    def test_no_rows_sends_nothing(self):
        mock_send = self._run(db_rows=[])
        mock_send.assert_called_once()
        actionable = mock_send.call_args[0][0]
        assert actionable == []

    def test_already_translated_post_is_skipped(self):
        ajo = make_ajo(status="translated")
        mock_send = self._run(
            db_rows=[{"id": ajo.id}],
            ajos=[ajo],
            submissions={ajo.id: make_submission(post_id=ajo.id, num_comments=10)},
        )
        actionable = mock_send.call_args[0][0]
        assert actionable == []

    def test_doublecheck_post_is_skipped(self):
        ajo = make_ajo(status="doublecheck")
        mock_send = self._run(
            db_rows=[{"id": ajo.id}],
            ajos=[ajo],
            submissions={ajo.id: make_submission(post_id=ajo.id, num_comments=10)},
        )
        actionable = mock_send.call_args[0][0]
        assert actionable == []

    def test_already_closed_out_post_is_skipped(self):
        ajo = make_ajo(closed_out=True)
        mock_send = self._run(
            db_rows=[{"id": ajo.id}],
            ajos=[ajo],
            submissions={ajo.id: make_submission(post_id=ajo.id, num_comments=10)},
        )
        actionable = mock_send.call_args[0][0]
        assert actionable == []

    def test_post_below_comment_threshold_not_actionable(self):
        ajo = make_ajo()
        sub = make_submission(post_id=ajo.id, num_comments=2)  # below minimum of 3
        mock_send = self._run(
            db_rows=[{"id": ajo.id}],
            ajos=[ajo],
            submissions={ajo.id: sub},
        )
        actionable = mock_send.call_args[0][0]
        assert actionable == []

    def test_post_above_comment_threshold_is_actionable(self):
        ajo = make_ajo()
        sub = make_submission(post_id=ajo.id, num_comments=5)
        mock_send = self._run(
            db_rows=[{"id": ajo.id}],
            ajos=[ajo],
            submissions={ajo.id: sub},
        )
        actionable = mock_send.call_args[0][0]
        assert sub in actionable

    def test_deleted_post_is_skipped(self):
        ajo = make_ajo()
        sub = make_submission(post_id=ajo.id, num_comments=10)
        sub.author = None
        mock_send = self._run(
            db_rows=[{"id": ajo.id}],
            ajos=[ajo],
            submissions={ajo.id: sub},
        )
        actionable = mock_send.call_args[0][0]
        assert actionable == []

    def test_removed_post_selftext_is_skipped(self):
        ajo = make_ajo()
        sub = make_submission(post_id=ajo.id, num_comments=10, selftext="[removed]")
        mock_send = self._run(
            db_rows=[{"id": ajo.id}],
            ajos=[ajo],
            submissions={ajo.id: sub},
        )
        actionable = mock_send.call_args[0][0]
        assert actionable == []

    def test_removed_by_category_is_skipped(self):
        ajo = make_ajo()
        sub = make_submission(
            post_id=ajo.id, num_comments=10, removed_by_category="moderator"
        )
        mock_send = self._run(
            db_rows=[{"id": ajo.id}],
            ajos=[ajo],
            submissions={ajo.id: sub},
        )
        actionable = mock_send.call_args[0][0]
        assert actionable == []

    def test_failed_ajo_loader_is_skipped(self):
        mock_send = self._run(
            db_rows=[{"id": "ghost_id"}],
            ajos=[None],  # ajo_loader returns None
        )
        actionable = mock_send.call_args[0][0]
        assert actionable == []

    def test_post_is_marked_closed_out_regardless_of_comment_count(self):
        ajo = make_ajo()
        sub = make_submission(post_id=ajo.id, num_comments=0)  # below threshold
        self._run(
            db_rows=[{"id": ajo.id}],
            ajos=[ajo],
            submissions={ajo.id: sub},
        )
        ajo.set_closed_out.assert_called_once_with(True)
        ajo.update_reddit.assert_called_once()

    def test_ajos_map_passed_to_send(self):
        ajo = make_ajo(post_id="xyz789")
        sub = make_submission(post_id="xyz789", num_comments=5)
        mock_send = self._run(
            db_rows=[{"id": "xyz789"}],
            ajos=[ajo],
            submissions={"xyz789": sub},
        )
        ajos_map = mock_send.call_args[0][1]
        assert "xyz789" in ajos_map
        assert ajos_map["xyz789"] is ajo
