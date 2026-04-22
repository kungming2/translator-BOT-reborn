#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
Country lookup and flag-emoji utilities used across the r/translator bot
ecosystem.

This module is intentionally independent of the language loader in
lang/languages.py. Its only external dependency from this project is
config.Paths for dataset file locations. It can therefore be imported and
tested without loading any language data.

Key components:
    country_converter    -- Resolve a name/code string to (alpha2, name).
    get_country_emoji    -- Return the flag emoji for a country name.
    get_language_emoji   -- Return the flag emoji for a language code.
    _load_country_list   -- Internal CSV loader with module-level cache.

Logger tag: [LANG:COUNTRIES]
"""

# ─── Imports ──────────────────────────────────────────────────────────────────

import contextlib  # used for search_fuzzy fallback in get_country_emoji
import csv
import logging

import pycountry

from config import Paths, load_settings
from config import logger as _base_logger

# ─── Module-level constants ───────────────────────────────────────────────────

logger = logging.LoggerAdapter(_base_logger, {"tag": "LANG:COUNTRIES"})

_country_list_cache = None  # cached country list from CSV
_language_full_data_cache = None  # cached language YAML data for emoji lookups


# ─── Dataset loader ───────────────────────────────────────────────────────────


def _load_country_list() -> list[tuple[str, str, str, str, list[str]]]:
    """
    Load countries from a CSV file.

    Expected CSV columns: Country Name, Alpha-2, Alpha-3, Numeric Code,
                          Synonyms (semicolon-separated)

    Returns:
        List of tuples containing (name, alpha2, alpha3, numeric_code, keywords).
    """
    global _country_list_cache
    if _country_list_cache is not None:
        return _country_list_cache

    country_list: list[tuple[str, str, str, str, list[str]]] = []
    try:
        with open(
            Paths.DATASETS["COUNTRIES"], newline="", encoding="utf-8-sig"
        ) as csvfile:
            reader = csv.reader(csvfile)
            next(
                reader
            )  # Skip header row: Country Name, Alpha-2, Alpha-3, Numeric Code, Synonyms
            for row in reader:
                name: str = row[0].strip()
                alpha2: str = row[1].strip()
                alpha3: str = row[2].strip()
                numeric: str = row[3].strip()
                keywords: list[str] = (
                    row[4].strip().split(";") if len(row) > 4 and row[4].strip() else []
                )
                country_list.append((name, alpha2, alpha3, numeric, keywords))
    except FileNotFoundError:
        logger.error(f"Country dataset not found: {Paths.DATASETS['COUNTRIES']}")
        raise
    except (IndexError, ValueError) as e:
        logger.error(
            f"Malformed row in country dataset ({Paths.DATASETS['COUNTRIES']}): {e}"
        )
        raise

    _country_list_cache = country_list
    return _country_list_cache


# ─── Country resolution ───────────────────────────────────────────────────────


def country_converter(
    text_input: str, abbreviations_okay: bool = True
) -> tuple[str, str]:
    """
    Detect a country based on input. Supports full names, 2-letter
    and 3-letter codes, or associated keywords.

    Args:
        text_input: The input text to match.
        abbreviations_okay: If True, allow matching by abbreviations,
                            like 'CN' or 'MX'. Default is True.

    Returns:
        Tuple of (country_code, country_name). Returns ("", "") if no match found.
    """
    country_list = _load_country_list()

    text: str = text_input.strip()
    if len(text) <= 1:
        return "", ""

    text_upper: str = text.upper()
    text_title: str = text.title()

    # Match 2-letter code
    if len(text) == 2 and abbreviations_okay:
        for name, alpha2, _, _, _ in country_list:
            if text_upper == alpha2:
                return alpha2, name

    # Match 3-letter code
    if len(text) == 3 and abbreviations_okay:
        for name, alpha2, alpha3, _, _ in country_list:
            if text_upper == alpha3:
                return alpha2, name

    # Initialise fallback match variables
    possible_code: str = ""
    possible_name: str = ""

    # Match exact or partial name
    for name, alpha2, _, _, _ in country_list:
        if text_title == name:
            return alpha2, name
        elif text_title in name and len(text_title) >= 3:
            if possible_name:
                logger.debug(
                    f"Ambiguous partial match for {text_title!r}: "
                    f"{possible_name!r} overwritten by {name!r}"
                )
            possible_code = alpha2
            possible_name = name

    # Match keyword
    for name, alpha2, _, _, keywords in country_list:
        if any(text_title == kw for kw in keywords):
            return alpha2, name

    # Fallback to partial name match
    if possible_code and possible_name:
        return possible_code, possible_name

    return "", ""


# ─── Flag emoji utilities ─────────────────────────────────────────────────────


def _alpha2_to_emoji(alpha2: str) -> str:
    """Convert an ISO 3166-1 alpha-2 code to its regional indicator flag emoji."""
    return chr(ord(alpha2[0]) + 127397) + chr(ord(alpha2[1]) + 127397)


def get_country_emoji(country_name: str) -> str:
    """
    Return the flag emoji for a given country name.

    Attempts multiple lookup strategies in order:
    1. CSV-based lookup via country_converter (handles aliases, alternate
       spellings, keywords, and partial names — e.g. "Turkey", "Ivory Coast",
       "Czechia", "England").
    2. pycountry direct name match.
    3. pycountry common_name match (e.g. "South Korea").
    4. pycountry fuzzy search as a last resort.

    Args:
        country_name: The country name (or alias) to look up.

    Returns:
        The country's flag emoji as a string, or empty string if not found.
    """
    if not country_name:
        return ""

    # Strategy 1: CSV dataset via country_converter — most flexible path:
    # handles official names, alternate spellings (e.g. "Turkey" for Türkiye),
    # keywords, and partial matches.
    alpha2, _ = country_converter(country_name, abbreviations_okay=True)
    if alpha2:
        return _alpha2_to_emoji(alpha2)

    # Strategies 2–4: pycountry fallback — catches entries present in pycountry
    # but absent from the CSV.
    country = None

    country = pycountry.countries.get(name=country_name)

    if not country:
        country = pycountry.countries.get(common_name=country_name)

    if not country:
        with contextlib.suppress(LookupError):
            matches = pycountry.countries.search_fuzzy(country_name)
            if matches:
                country = matches[0]

    if country:
        return _alpha2_to_emoji(country.alpha_2)

    return ""


def get_language_emoji(language_code: str) -> str:
    """
    Return the flag emoji for a language, looked up by its preferred code.
    Intended for use primarily with ISO 639-1 codes.

    Reads the language YAML to find the associated country for the code,
    then delegates to get_country_emoji.

    Args:
        language_code: The language code (e.g. 'fr', 'zh') to look up.

    Returns:
        The country's flag emoji as a string, or empty string if not available.
    """
    global _language_full_data_cache
    if not language_code:
        return ""

    if _language_full_data_cache is None:
        _language_full_data_cache = load_settings(Paths.STATES["LANGUAGE_DATA"]) or {}

    if language_code not in _language_full_data_cache:
        return ""

    country_listed = _language_full_data_cache[language_code].get("country")
    if not country_listed:
        return ""
    return get_country_emoji(country_listed)
