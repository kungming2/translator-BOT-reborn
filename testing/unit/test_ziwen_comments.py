import importlib
import sys
import types
from unittest.mock import MagicMock

from models.komando import Komando, action_count_for_statistics


class FakeTransientError(Exception):
    pass


def _make_stub_module(name: str, **attrs) -> types.ModuleType:
    module = types.ModuleType(name)
    for key, value in attrs.items():
        setattr(module, key, value)
    return module


def _import_ziwen_comments():
    stubs = {
        "praw.models": _make_stub_module("praw.models", Comment=MagicMock()),
        "config": _make_stub_module(
            "config",
            SETTINGS={
                "subreddit": "translator",
                "max_posts": 0,
                "thanks_keywords": ["thanks", "thank you"],
                "testing_mode": True,
            },
            TRANSIENT_ERRORS=(FakeTransientError,),
            logger=MagicMock(),
        ),
        "database": _make_stub_module("database", db=MagicMock()),
        "error": _make_stub_module("error", error_log_basic=MagicMock()),
        "models.ajo": _make_stub_module(
            "models.ajo", Ajo=MagicMock(), ajo_loader=MagicMock()
        ),
        "models.diskuto": _make_stub_module(
            "models.diskuto", diskuto_exists=MagicMock(return_value=False)
        ),
        "models.instruo": _make_stub_module(
            "models.instruo",
            Instruo=MagicMock(),
            comment_has_command=MagicMock(return_value=False),
        ),
        "monitoring.points": _make_stub_module(
            "monitoring.points", points_tabulator=MagicMock()
        ),
        "monitoring.edit_tracker": _make_stub_module(
            "monitoring.edit_tracker", cache_processed_comment=MagicMock()
        ),
        "monitoring.action_statistics": _make_stub_module(
            "monitoring.action_statistics", action_counter=MagicMock()
        ),
        "monitoring.user_statistics": _make_stub_module(
            "monitoring.user_statistics", user_statistics_writer=MagicMock()
        ),
        "reddit.connection": _make_stub_module(
            "reddit.connection",
            REDDIT=MagicMock(),
            credentials_source={"USERNAME": "translator-BOT"},
            is_internal_post=MagicMock(return_value=False),
        ),
        "reddit.reddit_sender": _make_stub_module(
            "reddit.reddit_sender", message_send=MagicMock()
        ),
        "reddit.verification": _make_stub_module(
            "reddit.verification", VERIFIED_POST_ID="verified_post"
        ),
        "responses": _make_stub_module("responses", RESPONSE=MagicMock()),
        "title.title_handling": _make_stub_module(
            "title.title_handling", process_title=MagicMock()
        ),
        "ziwen_commands": _make_stub_module("ziwen_commands", HANDLERS={}),
    }
    originals = {name: sys.modules.get(name) for name in stubs}
    original_process_module = sys.modules.pop("processes.ziwen_comments", None)
    try:
        sys.modules.update(stubs)
        return importlib.import_module("processes.ziwen_comments")
    finally:
        for name, original in originals.items():
            if original is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = original
        if original_process_module is None:
            sys.modules.pop("processes.ziwen_comments", None)
        else:
            sys.modules["processes.ziwen_comments"] = original_process_module


def test_lookup_cjk_counts_each_payload_item() -> None:
    komando = Komando(
        "lookup_cjk",
        data=[("zh", "注水", False), ("zh", "質疑", False)],
    )

    assert action_count_for_statistics(komando) == 2


def test_lookup_wp_counts_each_payload_item() -> None:
    komando = Komando(
        "lookup_wp",
        data=[("紫禁城", "zh"), ("Eiffel Tower", None)],
    )

    assert action_count_for_statistics(komando) == 2


def test_lookup_wt_counts_each_payload_item() -> None:
    komando = Komando(
        "lookup_wt",
        data=[("eo", "kunulo", True), ("eo", "amiko", True)],
    )

    assert action_count_for_statistics(komando) == 2


def test_non_lookup_command_counts_as_one_action() -> None:
    komando = Komando("identify", data=["zh", "ja"])

    assert action_count_for_statistics(komando) == 1


def test_point_tabulation_runs_for_command_comments() -> None:
    ziwen_comments = _import_ziwen_comments()

    assert ziwen_comments._should_tabulate_points(
        True, "ordinary command body", "helper", "op", ["thanks"]
    )


def test_point_tabulation_runs_for_long_non_op_comments() -> None:
    ziwen_comments = _import_ziwen_comments()
    long_body = "x" * 121

    assert ziwen_comments._should_tabulate_points(
        False, long_body, "helper", "op", ["thanks"]
    )


def test_point_tabulation_skips_short_non_op_non_command_comments() -> None:
    ziwen_comments = _import_ziwen_comments()

    assert not ziwen_comments._should_tabulate_points(
        False, "ordinary reply", "helper", "op", ["thanks"]
    )


def test_point_tabulation_runs_for_short_op_thanks() -> None:
    ziwen_comments = _import_ziwen_comments()

    assert ziwen_comments._should_tabulate_points(
        False, "thank you", "op", "op", ["thanks", "thank you"]
    )


def test_point_tabulation_skips_short_op_comment_without_thanks() -> None:
    ziwen_comments = _import_ziwen_comments()

    assert not ziwen_comments._should_tabulate_points(
        False, "done", "op", "op", ["thanks", "thank you"]
    )


def test_point_tabulation_skips_long_op_thanks() -> None:
    ziwen_comments = _import_ziwen_comments()
    long_thanks = "thank you " + ("very " * 30)

    assert not ziwen_comments._should_tabulate_points(
        False, long_thanks, "op", "op", ["thanks", "thank you"]
    )


def test_short_thanks_success_marks_author_messaged() -> None:
    ziwen_comments = _import_ziwen_comments()
    comment = types.SimpleNamespace(
        author=types.SimpleNamespace(name="requester"),
        body="thanks",
    )
    ajo = MagicMock(
        author="requester",
        type="single",
        status="untranslated",
        is_identified=False,
        id="post1",
    )
    ziwen_comments.message_send.return_value = True

    ziwen_comments._mark_short_thanks_as_translated(comment, ajo)

    ajo.set_author_messaged.assert_called_once_with(True)


def test_short_thanks_failed_message_does_not_mark_author_messaged() -> None:
    ziwen_comments = _import_ziwen_comments()
    comment = types.SimpleNamespace(
        author=types.SimpleNamespace(name="requester"),
        body="thanks",
    )
    ajo = MagicMock(
        author="requester",
        type="single",
        status="untranslated",
        is_identified=False,
        id="post1",
    )
    ziwen_comments.message_send.return_value = False

    ziwen_comments._mark_short_thanks_as_translated(comment, ajo)

    ajo.set_author_messaged.assert_not_called()


def test_plain_comment_body_is_cached_as_edit_baseline() -> None:
    ziwen_comments = _import_ziwen_comments()

    class FakeCursor:
        def execute(self, query, _params=()):
            if "SELECT 1 FROM old_comments" in query:
                return types.SimpleNamespace(fetchone=lambda: None)
            if "SELECT filtered FROM old_posts" in query:
                return types.SimpleNamespace(fetchone=lambda: None)
            return self

    fake_post = types.SimpleNamespace(
        id="post1",
        author=types.SimpleNamespace(name="requester"),
    )
    fake_comment = types.SimpleNamespace(
        id="comment1",
        submission=fake_post,
        body="Initial body without a lookup",
        author=types.SimpleNamespace(name="helper"),
        created_utc=123,
        permalink="/r/translator/comments/post1/title/comment1/",
    )
    ziwen_comments.REDDIT.subreddit.return_value.comments.return_value = [fake_comment]
    ziwen_comments.db.cursor_main = FakeCursor()
    ziwen_comments.db.conn_main = types.SimpleNamespace(commit=MagicMock())
    ziwen_comments.ajo_loader.return_value = types.SimpleNamespace(lingvo="Spanish")
    ziwen_comments.comment_has_command.return_value = False

    ziwen_comments.ziwen_commands()

    ziwen_comments.cache_processed_comment.assert_called_once_with(
        "comment1",
        "Initial body without a lookup",
        123,
        [],
    )


def test_comment_processing_failure_writes_error_log() -> None:
    ziwen_comments = _import_ziwen_comments()
    error_entries: list[tuple[str, str]] = []

    class FakeCursor:
        def execute(self, query, _params=()):
            if "SELECT 1 FROM old_comments" in query:
                return types.SimpleNamespace(fetchone=lambda: None)
            if "SELECT filtered FROM old_posts" in query:
                return types.SimpleNamespace(fetchone=lambda: None)
            return self

    def raise_handler(_comment, _instruo, _komando, _ajo):
        raise RuntimeError("handler failed")

    fake_post = types.SimpleNamespace(id="post1")
    fake_comment = types.SimpleNamespace(
        id="comment1",
        submission=fake_post,
        body="!nuke",
        author=types.SimpleNamespace(name="helper"),
        created_utc=123,
        permalink="/r/translator/comments/post1/title/comment1/",
    )
    fake_subreddit = types.SimpleNamespace(
        comments=MagicMock(return_value=[fake_comment])
    )
    ziwen_comments.REDDIT.subreddit.return_value = fake_subreddit
    ziwen_comments.db.cursor_main = FakeCursor()
    ziwen_comments.db.conn_main = types.SimpleNamespace(commit=MagicMock())
    ziwen_comments.ajo_loader.return_value = types.SimpleNamespace(lingvo="German")
    ziwen_comments.comment_has_command.return_value = True
    ziwen_comments.Instruo.from_comment.return_value = types.SimpleNamespace(
        commands=[types.SimpleNamespace(name="nuke", data=[])]
    )
    ziwen_comments.HANDLERS["nuke"] = raise_handler
    ziwen_comments.error_log_basic = (
        lambda entry, routine: error_entries.append((entry, routine))
    )

    ziwen_comments.ziwen_commands()

    assert len(error_entries) == 1
    entry, routine = error_entries[0]
    assert routine == "Ziwen Comments"
    assert "Failed while processing comment `comment1` on post `post1`." in entry
    assert (
        "Comment URL: https://www.reddit.com/r/translator/comments/post1/title/comment1/"
        in entry
    )
    assert "RuntimeError: handler failed" in entry


def test_transient_comment_processing_failure_is_not_written_to_error_log() -> None:
    ziwen_comments = _import_ziwen_comments()
    fake_post = types.SimpleNamespace(id="post1")
    fake_comment = types.SimpleNamespace(
        id="comment1",
        submission=fake_post,
        body="ordinary reply",
        author=types.SimpleNamespace(name="helper"),
        permalink="/r/translator/comments/post1/title/comment1/",
    )
    ziwen_comments.REDDIT.subreddit.return_value = types.SimpleNamespace(
        comments=MagicMock(return_value=[fake_comment])
    )
    ziwen_comments.is_internal_post.side_effect = FakeTransientError(
        "received 500 HTTP response"
    )
    ziwen_comments.error_log_basic = MagicMock()
    ziwen_comments.logger = MagicMock()

    ziwen_comments.ziwen_commands()

    ziwen_comments.error_log_basic.assert_not_called()
    ziwen_comments.logger.warning.assert_called_once_with(
        "Transient error while processing comment `%s` on post `%s`: %s: %s. "
        "Skipping it for this cycle.",
        "comment1",
        "post1",
        "FakeTransientError",
        ziwen_comments.is_internal_post.side_effect,
    )
