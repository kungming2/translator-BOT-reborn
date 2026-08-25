#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""Shared primitives for lookup parsing."""

import re
import unicodedata

# The bot's lookup syntax uses exactly one backtick on each side. Backticks that
# touch another backtick belong to a longer Markdown delimiter (or are commonly
# used as TeX-style opening quotation marks) and must not be paired across prose.
BACKTICK_LOOKUP_PATTERN: re.Pattern[str] = re.compile(
    r"(?<!`)`(?!`)([^`\r\n]+?)`(?!`)(?::([^!\s]+))?(!)?"
)


def normalize_lookup_term(term: str) -> str | None:
    """Trim a lookup term and reject empty or control-bearing input."""
    if any(unicodedata.category(character) == "Cc" for character in term):
        return None

    normalized_term = term.strip()
    return normalized_term or None
