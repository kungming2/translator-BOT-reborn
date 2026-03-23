#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
Hermes matching logic.

Parses r/Language_Exchange post titles into offered/sought language
codes and proficiency levels, then matches them against the stored
user database.

All language resolution is done via the shared ``languages.converter()``
which returns Lingvo objects.  Only the ``preferred_code`` (a compact
2- or 3-letter string) is stored in the database and used for matching.

Logger tag: [HM:MATCH]
"""

# ─── Imports ──────────────────────────────────────────────────────────────────

import random
import re
import time

import praw
from praw.exceptions import PRAWException

from config import get_hermes_logger
from hermes import HERMES_SETTINGS
from hermes.hermes_database import hermes_db
from lang.languages import converter
from responses import RESPONSE
from time_handling import convert_to_day
from title.title_handling import title_settings

# ─── Module-level constants ───────────────────────────────────────────────────

logger = get_hermes_logger("HM:MATCH")

# English word filter lists sourced from title_settings YAML.
# title_settings["ENGLISH_2_WORDS"] is a list of Title-cased strings.
# title_settings["ENGLISH_3_WORDS"] is a single space-separated string.
_ENGLISH_2_WORDS: frozenset[str] = frozenset(
    w.lower() for w in title_settings["ENGLISH_2_WORDS"]
)
_ENGLISH_3_WORDS: frozenset[str] = frozenset(
    w.lower() for w in title_settings["ENGLISH_3_WORDS"].split()
)

# "N" is a common shorthand for Native seen in real post titles e.g. "(N)", "(N1)"
PROFICIENCY_LEVELS: frozenset[str] = frozenset(HERMES_SETTINGS["proficiency_levels"])

# Module-level constant so language_matcher doesn't re-read settings on every call.
_CUT_OFF: int = HERMES_SETTINGS["cut_off"]

# Bot disclaimer text adapted for r/Language_Exchange.
HERMES_BOT_DISCLAIMER: str = RESPONSE.BOT_DISCLAIMER.replace(
    "r/translator ", "r/Language_Exchange "
).replace("Ziwen", "Hermes")


# ─── Title tokenisation & segmentation ───────────────────────────────────────


def _tokenize(text: str) -> list[str]:
    """Extract alpha words (including extended Latin) and title-case them."""
    words = re.findall(r"[a-zA-Z\u00c0-\u017f]+", text)
    return [w.title() for w in words]


def _extract_segments(title: str) -> tuple[str | None, str | None]:
    """
    Split a normalised (lowercased, alias-replaced) title into raw offering
    and seeking text segments, handling three structural variants:

    1. Standard  — ``offering: <langs> | seeking: <langs>``
    2. Reversed  — ``seeking: <langs> | offering: <langs>``
    3. Bracket   — ``[offering] <langs> [seeking] <langs>``

    Returns ``(offering_raw, seeking_raw)``, either of which may be None if
    the corresponding keyword was not found.
    """
    # ── Bracket style: [Offering] … [Seeking] … (order-independent) ──────────
    bm_o = re.search(r"\[offering]\s*:?\s*(.*?)(?=\[|$)", title)
    bm_s = re.search(r"\[seeking]\s*:?\s*(.*?)(?=\[|$)", title)
    if bm_o or bm_s:
        return (
            bm_o.group(1).strip() if bm_o else None,
            bm_s.group(1).strip() if bm_s else None,
        )

    # ── Locate keyword positions to determine order ───────────────────────────
    offer_m = re.search(r"offering", title)
    seek_m = re.search(r"seeking", title)

    if not offer_m and not seek_m:
        return None, None

    offering_raw: str | None = None
    seeking_raw: str | None = None

    if offer_m and seek_m:
        offer_pos = offer_m.start()
        seek_pos = seek_m.start()

        if offer_pos < seek_pos:
            # Normal order: offering … seeking …
            seg_o = title[offer_m.end() :]
            offering_raw = seg_o.split("seeking")[0].strip()
            seg_s = title[seek_m.end() :]
            seeking_raw = seg_s.split("offering")[0].strip()
        else:
            # Reversed order: seeking … offering …
            seg_s = title[seek_m.end() :]
            seeking_raw = seg_s.split("offering")[0].strip()
            seg_o = title[offer_m.end() :]
            offering_raw = seg_o.split("seeking")[0].strip()

    elif offer_m:
        offering_raw = title[offer_m.end() :].strip()
    else:
        seeking_raw = title[seek_m.end() :].strip()  # type: ignore[union-attr]

    # Strip leading punctuation left by separators like ": ", "- ", "] "
    _punct_prefix = re.compile(r"^[\s:;\-\[\]|/.,]+")
    if offering_raw:
        offering_raw = _punct_prefix.sub("", offering_raw).strip() or None
    if seeking_raw:
        seeking_raw = _punct_prefix.sub("", seeking_raw).strip() or None

    return offering_raw, seeking_raw


# ─── Language & level parsing ─────────────────────────────────────────────────


def language_parser(
    text: str | None,
    include_iso_639_3: bool = False,
) -> tuple[list[str], list[str | None]]:
    """
    Parse language codes from a text segment.

    Uses the shared ``converter()`` from ``languages.py`` so all resolution
    goes through Lingvo objects.

    Args:
        text: The text to parse.
        include_iso_639_3: If True, also accept 3-letter codes; otherwise only
                           keep 2-letter ISO 639-1 codes.

    Returns:
        A tuple of (unique_codes, indices) where ``indices`` is a parallel list
        mapping each candidate word to its resolved code (or None).
    """
    if not text:
        return [], []

    cases = _tokenize(text)
    cases = [
        w
        for w in cases
        if w.lower() not in _ENGLISH_2_WORDS and w.lower() not in _ENGLISH_3_WORDS
    ]

    codes: list[str] = []
    indices: list[str | None] = []

    for word in cases:
        lingvo = converter(word)
        if lingvo is not None:
            code = lingvo.preferred_code
            codes.append(code)
            indices.append(code)
        else:
            indices.append(None)

    unique_codes = list(dict.fromkeys(codes))  # deduplicate, preserving order

    if not include_iso_639_3:
        # Keep only 2-letter (ISO 639-1) codes
        unique_codes = [c for c in unique_codes if len(c) == 2]
    else:
        # When ISO 639-3 is enabled, exclude plain country codes (2-letter
        # upper-case) which are easy to confuse with language codes.
        unique_codes = [c for c in unique_codes if len(c) < 4]

    # Remove spurious Latin / Spanish overlap (e.g. "Spanish (Latin American)")
    if "es" in unique_codes and "la" in unique_codes:
        unique_codes = [c for c in unique_codes if c != "la"]

    return unique_codes, indices


def level_parser(
    raw_segment: str,
    code_list: list[str],
    segment_indices: list[str | None],
) -> dict[str, str]:
    """
    Extract CEFR / native proficiency levels from a text segment.

    Looks for a proficiency level *immediately following* each language code
    in the tokenised word stream.

    Args:
        raw_segment: The raw text containing languages and levels.
        code_list: Codes whose levels we want.
        segment_indices: Parallel index list from ``language_parser()``.

    Returns:
        A dict mapping language code → proficiency string.
    """
    language_levels: dict[str, str] = {}

    words = re.findall(r"[a-zA-Z0-9]+", raw_segment)
    cases = [w.title() for w in words]
    cases = [
        w
        for w in cases
        if w.lower() not in _ENGLISH_2_WORDS and w.lower() not in _ENGLISH_3_WORDS
    ]

    logger.debug(f"Level Parser indices: {segment_indices}")

    for code in code_list:
        try:
            idx = segment_indices.index(code)
            following = cases[idx + 1]
            if following in PROFICIENCY_LEVELS:
                language_levels[code] = following
        except (ValueError, IndexError):
            continue

    return language_levels


def title_parser(
    title: str,
    include_iso_639_3: bool = False,
) -> tuple[list[str], list[str], dict[str, str]]:
    """
    Parse a post title into offered languages, sought languages, and
    proficiency levels for each offered language.

    Args:
        title: The r/Language_Exchange post title.
        include_iso_639_3: Whether to include 3-letter ISO 639-3 codes.

    Returns:
        Tuple of (offering_codes, seeking_codes, offering_levels).
    """
    title = title.lower()

    for alias in ("looking", "requesting", "seeing", "searching"):
        title = title.replace(alias, "seeking")

    offering_raw, seeking_raw = _extract_segments(title)

    offering_codes, offering_indices = (
        language_parser(offering_raw, include_iso_639_3) if offering_raw else ([], [])
    )
    seeking_codes, _ = (
        language_parser(seeking_raw, include_iso_639_3) if seeking_raw else ([], [])
    )

    logger.info(f"Title Parser | offering: {offering_codes}")
    logger.info(f"Title Parser | seeking:  {seeking_codes}")

    offering_levels = (
        level_parser(offering_raw, offering_codes, offering_indices)
        if offering_raw
        else {}
    )
    logger.info(f"Title Parser | levels:   {offering_levels}")

    return offering_codes, seeking_codes, offering_levels


# ─── Matching ─────────────────────────────────────────────────────────────────


def language_matcher(
    query_offering: list[str],
    query_seeking: list[str],
) -> dict[str, list] | None:
    """
    Search the entries database for users whose languages overlap with
    those of the querying user.

    Match-weight rules
    ------------------
    +5 flat          : target both offers something querier seeks AND seeks
                       something querier offers (mutual match in both directions)
    +1 per language  : target offers a matched language at Native level (stacks)
    +3 per language  : target *only* offers something the querier seeks
    +2 per language  : target *only* seeks something the querier offers

    Args:
        query_offering: Language codes the querying user offers.
        query_seeking:  Language codes the querying user seeks.

    Returns:
        Dict of ``{username: [score, offered_matches, sought_matches,
        post_id, levels]}`` or None if no matches found.
    """
    if not query_offering and not query_seeking:
        return None

    current_time = time.time()
    matches: dict[str, list] = {}

    for username, data, posted_utc in hermes_db.get_all_entries():
        if current_time - posted_utc > _CUT_OFF:
            continue

        target_offering: list[str] = data.get("offering", [])
        target_levels: dict[str, str] = data.get("level", {})
        target_seeking: list[str] = data.get("seeking", [])
        user_post_id: str = data.get("id", "")

        matched_o = sorted(set(target_offering) & set(query_seeking))
        matched_s = sorted(set(target_seeking) & set(query_offering))

        if matched_o and matched_s:
            # 5 points: target both offers something the OP seeks AND seeks
            # something the OP offers — a mutual match in both directions.
            # This is a flat score, not additive, per the scoring spec.
            score = 5
            native_bonus = sum(
                1 for code in matched_o if target_levels.get(code) in {"Native", "N"}
            )
            matches[username] = [
                score + native_bonus,
                matched_o,
                matched_s,
                user_post_id,
                target_levels,
            ]

        elif matched_o:
            # 3 points per language: target offers what the OP seeks.
            native_bonus = sum(
                1 for code in matched_o if target_levels.get(code) in {"Native", "N"}
            )
            matches[username] = [
                3 * len(matched_o) + native_bonus,
                matched_o,
                None,
                user_post_id,
                target_levels,
            ]

        elif matched_s:
            # 2 points per language: target seeks what the OP offers.
            matches[username] = [
                2 * len(matched_s),
                None,
                matched_s,
                user_post_id,
                target_levels,
            ]

    return matches or None


# ─── Match formatting ─────────────────────────────────────────────────────────


def get_language_greeting(offering: list[str], seeking: list[str]) -> str:
    """
    Pick a random non-English language from the combined offering/seeking
    codes and return a greeting in that language.

    Both lists contain preferred_code strings as returned by title_parser.
    Falls back to an empty string if no suitable language is found.

    Args:
        offering: Language codes the querying user offers.
        seeking:  Language codes the querying user seeks.

    Returns:
        A greeting string ending with a space (e.g. "Hola, "), or "".
    """
    eng_codes = frozenset({"en", "eng"})

    candidates = [
        code
        for code in dict.fromkeys(offering + seeking)  # deduplicated, order-preserved
        if code not in eng_codes
    ]

    if not candidates:
        return ""

    chosen_code = random.choice(candidates)
    lingvo = converter(chosen_code)

    if not lingvo:
        return ""

    logger.debug(f"Selected language: {lingvo.name} (`{lingvo.preferred_code}`).")
    greeting = lingvo.greetings or "Hello"
    return f"{greeting}, "


def format_matches(
    matches: dict[str, list] | None,
    reddit: praw.Reddit | None,
) -> str | None:
    """
    Format a dict of matches (from ``language_matcher``) as a Markdown table.

    Args:
        matches: The raw matches dict.
        reddit:  An authenticated PRAW Reddit instance (needed to look up posts).

    Returns:
        A Markdown table string, or None if there are no qualifying matches.
    """
    if not matches or reddit is None:
        return None

    num_of_entries: int = HERMES_SETTINGS["num_of_entries"]
    score_cutoff: int = HERMES_SETTINGS["score_cutoff"]
    matches_limit: int = HERMES_SETTINGS["matches_limit"]

    sorted_matches = sorted(matches.items(), key=lambda x: x[1][0], reverse=True)
    logger.info(f"Format Matches: {len(sorted_matches)} raw candidates.")

    reserved: list = []
    randomised: list = []

    for idx, match in enumerate(sorted_matches[:matches_limit]):
        score = match[1][0]
        if score < score_cutoff:
            continue
        if idx > 10 and score < 5:
            continue
        (reserved if score > 5 else randomised).append(match)

    try:
        selected = reserved + random.sample(
            randomised, k=min(num_of_entries, len(randomised))
        )
    except ValueError:
        return None

    selected = sorted(selected, key=lambda x: x[1][0], reverse=True)

    lines: list[str] = []
    for match in selected[:num_of_entries]:
        username, data = match
        score = data[0]
        offered_levels: dict[str, str] = data[4]

        try:
            submission = reddit.submission(data[3])
        except (PRAWException, AttributeError):
            continue

        # Format offered languages
        if data[1]:
            parts: list[str] = []
            for code in data[1]:
                lingvo = converter(code)
                if lingvo is None or lingvo.name is None:
                    continue
                level = offered_levels.get(code)
                parts.append(f"{lingvo.name} ({level})" if level else lingvo.name)
            offered_str = ", ".join(parts)
        else:
            offered_str = "---"

        # Format sought languages
        if data[2]:
            parts_s: list[str] = []
            for code in data[2]:
                lingvo = converter(code)
                if lingvo is None or lingvo.name is None:
                    continue
                parts_s.append(lingvo.name)
            sought_str = ", ".join(parts_s)
        else:
            sought_str = "---"

        date_str = convert_to_day(submission.created_utc)
        safe_user = username.replace("_", r"\_")

        line = (
            f"| u\\/{safe_user} | {date_str} | "
            f"[Post]({submission.permalink}) | `{score}` | "
            f"{offered_str} | {sought_str} |"
        )

        if line not in lines:
            lines.append(line)

    if not lines:
        return None

    header = (
        "| Username | Date | Post Link | Relevance | Offered Matches | Sought Matches |\n"
        "|----------|------|-----------|-----------|-----------------|----------------|\n"
    )
    footer = (
        "\n\n*Please feel free to comment on the above posts "
        "to get in contact with their authors.*"
    )
    return header + "\n".join(lines) + footer
