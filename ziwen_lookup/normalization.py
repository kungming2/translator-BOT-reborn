#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""Shared normalization for dictionary and cache lookup keys."""

import unicodedata


def normalize_lookup_key(text: str) -> str:
    """Strip surrounding whitespace and normalize Unicode compatibility forms."""
    return unicodedata.normalize("NFKC", text.strip())
