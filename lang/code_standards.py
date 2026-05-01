#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
Small adapter around langcodes for standards-backed language-code handling.

This module intentionally returns plain strings/parts. The project-level
canonical object remains ``models.lingvo.Lingvo`` and resolution still happens
in ``lang.languages``.
"""

from __future__ import annotations

from dataclasses import dataclass

from langcodes import Language, standardize_tag
from langcodes.tag_parser import LanguageTagError

PROJECT_LANGUAGE_CODES = {"unknown", "multiple", "generic"}


@dataclass(frozen=True)
class StandardLanguageTag:
    """Parsed BCP 47-style tag parts relevant to translator-BOT."""

    tag: str
    language: str | None = None
    script: str | None = None
    territory: str | None = None


def standardize_language_tag(tag: str) -> str | None:
    """
    Return a normalized BCP 47 tag, or None if it cannot be parsed.

    Project-specific compatibility codes are deliberately not translated to ISO
    special codes here. For example, ``unknown`` stays outside this adapter
    instead of becoming BCP 47 ``und``.
    """
    cleaned = tag.strip()
    if not cleaned or cleaned.lower() in PROJECT_LANGUAGE_CODES:
        return None

    try:
        return standardize_tag(cleaned)
    except (LanguageTagError, ValueError):
        return None


def parse_language_tag(tag: str) -> StandardLanguageTag | None:
    """Parse a BCP 47-style tag into language/script/territory components."""
    standardized = standardize_language_tag(tag)
    if standardized is None:
        return None

    try:
        parsed = Language.get(standardized)
    except (LanguageTagError, ValueError):
        return None

    return StandardLanguageTag(
        tag=standardized,
        language=parsed.language,
        script=parsed.script,
        territory=parsed.territory,
    )


def alpha3_code(code: str, variant: str = "T") -> str | None:
    """
    Return the ISO 639-2/3 alpha-3 code for a language code.

    ``variant="T"`` returns terminology codes and ``variant="B"`` returns
    bibliographic codes when they differ. Unknown or project-specific codes
    return None.
    """
    cleaned = code.strip()
    if not cleaned or cleaned.lower() in PROJECT_LANGUAGE_CODES:
        return None

    try:
        return Language.get(cleaned).to_alpha3(variant=variant)
    except (LanguageTagError, LookupError, ValueError):
        return None


def preferred_standard_code(code: str) -> str | None:
    """
    Return langcodes' shortest standard language code for code-like input.

    This maps overlong and bibliographic forms such as ``eng`` -> ``en`` and
    ``fre`` -> ``fr``. Region/script subtags are ignored by callers that need a
    base language lookup.
    """
    parsed = parse_language_tag(code)
    if parsed is None:
        return None
    return parsed.language
