#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""Tests for Zhongsheng recruitment command output."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from zhongsheng import recruit as recruit_module


def test_recruit_discord_response_includes_subject(monkeypatch) -> None:
    """The Discord /recruit command returns both copyable post fields."""
    language_matches = [SimpleNamespace(name="English", preferred_code="en")]
    sent_message = None

    async def capture_long_message(ctx, content: str) -> None:
        nonlocal sent_message
        sent_message = content

    monkeypatch.setattr(
        recruit_module,
        "resolve_recruit_languages",
        lambda languages: (language_matches, []),
    )
    monkeypatch.setattr(
        recruit_module,
        "build_recruitment_subject",
        lambda matches: "Please help us translate English requests on Reddit!",
    )
    monkeypatch.setattr(
        recruit_module,
        "build_recruitment_markdown",
        lambda matches: "Recruitment post body",
    )
    monkeypatch.setattr(recruit_module, "send_long_message", capture_long_message)

    ctx = SimpleNamespace(author=SimpleNamespace(name="moderator"), send=AsyncMock())

    asyncio.run(recruit_module.recruit(ctx, languages="en"))

    assert sent_message is not None
    assert "Copy this subject into the recruitment post:" in sent_message
    assert "Please help us translate English requests on Reddit!" in sent_message
    assert "Copy this Markdown into the recruitment post body:" in sent_message
    assert "Recruitment post body" in sent_message


def test_recruitment_markdown_starts_with_native_greeting(monkeypatch) -> None:
    """The post body uses a native greeting when the Lingvo provides one."""
    monkeypatch.setattr(
        recruit_module,
        "RESPONSE",
        SimpleNamespace(
            POST_RECRUITMENT_POST_INTRO=(
                "We're mods over at r/translator for {target_languages}."
            ),
            MSG_SUBSCRIBE_LINK="https://reddit.example/compose?message=",
        ),
    )
    monkeypatch.setattr(
        recruit_module,
        "describe_language_frequency",
        lambda lingvo: None,
    )

    markdown = recruit_module.build_recruitment_markdown(
        [
            SimpleNamespace(
                name="French",
                preferred_code="fr",
                greetings="Bonjour!",
                thanks="Thanks",
            )
        ]
    )

    assert markdown.startswith("Bonjour!\n\nWe're mods over at r/translator")


def test_recruitment_markdown_omits_default_english_greeting(monkeypatch) -> None:
    """The default Lingvo greeting is not treated as a native greeting."""
    monkeypatch.setattr(
        recruit_module,
        "RESPONSE",
        SimpleNamespace(
            POST_RECRUITMENT_POST_INTRO=(
                "We're mods over at r/translator for {target_languages}."
            ),
            MSG_SUBSCRIBE_LINK="https://reddit.example/compose?message=",
        ),
    )
    monkeypatch.setattr(
        recruit_module,
        "describe_language_frequency",
        lambda lingvo: None,
    )

    markdown = recruit_module.build_recruitment_markdown(
        [
            SimpleNamespace(
                name="Example",
                preferred_code="ex",
                greetings="Hello",
                thanks="Thanks",
            )
        ]
    )

    assert markdown.startswith("We're mods over at r/translator")


def test_recruitment_markdown_puts_signup_before_frequency(monkeypatch) -> None:
    """The signup link is the second table column."""
    monkeypatch.setattr(
        recruit_module,
        "RESPONSE",
        SimpleNamespace(
            POST_RECRUITMENT_POST_INTRO=(
                "We're mods over at r/translator for {target_languages}."
            ),
            MSG_SUBSCRIBE_LINK="https://reddit.example/compose?message=",
        ),
    )
    monkeypatch.setattr(
        recruit_module,
        "describe_language_frequency",
        lambda lingvo: (9.12, "year"),
    )

    markdown = recruit_module.build_recruitment_markdown(
        [
            SimpleNamespace(
                name="Yoruba",
                preferred_code="yo",
                greetings="Hello",
                thanks="Thanks",
            )
        ]
    )

    assert "| Language | Notification signup | Estimated request frequency |" in markdown
    assert "|---|---|---:|" in markdown
    assert (
        "| Yoruba | ➡️ **[Get Yoruba translation notifications]"
        "(https://reddit.example/compose?message=yo)** | 9.12 posts/year |"
        in markdown
    )


def test_recruitment_markdown_ends_with_native_thanks(monkeypatch) -> None:
    """The post body uses native thanks when the Lingvo provides one."""
    monkeypatch.setattr(
        recruit_module,
        "RESPONSE",
        SimpleNamespace(
            POST_RECRUITMENT_POST_INTRO=(
                "We're mods over at r/translator for {target_languages}."
            ),
            MSG_SUBSCRIBE_LINK="https://reddit.example/compose?message=",
        ),
    )
    monkeypatch.setattr(
        recruit_module,
        "describe_language_frequency",
        lambda lingvo: None,
    )

    markdown = recruit_module.build_recruitment_markdown(
        [
            SimpleNamespace(
                name="French",
                preferred_code="fr",
                greetings="Hello",
                thanks="Merci!",
            )
        ]
    )

    assert markdown.endswith("\n\nMerci!")


def test_recruitment_markdown_falls_back_to_default_thanks(monkeypatch) -> None:
    """The default Lingvo thanks value keeps the English closing line."""
    monkeypatch.setattr(
        recruit_module,
        "RESPONSE",
        SimpleNamespace(
            POST_RECRUITMENT_POST_INTRO=(
                "We're mods over at r/translator for {target_languages}."
            ),
            MSG_SUBSCRIBE_LINK="https://reddit.example/compose?message=",
        ),
    )
    monkeypatch.setattr(
        recruit_module,
        "describe_language_frequency",
        lambda lingvo: None,
    )

    markdown = recruit_module.build_recruitment_markdown(
        [
            SimpleNamespace(
                name="Example",
                preferred_code="ex",
                greetings="Hello",
                thanks="Thanks",
            )
        ]
    )

    assert markdown.endswith("\n\nThanks, everyone!")
