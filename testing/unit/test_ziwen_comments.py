import importlib
import sys
import types
from unittest.mock import MagicMock

from models.komando import Komando, action_count_for_statistics


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
            TRANSIENT_ERRORS=(Exception,),
            logger=MagicMock(),
        ),
        "database": _make_stub_module("database", db=MagicMock()),
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
        "monitoring.usage_statistics": _make_stub_module(
            "monitoring.usage_statistics",
            action_counter=MagicMock(),
            user_statistics_writer=MagicMock(),
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
