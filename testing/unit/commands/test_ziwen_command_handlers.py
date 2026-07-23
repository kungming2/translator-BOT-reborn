#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""Focused handler tests for Ziwen command modules."""

import importlib.util
import logging
import sys
import types
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from typing import Protocol
from unittest.mock import MagicMock


class FakeNotFound(Exception):
    pass


class HasId(Protocol):
    id: str


class FakeAuthor:
    def __init__(self, name: str, created_utc: int = 0) -> None:
        self.name = name
        self.created_utc = created_utc

    def __str__(self) -> str:
        return self.name


class FakeComment:
    def __init__(
        self,
        author: FakeAuthor | None = None,
        body: str = "",
        submission: "FakeSubmission | None" = None,
        comment_id: str = "comment1",
        parent: object | None = None,
    ) -> None:
        self.author = author or FakeAuthor("helper")
        self.body = body
        self.submission = submission or FakeSubmission()
        self.id = comment_id
        self.permalink = f"/r/translator/comments/post/{comment_id}/"
        self._parent = parent
        self.mod = SimpleNamespace(distinguish=MagicMock())

    def parent(self) -> object | None:
        return self._parent


class FakeSubmission:
    def __init__(
        self,
        author: FakeAuthor | None = None,
        post_id: str = "post1",
        url: str = "https://example.com/image.jpg",
        is_self: bool = False,
        selftext: str = "",
    ) -> None:
        self.author = author or FakeAuthor("op")
        self.id = post_id
        self.permalink = f"/r/translator/comments/{post_id}/title/"
        self.url = url
        self.is_self = is_self
        self.selftext = selftext
        self.title = "Request title"
        self.is_gallery = False


class FakeAjo:
    def __init__(self, submission: FakeSubmission | None = None) -> None:
        self.id = "post1"
        self.submission = submission or FakeSubmission()
        self.author = self.submission.author.name
        self.lingvo = FakeLang("German", "de")
        self.status = "untranslated"
        self.type = "single"
        self.is_defined_multiple = False
        self.is_long = False
        self.language_name = "German"
        self.title_original = "Original title"
        self.notified: list[object] = []
        self.reset_called = False

    def add_notified(self, people: list[object]) -> None:
        self.notified.extend(people)

    def reset(self) -> None:
        self.reset_called = True

    def set_is_long(self, value: bool) -> None:
        self.is_long = value


class FakeLang:
    def __init__(self, name: str = "German", preferred_code: str = "de") -> None:
        self.name = name
        self.preferred_code = preferred_code
        self.greetings = "Hallo"

    def __repr__(self) -> str:
        return f"FakeLang({self.name!r}, {self.preferred_code!r})"

    def __eq__(self, other: object) -> bool:
        return (
            isinstance(other, FakeLang)
            and self.name == other.name
            and self.preferred_code == other.preferred_code
        )


class FakeNotificationResult:
    def __init__(
        self,
        *,
        subscriber_count: int = 0,
        already_contacted_count: int = 0,
        eligible_count: int = 0,
        attempted_count: int = 0,
        sent_usernames: list[str] | None = None,
        failed_usernames: list[str] | None = None,
        suppressed_reason: str | None = None,
    ) -> None:
        self.subscriber_count = subscriber_count
        self.already_contacted_count = already_contacted_count
        self.eligible_count = eligible_count
        self.attempted_count = attempted_count
        self.sent_usernames = sent_usernames or []
        self.failed_usernames = failed_usernames or []
        self.suppressed_reason = suppressed_reason


class FakeKomando:
    def __init__(self, data: object = None, name: str = "command") -> None:
        self.name = name
        self.data = data


class FakeKunulo:
    def __init__(self) -> None:
        self.deleted: list[str] = []
        self.op_thanks = False
        self.existing_cjk_reply: str | None = None
        self.existing_wp_reply: str | None = None
        self.existing_wt_reply: str | None = None

    def delete(self, tag: str) -> None:
        self.deleted.append(tag)

    @staticmethod
    def get_tag(_tag: str) -> None:
        return None

    @staticmethod
    def check_existing_cjk_lookups(*_args, **_kwargs) -> None:
        return None

    def find_cjk_reply_for_comment(self, _comment_id: str) -> str | None:
        return self.existing_cjk_reply

    def find_wp_reply_for_comment(self, _comment_id: str) -> str | None:
        return self.existing_wp_reply

    def find_wt_reply_for_comment(self, _comment_id: str) -> str | None:
        return self.existing_wt_reply

    @staticmethod
    def get_comment_permalink(comment_id: str) -> str:
        return f"https://www.reddit.com/r/translator/comments/post/{comment_id}/"


def _make_stub_module(name: str, **attrs: object) -> types.ModuleType:
    module = types.ModuleType(name)
    for attr_name, value in attrs.items():
        setattr(module, attr_name, value)
    return module


def _response_stub() -> SimpleNamespace:
    return SimpleNamespace(
        BOT_DISCLAIMER="\n\n--bot--",
        ANCHOR_CJK="\n\n[](#cjk_lookup)",
        ANCHOR_WIKIPEDIA="\n\n[](#wikipedia_lookup)",
        ANCHOR_WIKTIONARY="\n\n[](#wiktionary_lookup)",
        COMMENT_CALENDAR_USAGE="calendar usage",
        COMMENT_CALENDAR_INVALID="calendar invalid",
        COMMENT_CALENDAR_RESULT="Calendar conversion for `{query}`:\n\n{gregorian_dates}",
        COMMENT_CALENDAR_YEAR_RESULT="Recent Gregorian years matching `{query}`:\n\n{gregorian_years}",
        COMMENT_CJK_LOOKUP_DUPLICATE="duplicate {lookup_terms} {permalink}",
        COMMENT_CLAIM="claim {claimer} {time} {language_name} {language_code}",
        COMMENT_CURRENTLY_CLAIMED=(
            "claimed {language_name} {language_code} {claimer_name} {remaining_time}"
        ),
        COMMENT_LANGUAGE_NO_RESULTS="invalid language {id_comment_body}",
        COMMENT_NO_LANGUAGE="no subscribers {language_name} {language_code}",
        COMMENT_PAGE_NO_ADDITIONAL_RECIPIENTS=(
            "no additional recipients {language_name} {language_code}"
        ),
        COMMENT_PAGE_DISALLOWED="too young {age}",
        COMMENT_SEARCH_RESULTS_HEADER='results for "{search_query}"',
        COMMENT_SELF_ALREADY_CLAIMED="already claimed",
        COMMENT_TRANSFORM_ERROR="transform error {0}",
        COMMENT_TRANSFORM_INDEX_OOB="index oob {0} {1}",
        COMMENT_TRANSFORM_INDEX_SINGLE="index single",
        COMMENT_TRANSFORM_INVALID="invalid transform {0}",
        COMMENT_TRANSFORM_NO_DATA="no transform data",
        COMMENT_TRANSFORM_NO_IMAGE="no image",
        COMMENT_TRANSFORM_SUCCESS_REPLY="transformed {0} {1} {2}",
        MSG_MISSING_ASSETS="missing {author} {permalink}",
        MSG_MISSING_ASSETS_SUBJECT="missing subject",
        MSG_NUKE_SUCCESS="nuked {username} {permalink}",
        MSG_NUKE_SUCCESS_SUBJECT="nuked {username}",
        MSG_RESET_SUCCESS="reset {post_id} {permalink}",
        MSG_RESET_SUCCESS_SUBJECT="reset subject",
        MSG_SET_INVALID_LANGUAGE_SUBJECT="invalid set",
        MSG_SET_LANGUAGE_SUCCESS="{greeting} {moderator} {permalink} {language_name} {language_code}",
        MSG_SET_LANGUAGES_SUCCESS="{greeting} {moderator} {permalink} {languages}",
        MSG_SET_RECLASSIFICATION_FAILED_SUBJECT="reclass failed",
        MSG_SET_RECLASSIFICATION_INVALID="reclass invalid {moderator} {post_id}",
        MSG_SET_RECLASSIFICATION_SUCCESS="reclass success {moderator} {permalink} {post_type}",
        MSG_SET_RECLASSIFICATION_SUCCESS_SUBJECT="reclass success",
        MSG_SET_RECLASSIFICATION_WRITE_FAILED="reclass write failed {moderator} {post_id}",
        MSG_SET_SUCCESS_SUBJECT="set subject",
        SNIPPET_LOOKUP_TRUNCATED="truncated {content_type}",
    )


def _common_stubs(monkeypatch) -> dict[str, types.ModuleType]:
    command_package = _make_stub_module(
        "ziwen_commands",
        update_language=MagicMock(),
        update_status=MagicMock(),
    )
    command_package.__path__ = [
        str(Path(__file__).resolve().parents[3] / "ziwen_commands")
    ]
    prawcore_exceptions = _make_stub_module(
        "prawcore.exceptions", NotFound=FakeNotFound
    )

    reddit = SimpleNamespace(
        comment=MagicMock(),
        redditor=MagicMock(side_effect=lambda name: FakeAuthor(str(name))),
        submission=MagicMock(return_value=FakeSubmission()),
        subreddit=MagicMock(),
    )

    stubs = {
        "ziwen_commands": command_package,
        "praw": _make_stub_module("praw"),
        "praw.models": _make_stub_module(
            "praw.models", Comment=FakeComment, Submission=FakeSubmission
        ),
        "prawcore": _make_stub_module(
            "prawcore", exceptions=prawcore_exceptions
        ),
        "prawcore.exceptions": prawcore_exceptions,
        "config": _make_stub_module(
            "config",
            logger=logging.getLogger("test"),
            SETTINGS={
                "claim_period": 8 * 60 * 60,
                "image_retention_age": 30,
                "internal_post_types": ["community", "meta"],
                "max_gallery_images_transform": 5,
                "max_page_languages": 10,
                "subreddit": "translator",
                "user_age_page": 7,
            },
            Paths=SimpleNamespace(SETTINGS={"LANGUAGES_SETTINGS": "unused"}),
            load_settings=lambda _path: {
                "CJK_LANGUAGES": {
                    "Chinese": ["zh", "yue", "wuu"],
                    "Japanese": ["ja"],
                    "Korean": ["ko"],
                }
            },
        ),
        "models": _make_stub_module("models"),
        "models.ajo": _make_stub_module(
            "models.ajo", Ajo=FakeAjo, ajo_delete=MagicMock()
        ),
        "models.diskuto": _make_stub_module(
            "models.diskuto",
            Diskuto=MagicMock(),
            diskuto_writer=MagicMock(),
        ),
        "models.instruo": _make_stub_module("models.instruo", Instruo=object),
        "models.komando": _make_stub_module("models.komando", Komando=FakeKomando),
        "models.kunulo": _make_stub_module("models.kunulo", Kunulo=MagicMock()),
        "reddit": _make_stub_module("reddit"),
        "reddit.connection": _make_stub_module(
            "reddit.connection",
            REDDIT=reddit,
            create_mod_note=MagicMock(),
            is_mod=MagicMock(return_value=False),
            remove_content=MagicMock(),
        ),
        "reddit.messaging": _make_stub_module(
            "reddit.messaging", notify_op_translated_post=MagicMock()
        ),
        "reddit.notifications": _make_stub_module(
            "reddit.notifications",
            notifier=MagicMock(return_value=FakeNotificationResult()),
        ),
        "reddit.reddit_sender": _make_stub_module(
            "reddit.reddit_sender",
            message_send=MagicMock(),
            reddit_edit=MagicMock(),
            reddit_reply=MagicMock(),
        ),
        "reddit.verification": _make_stub_module(
            "reddit.verification", process_verification=MagicMock()
        ),
        "reddit.wiki": _make_stub_module(
            "reddit.wiki",
            search_integration=MagicMock(return_value=None),
            update_wiki_page=MagicMock(),
        ),
        "responses": _make_stub_module("responses", RESPONSE=_response_stub()),
        "time_handling": _make_stub_module(
            "time_handling",
            get_current_utc_date=MagicMock(return_value="2026-06-26"),
            get_current_utc_time=MagicMock(return_value="2026-06-26T00:00:00Z"),
        ),
        "lang": _make_stub_module("lang"),
        "lang.code_standards": _make_stub_module(
            "lang.code_standards", PROJECT_LANGUAGE_CODES=frozenset({"und", "mul"})
        ),
        "lang.languages": _make_stub_module(
            "lang.languages",
            converter=MagicMock(side_effect=lambda code: FakeLang(code.upper(), code)),
        ),
        "integrations": _make_stub_module("integrations"),
        "integrations.image_handling": _make_stub_module(
            "integrations.image_handling",
            TRANSFORM_MAP={"h": "flip_h", "v": "flip_v"},
            rotate_or_flip_image=MagicMock(return_value=b"image"),
            upload_to_imgbb=MagicMock(return_value="https://imgbb.example/out.jpg"),
        ),
        "integrations.search_handling": _make_stub_module(
            "integrations.search_handling",
            build_search_results=MagicMock(return_value="post results"),
            fetch_search_reddit_posts=MagicMock(return_value=["abc"]),
        ),
        "utility": _make_stub_module(
            "utility",
            check_url_extension=MagicMock(return_value=True),
            clean_reddit_image_url=MagicMock(side_effect=lambda url: url),
            is_valid_image_url=MagicMock(return_value=True),
        ),
        "calendar_handling": _make_stub_module(
            "calendar_handling",
            convert_calendar_payload=MagicMock(return_value=date(2024, 2, 10)),
            format_calendar_query=MagicMock(side_effect=lambda payload: payload),
        ),
        "ziwen_lookup": _make_stub_module("ziwen_lookup"),
        "ziwen_lookup.ja": _make_stub_module(
            "ziwen_lookup.ja",
            ja_character=MagicMock(return_value="ja character"),
            ja_word=MagicMock(return_value="ja word"),
        ),
        "ziwen_lookup.ko": _make_stub_module(
            "ziwen_lookup.ko", ko_word=MagicMock(return_value="ko word")
        ),
        "ziwen_lookup.wiktionary": _make_stub_module(
            "ziwen_lookup.wiktionary",
            format_wiktionary_markdown=MagicMock(
                side_effect=lambda _result, term, language: f"WT {term} {language}"
            ),
            wiktionary_search=MagicMock(
                return_value={"word": "kunulo", "definition": ["companion"]}
            ),
        ),
        "ziwen_lookup.wp_utils": _make_stub_module(
            "ziwen_lookup.wp_utils",
            wikipedia_lookup=MagicMock(
                side_effect=lambda terms, language_code="en": (
                    f"WP {language_code}:{','.join(terms)}"
                )
            ),
        ),
        "ziwen_lookup.zh": _make_stub_module(
            "ziwen_lookup.zh",
            zh_character=MagicMock(return_value="zh character"),
            zh_word=MagicMock(return_value="zh word"),
        ),
    }

    for module_name, module in stubs.items():
        monkeypatch.setitem(sys.modules, module_name, module)
    return stubs


def _load_command_module(monkeypatch, command_name: str):
    _common_stubs(monkeypatch)
    command_path = (
        Path(__file__).resolve().parents[3] / "ziwen_commands" / f"{command_name}.py"
    )
    module_name = f"ziwen_commands.{command_name}"
    spec = importlib.util.spec_from_file_location(module_name, command_path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, module_name, module)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _patch_kunulo(monkeypatch, module, kunulo: FakeKunulo) -> None:
    monkeypatch.setattr(
        module, "Kunulo", SimpleNamespace(from_submission=MagicMock(return_value=kunulo))
    )


def _setup_nuke_test(monkeypatch, nuked: FakeAuthor):
    module = _load_command_module(monkeypatch, "nuke")
    mod = FakeAuthor("mod")
    parent = FakeComment(author=nuked)
    comment = FakeComment(author=mod, parent=parent)
    banned = SimpleNamespace(add=MagicMock())
    reddit = SimpleNamespace(
        subreddit=MagicMock(return_value=SimpleNamespace(banned=banned))
    )
    removed: list[HasId] = []
    sent: list[tuple[object, str, str]] = []
    monkeypatch.setattr(module, "is_mod", lambda _author: True)
    monkeypatch.setattr(module, "REDDIT", reddit)
    monkeypatch.setattr(
        module, "remove_content", lambda item, *_args: removed.append(item)
    )
    monkeypatch.setattr(
        module,
        "message_send",
        lambda target, subject, body: sent.append((target, subject, body)),
    )
    monkeypatch.setattr(module, "create_mod_note", MagicMock())
    return module, mod, parent, comment, banned, removed, sent


def _assert_nuke_completed(module, mod: FakeAuthor, banned, sent) -> None:
    banned.add.assert_called_once()
    assert sent[0][0] is mod
    module.create_mod_note.assert_called_once_with(
        "PERMA_BAN", "spammer", "Mod u/mod nuked u/spammer."
    )


def test_calendar_replies_with_converted_date(monkeypatch) -> None:
    module = _load_command_module(monkeypatch, "calendar")
    replies: list[str] = []
    monkeypatch.setattr(module, "reddit_reply", lambda _comment, body: replies.append(body))
    monkeypatch.setattr(module, "convert_calendar_payload", lambda _payload: date(2024, 2, 10))

    module.handle(FakeComment(), None, FakeKomando(["hebrew:5784:Adar:1"]), FakeAjo())

    assert "hebrew:5784:Adar:1" in replies[0]
    assert "2024-02-10" in replies[0]


def test_parse_claim_comment_uses_eight_hour_claim_window(monkeypatch) -> None:
    module = _load_command_module(monkeypatch, "claim")

    claim_comment = (
        "**Claimer:** u/Maty3105 at "
        "[2026-06-25T19:06:18Z UTC](https://time.lol/#2026-06-25T19:06:18Z)\n\n"
        "**Language:** German (`de`)"
    )
    current_time = 1782414554  # 2026-06-25T19:09:14Z

    parsed = module.parse_claim_comment(claim_comment, current_time)

    assert parsed["claimer"] == "Maty3105"
    assert parsed["language"].preferred_code == "de"
    assert parsed["seconds_until_expiry"] == 28624


def test_parse_claim_comment_marks_claim_expired_after_window(monkeypatch) -> None:
    module = _load_command_module(monkeypatch, "claim")

    claim_comment = (
        "**Claimer:** u/Maty3105 at "
        "[2026-06-25T19:06:18Z UTC](https://time.lol/#2026-06-25T19:06:18Z)\n\n"
        "**Language:** German (`de`)"
    )
    current_time = 1782443185  # 2026-06-26T03:06:25Z

    parsed = module.parse_claim_comment(claim_comment, current_time)

    assert parsed["seconds_until_expiry"] == -7


def test_claim_marks_language_in_progress_and_posts_claim_comment(monkeypatch) -> None:
    module = _load_command_module(monkeypatch, "claim")
    language = FakeLang("German", "de")
    ajo = FakeAjo()
    replies: list[tuple[object, str]] = []
    updates: list[tuple[object, object, str, list[FakeLang]]] = []
    claim_reply = FakeComment()
    _patch_kunulo(monkeypatch, module, FakeKunulo())
    monkeypatch.setattr(module, "update_status", lambda *args: updates.append(args))
    monkeypatch.setattr(
        module,
        "reddit_reply",
        lambda target, body: replies.append((target, body)) or claim_reply,
    )

    module.handle(
        FakeComment(body="!claim", submission=ajo.submission),
        None,
        FakeKomando([language], "claim"),
        ajo,
    )

    assert updates[0][2] == "inprogress"
    assert updates[0][3] == [language]
    assert replies[0][0] is ajo.submission
    assert "German" in replies[0][1]
    claim_reply.mod.distinguish.assert_called_once_with(sticky=True)


def test_doublecheck_updates_status_and_deletes_claim_comment(monkeypatch) -> None:
    module = _load_command_module(monkeypatch, "doublecheck")
    kunulo = FakeKunulo()
    updates: list[tuple[object, object, str]] = []
    _patch_kunulo(monkeypatch, module, kunulo)
    monkeypatch.setattr(module, "update_status", lambda *args: updates.append(args))

    module.handle(FakeComment(), None, FakeKomando(name="doublecheck"), FakeAjo())

    assert updates[0][2] == "doublecheck"
    assert kunulo.deleted == ["comment_claim"]


def test_identify_updates_language_sends_notifications_and_deletes_unknown_comment(
    monkeypatch,
) -> None:
    module = _load_command_module(monkeypatch, "identify")
    new_language = FakeLang("Japanese", "ja")
    ajo = FakeAjo()
    kunulo = FakeKunulo()
    _patch_kunulo(monkeypatch, module, kunulo)
    monkeypatch.setattr(module, "update_language", lambda target, _cmd: setattr(target, "lingvo", new_language))
    monkeypatch.setattr(
        module,
        "notifier",
        MagicMock(
            return_value=FakeNotificationResult(
                subscriber_count=1,
                eligible_count=1,
                attempted_count=1,
                sent_usernames=["reader1"],
            )
        ),
    )

    module.handle(
        FakeComment(body="!identify:ja", submission=ajo.submission),
        SimpleNamespace(commands=[]),
        FakeKomando([new_language], "identify"),
        ajo,
    )

    module.update_wiki_page.assert_called_once()
    module.notifier.assert_called_once_with(new_language, ajo.submission, "identify")
    assert ajo.notified == ["reader1"]
    assert kunulo.deleted == ["comment_unknown"]


def test_long_toggles_off_and_deletes_long_comment_for_original_poster(
    monkeypatch,
) -> None:
    module = _load_command_module(monkeypatch, "long")
    author = FakeAuthor("op")
    submission = FakeSubmission(author=author)
    ajo = FakeAjo(submission)
    ajo.is_long = True
    kunulo = FakeKunulo()
    _patch_kunulo(monkeypatch, module, kunulo)

    module.handle(FakeComment(author=author, submission=submission), None, FakeKomando(), ajo)

    assert ajo.is_long is False
    assert kunulo.deleted == ["comment_long"]


def test_lookup_cjk_replies_with_lookup_result(monkeypatch) -> None:
    module = _load_command_module(monkeypatch, "lookup_cjk")
    _patch_kunulo(monkeypatch, module, FakeKunulo())
    replies: list[str] = []
    monkeypatch.setattr(module, "reddit_reply", lambda _comment, body: replies.append(body))

    async def fake_lookup(_language: str, terms: list[str]) -> list[str]:
        return [f"lookup {term}" for term in terms]

    monkeypatch.setattr(module, "perform_cjk_lookups", fake_lookup)

    module.handle(
        FakeComment(comment_id="cjk1"),
        SimpleNamespace(commands=[]),
        FakeKomando([("zh", "成功", False)], "lookup_cjk"),
        FakeAjo(),
    )

    assert "lookup 成功" in replies[0]
    assert "[](#cjk_parent_cjk1)" in replies[0]


def test_lookup_wp_groups_terms_by_language_and_replies(monkeypatch) -> None:
    module = _load_command_module(monkeypatch, "lookup_wp")
    _patch_kunulo(monkeypatch, module, FakeKunulo())
    replies: list[str] = []
    monkeypatch.setattr(module, "reddit_reply", lambda _comment, body: replies.append(body))

    module.handle(
        FakeComment(comment_id="wp1"),
        None,
        FakeKomando([("紫禁城", "zh")], "lookup_wp"),
        FakeAjo(),
    )

    assert "WP zh:紫禁城" in replies[0]
    assert "[](#wp_parent_wp1)" in replies[0]


def test_lookup_wt_uses_explicit_language_and_replies(monkeypatch) -> None:
    module = _load_command_module(monkeypatch, "lookup_wt")
    _patch_kunulo(monkeypatch, module, FakeKunulo())
    replies: list[str] = []
    monkeypatch.setattr(module, "reddit_reply", lambda _comment, body: replies.append(body))

    module.handle(
        FakeComment(comment_id="wt1"),
        None,
        FakeKomando([("eo", "kunulo", True)], "lookup_wt"),
        FakeAjo(),
    )

    assert "WT kunulo EO" in replies[0]
    assert "[](#wt_parent_wt1)" in replies[0]


def test_lookup_wt_skips_result_without_definitions(monkeypatch) -> None:
    module = _load_command_module(monkeypatch, "lookup_wt")
    _patch_kunulo(monkeypatch, module, FakeKunulo())
    replies: list[str] = []
    monkeypatch.setattr(module, "reddit_reply", lambda _comment, body: replies.append(body))
    monkeypatch.setattr(
        module,
        "wiktionary_search",
        lambda term, _language: (
            {"word": term, "definition": None}
            if term == "empty"
            else {"word": term, "definition": ["usable"]}
        ),
    )

    module.handle(
        FakeComment(comment_id="wt2"),
        None,
        FakeKomando(
            [("eo", "empty", True), ("eo", "valid", True)],
            "lookup_wt",
        ),
        FakeAjo(),
    )

    assert len(replies) == 1
    assert "WT valid EO" in replies[0]
    assert "WT empty EO" not in replies[0]


def test_lookup_wt_does_not_reply_when_all_results_lack_definitions(
    monkeypatch,
) -> None:
    module = _load_command_module(monkeypatch, "lookup_wt")
    _patch_kunulo(monkeypatch, module, FakeKunulo())
    replies: list[str] = []
    monkeypatch.setattr(module, "reddit_reply", lambda _comment, body: replies.append(body))
    monkeypatch.setattr(
        module,
        "wiktionary_search",
        lambda term, _language: {"word": term, "definition": None},
    )

    module.handle(
        FakeComment(comment_id="wt3"),
        None,
        FakeKomando([("it", "empty", True)], "lookup_wt"),
        FakeAjo(),
    )

    assert replies == []


def test_missing_updates_status_and_messages_original_poster(monkeypatch) -> None:
    module = _load_command_module(monkeypatch, "missing")
    updates: list[tuple[object, object, str]] = []
    sent: list[tuple[object, str, str]] = []
    monkeypatch.setattr(module, "update_status", lambda *args: updates.append(args))
    monkeypatch.setattr(module, "message_send", lambda target, subject, body: sent.append((target, subject, body)))

    module.handle(FakeComment(), None, FakeKomando(name="missing"), FakeAjo())

    assert updates[0][2] == "missing"
    assert sent[0][1] == "missing subject"
    assert "missing op" in sent[0][2]


def test_nuke_bans_removes_content_messages_mod_and_notes(monkeypatch) -> None:
    nuked = FakeAuthor("spammer")
    nuked.submissions = SimpleNamespace(
        new=lambda limit=None: iter(
            [
                SimpleNamespace(
                    id="submission1",
                    subreddit=SimpleNamespace(display_name="translator"),
                )
            ]
        )
    )
    nuked.comments = SimpleNamespace(
        new=lambda limit=None: iter(
            [
                SimpleNamespace(
                    id="comment1",
                    subreddit=SimpleNamespace(display_name="translator"),
                ),
                SimpleNamespace(
                    id="comment2",
                    subreddit=SimpleNamespace(display_name="translator"),
                ),
            ]
        )
    )
    module, mod, _, comment, banned, removed, sent = _setup_nuke_test(
        monkeypatch, nuked
    )

    module.handle(comment, None, FakeKomando(name="nuke"), FakeAjo())

    assert [item.id for item in removed] == ["comment1", "submission1", "comment2"]
    _assert_nuke_completed(module, mod, banned, sent)


def test_nuke_continues_when_shadowbanned_user_history_404s(monkeypatch) -> None:
    nuked = FakeAuthor("spammer")

    def unavailable_history():
        fetch_item = MagicMock(side_effect=FakeNotFound("shadowbanned"))
        return iter(fetch_item, None)

    nuked.submissions = SimpleNamespace(new=lambda limit=None: unavailable_history())
    nuked.comments = SimpleNamespace(new=lambda limit=None: unavailable_history())
    module, mod, parent, comment, banned, removed, sent = _setup_nuke_test(
        monkeypatch, nuked
    )

    module.handle(comment, None, FakeKomando(name="nuke"), FakeAjo())

    assert removed == [parent]
    _assert_nuke_completed(module, mod, banned, sent)


def test_page_replies_when_no_subscribers_exist(monkeypatch) -> None:
    module = _load_command_module(monkeypatch, "page")
    author = FakeAuthor("helper", created_utc=0)
    language = FakeLang("Esperanto", "eo")
    replies: list[str] = []
    monkeypatch.setattr(module.time, "time", lambda: 20 * 86400)
    monkeypatch.setattr(module, "reddit_reply", lambda _comment, body: replies.append(body))
    monkeypatch.setattr(
        module, "notifier", MagicMock(return_value=FakeNotificationResult())
    )

    module.handle(
        FakeComment(author=author),
        None,
        FakeKomando([language], "page"),
        FakeAjo(),
    )

    module.notifier.assert_called_once()
    assert "no subscribers Esperanto eo" in replies[0]


def test_page_distinguishes_unreachable_subscribers_from_no_coverage(
    monkeypatch,
) -> None:
    module = _load_command_module(monkeypatch, "page")
    author = FakeAuthor("helper", created_utc=0)
    language = FakeLang("Persian", "fa")
    replies: list[str] = []
    result = FakeNotificationResult(
        subscriber_count=20,
        already_contacted_count=19,
        eligible_count=1,
        attempted_count=1,
        failed_usernames=["blocked_user"],
    )
    monkeypatch.setattr(module.time, "time", lambda: 20 * 86400)
    monkeypatch.setattr(module, "reddit_reply", lambda _comment, body: replies.append(body))
    monkeypatch.setattr(module, "notifier", MagicMock(return_value=result))

    module.handle(
        FakeComment(author=author),
        None,
        FakeKomando([language], "page"),
        FakeAjo(),
    )

    assert "no additional recipients Persian fa" in replies[0]
    assert "no subscribers" not in replies[0]


def test_page_replies_for_invalid_language_without_notifier(monkeypatch) -> None:
    module = _load_command_module(monkeypatch, "page")
    author = FakeAuthor("helper", created_utc=0)
    replies: list[str] = []
    monkeypatch.setattr(module.time, "time", lambda: 20 * 86400)
    monkeypatch.setattr(module, "reddit_reply", lambda _comment, body: replies.append(body))
    monkeypatch.setattr(module, "notifier", MagicMock(return_value=["reader1"]))

    module.handle(
        FakeComment(author=author, body="!page:ber"),
        None,
        FakeKomando([None], "page"),
        FakeAjo(),
    )

    module.notifier.assert_not_called()
    assert replies == ["invalid language !page:ber"]


def test_reset_resets_post_and_messages_caller(monkeypatch) -> None:
    module = _load_command_module(monkeypatch, "reset")
    author = FakeAuthor("op")
    submission = FakeSubmission(author=author)
    ajo = FakeAjo(submission)
    sent: list[tuple[object, str, str]] = []
    monkeypatch.setattr(module, "message_send", lambda target, subject, body: sent.append((target, subject, body)))

    module.handle(FakeComment(author=author, submission=submission), None, FakeKomando(), ajo)

    assert ajo.reset_called is True
    assert sent[0][0] is author
    assert sent[0][1] == "reset subject"


def test_search_replies_with_frequently_translated_advisory(monkeypatch) -> None:
    module = _load_command_module(monkeypatch, "search")
    replies: list[str] = []
    monkeypatch.setattr(module, "search_integration", MagicMock(return_value="Advisory: common request"))
    monkeypatch.setattr(module, "fetch_search_reddit_posts", MagicMock())
    monkeypatch.setattr(module, "reddit_reply", lambda _comment, body: replies.append(body))

    module.handle(FakeComment(), None, FakeKomando(["allergy"], "search"), FakeAjo())

    assert replies == ["Advisory: common request\n\n--bot--"]
    module.fetch_search_reddit_posts.assert_not_called()


def test_set_updates_language_deletes_stale_comments_and_messages_mod(monkeypatch) -> None:
    module = _load_command_module(monkeypatch, "set")
    mod = FakeAuthor("mod")
    language = FakeLang("Japanese", "ja")
    kunulo = FakeKunulo()
    sent: list[tuple[object, str, str]] = []
    _patch_kunulo(monkeypatch, module, kunulo)
    monkeypatch.setattr(module, "is_mod", lambda _author: True)
    monkeypatch.setattr(module, "update_language", MagicMock())
    monkeypatch.setattr(module, "message_send", lambda target, subject, body: sent.append((target, subject, body)))

    module.handle(
        FakeComment(author=mod),
        None,
        FakeKomando([language], "set"),
        FakeAjo(),
    )

    module.update_language.assert_called_once()
    assert kunulo.deleted == ["comment_defined_multiple", "comment_unknown"]
    assert sent[0][1] == "set subject"
    assert "Japanese" in sent[0][2]


def test_transform_processes_single_image_and_replies(monkeypatch) -> None:
    module = _load_command_module(monkeypatch, "transform")
    replies: list[str] = []
    monkeypatch.setattr(module, "reddit_reply", lambda _comment, body: replies.append(body))

    module.handle(
        FakeComment(body="!transform:90"),
        None,
        FakeKomando(["90"], "transform"),
        FakeAjo(),
    )

    module.rotate_or_flip_image.assert_called_once_with(
        "https://example.com/image.jpg", "90"
    )
    module.upload_to_imgbb.assert_called_once()
    assert "90° clockwise rotation" in replies[0]
    assert "https://imgbb.example/out.jpg" in replies[0]


def test_translated_updates_status_deletes_tracking_comments_and_notifies_op(
    monkeypatch,
) -> None:
    module = _load_command_module(monkeypatch, "translated")
    author = FakeAuthor("translator")
    ajo = FakeAjo()
    ajo.author = "op"
    kunulo = FakeKunulo()
    updates: list[tuple[object, object, str]] = []
    _patch_kunulo(monkeypatch, module, kunulo)
    monkeypatch.setattr(module, "update_status", lambda *args: updates.append(args))
    monkeypatch.setattr(module, "notify_op_translated_post", MagicMock())

    module.handle(
        FakeComment(author=author, submission=ajo.submission),
        None,
        FakeKomando(name="translated"),
        ajo,
    )

    assert updates[0][2] == "translated"
    assert kunulo.deleted == ["comment_long", "comment_claim"]
    module.notify_op_translated_post.assert_called_once_with(
        "op", ajo.submission.permalink
    )


def test_verify_delegates_to_verification_processor(monkeypatch) -> None:
    module = _load_command_module(monkeypatch, "verify")
    comment = FakeComment(body="!verify")

    module.handle(comment, None, FakeKomando(name="verify"), FakeAjo())

    module.process_verification.assert_called_once_with(comment)
