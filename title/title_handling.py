#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
Language processing and filtering for r/translator post titles.

This module parses Reddit post titles to extract source and target languages,
filters titles that don't meet community formatting rules, assigns flair
metadata, and determines translation direction. The primary output type is
the Titolo class, which carries all parsed results downstream.

The AI fallback path (for titles that defeat the rule-based parser) lives in
title/title_ai.py and is called from process_title when no non-English
language can be resolved.

Key components:
    process_title        -- Main entry point: title string or PRAW submission → Titolo.
    main_posts_filter    -- Pre-filter: check title meets formatting rules.
    extract_lingvos_from_text -- Find Lingvo objects in free text.
    is_english_only      -- True if source and target are both English.

Note: The Titolo class lives in models/titolo.py.

Logger tag: [T:TITLE]
"""

import logging
import re
import string
from typing import List, Literal, Optional

from praw.models import Submission
from rapidfuzz import fuzz

from config import Paths, load_settings
from config import logger as _base_logger
from lang.countries import country_converter
from lang.languages import converter, define_language_lists
from models.lingvo import Lingvo
from models.titolo import Titolo
from title.title_ai import title_ai_parser, update_titolo_from_ai_result

logger = logging.LoggerAdapter(_base_logger, {"tag": "T:TITLE"})

# Load the title module's settings.
title_settings = load_settings(Paths.SETTINGS["TITLE_MODULE_SETTINGS"])


# ---------------------------------------------------------------------------
# Flair helpers (module-level — do not nest inside _determine_flair)
# ---------------------------------------------------------------------------


def _resolve_flair_code(lang_obj: Lingvo) -> str:
    """
    Return the best flair CSS code for a Lingvo, or 'generic' if none applies.

    Prefers language_code_1 (ISO 639-1) over language_code_3, and only uses
    either if the language is marked as supported.
    """
    if lang_obj is None:
        return "generic"
    if lang_obj.language_code_1 and lang_obj.supported:
        return lang_obj.language_code_1
    if lang_obj.language_code_3 and lang_obj.supported:
        return lang_obj.language_code_3
    return "generic"


def _generate_multi_flair_text(language_codes: list[str], max_length: int = 64) -> str:
    """
    Build the flair display string for a multiple-language post.

    Fits as many language codes as possible within max_length, abbreviating
    by dropping trailing codes if the full list would exceed the limit.

    Args:
        language_codes: List of uppercase preferred codes to include.
        max_length: Maximum character length for the resulting string.

    Returns:
        A string like "Multiple Languages [DE, FR, ZH]", truncated if needed.
    """
    sorted_codes = sorted(language_codes)
    full_text = f"Multiple Languages [{', '.join(sorted_codes)}]"

    if len(full_text) <= max_length:
        return full_text

    prefix = "Multiple Languages ["
    suffix = "]"
    max_content_length = max_length - len(prefix) - len(suffix)

    included_codes: list[str] = []
    current_length = 0

    for code in sorted_codes:
        separator_length = 2 if included_codes else 0  # ", "
        code_length = len(code) + separator_length
        if current_length + code_length <= max_content_length:
            included_codes.append(code)
            current_length += code_length
        else:
            break

    return f"{prefix}{', '.join(included_codes)}{suffix}"


def _first_non_english(language_list: list) -> Optional[Lingvo]:
    """
    Return the first Lingvo in the list whose name is not 'English', or None.
    """
    for lang in language_list:
        if lang and lang.name != "English":
            return lang
    return None


# ---------------------------------------------------------------------------
# Flair determination
# ---------------------------------------------------------------------------


def _determine_flair(titolo_object: Titolo) -> None:
    """
    Set final_code and final_text on titolo_object.

    Decision logic (in order):
    1. If English is in target → flair on the non-English source language.
    2. If English is in source → flair on the non-English target language.
       In both cases, if there are multiple non-English candidates on that
       side, build a "Multiple Languages [...]" flair rather than picking one.
    3. Fallback for english_to: flair on source[0].
    4. Fallback for english_from / english_none: flair on target(s), or
       source if target is empty, or generic if nothing is available.
    """
    source = titolo_object.source or []
    target = titolo_object.target or []

    source_has_english = any(lang.name == "English" for lang in source)
    target_has_english = any(lang.name == "English" for lang in target)

    # --- Cases 1 and 2: one side has English ---
    # Pick the non-English candidates from the opposite side and flair on them.
    if target_has_english or source_has_english:
        candidates = (
            [lng for lng in source if lng.name != "English"]
            if target_has_english
            else [lng for lng in target if lng.name != "English"]
        )

        if len(candidates) > 1:
            preferred_codes = [
                lng.preferred_code.upper() for lng in candidates if lng.preferred_code
            ]
            titolo_object.add_final_code("multiple")
            titolo_object.add_final_text(_generate_multi_flair_text(preferred_codes))
            return

        if len(candidates) == 1:
            lang = candidates[0]
            titolo_object.add_final_code(_resolve_flair_code(lang))
            titolo_object.add_final_text(lang.name or "Unknown")
            return

        # candidates is empty — fall through to direction-based logic below

    # --- Case 3: english_to (English is source, non-English target already
    #     handled above; this catches the edge case where candidates was empty)
    if titolo_object.direction == "english_to":
        if not source:
            return
        lang = source[0]
        titolo_object.add_final_code(_resolve_flair_code(lang))
        titolo_object.add_final_text(lang.name or "Unknown")
        return

    # --- Case 4: english_from / english_none ---
    if titolo_object.direction in ("english_from", "english_none"):
        if len(target) > 1:
            preferred_codes = [
                lng.preferred_code.upper()
                for lng in target
                if hasattr(lng, "preferred_code") and lng.preferred_code
            ]
            titolo_object.add_final_code("multiple")
            titolo_object.add_final_text(_generate_multi_flair_text(preferred_codes))
            return

        if len(target) == 1:
            lang = target[0]
            if getattr(lang, "preferred_code", "") == "multiple":
                titolo_object.add_final_code("multiple")
                titolo_object.add_final_text("Multiple Languages")
            else:
                titolo_object.add_final_code(_resolve_flair_code(lang))
                titolo_object.add_final_text(lang.name or "Unknown")
            return

        # No targets — fall back to source
        if source:
            lang = source[0]
            titolo_object.add_final_code(_resolve_flair_code(lang))
            titolo_object.add_final_text(lang.name or "Unknown")
            return

    # Nothing resolved — assign generic
    titolo_object.add_final_code("generic")
    titolo_object.add_final_text("Generic")
    logger.warning(f"_determine_flair: fell through to generic for {titolo_object}")


# ---------------------------------------------------------------------------
# Direction and notification helpers
# ---------------------------------------------------------------------------


def _determine_title_direction(
    source_languages: list, target_languages: list
) -> Literal["english_from", "english_to", "english_both", "english_none"]:
    """
    Determine the direction of English language usage in a translation request.
    Used for statistics in Ajos and Wenyuan.

    :param source_languages: List of source Lingvo objects.
    :param target_languages: List of target Lingvo objects.
    :return: One of 'english_from', 'english_to', 'english_both', 'english_none'.
    """
    src = [lang for lang in source_languages if lang is not None]
    tgt = [lang for lang in target_languages if lang is not None]

    # If all entries on a side contain 'English' (like 'Middle English') and
    # the list has more than one entry, remove plain 'English' to avoid bias.
    if all("English" in lang.name for lang in src) and len(src) > 1:
        src = [lang for lang in src if lang.name != "English"]
    elif all("English" in lang.name for lang in tgt) and len(tgt) > 1:
        tgt = [lang for lang in tgt if lang.name != "English"]

    src_names = [lang.name for lang in src]
    tgt_names = [lang.name for lang in tgt]

    # If English appears on both sides and the combined list is long enough,
    # remove it from the longer side to reduce bias.
    if "English" in src_names and "English" in tgt_names:
        if len(src) + len(tgt) >= 3:
            if len(src) >= 2:
                src = [lang for lang in src if lang.name != "English"]
                src_names = [lang.name for lang in src]
            elif len(tgt) >= 2:
                tgt = [lang for lang in tgt if lang.name != "English"]
                tgt_names = [lang.name for lang in tgt]

    if "English" in src_names and "English" not in tgt_names:
        return "english_from"
    if "English" in tgt_names and "English" not in src_names:
        return "english_to"
    if "English" in src_names and "English" in tgt_names:
        return "english_both"
    return "english_none"


def _get_notification_languages(assess_request: Titolo) -> Optional[list]:
    """
    Return the unique non-English languages to notify subscribers for.

    Returns None if the request is English-only on both sides (no notification
    needed), or if no non-English languages are present after deduplication.

    :param assess_request: A Titolo object with source, target, and direction set.
    :return: List of unique non-English Lingvo objects, or None.
    """
    if assess_request.direction == "english_both":
        logger.warning("Both English. Not sending notifications.")
        return None

    combined = list(set(assess_request.source) | set(assess_request.target))
    combined = [x for x in combined if x.name != "English"]

    unique = {lang.preferred_code: lang for lang in combined}
    result = list(unique.values())
    return result if result else None


# ---------------------------------------------------------------------------
# Text extraction helpers
# ---------------------------------------------------------------------------


def extract_lingvos_from_text(
    text: str, return_english: bool = False
) -> List[Lingvo] | None:
    """
    Extract Lingvo objects from a paragraph based on capitalized language-like words.
    Includes supported languages, and optionally 'English' even if unsupported.

    :param text: The paragraph or sentence to search.
    :param return_english: Whether to include 'English' even if unsupported.
    :return: A sorted list of Lingvo objects, or None if nothing valid was found.
    """
    matches = re.findall(r"\b[A-Z][a-z]+", text)
    found = []

    for word in matches:
        if len(word) <= 3:
            continue
        lingvo = converter(word)
        if lingvo and lingvo.name:
            if lingvo.supported or (
                return_english and lingvo.name.lower() == "english"
            ):
                if lingvo not in found:
                    found.append(lingvo)

    return sorted(found, key=lambda ling: ling.name or "") if found else None


def _english_fuzz(word: str) -> bool:
    """
    Return True if word is likely a misspelling of 'English' (>70% similarity).
    """
    closeness: float = fuzz.ratio("English", word.title())
    return closeness > 70


def _normalize_misspelled_english(title: str) -> str:
    """
    Replace common misspellings of 'English' in a post title.

    :param title: The original r/translator post title.
    :return: The title with misspellings of 'English' corrected.
    """
    title = re.sub(r'[,.;@#?!&$()"\'•]+\s*', " ", title)
    for word in title.split():
        if _english_fuzz(word):
            title = title.replace(word, "English")
    return title


# ---------------------------------------------------------------------------
# Filtering (first round)
# ---------------------------------------------------------------------------


def _build_required_title_keywords() -> dict[str, list[str]]:
    """
    Generate keyword phrases for detecting valid r/translator post titles.

    Combines English aliases, supported language names, and connector terms
    ('to', '>') into acceptable title patterns, with known false positives removed.

    :return: Dict with keys:
        - 'total': all valid keyword combinations.
        - 'to_phrases': only the "to LANGUAGE" style combinations.
    """
    keywords: dict[str, list[str]] = {"total": [], "to_phrases": []}
    supported_languages = define_language_lists()["SUPPORTED_LANGUAGES"]

    english_aliases = title_settings["ENGLISH_ALIASES"]
    connectors = title_settings["CONNECTORS"]

    for eng in english_aliases:
        for conn in connectors:
            pairs = [f" {conn} {eng}", f"{eng} {conn} "]
            if conn != "to":
                pairs += [f"{conn}{eng}", f"{eng}{conn}"]
            else:
                keywords["to_phrases"] += pairs
            keywords["total"] += pairs

    for lang in supported_languages:
        lang = lang.lower()
        for conn in connectors:
            pairs = [f" {conn} {lang}", f"{lang} {conn} "]
            if conn != "to":
                pairs += [f"{conn}{lang}", f"{lang}{conn}"]
            else:
                keywords["to_phrases"] += pairs
            keywords["total"] += pairs

    keywords["total"] += [">", "[unknown]", "[community]", "[meta]"]
    keywords["total"] += sorted(d.lower() for d in title_settings["ENGLISH_DASHES"])

    bad_matches = {
        "ch to ",
        "en to ",
        " to en",
        " to me",
        " to mi",
        " to my",
        " to mr",
        " to kn",
    }
    keywords["to_phrases"] = [k for k in keywords["to_phrases"] if k not in bad_matches]
    keywords["total"] = [k for k in keywords["total"] if k not in bad_matches]

    return keywords


def main_posts_filter(title: str) -> tuple[bool, str | None, str | None]:
    """
    Filter r/translator post titles based on community formatting guidelines.

    :param title: The original post title.
    :return: Tuple of (post_okay, title_or_none, filter_reason_or_none).
        filter_reason codes:
            '1'  — Missing required keywords.
            '1A' — "to English" phrasing not early in the title.
            '1B' — Too short and generic (e.g., "Translation to English").
            '2'  — '>' present but poorly placed or not formatted.
    """
    title_lower = title.lower()

    keywords = _build_required_title_keywords()
    mandatory_keywords = keywords["total"]
    to_phrases = keywords["to_phrases"]

    # Rule 1: required keywords
    if not any(kw in title_lower for kw in mandatory_keywords):
        title = _normalize_misspelled_english(title)
        title_lower = title.lower()

        if not any(kw in title_lower for kw in mandatory_keywords):
            filter_reason = "1"
            logger.info(
                f"Main_Posts_Filter: > Filtered a post with an incorrect title format. "
                f"Rule: #{filter_reason}"
            )
            return False, None, filter_reason

    # Rule 1A and 1B: "to LANGUAGE" phrasing issues
    if ">" not in title_lower and any(phrase in title_lower for phrase in to_phrases):
        if not any(phrase in title_lower[:25] for phrase in to_phrases):
            filter_reason = "1A"
            logger.info(
                f"Main_Posts_Filter: > Filtered a post with an incorrect title format. "
                f"Rule: #{filter_reason}"
            )
            return False, None, filter_reason

        if len(title) < 35 and "[" not in title:
            listed_lingvos = extract_lingvos_from_text(title.title()) or []
            non_english_lingvos = [
                lng for lng in listed_lingvos if lng.name != "English"
            ]

            if not non_english_lingvos:
                filter_reason = "1B"
                logger.info(
                    f"Main_Posts_Filter: > Filtered a post with no valid language. "
                    f"Rule: #{filter_reason}"
                )
                return False, None, filter_reason

    # Rule 2: '>' present but poorly positioned
    if ">" in title and "]" not in title and ">" not in title[:50]:
        filter_reason = "2"
        logger.info(
            f"Main_Posts_Filter: > Filtered a post due to incorrect placement of '>'. "
            f"Rule: #{filter_reason}"
        )
        return False, None, filter_reason

    return True, title, None


# ---------------------------------------------------------------------------
# Preprocessing (second round)
# ---------------------------------------------------------------------------


def _move_bracketed_tag_to_front(title: str) -> str:
    """
    Move the first bracketed or parenthesized tag to the front of the title,
    normalizing parentheses to brackets.

    Only moves tags when the title doesn't already start with a language pattern.
    """
    if re.match(r"^[A-Za-z\s]+\s*(?:>|to)\s*[A-Za-z]+", title, re.IGNORECASE):
        return title

    match = re.search(r"\[.*?]", title)
    if match:
        tag = match.group(0)
        remainder = title.replace(tag, "", 1).strip()
        return f"{tag} {remainder}".strip()

    match = re.search(r"\(([^)]*(?:>|to)[^)]*)\)", title)
    if match:
        tag = f"[{match.group(1)}]"
        remainder = title.replace(match.group(0), "", 1).strip()
        return f"{tag} {remainder}".strip()

    # Malformed unclosed bracket: "Title [JP"
    if "[" in title:
        parts = title.split("[", 1)
        if len(parts) == 2:
            tag = f"[{parts[1].rstrip(']')}]"
            return f"{tag} {parts[0].strip()}".strip()

    # Malformed unclosed parenthesis with language indicator: "Title (JP to EN"
    if "(" in title and (">" in title or "to" in title.lower()):
        parts = title.split("(", 1)
        if len(parts) == 2:
            tag = f"[{parts[1].rstrip(')')}]"
            return f"{tag} {parts[0].strip()}".strip()

    return title


def _reformat_detected_languages_in_title(title: str) -> str | None:
    """
    Attempt to reformat a poorly structured title by detecting language names
    in the first and last few words and building a canonical [Source > Target] tag.

    Returns the reformatted title string, or None if insufficient languages
    were found to construct a tag.
    """
    logger.debug(f"Initial title: '{title}'")
    title_words = re.findall(r"\w+", title)
    logger.debug(f"Extracted words: {title_words}")

    if not title_words:
        return None

    detected_languages: dict[str, str] = {}
    first_lang = last_lang = last_lang_word = None

    # Scan first ~5 words for source language
    for word in title_words[:5]:
        if word.lower() == "to":
            continue
        match = extract_lingvos_from_text(word.title())
        if match:
            detected_languages[word] = match[0].name or "Unknown"
            if not first_lang:
                first_lang = match[0].name or "Unknown"

    # Scan last ~5 words (reversed) for target language
    for word in reversed(title_words[-5:]):
        match = extract_lingvos_from_text(word.title(), True)
        if not match:
            continue
        potential_lang = match[0].name
        if potential_lang != first_lang:
            last_lang = potential_lang
            last_lang_word = word
            break
        # Same as source — only use it if it appears multiple times
        if (
            sum(
                1
                for w in title_words
                if potential_lang and potential_lang.lower() in w.lower()
            )
            > 1
        ):
            last_lang = potential_lang
            last_lang_word = word
            break

    logger.debug(
        f"Detected: first_lang={first_lang}, last_lang={last_lang}, "
        f"last_lang_word={last_lang_word}"
    )

    if not first_lang or not last_lang:
        return None

    lang_tag = f"[{first_lang} > {last_lang}]"
    reformatted = title

    # Remove the target language word first (if different from source)
    if first_lang != last_lang and last_lang_word:
        reformatted = reformatted.replace(last_lang_word, "", 1)

    # Replace the first language word with the full tag
    for original_word, lang_name in detected_languages.items():
        if lang_name == first_lang:
            reformatted = reformatted.replace(original_word, lang_tag, 1)
            break

    reformatted = re.sub(r"\b(to|into)\b", ">", reformatted, flags=re.IGNORECASE)
    reformatted = re.sub(r"\s{2,}", " ", reformatted).strip()
    reformatted = re.sub(r"\s*[>-]\s*$", "", reformatted).strip()

    logger.debug(f"Final reformatted title: '{reformatted}'")
    return reformatted


def _preprocess_title(post_title: str) -> str:
    """
    Normalize a Reddit post title by fixing brackets, typos, symbols,
    misused language tags, and removing cross-post markers.
    """
    title: str = re.sub(r"\(x-post.*", "", post_title).strip()

    has_clear_format = bool(re.match(r"^[A-Za-z\s]+\s+to\s+[A-Za-z]+\s*:", title))

    # Correct known spelling/alias issues
    _en_lingvo = converter("en")
    for spelling in _en_lingvo.name_alternates if _en_lingvo is not None else []:
        title = title.replace(spelling, "English")
    title = title.replace("english", "English")
    title = title.replace("Old English", "Anglosaxon")
    title = title.replace("Anglo-Saxon", "Anglosaxon")
    title = title.replace("Scots Gaelic", "Scottish Gaelic")

    # Replace unicode bracket/direction variants
    for keyword in title_settings["WRONG_DIRECTIONS"]:
        title = title.replace(keyword, " > ")
    for keyword in title_settings["WRONG_BRACKETS_LEFT"]:
        title = title.replace(keyword, " [")
    for keyword in title_settings["WRONG_BRACKETS_RIGHT"]:
        title = title.replace(keyword, "] ")

    # Normalize "to" casing and fix malformed bracket types
    title = re.sub(r"\b(To|TO|tO)\b", "to", title)
    if not any(b in title for b in ["[", "]"]) and re.match(
        r"[({].+(>| to ).+[)}]", title
    ):
        title = title.replace("(", "[", 1).replace(")", "]", 1)
        title = title.replace("{", "[", 1).replace("}", "]", 1)

    # Attempt reformatting only if no clear format and no brackets present
    if not any(b in title for b in ["[", "]"]) and not has_clear_format:
        reformatted = _reformat_detected_languages_in_title(title)
        if reformatted:
            title = reformatted

    # Normalize bracketed language tags and country suffixes
    title = re.sub(r"(]\s*[>\\-]\s*\[)", " > ", title)
    if "{" in title and "}" in title and "[" in title:
        match = re.search(r"{(\D+)}", title)
        if match:
            code = country_converter(match.group(1))[0]
            if code:
                title = title.split("{", 1)[0].strip() + title.split("}", 1)[1]
    elif "{" in title and "[" not in title:
        title = title.replace("{", "[").replace("}", "]")

    # Handle dash-as-separator for English variants
    if "-" in title[:20] and any(
        k in title.title() for k in title_settings["ENGLISH_DASHES"]
    ):
        title = title.replace("-", " > ")

    # Move bracketed/parenthesized tag to front if needed
    has_bracket = "[" in title and "[" not in title[:10]
    has_paren = "(" in title and "(" not in title[:10]
    if not has_clear_format and (has_bracket or has_paren):
        title = _move_bracketed_tag_to_front(title.strip())

    title = title.replace("English.", "English] ").replace("_", " ")

    # Fix improperly hyphenated words that aren't valid language codes
    hyphen_match = re.search(r"((?:\w+-)+\w+)", title[:25])
    if hyphen_match:
        converted = converter(hyphen_match.group(0))
        if converted is not None and not converted.name:
            title = title.replace("-", " ")

    # Normalise stray symbols
    for ch in ["&", "+", "/", "\\", "|", "?"]:
        title = title.replace(ch, f" {ch} ")
    for compound in [">>>", ">>", "> >", "<"]:
        title = title.replace(compound, " > ")

    # Restore missing brackets around 'English'
    if ">" in title and "English" in title and "]" not in title and "[" not in title:
        title = title.replace("English", "English]")
        title = "[" + title

    # Catch remaining malformed directional hints
    if ">" not in title:
        if any(k in title[:25] for k in ["- Eng", "-Eng"]):
            title = title.replace("-", " > ")
        title = title.replace(" into ", ">")

    # Fix frequent false match for "KR"
    if "KR " in title.upper()[:10]:
        title = title.replace("KR ", "Korean ")

    # Normalise unknown/unclear entries
    if (
        "[Unknown]" in title.title()
        or title.lstrip().startswith("[?")
        or title.lstrip().startswith("[ ?")
    ):
        match = re.search(r"(?:>|to)\s*([^]]+)", title, re.IGNORECASE)
        if match:
            target_lang = match.group(1).strip().rstrip("]")
            title = f"[Unknown > {target_lang}]"
        else:
            title = "[Unknown > English]"

    return title


# ---------------------------------------------------------------------------
# Language chunk extraction and resolution
# ---------------------------------------------------------------------------


def _is_punctuation_only(s: str) -> bool:
    """Return True if s is non-empty and consists entirely of punctuation."""
    s = s.strip()
    return len(s) > 0 and all(c in string.punctuation for c in s)


def _clean_text(
    text: str, preserve_commas: bool = False, preserve_separators: bool = False
) -> str:
    """
    Insert spaces around brackets/parentheses and strip unwanted punctuation.

    Args:
        preserve_commas: If True, keep commas.
        preserve_separators: If True, keep &, /, and commas for language separation.
    """
    text = re.sub(r"([\[\]()])", r" \1 ", text)

    if preserve_separators:
        text = re.sub(r"[.;@#?!$" "'\"•]+ *", " ", text)
    elif preserve_commas:
        text = re.sub(r"[.;@#?!&$" "'\"•/]+ *", " ", text)
    else:
        text = re.sub(r"[,.;@#?!&$" "'\"•/]+ *", " ", text)

    return re.sub(r"\s+", " ", text).strip()


def _extract_source_chunk(title: str) -> str:
    """Extract the source language text from a preprocessed title."""
    if "[" in title and "]" in title:
        bracket_content = title[title.index("[") + 1 : title.index("]")]
        if ">" in bracket_content:
            return _clean_text(bracket_content.split(">")[0])
        if " to " in bracket_content:
            return _clean_text(bracket_content.split(" to ")[0])
        return _clean_text(bracket_content)

    for sep in [">", " to ", "-", "<"]:
        if sep in title:
            return _clean_text(title.split(sep)[0])
    return _clean_text(title)


def _extract_target_chunk(title: str) -> str:
    """Extract the target language text from a preprocessed title."""
    if "[" in title and "]" in title:
        bracket_content = title[title.index("[") + 1 : title.index("]")]
        if ">" in bracket_content:
            return _clean_text(bracket_content.split(">")[-1], preserve_separators=True)
        if " to " in bracket_content:
            return _clean_text(
                bracket_content.split(" to ")[-1], preserve_separators=True
            )

    for sep in [">", " to ", "-", "<"]:
        if sep in title:
            chunk = title.split(sep, 1)[1]
            if "]" in chunk:
                chunk = chunk.split("]", 1)[0]
            return _clean_text(chunk, preserve_separators=True)
    return ""


def _clean_chunk(chunk: str) -> str:
    """Strip brackets, whitespace, and trailing punctuation from a language chunk."""
    chunk = chunk.strip().lstrip("[").rstrip("]").strip()
    return re.sub(r"\W+$", "", chunk.lower())


def _resolve_languages(chunk: str, is_source: bool) -> list[Lingvo]:
    """
    Resolve a raw text chunk from a title into a list of Lingvo objects.

    Handles single languages, OR/AND/slash/ampersand/comma-separated lists,
    unknown indicators, and ISO codes.

    :param chunk: Text extracted from the title (e.g., "English OR German").
    :param is_source: True if this is the source side (affects debug labels).
    :return: List of resolved Lingvo objects (may be empty).
    """
    cleaned = _clean_chunk(chunk)
    logger.debug(f"Cleaned Chunk: {cleaned}")

    if cleaned in {"unknown", "unk", "???", "n/a"}:
        logger.debug("Handling 'unknown' chunk explicitly.")
        _unknown = converter("unknown")
        assert _unknown is not None, (
            "converter('unknown') returned None — check language data"
        )
        return [_unknown]

    if "]" in chunk:
        chunk = chunk.split("]", 1)[0]

    # Split on OR/AND/slash/ampersand/comma and resolve each part recursively
    separator_pattern = r"\s+(?:or|and)\s+|[&/,]"
    if re.search(separator_pattern, chunk, flags=re.IGNORECASE):
        parts = re.split(separator_pattern, chunk, flags=re.IGNORECASE)
        all_languages: list[Lingvo] = []
        for part in parts:
            part = part.strip()
            if part:
                all_languages.extend(_resolve_languages(part, is_source))

        if all_languages:
            unique: dict[str, Lingvo] = {}
            for lang in all_languages:
                key = lang.name or lang.language_code_3 or ""
                if key:
                    unique[key] = lang
            return list(unique.values())

    words = [w for w in chunk.split() if not _is_punctuation_only(w)]

    # Try multi-word phrases first (e.g., "Old French")
    if 2 <= len(words) <= 3:
        words.insert(0, " ".join(words))

    english_2_words = set(title_settings["ENGLISH_2_WORDS"])
    english_3_words = set(title_settings["ENGLISH_3_WORDS"].split())

    cleaned_words = [
        w
        for w in words
        if not (
            (len(w) == 2 and w.title() in english_2_words)
            or (len(w) == 3 and w.title() in english_3_words)
        )
    ]

    max_words_to_check = max(5, len(cleaned_words))
    resolved: list[Lingvo] = []

    for word in cleaned_words[:max_words_to_check]:
        word = word.rstrip("-_.,;:!?")
        if "Eng" in word and len(word) <= 8:
            word = "English"
        result = converter(word)
        if result:
            resolved.append(result)
            if " " in word:
                break  # Multi-word match found — stop here

    resolved_unique: dict[str, Lingvo] = {}
    for lang in resolved:
        key = lang.name or lang.language_code_3 or ""
        if key:
            resolved_unique[key] = lang

    logger.debug(
        f"{'Source' if is_source else 'Target'} resolved: {list(resolved_unique.values())}"
    )
    return list(resolved_unique.values())


def _extract_actual_title(title: str) -> str:
    """Return the post body text after the language tag is stripped."""
    actual = title.split("]", 1)[1] if "]" in title else ""
    return actual.strip("].> ,:.") if actual else ""


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def process_title(
    title_or_post: str | Submission,
    post: Submission | None = None,
    discord_notify: bool = True,
) -> Titolo:
    """
    Parse a Reddit post title and return a populated Titolo object.

    Accepts either a plain title string or a PRAW Submission object. When a
    Submission is passed as the first argument, the title is read from it and
    the post reference is set automatically — no need to pass post separately.

    Args:
        title_or_post: A title string, or a PRAW Submission whose .title is used.
        post: A PRAW Submission for AI fallback and Discord alerts. Inferred
              automatically when title_or_post is itself a Submission.
        discord_notify: Whether to send a Discord alert if the AI fallback fires.

    Returns:
        Titolo: Fully populated with source, target, direction, flair, and title fields.
    """
    if isinstance(title_or_post, str):
        title = title_or_post
    else:  # PRAW Submission
        title = str(title_or_post.title)
        post = title_or_post

    processed = _preprocess_title(title)
    logger.debug(f"Title as Processed: {processed}")

    result = Titolo()
    result.title_original = str(title)
    result.title_processed = processed
    result.title_actual = _extract_actual_title(processed)

    source_chunk = _extract_source_chunk(processed)
    logger.debug(f"Source chunk: {source_chunk}")
    result.source = _resolve_languages(source_chunk, is_source=True)

    target_chunk = _extract_target_chunk(processed)
    logger.debug(f"Target chunk: {target_chunk}")
    result.target = _resolve_languages(target_chunk, is_source=False)

    result.direction = _determine_title_direction(result.source, result.target)
    result.notify_languages = _get_notification_languages(result) or []

    # AI fallback: triggered when no non-English language was resolved
    combined_languages = [
        x
        for x in (result.source or []) + (result.target or [])
        if x.preferred_code != "en"
    ]
    logger.debug(
        "Combined languages (non-English): "
        + str([x.preferred_code for x in combined_languages])
    )

    if not combined_languages:
        logger.info(f"> Could not make sense of title ({title!r}). Asking AI...")
        ai_result = title_ai_parser(title, post)
        if isinstance(ai_result, dict):
            update_titolo_from_ai_result(
                result,
                ai_result,
                post,
                discord_notify,
                determine_flair_fn=_determine_flair,
                determine_direction_fn=_determine_title_direction,
                get_notification_languages_fn=_get_notification_languages,
            )
        else:
            logger.error(f"AI parser failed for title ({title!r}): {ai_result[1]}")
    else:
        _determine_flair(result)

    return result


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------


def is_english_only(titolo_content: Titolo) -> bool:
    """
    Return True if both source and target contain only English Lingvo objects.
    """
    source = getattr(titolo_content, "source", []) or []
    target = getattr(titolo_content, "target", []) or []
    if not source or not target:
        return False
    return all(getattr(lng, "preferred_code", None) == "en" for lng in source) and all(
        getattr(lng, "preferred_code", None) == "en" for lng in target
    )
