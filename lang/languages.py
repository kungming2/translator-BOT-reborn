#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
Language dataset loader, converter, and list-building utilities for the
r/translator bot ecosystem.

This module owns the in-memory language dataset (a dict of Lingvo objects),
exposes the converter() entry point for resolving arbitrary strings to Lingvo
instances, and provides helpers for list parsing and dataset maintenance.

Dependency note: Lingvo lives in models/lingvo.py. Country utilities (emoji,
country_converter) live in services/countries.py. This module imports from
both; neither of those imports back here at module load time.

Key components:
    get_lingvos          -- Return (and cache) the full {code: Lingvo} dict.
    define_language_lists -- Return (and cache) derived lookup structures.
    converter            -- Resolve a string to a Lingvo; main public entry point.
    parse_language_list  -- Split a delimited string into a list of Lingvos.
    normalize            -- Lowercase + strip punctuation for fuzzy matching.
    add_alt_language_name -- Write a new alternate name back to the YAML dataset.
    validate_lingvo_dataset -- Report codes missing required fields.
    select_random_language  -- Pick a random Lingvo from the ISO CSV.

Logger tag: [LANG:LANGUAGES]
"""

# ─── Imports ──────────────────────────────────────────────────────────────────

import copy
import csv
import logging
import random
import re
from typing import Any

import orjson
import yaml
from rapidfuzz import fuzz

from config import Paths, load_settings
from config import logger as _base_logger
from lang.code_standards import (
    alpha3_code,
    parse_language_tag,
    preferred_standard_code,
)
from lang.countries import country_converter
from models.lingvo import Lingvo

# ─── Module-level constants ───────────────────────────────────────────────────

logger = logging.LoggerAdapter(_base_logger, {"tag": "LANG:LANGUAGES"})

language_module_settings = load_settings(Paths.SETTINGS["LANGUAGES_SETTINGS"])

_lingvos_cache = None  # cached {code: Lingvo} dict
_language_lists_cache = None  # cached output of define_language_lists()
_iso_csv_cache: list | None = None  # cached rows from ISO_CODES CSV


# ─── Dataset loader ───────────────────────────────────────────────────────────


def _combine_language_data() -> dict[str, dict[str, Any]]:
    """
    Combine raw language data, utility data, and statistics into a single dict.

    Merges three data sources in order of precedence:
    1. Raw language data (base layer from language_data.yaml)
    2. Utility language data (overlay from utility_lingvo.yaml)
    3. Statistics data (filtered overlay from statistics.json)

    Returns:
        A dictionary mapping language codes to their combined attribute dicts.
    """
    allowed_keys = {
        "num_months",
        "permalink",
        "rate_daily",
        "rate_monthly",
        "rate_yearly",
    }

    raw_data = load_settings(Paths.STATES["LANGUAGE_DATA"])
    utility_data = load_settings(Paths.STATES["UTILITY_LINGVO_DATA"])
    with open(Paths.STATES["STATISTICS"], "rb") as f:
        statistics_data = orjson.loads(f.read())

    combined_data: dict[str, dict[str, Any]] = {}

    for code, attrs in raw_data.items():
        combined_data[code] = attrs.copy()

    for code, attrs in utility_data.items():
        if code in combined_data:
            combined_data[code].update(attrs)
        else:
            combined_data[code] = attrs.copy()

    for code, stats in statistics_data.items():
        filtered_stats = {k: v for k, v in stats.items() if k in allowed_keys}
        if not filtered_stats:
            continue
        if code in combined_data:
            combined_data[code].update(filtered_stats)
        else:
            combined_data[code] = filtered_stats.copy()

    return combined_data


def _load_lingvo_dataset(debug: bool = False) -> dict[str, Lingvo]:
    """
    Load the language dataset and return a dictionary of Lingvo instances.

    Args:
        debug: If True, log detailed information about each language code.

    Returns:
        Dictionary mapping language codes to Lingvo instances.
    """
    combined_data = _combine_language_data()
    lingvo_dict: dict[str, Lingvo] = {}

    for code, attrs in combined_data.items():
        if debug:
            logger.debug(f"combined_data[{code}] = {attrs}")

        name = attrs.get("name", None)
        lang_code = attrs.get("language_code", code)
        extra_attrs = {
            k: v for k, v in attrs.items() if k not in ("name", "language_code")
        }

        lingvo_dict[code] = Lingvo(
            language_code=lang_code, name=name or "unknown", **extra_attrs
        )

    return lingvo_dict


def get_lingvos(force_refresh: bool = False) -> dict[str, Lingvo]:
    """
    Return the lingvos dataset, optionally forcing a refresh.

    Args:
        force_refresh: If True, reload the dataset even if cached. Used
                       when the underlying data has been altered.

    Returns:
        Dictionary mapping language codes to Lingvo instances.
    """
    global _lingvos_cache, _language_lists_cache
    if _lingvos_cache is None or force_refresh:
        _lingvos_cache = _load_lingvo_dataset()
        _language_lists_cache = None  # invalidate derived cache when lingvos reload
    return _lingvos_cache


def define_language_lists() -> dict[str, Any]:
    """
    Generate various language code and name mappings from the language dataset.
    Result is cached since lingvos themselves are cached — no need to rebuild
    on every converter() call.

    Returns:
        A dictionary with structured language metadata lists and mappings:
        - SUPPORTED_CODES: List of supported language codes
        - SUPPORTED_LANGUAGES: List of supported language names
        - ISO_DEFAULT_ASSOCIATED: List of language-country pairs (e.g., "en-US")
        - ISO_639_1: List of 2-letter ISO 639-1 codes
        - ISO_639_2B: Mapping of ISO 639-2B codes to ISO 639-1 codes
        - ISO_639_3: List of 3-letter ISO 639-3 codes
        - ISO_NAMES: List of language names
        - MISTAKE_ABBREVIATIONS: Mapping of common mistakes to correct codes
        - LANGUAGE_COUNTRY_ASSOCIATED: Mapping of codes to associated countries
    """
    global _language_lists_cache
    if _language_lists_cache is not None:
        return _language_lists_cache

    lingvos = get_lingvos()

    supported_codes: list[str] = []
    supported_languages: list[str] = []
    iso_default_associated: list[str] = []
    iso_639_1: set[str] = set()
    iso_639_2b: dict[str, str] = {}
    iso_639_3: list[str] = []
    iso_names: list[str] = []
    mistake_abbreviations: dict[str, str] = {}
    language_country_associated: dict[str, Any] = {}

    for code_1, lingvo in lingvos.items():
        if len(code_1) == 2:
            iso_639_1.add(code_1)

        if lingvo.language_code_3:
            iso_639_3.append(lingvo.language_code_3)

        if hasattr(lingvo, "language_code_synonym") and lingvo.language_code_synonym:
            iso_639_3.append(lingvo.language_code_synonym)

        if lingvo.name:
            iso_names.append(lingvo.name)

        iso_names.extend(lingvo.name_alternates or [])

        if getattr(lingvo, "supported", False):
            supported_codes.append(code_1)
            if lingvo.name is not None:
                supported_languages.append(lingvo.name)

        if lingvo.countries_default:
            iso_default_associated.append(f"{code_1}-{lingvo.countries_default}")

        if hasattr(lingvo, "countries_associated") and lingvo.countries_associated:
            language_country_associated[code_1] = lingvo.countries_associated

        if hasattr(lingvo, "mistake_abbreviation") and lingvo.mistake_abbreviation:
            mistake_abbreviations[lingvo.mistake_abbreviation] = code_1

        if hasattr(lingvo, "language_code_2b") and lingvo.language_code_2b:
            iso_639_2b[lingvo.language_code_2b] = code_1

        alpha3_t = alpha3_code(code_1, variant="T")
        alpha3_b = alpha3_code(code_1, variant="B")
        if alpha3_b and alpha3_b != alpha3_t:
            iso_639_2b[alpha3_b] = code_1

    _language_lists_cache = {
        "SUPPORTED_CODES": supported_codes,
        "SUPPORTED_LANGUAGES": supported_languages,
        "ISO_DEFAULT_ASSOCIATED": iso_default_associated,
        "ISO_639_1": iso_639_1,
        "ISO_639_2B": iso_639_2b,
        "ISO_639_3": iso_639_3,
        "ISO_NAMES": iso_names,
        "MISTAKE_ABBREVIATIONS": mistake_abbreviations,
        "LANGUAGE_COUNTRY_ASSOCIATED": language_country_associated,
    }
    return _language_lists_cache


# ─── Normalisation & fuzzy matching ──────────────────────────────────────────


def normalize(text: str) -> str:
    """
    Clean text for processing: lowercase, remove punctuation, and normalise
    whitespace.

    Args:
        text: The text to normalize.

    Returns:
        Normalized text in lowercase with punctuation removed
        and whitespace normalized.
    """
    text = text.lower()
    text = re.sub(r"[^\w\s]", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _fuzzy_text(word: str, supported_languages: list[str]) -> str | None:
    """
    Attempt to fuzzy-match *word* against the list of known language names,
    ignoring configured false-positive names.

    Args:
        word: The word to match against language names.
        supported_languages: List of language names to match against.

    Returns:
        The best matching language name, or None if no match exceeds the threshold.
    """
    exclude = language_module_settings["FUZZ_IGNORE_LANGUAGE_NAMES"]
    threshold = language_module_settings["FUZZY_THRESHOLD"]
    word_norm = normalize(word)

    best_match: str | None = None
    best_score = threshold

    for language in supported_languages:
        if language in exclude:
            continue
        lang_norm = normalize(language)
        score = fuzz.token_set_ratio(lang_norm, word_norm)
        if score > best_score:
            best_score = score
            best_match = language

    return best_match


# ─── ISO deep search ──────────────────────────────────────────────────────────


def _iso_codes_deep_search(
    search_term: str, script_search: bool = False
) -> Lingvo | None:
    """
    Search for a language or script code in the ISO 639-3 or ISO 15924 CSV.

    Args:
        search_term: The term to search for (code or name).
        script_search: If True, search in script codes (ISO 15924, 4-letter codes).
                       If False, search in language codes (ISO 639-3).

    Returns:
        Lingvo object if a match is found, None otherwise.
    """
    search_term = search_term.strip().lower()

    if script_search:
        dataset_path: str = Paths.DATASETS["ISO_SCRIPT_CODES"]
        code_key: str = "Script Code"
        name_key: str = "Script Name"
        alt_key: str = "Alternate Names"
    else:
        dataset_path = Paths.DATASETS["ISO_CODES"]
        code_key = "ISO 639-3"
        name_key = "Language Name"
        alt_key = "Alternate Names"

    try:
        with open(dataset_path, encoding="utf-8-sig") as file:
            reader = csv.DictReader(file)
            for row in reader:
                if not row.get(name_key):
                    continue  # Skip malformed/incomplete rows

                code: str = row.get(code_key, "").strip().lower()
                name: str = row.get(name_key, "").strip()
                alt_raw: str = row.get(alt_key) or ""
                alternates: list[str] = [
                    alt.strip().lower() for alt in alt_raw.split(";") if alt.strip()
                ]

                if search_term in {code, name.lower()} or search_term in alternates:
                    if script_search:
                        return Lingvo(
                            name=name,
                            name_alternates=alternates,
                            language_code_1="unknown",
                            language_code_3="unknown",
                            script_code=row.get("Script Code"),
                            supported=True,
                        )
                    else:
                        return Lingvo.from_csv_row(row)

    except FileNotFoundError:
        logger.error(f"Dataset not found: {dataset_path}")
        return None

    return None


def _copy_lingvo_for_return(lingvo: Lingvo, preserve_country: bool = False) -> Lingvo:
    """Return a Lingvo copy, clearing stored country metadata unless requested."""
    lingvo_copy = copy.deepcopy(lingvo)
    if not preserve_country:
        lingvo_copy.country = None
    return lingvo_copy


def _apply_country(base: Lingvo, cc: str, country_name: str) -> Lingvo:
    """Return a deep copy of base with the country name and code applied."""
    lingvo_with_country = copy.deepcopy(base)
    lingvo_with_country.name = (lingvo_with_country.name or "") + f" {{{country_name}}}"
    lingvo_with_country.country = cc.upper()
    return lingvo_with_country


def _lookup_lingvo_by_standard_code(
    input_text: str, preserve_country: bool = False
) -> Lingvo | None:
    """
    Resolve code-like input through langcodes before project dataset lookup.

    This catches equivalent codes such as ``eng`` -> ``en`` and ``fre`` -> ``fr``
    while preserving the project-specific Lingvo layer.
    """
    canonical_code = preferred_standard_code(input_text)
    if not canonical_code:
        return None

    lingvo = get_lingvos().get(canonical_code.lower())
    if lingvo is None:
        return None
    return _copy_lingvo_for_return(lingvo, preserve_country=preserve_country)


def _resolve_standard_compound_tag(
    input_text: str, preserve_country: bool = False
) -> Lingvo | None:
    """
    Resolve BCP 47-style language-script-region tags via langcodes.

    Region-specific macrolanguage overrides still come from project settings.
    Script subtags on known languages normalize to the base Lingvo; script-only
    requests remain handled by the existing ``unknown-<Script>`` path.
    """
    parsed = parse_language_tag(input_text)
    if parsed is None or not parsed.language:
        return None

    lingvos = get_lingvos()
    language_code = parsed.language.lower()
    territory_code = parsed.territory.upper() if parsed.territory else None

    if territory_code:
        combo = f"{language_code}-{territory_code}"
        mapped_code = language_module_settings["ISO_LANGUAGE_COUNTRY_ASSOCIATED"].get(
            combo
        )
        if mapped_code and mapped_code in lingvos:
            return _copy_lingvo_for_return(
                lingvos[mapped_code], preserve_country=preserve_country
            )

    lingvo = lingvos.get(language_code)
    if lingvo is None:
        return None

    if territory_code:
        country_info = country_converter(territory_code, abbreviations_okay=True)
        if country_info[0]:
            return _apply_country(lingvo, country_info[0], country_info[1])

    return _copy_lingvo_for_return(lingvo, preserve_country=preserve_country)


# ─── Resolution engine ────────────────────────────────────────────────────────


def _resolve_to_lingvo(
    input_text: str,
    fuzzy: bool = True,
    specific_mode: bool = False,
    preserve_country: bool = False,
) -> Lingvo | None:
    """
    Convert an input string to a Lingvo object.
    Input can be a language code, name, or compound like zh-CN or
    unknown-cyrl. This is wrapped by converter() for debug logging.

    :param input_text: The input string to resolve.
    :param fuzzy: Whether to apply fuzzy name matching.
    :param specific_mode: If True, use strict lookups (ISO_639_3 for 3-char,
                          ISO_15924 for 4-char).
    :param preserve_country: If True, keep the country field from YAML data.
                            If False (default), clear country for simple lookups.
    :return: A Lingvo instance or None if not found.
    """
    lingvos = get_lingvos()

    input_text = input_text.strip()
    input_lower = input_text.lower()
    reference_lists = define_language_lists()

    if len(input_text) <= 1:
        logger.debug(f"Skipping {input_text} as it's too short.")
        return None

    # Specific mode: strict lookups only
    if specific_mode:
        if len(input_text) == 2:
            if input_lower in reference_lists.get("ISO_639_1", set()):
                lingvo = lingvos.get(input_lower)
                if lingvo:
                    return _copy_lingvo_for_return(
                        lingvo, preserve_country=preserve_country
                    )
            return None
        elif len(input_text) == 3:
            standard_lingvo = _lookup_lingvo_by_standard_code(
                input_text, preserve_country=preserve_country
            )
            if standard_lingvo:
                return standard_lingvo
            iso_search = _iso_codes_deep_search(input_text, script_search=False)
            if iso_search:
                return _copy_lingvo_for_return(
                    iso_search, preserve_country=preserve_country
                )
            return None
        elif len(input_text) == 4:
            iso_search = _iso_codes_deep_search(input_text, script_search=True)
            if iso_search:
                return _copy_lingvo_for_return(
                    iso_search, preserve_country=preserve_country
                )
            return None
        else:
            return None

    # Normal mode
    standard_lingvo = _resolve_standard_compound_tag(
        input_text, preserve_country=preserve_country
    )
    if standard_lingvo:
        return standard_lingvo

    # Handle compound codes like zh-CN or unknown-Cyrl first,
    # because that affects country assignment logic
    if "-" in input_text and "Anglo" not in input_text:
        broader, specific = input_text.split("-", 1)
        combo = f"{broader.lower()}-{specific.upper()}"

        # Direct lookup in ISO_LANGUAGE_COUNTRY_ASSOCIATED
        # e.g. `de-CH` becomes `gsw`
        iso_map = language_module_settings["ISO_LANGUAGE_COUNTRY_ASSOCIATED"]
        if combo in iso_map:
            mapped_code = iso_map[combo]
            lingvo = lingvos.get(mapped_code)
            if lingvo:
                return _copy_lingvo_for_return(
                    lingvo, preserve_country=preserve_country
                )

        # Prefixed script code ("unknown-Cyrl")
        if broader.lower() == "unknown":
            try:
                result = _iso_codes_deep_search(specific, script_search=True)
                script_name = getattr(result, "name", None)
                if not script_name:
                    return None
                return Lingvo(
                    name=script_name,
                    language_code_1="unknown",
                    language_code_3="unknown",
                    script_code=specific.lower(),
                    supported=True,
                )
            except (AttributeError, TypeError):
                return None

        # Language-region combo (fallback, less strict)
        country_info = country_converter(specific, abbreviations_okay=True)
        if country_info[0]:
            country_code = country_info[0].upper()
            language_code = broader.lower()
            if language_code in lingvos:
                lingvo = copy.deepcopy(lingvos[language_code])
            else:
                # broader may be a full name like "portuguese" — look it up directly
                # without recursing into _resolve_to_lingvo, which risks re-entering
                # the compound-code branch and infinite recursion on inputs like
                # "anglo-saxon-br".
                broader_title = broader.title()
                lingvo = None
                for candidate in lingvos.values():
                    if broader_title == candidate.name or broader_title in (
                        a.title() for a in candidate.name_alternates or []
                    ):
                        lingvo = copy.deepcopy(candidate)
                        break
                if lingvo is None and language_code in lingvos:
                    lingvo = copy.deepcopy(lingvos[language_code])
            if lingvo:
                lingvo.name = (
                    lingvo.name or ""
                ) + f" {{{country_info[1]}}}"  # e.g., "Portuguese {Brazil}"
                lingvo.country = country_code  # e.g. 'BR'
                return lingvo

    # Search by name or alternate name
    input_norm = normalize(input_text)
    for _code, lingvo in lingvos.items():
        if lingvo.name and input_norm == normalize(lingvo.name):
            lingvo_copy = copy.deepcopy(lingvo)
            if not preserve_country:
                lingvo_copy.country = None
            return lingvo_copy
        if any(input_norm == normalize(alt) for alt in (lingvo.name_alternates or [])):
            lingvo_copy = copy.deepcopy(lingvo)
            if not preserve_country:
                lingvo_copy.country = None
            return lingvo_copy

    # For multi-word inputs (including parenthetical forms like "french (canada)"),
    # check if part of the input names a country and the rest names a language.
    # Strategy 1: extract a parenthesized token as the country hint first.
    # e.g. "french (canada)" -> country_hint="canada", lang_part="french"
    paren_match = re.search(r"\(([^)]+)\)", input_text)
    if paren_match:
        country_hint = paren_match.group(1).strip()
        lang_part = (
            input_text[: paren_match.start()].strip()
            + " "
            + input_text[paren_match.end() :].strip()
        ).strip()
        if lang_part:
            country_info = country_converter(country_hint, abbreviations_okay=False)
            if country_info[0]:
                lang_result = _resolve_to_lingvo(
                    lang_part, fuzzy=fuzzy, preserve_country=False
                )
                if lang_result:
                    return _apply_country(lang_result, country_info[0], country_info[1])
            else:
                lang_result = _resolve_to_lingvo(
                    lang_part, fuzzy=fuzzy, preserve_country=False
                )
                if lang_result:
                    return lang_result

    # Strategy 2: scan each bare word as a potential country name.
    # e.g. "canadian french" or "brazil portuguese"
    # abbreviations_okay=False prevents short words like "in" matching country codes.
    words = input_text.split()
    if len(words) >= 2:
        for i, word in enumerate(words):
            bare_word = re.sub(r"\W", "", word)  # strip stray punctuation like parens
            country_info = country_converter(bare_word, abbreviations_okay=False)
            if country_info[0]:
                remaining = " ".join(w for j, w in enumerate(words) if j != i)
                lang_result = _resolve_to_lingvo(
                    remaining, fuzzy=fuzzy, preserve_country=False
                )
                if lang_result:
                    return _apply_country(lang_result, country_info[0], country_info[1])

    # Try to find a Lingvo by 2-letter code first
    if input_lower in reference_lists["ISO_639_1"]:
        lingvo = lingvos.get(input_lower)
        if lingvo:
            return _copy_lingvo_for_return(lingvo, preserve_country=preserve_country)

    # If input is 3 letters, find the entry whose language_code_3 matches
    if len(input_lower) == 3:
        standard_lingvo = _lookup_lingvo_by_standard_code(
            input_text, preserve_country=preserve_country
        )
        if standard_lingvo:
            return standard_lingvo
        for _code_1, lingvo in lingvos.items():
            if lingvo.language_code_3 == input_lower:
                return _copy_lingvo_for_return(
                    lingvo, preserve_country=preserve_country
                )

    # Try ISO deep search (language codes then script codes)
    iso_search = _iso_codes_deep_search(input_text)
    if not iso_search:
        iso_search = _iso_codes_deep_search(input_text, script_search=True)

    if iso_search:
        return _copy_lingvo_for_return(iso_search, preserve_country=preserve_country)

    # Special abbreviation fixes (like 'vn' meaning Vietnamese)
    if input_lower in reference_lists["MISTAKE_ABBREVIATIONS"]:
        fixed = reference_lists["MISTAKE_ABBREVIATIONS"][input_lower]
        lingvo = lingvos.get(fixed)
        if lingvo:
            return _copy_lingvo_for_return(lingvo, preserve_country=preserve_country)

    # ISO 639-2B mapping (e.g., 'fre' -> 'fr')
    if input_lower in reference_lists["ISO_639_2B"]:
        canonical_code = reference_lists["ISO_639_2B"][input_lower]
        lingvo = lingvos.get(canonical_code)
        if lingvo:
            return _copy_lingvo_for_return(lingvo, preserve_country=preserve_country)

    # Fuzzy match if nothing else worked
    if (
        fuzzy
        and input_text.title() not in language_module_settings["FUZZ_IGNORE_WORDS"]
    ):
        input_title = input_text.title()
        fuzzy_result = _fuzzy_text(input_title, reference_lists["SUPPORTED_LANGUAGES"])
        if fuzzy_result:
            return converter(
                fuzzy_result, fuzzy=False, preserve_country=preserve_country
            )

    # Final fallback: maybe a script code
    if len(input_text) == 4:
        try:
            lingvo_script = _iso_codes_deep_search(input_text, script_search=True)
            if lingvo_script:
                return _copy_lingvo_for_return(
                    lingvo_script, preserve_country=preserve_country
                )
            else:
                return None
        except TypeError:
            pass

    return None


# ─── Public converter interface ───────────────────────────────────────────────


def converter(
    input_text: str,
    fuzzy: bool = True,
    specific_mode: bool = False,
    preserve_country: bool = False,
) -> Lingvo | None:
    """
    Resolve an arbitrary string to a Lingvo object.

    Wraps _resolve_to_lingvo to provide debug logging of every conversion.
    This is the primary public entry point for language resolution.
    """
    result = _resolve_to_lingvo(
        input_text,
        fuzzy=fuzzy,
        specific_mode=specific_mode,
        preserve_country=preserve_country,
    )
    logger.debug(f"Conversion: {input_text!r} → {result!r}")
    return result


def parse_language_list(list_string: str) -> list[Lingvo]:
    """
    Split a string of language codes or names using flexible delimiters.

    Handles multiple delimiter formats including commas, plus signs, newlines,
    slashes, colons, and semicolons. Also handles space-delimited lists.

    Examples: "ar, latin, yi", "ko+lo", "en/fr/de"

    Args:
        list_string: A possible list of languages as a string.

    Returns:
        A sorted list of Lingvo objects, or an empty list if none found.
        Results are deduplicated by preferred code and sorted alphabetically.
    """
    logger.debug(f"Input list_string: {repr(list_string)}")

    if not list_string:
        logger.debug("Empty list_string, returning empty list")
        return []

    # Strip 'LANGUAGES:' prefix if present
    if "LANGUAGES:" in list_string:
        list_string = list_string.rpartition("LANGUAGES:")[-1].strip()
        logger.debug(f"After stripping LANGUAGES: prefix: {repr(list_string)}")
    else:
        list_string = "\n".join(
            line
            for line in list_string.splitlines()
            if not line.lstrip().startswith("#")
        ).strip()
        logger.debug(
            f"After stripping instruction lines (no LANGUAGES: prefix): {repr(list_string)}"
        )

    list_string = re.sub(r"(?m)^\s*>\s?", "", list_string).strip()
    logger.debug(f"After stripping leading quote prompts: {repr(list_string)}")

    # Normalize various delimiters to commas
    for delimiter in ["+", "\n", "/", ":", ";"]:
        list_string = list_string.replace(delimiter, ",")
    logger.debug(f"After normalizing delimiters: {repr(list_string)}")

    # Split on commas (or use the whole string if no commas)
    if "," in list_string:
        items = list_string.split(",")
        logger.debug(f"Split on comma, items: {items}")
    elif " " in list_string:
        # Space-delimited case — try the whole string first
        match = converter(list_string)
        items = [list_string] if match is not None else list_string.split()
        logger.debug(f"Space-delimited case, match={match}, items: {items}")
    else:
        items = [list_string]
        logger.debug(f"Single item, no delimiters: {items}")

    utility_codes = {"meta", "community", "all"}
    final_lingvos: dict[str, Lingvo] = {}

    for item in items:
        item = item.strip().lower()
        logger.debug(f"Processing item: {repr(item)}")

        if not item:
            logger.debug("Item is empty, skipping")
            continue

        if item in utility_codes:
            logger.debug(f"Item {repr(item)} is a utility code, skipping")
            continue

        lang = converter(item)
        logger.debug(f"converter({repr(item)}) returned: {lang}")
        if lang:
            final_lingvos[lang.preferred_code] = lang
            logger.debug(f"Added {lang.preferred_code} -> {lang.name}")
        else:
            logger.debug(f"converter returned None for {repr(item)}")

    logger.debug(f"Final lingvos dict keys: {list(final_lingvos.keys())}")
    result = sorted(
        final_lingvos.values(), key=lambda lingvo: lingvo.preferred_code.lower()
    )
    logger.debug(
        f"Returning {len(result)} Lingvo objects: {[x.preferred_code for x in result]}"
    )
    return result


# ─── Dataset editing & validation ────────────────────────────────────────────


def add_alt_language_name(language_code: str, alt_name: str) -> bool:
    """
    Add an alternate name for a given language in the LANGUAGE_DATA YAML file.
    If the language doesn't have a 'name_alternates' field, it is created.
    If the alt_name already exists, nothing is changed.
    """
    try:
        language_data_path = Paths.STATES["LANGUAGE_DATA"]

        with open(language_data_path, encoding="utf-8") as f:
            existing_data = yaml.safe_load(f) or {}

        if language_code not in existing_data:
            logger.warning(f"Language code '{language_code}' not found in dataset.")
            return False

        lang_entry = existing_data[language_code]

        if "name_alternates" not in lang_entry or not isinstance(
            lang_entry["name_alternates"], list
        ):
            lang_entry["name_alternates"] = []

        if alt_name.title().strip() not in lang_entry["name_alternates"]:
            lang_entry["name_alternates"].append(alt_name.title().strip())
            existing_data[language_code] = lang_entry

            with open(language_data_path, "w", encoding="utf-8") as f:
                yaml.dump(existing_data, f, allow_unicode=True, sort_keys=True)

            logger.info(f"Added alternate name '{alt_name}' to '{language_code}'.")
            return True
        else:
            logger.info(
                f"Alternate name '{alt_name}' already exists for '{language_code}'."
            )
            return False

    except Exception as e:
        logger.error(f"Error while adding alternate name: {e}")
        return False


def validate_lingvo_dataset() -> list[str]:
    """
    Validate the language dataset by checking for codes missing required fields.

    Returns:
        List of language codes missing required fields (name or language_code).
    """
    combined_data = _combine_language_data()

    problematic_codes: list[str] = []
    for code, attrs in combined_data.items():
        name = attrs.get("name")
        lang_code = attrs.get("language_code", code)

        if not name or not lang_code:
            problematic_codes.append(code)
            logger.debug(f"Problematic code: `{code}`")

    return problematic_codes


# ─── Dataset utilities ────────────────────────────────────────────────────────


def select_random_language(iso_639_1: bool = False) -> Lingvo | None:
    """
    Pick a random language code and name from the ISO CSV file.

    Args:
        iso_639_1: If True, select ISO 639-1 codes (2-letter).
                   Otherwise, select ISO 639-3 codes (3-letter).

    Returns:
        A randomly selected Lingvo object, or None if no match found.
    """
    global _iso_csv_cache
    pattern: str = r"^[a-z]{2}$" if iso_639_1 else r"^[a-z]{3}$"

    if _iso_csv_cache is None:
        with open(Paths.DATASETS["ISO_CODES"], newline="", encoding="utf-8") as csvfile:
            reader = csv.reader(csvfile)
            next(reader, None)  # Skip header
            _iso_csv_cache = [row for row in reader if row]

    filtered: list = [
        row
        for row in _iso_csv_cache
        if re.match(pattern, row[1] if iso_639_1 else row[0])
        and (iso_639_1 or not ("qaa" <= row[0].lower() <= "qtz"))
    ]

    if not filtered:
        return None

    chosen = random.choice(filtered)
    code_index: int = 1 if iso_639_1 else 0
    selected_language = converter(chosen[code_index])
    return selected_language
