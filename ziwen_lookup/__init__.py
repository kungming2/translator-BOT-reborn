#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""Shared primitives for lookup parsing."""

import re

# The bot's lookup syntax uses exactly one backtick on each side. Backticks that
# touch another backtick belong to a longer Markdown delimiter (or are commonly
# used as TeX-style opening quotation marks) and must not be paired across prose.
BACKTICK_LOOKUP_PATTERN: re.Pattern[str] = re.compile(
    r"(?<!`)`(?!`)([^`]+?)`(?!`)(?::([^!\s]+))?(!)?"
)
