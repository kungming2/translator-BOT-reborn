#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
Generate recruitment-post notification links for moderators.

Logger tag: [ZS:RECRUIT]
"""

import logging
import re
from urllib.parse import quote_plus

from discord.ext import commands

from config import logger as _base_logger
from lang.languages import Lingvo, converter
from monitoring.usage_statistics import describe_language_frequency
from responses import RESPONSE

from . import command, send_long_message

logger = logging.LoggerAdapter(_base_logger, {"tag": "ZS:RECRUIT"})

RECRUIT_DELIMITER_PATTERN = re.compile(r"[,+/\n:;]+")


@command(
    name="recruit",
    help_text="Generate copyable recruitment-post notification links for language codes.",
    roles=["Moderator"],
)
async def recruit(ctx: commands.Context, languages: str) -> None:
    """
    Generate Markdown rows for a recruitment post.

    Usage:
        /recruit id, nan, ban
    """
    language_matches, unresolved_items = resolve_recruit_languages(languages)

    if not language_matches:
        await ctx.send(
            f"⚠️ No valid language codes found in: `{languages}`\n"
            f"Please use ISO 639 codes or language names, separated by commas."
        )
        return

    logger.info(
        "Recruitment link request from %s for %s language(s)",
        ctx.author.name,
        len(language_matches),
    )

    subject = build_recruitment_subject(language_matches)
    markdown = build_recruitment_markdown(language_matches)
    response = (
        "Copy this subject into the recruitment post:\n\n"
        f"```\n{subject}\n```\n\n"
        "Copy this Markdown into the recruitment post body:\n\n"
        f"```\n{markdown}\n```"
    )
    if unresolved_items:
        response += "\n\nSkipped unresolved items: " + ", ".join(
            f"`{item}`" for item in unresolved_items
        )
    await send_long_message(ctx, response)


def parse_recruit_languages(language_text: str) -> list:
    """Resolve a moderator-entered language list while preserving input order."""
    matches, _unresolved_items = resolve_recruit_languages(language_text)
    return matches


def resolve_recruit_languages(language_text: str) -> tuple[list, list[str]]:
    """Resolve recruitment languages and return both matches and unresolved input."""
    if not language_text:
        return [], []

    items = _split_recruit_language_items(language_text)

    matches = []
    unresolved_items = []
    seen_codes = set()
    for item in items:
        item = item.strip()
        if not item:
            continue

        lingvo = converter(item, fuzzy=False)
        if lingvo is None:
            unresolved_items.append(item)
            continue
        if lingvo.preferred_code in seen_codes:
            continue

        matches.append(lingvo)
        seen_codes.add(lingvo.preferred_code)

    return matches, unresolved_items


def _split_recruit_language_items(language_text: str) -> list[str]:
    """Split a recruitment language list without breaking known multi-word names."""
    if RECRUIT_DELIMITER_PATTERN.search(language_text):
        return RECRUIT_DELIMITER_PATTERN.split(language_text)

    whole_match = converter(language_text, fuzzy=False)
    if whole_match is not None:
        return [language_text]
    return language_text.split()


def build_recruitment_markdown(language_matches: list) -> str:
    """Build copyable Markdown recruitment text with notification signup links."""
    target_languages = _format_target_languages(language_matches)
    intro = RESPONSE.POST_RECRUITMENT_POST_INTRO.format(
        target_languages=target_languages
    ).rstrip("\n")
    greeting = _format_recruitment_greeting(language_matches)
    if greeting:
        intro = f"{greeting}!\n\n{intro}"
    rows = [
        "| Language | Estimated request frequency | Notification signup |",
        "|---|---:|---|",
    ]

    for lingvo in language_matches:
        language_name = _escape_markdown_table_cell(
            lingvo.name or lingvo.preferred_code
        )
        frequency = _format_frequency(lingvo)
        link = _subscription_link(lingvo)
        rows.append(
            f"| {language_name} | {frequency} | "
            f"[Get {language_name} translation notifications]({link}) |"
        )

    rows.extend(
        [
            "",
            _format_recruitment_thanks(language_matches),
        ]
    )
    return "\n".join([intro, "", *rows])


def build_recruitment_subject(language_matches: list) -> str:
    """Build a copyable Reddit post subject for a recruitment post."""
    target_languages = _format_target_languages(language_matches, escape=False)
    return RESPONSE.POST_RECRUITMENT_POST_SUBJECT.format(
        target_languages=target_languages
    )


def _format_target_languages(language_matches: list, escape: bool = True) -> str:
    """Return language names for the recruitment intro sentence."""
    names = [
        _escape_markdown_inline(lingvo.name or lingvo.preferred_code)
        if escape
        else lingvo.name or lingvo.preferred_code
        for lingvo in language_matches
    ]
    if not names:
        return "the target language"
    if len(names) == 1:
        return names[0]
    if len(names) == 2:
        return f"{names[0]} or {names[1]}"
    return f"{', '.join(names[:-1])}, or {names[-1]}"


def _format_recruitment_greeting(language_matches: list) -> str:
    """Return native greetings to lead the recruitment post body, when available."""
    return _format_native_recruitment_phrase(language_matches, "greetings", "hello")


def _format_recruitment_thanks(language_matches: list) -> str:
    """Return native thanks to close the recruitment post body, when available."""
    thanks = _format_native_recruitment_phrase(language_matches, "thanks", "thanks")
    if thanks:
        return f"{thanks}!"
    return "Thanks, everyone!"


def _format_native_recruitment_phrase(
    language_matches: list, attribute: str, default_value: str
) -> str:
    """Return unique native Lingvo phrases, excluding default placeholder values."""
    phrases = []
    seen_phrases = set()
    for lingvo in language_matches:
        phrase = getattr(lingvo, attribute, "").strip().rstrip("!.?")
        if not phrase or phrase.lower() == default_value:
            continue
        if phrase in seen_phrases:
            continue
        phrases.append(phrase)
        seen_phrases.add(phrase)

    return " ".join(phrases)


def _subscription_link(lingvo: Lingvo) -> str:
    """Return a Reddit compose URL that subscribes to one language."""
    payload = lingvo.preferred_code
    return RESPONSE.MSG_SUBSCRIBE_LINK + quote_plus(payload)


def _format_frequency(lingvo: Lingvo) -> str:
    """Return a short human-readable frequency estimate for the recruitment table."""
    frequency = describe_language_frequency(lingvo)
    if frequency is None:
        return "No recorded statistics"

    rate, period = frequency
    return f"{rate:.2f} posts/{period}"


def _escape_markdown_table_cell(text: str) -> str:
    """Escape Markdown table separators in generated cell text."""
    return text.replace("|", r"\|")


def _escape_markdown_inline(text: str) -> str:
    """Escape Markdown syntax that would affect the recruitment intro."""
    return text.replace("*", r"\*").replace("[", r"\[").replace("]", r"\]")
