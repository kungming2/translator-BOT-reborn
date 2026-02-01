#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
This handles language processing from posts' titles and also
filters out posts that do not match the community rules. The primary class
associated with requests is the Titolo class.
"""

import json
import logging
import re
import string
from pprint import pprint
from typing import Any, List, Optional, Union

from praw.models import Submission
from rapidfuzz import fuzz

from ai import ai_query, openai_access
from config import SETTINGS, Paths, load_settings, logger
from connection import REDDIT_HELPER
from discord_utils import send_discord_alert
from languages import Lingvo, converter, country_converter, define_language_lists
from responses import RESPONSE


# When a post is processed, it is given this class which should contain
# all the necessary information for other functions to act on it.
class Titolo:
    def __init__(self):
        self.source = []  # List of source languages
        self.target = []  # List of target languages
        self.final_code = None  # Final language code for the title
        self.final_text = None  # Final language name for the title
        self.title_original = None  # Original title as-is
        self.title_actual = None  # Original title minus language tag
        self.title_processed = None  # Processed title including modifications
        self.notify_languages = []  # Languages to notify (main + others if needed)
        self.language_country = None  # Optional country specification
        self.direction = None  # Translation direction relative to English
        self.ai_assessed = False  # Whether this result came from the AI fallback

    def __repr__(self):
        return f"<Titolo: ({self.source} > {self.target}) | {self.title_original}>"

    def __str__(self):
        return (
            f"Titolo(\n"
            f"  source={self.source},\n"
            f"  target={self.target},\n"
            f"  final_code='{self.final_code}',\n"
            f"  final_text='{self.final_text}',\n"
            f"  title_original='{self.title_original}',\n"
            f"  title_actual='{self.title_actual}',\n"
            f"  title_processed='{self.title_processed}',\n"
            f"  notify_languages={self.notify_languages},\n"
            f"  language_country='{self.language_country}',\n"
            f"  direction='{self.direction}',\n"
            f"  ai_assessed={self.ai_assessed}\n)"
        )

    # Helper methods for flair setting.
    def add_final_code(self, code):
        """Add a CSS code to the object used for flairs."""
        self.final_code = code

    def add_final_text(self, text):
        """Add a CSS text to the object used for flairs."""
        self.final_text = text

    @classmethod
    def process_title(cls, title_text_or_post, post=None):
        """
        Class method that processes a title or submission and returns
        a new Titolo instance.
        """
        if hasattr(title_text_or_post, "title"):  # It's a PRAW submission
            title = str(title_text_or_post.title)  # ensure it's a string
            post = title_text_or_post  # assign the submission
        else:
            title = str(title_text_or_post)  # raw string input

        updated = process_title(title, post)
        return updated  # Already a Titolo instance


# Load the title module's settings.
title_settings = load_settings(Paths.SETTINGS["TITLE_MODULE_SETTINGS"])


def extract_lingvos_from_text(
    text: str, return_english: bool = False
) -> List[Lingvo] | None:
    """
    Extracts Lingvo objects from a paragraph based on capitalized language-like words.
    Includes supported languages, and optionally 'English' even if unsupported.

    :param text: The paragraph or sentence to search.
    :param return_english: Whether to include 'English' even if unsupported.
    :return: A list of Lingvo objects, or None if nothing valid was found.
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

    return sorted(found, key=lambda ling: ling.name) if found else None


def _english_fuzz(word: str) -> bool:
    """
    A quick function that detects if a word is likely to be "English."
    Used in replace_bad_english_typing below.

    Uses fuzzy string matching to determine if a word is a misspelling of
    "English" (e.g., "Enlgish", "Englsh", "Englich").

    Args:
        word: Any word to check for similarity to "English".

    Returns:
        True if the word has >70% similarity to "English", False otherwise.
    """
    word = word.title()
    closeness: float = fuzz.ratio("English", word)
    if closeness > 70:  # Very likely
        return True
    else:  # Unlikely
        return False


def _normalize_misspelled_english(title: str) -> str:
    """
    Replaces common misspellings of 'English' in a post title so that it
    passes title filter routines.

    :param title: The original r/translator post title.
    :return: The cleaned title with misspellings of 'English' replaced.
    """
    # Remove common punctuation and normalize spaces
    title = re.sub(r"""[,.;@#?!&$()“”’"•]+\s*""", " ", title, flags=re.VERBOSE)

    # Replace each word that fuzzy-matches "English"
    words = title.split()
    for word in words:
        if _english_fuzz(word):
            title = title.replace(word, "English")

    return title


def _build_required_title_keywords() -> dict[str, list[str]]:
    """
    Generates keyword phrases for detecting valid post titles on r/translator.

    Combines common representations of "English", supported languages, and connector terms (like "to" or ">")
    to form a list of acceptable title patterns. Also identifies specific "to LANGUAGE" phrases for special rule checks.

    :return: A dictionary with:
        - 'total': All valid keyword combinations.
        - 'to_phrases': Only the "to LANGUAGE" style combinations.
    """
    keywords = {"total": [], "to_phrases": []}
    supported_languages = define_language_lists()["SUPPORTED_LANGUAGES"]

    english_aliases = title_settings["ENGLISH_ALIASES"]
    connectors = title_settings["CONNECTORS"]

    # Generate combinations with English variants
    for eng in english_aliases:
        for conn in connectors:
            pairs = [f" {conn} {eng}", f"{eng} {conn} "]
            if conn != "to":
                pairs += [f"{conn}{eng}", f"{eng}{conn}"]
            else:
                keywords["to_phrases"] += pairs
            keywords["total"] += pairs

    # Generate combinations with supported languages
    for lang in supported_languages:
        lang = lang.lower()
        for conn in connectors:
            pairs = [f" {conn} {lang}", f"{lang} {conn} "]
            if conn != "to":
                pairs += [f"{conn}{lang}", f"{lang}{conn}"]
            else:
                keywords["to_phrases"] += pairs
            keywords["total"] += pairs

    # Add additional valid tags and punctuation variants
    keywords["total"] += [">", "[unknown]", "[community]", "[meta]"]
    keywords["total"] += sorted(d.lower() for d in title_settings["ENGLISH_DASHES"])

    # Remove known false positives
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


def _move_bracketed_tag_to_front(title: str) -> str:
    """
    Moves the first bracketed or parenthesized tag in the title to the front,
    normalizing parentheses to brackets.

    Only moves tags when the title doesn't already have language info at the start.
    """
    # **NEW: Don't move anything if title already starts with language pattern**
    # Pattern: "Word > Word:" or "Word to Word:" at the beginning
    if re.match(r"^[A-Za-z\s]+\s*(?:>|to)\s*[A-Za-z]+\s*:", title, re.IGNORECASE):
        return title  # Already properly formatted, don't touch it

    # Try to find bracketed tag first
    match = re.search(r"\[.*?]", title)
    if match:
        tag = match.group(0)
        remainder = title.replace(tag, "", 1).strip()
        return f"{tag} {remainder}".strip()

    # Try to find parenthesized tag (looking for language patterns)
    # Match parentheses that contain ">" or "to" suggesting a translation
    match = re.search(r"\(([^)]*(?:>|to)[^)]*)\)", title)
    if match:
        tag_content = match.group(1)
        tag = f"[{tag_content}]"  # Normalize to brackets
        remainder = title.replace(match.group(0), "", 1).strip()
        return f"{tag} {remainder}".strip()

    # Handle malformed title with unclosed bracket like "Title [JP"
    if "[" in title:
        parts = title.split("[", 1)
        if len(parts) == 2:
            tag = f"[{parts[1].rstrip(']')}]"
            remainder = parts[0].strip()
            return f"{tag} {remainder}".strip()

    # Handle malformed title with unclosed parenthesis like "Title (JP"
    # **MODIFIED: Only if it contains language indicators**
    if "(" in title and (">" in title or "to" in title.lower()):
        parts = title.split("(", 1)
        if len(parts) == 2:
            tag = f"[{parts[1].rstrip(')')}]"
            remainder = parts[0].strip()
            return f"{tag} {remainder}".strip()

    return title  # Nothing to do


def _reformat_detected_languages_in_title(title: str) -> str | None:
    """Attempts to reformat a poorly structured title."""
    logger.debug(f"Initial title: '{title}'")

    title_words = re.findall(r"\w+", title)
    logger.debug(f"Extracted words: {title_words}")

    if not title_words:
        logger.debug("No words found in title, returning None")
        return None

    detected_languages = {}
    first_lang = last_lang = None
    last_lang_word = None  # Track which word contains the last language

    # Scan first ~5 words for languages
    logger.debug(f"Scanning first 5 words: {title_words[:5]}")
    for word in title_words[:5]:
        if word.lower() == "to":
            logger.debug(f"Skipping word 'to': {word}")
            continue
        match = extract_lingvos_from_text(word.title())
        if match:
            detected_languages[word] = match[0].name
            logger.debug(f"Found language in word '{word}': {match[0].name}")
            if not first_lang:
                first_lang = match[0].name
                logger.debug(f"Set first_lang: {first_lang}")

    # Scan last ~5 words (reversed) for target language
    # NEW: Don't reuse the same language unless it appears multiple times
    logger.debug(
        f"Scanning last 5 words (reversed): {list(reversed(title_words[-5:]))}"
    )
    for word in reversed(title_words[-5:]):
        match = extract_lingvos_from_text(word.title(), True)
        if match:
            potential_lang = match[0].name
            logger.debug(
                f"Found potential last language in word '{word}': {potential_lang}"
            )

            # If different from source, use it
            if potential_lang != first_lang:
                last_lang = potential_lang
                last_lang_word = word  # Store the actual word
                logger.debug(
                    f"Different from first_lang, set last_lang: {last_lang}, word: {word}"
                )
                break
            # If same as source, check if it appears multiple times in title
            elif sum(1 for w in title_words if potential_lang.lower() in w.lower()) > 1:
                last_lang = potential_lang
                last_lang_word = word  # Store the actual word
                logger.debug(
                    f"Same as first_lang but appears multiple times, set last_lang: {last_lang}, word: {word}"
                )
                break
            else:
                logger.debug(
                    f"Same as first_lang {first_lang} and only appears once, skipping"
                )

    logger.debug(
        f"Final detected languages: first_lang={first_lang}, last_lang={last_lang}, last_lang_word={last_lang_word}"
    )
    logger.debug(f"All detected_languages: {detected_languages}")

    if not first_lang or not last_lang:
        logger.debug(
            f"Missing language (first_lang={first_lang}, last_lang={last_lang}), returning None"
        )
        return None

    lang_tag = f"[{first_lang} > {last_lang}]"
    logger.debug(f"Created lang_tag: '{lang_tag}'")

    reformatted = title
    logger.debug(f"Starting reformatted: '{reformatted}'")

    # Remove the last language word first (if different from first)
    if first_lang != last_lang and last_lang_word:
        logger.debug(
            f"Languages are different, removing last_lang word '{last_lang_word}' first"
        )
        old_reformatted = reformatted
        reformatted = reformatted.replace(last_lang_word, "", 1)
        logger.debug(f"Removed last language word '{last_lang_word}'")
        logger.debug(f"Title after removal: '{old_reformatted}' -> '{reformatted}'")
    else:
        logger.debug(
            "Languages are the same or no last_lang_word found, skipping last_lang removal"
        )

    # Now replace the first language word with the tag
    for original_word, lang_code in detected_languages.items():
        if lang_code == first_lang:
            old_reformatted = reformatted
            reformatted = reformatted.replace(original_word, lang_tag, 1)
            logger.debug(
                f"Replaced first language word '{original_word}' with '{lang_tag}'"
            )
            logger.debug(
                f"Title after replacement: '{old_reformatted}' -> '{reformatted}'"
            )
            break

    old_reformatted = reformatted
    reformatted = re.sub(r"\b(to|into)\b", ">", reformatted, flags=re.IGNORECASE)
    logger.debug(
        f"After replacing 'to/into' with '>': '{old_reformatted}' -> '{reformatted}'"
    )

    old_reformatted = reformatted
    reformatted = re.sub(r"\s{2,}", " ", reformatted).strip()
    logger.debug(f"After whitespace cleanup: '{old_reformatted}' -> '{reformatted}'")

    # Clean up any trailing separators (>, -, etc.) that may be left over
    old_reformatted = reformatted
    reformatted = re.sub(r"\s*[>-]\s*$", "", reformatted).strip()
    logger.debug(
        f"After removing trailing separators: '{old_reformatted}' -> '{reformatted}'"
    )

    logger.debug(f"Final reformatted title: '{reformatted}'")

    return reformatted


"""FILTERING (FIRST ROUND)"""


def main_posts_filter(title: str) -> tuple[bool, str | None, str | None]:
    """
    Filters r/translator post titles based on community formatting guidelines.

    :param title: The original post title.
    :return:
        - post_okay (bool): Whether the title passes formatting rules.
        - title (str | None): Possibly modified title if passed; None if rejected.
        - filter_reason (str | None): Code for why the post was rejected.
            - '1': Missing required keywords.
            - '1A': "to English" phrasing not early in the title.
            - '1B': Too short and generic (e.g., "Translation to English").
            - '2': '>' present but poorly placed or not formatted.
    """
    title_lower = title.lower()

    # Load required keyword sets
    keywords = _build_required_title_keywords()
    mandatory_keywords = keywords["total"]
    to_phrases = keywords["to_phrases"]

    # Rule 1: Check for required keywords
    if not any(kw in title_lower for kw in mandatory_keywords):
        title = _normalize_misspelled_english(title)
        title_lower = title.lower()  # Update lowercased version

        if not any(kw in title_lower for kw in mandatory_keywords):
            filter_reason = "1"
            logger.info(
                f"Main_Posts_Filter: > Filtered a post with an incorrect title format. Rule: #{filter_reason}"
            )
            return False, None, filter_reason

    # Rule 1A and 1B: "to LANGUAGE" phrasing issues
    if ">" not in title_lower and any(phrase in title_lower for phrase in to_phrases):
        if not any(phrase in title_lower[:25] for phrase in to_phrases):
            filter_reason = "1A"
            logger.info(
                f"Main_Posts_Filter: > Filtered a post with an incorrect title format. Rule: #{filter_reason}"
            )
            return False, None, filter_reason

        if len(title) < 35 and "[" not in title:
            listed_lingvos = extract_lingvos_from_text(title.title()) or []
            non_english_lingvos = [
                lingvo for lingvo in listed_lingvos if lingvo.name != "English"
            ]

            if not non_english_lingvos:
                filter_reason = "1B"
                logger.info(
                    f"Main_Posts_Filter: > Filtered a post with no valid language. Rule: #{filter_reason}"
                )
                return False, None, filter_reason

    # Rule 2: '>' is present but poorly positioned
    if ">" in title and "]" not in title and ">" not in title[:50]:
        filter_reason = "2"
        logger.info(
            f"Main_Posts_Filter: > Filtered a post due to incorrect placement of '>'. Rule: #{filter_reason}"
        )
        return False, None, filter_reason

    # Passed all filters
    return True, title, None


"""ASSESSING (SECOND ROUND)"""


def _preprocess_title(post_title: str) -> str:
    """
    Normalize a Reddit post title by fixing brackets, typos, symbols,
    misused language tags, and removing cross-post markers.
    """
    title: str = re.sub(r"\(x-post.*", "", post_title).strip()

    # **NEW: Check if title already has a clear "LANG to LANG" pattern at the start**
    # If so, don't aggressively move parentheticals around
    has_clear_format = bool(re.match(r"^[A-Za-z\s]+\s+to\s+[A-Za-z]+\s*:", title))

    # Correct spelling/alias issues
    for spelling in converter("en").name_alternates:
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

    # Normalize the case for "to" and fix malformed brackets
    title = re.sub(r"\b(To|TO|tO)\b", "to", title)
    if not any(b in title for b in ["[", "]"]) and re.match(
        r"[({].+(>| to ).+[)}]", title
    ):
        title = title.replace("(", "[", 1).replace(")", "]", 1)
        title = title.replace("{", "[", 1).replace("}", "]", 1)

    # **MODIFIED: Only attempt reformatting if no clear format exists**
    if not any(b in title for b in ["[", "]"]) and not has_clear_format:
        reformatted: str = _reformat_detected_languages_in_title(title)
        if reformatted:
            title = reformatted

    # Normalize bracketed language tags and country suffixes
    title = re.sub(r"(]\s*[>\\-]\s*\[)", " > ", title)
    if "{" in title and "}" in title and "[" in title:
        match = re.search(r"{(\D+)}", title)
        if match:
            country: str = match.group(1)
            code: str = country_converter(country)[0]
            if code:
                title = title.split("{", 1)[0].strip() + title.split("}", 1)[1]
    elif "{" in title and "[" not in title:
        title = title.replace("{", "[").replace("}", "]")

    # Handle special cases and cleanup
    if "-" in title[:20] and any(
        k in title.title() for k in title_settings["ENGLISH_DASHES"]
    ):
        title = title.replace("-", " > ")

    # **MODIFIED: Only move bracketed tags if there's no clear "X to Y" format already**
    has_bracket = "[" in title and "[" not in title[:10]
    has_paren = "(" in title and "(" not in title[:10]

    if not has_clear_format and (has_bracket or has_paren):
        title = _move_bracketed_tag_to_front(title.strip())

    title = title.replace("English.", "English] ").replace("_", " ")

    # Fix improperly hyphenated words
    hyphen_match = re.search(r"((?:\w+-)+\w+)", title[:25])
    if hyphen_match:
        converted = converter(hyphen_match.group(0))
        if converted is not None and not converted.name:
            title = title.replace("-", " ")

    # Clean up symbols and duplicate markers
    for ch in ["&", "+", "/", "\\", "|", "?"]:
        title = title.replace(ch, f" {ch} ")
    for compound in [">>>", ">>", "> >", "<"]:
        title = title.replace(compound, " > ")

    # Try to normalize missing brackets around 'English'
    if ">" in title and "English" in title and "]" not in title and "[" not in title:
        title = title.replace("English", "English]")
        title = "[" + title

    # Catch malformed directional hints
    if ">" not in title:
        if any(k in title[:25] for k in ["- Eng", "-Eng"]):
            title = title.replace("-", " > ")
        title = title.replace(" into ", ">")

    # Fix frequent false matches for "KR". This is a unique exception.
    if "KR " in title.upper()[:10]:
        title = title.replace("KR ", "Korean ")

    # Handle unknown or unclear entries - normalize to [Unknown > target]
    if (
        "[Unknown]" in title.title()
        or title.lstrip().startswith("[?")
        or title.lstrip().startswith("[ ?")
    ):
        # Try to extract target language
        match = re.search(r"(?:>|to)\s*([^]]+)", title, re.IGNORECASE)
        if match:
            target_lang = match.group(1).strip().rstrip("]")
            title = f"[Unknown > {target_lang}]"
        else:
            # No target language specified, default to English
            title = "[Unknown > English]"

    return title


def _is_punctuation_only(s: str) -> bool:
    """
    Check if a string contains only punctuation characters (after stripping whitespace).

    Args:
        s: The string to check.

    Returns:
        True if the string is non-empty and contains only punctuation, False otherwise.
    """
    # Strip whitespace first
    s = s.strip()
    # Check if s is empty or all chars are punctuation
    return len(s) > 0 and all(c in string.punctuation for c in s)


def _clean_text(
    text: str, preserve_commas: bool = False, preserve_separators: bool = False
) -> str:
    """
    Insert spaces around brackets/parentheses and remove other punctuation with extra spaces.

    Args:
        text: The text to clean.
        preserve_commas: If True, keep commas in the text. Default is False.
        preserve_separators: If True, keep &, /, and commas for language separation. Default is False.

    Returns:
        Cleaned text with normalized spacing and reduced punctuation.
    """
    # Insert spaces around brackets and parentheses
    text = re.sub(r"([\[\]()])", r" \1 ", text)

    # Remove other punctuation (excluding brackets/parentheses)
    if preserve_separators:
        # Keep &, /, and , for language separation
        text = re.sub(r"[.;@#?!$" "'\"•]+ *", " ", text)
    elif preserve_commas:
        text = re.sub(r"[.;@#?!&$" "'\"•/]+ *", " ", text)
    else:
        text = re.sub(r"[,.;@#?!&$" "'\"•/]+ *", " ", text)

    # Collapse multiple spaces into one
    text = re.sub(r"\s+", " ", text)

    return text.strip()


def _extract_source_chunk(title: str) -> str:
    """
    Extract the source language chunk from a processed title.

    Handles both properly formatted titles ([Source > Target]) and malformed
    titles with various separators (>, to, -, <).

    Args:
        title: The processed title string.

    Returns:
        The extracted and cleaned source language chunk.
    """
    # If title has proper bracket format [Source > Target], extract from within brackets
    if "[" in title and "]" in title:
        bracket_content: str = title[title.index("[") + 1 : title.index("]")]
        if ">" in bracket_content:
            # Get everything before the first > within brackets
            return _clean_text(bracket_content.split(">")[0])
        elif " to " in bracket_content:
            return _clean_text(bracket_content.split(" to ")[0])
        else:
            # No separator, entire bracket content is source
            return _clean_text(bracket_content)

    # Fallback to original logic for malformed titles
    for sep in [">", " to ", "-", "<"]:
        if sep in title:
            return _clean_text(title.split(sep)[0])
    return _clean_text(title)


def _extract_target_chunk(title: str) -> str:
    """
    Extract the target language chunk from a processed title.

    Handles both properly formatted titles ([Source > Target]) and malformed
    titles with various separators (>, to, -, <).

    Args:
        title: The processed title string.

    Returns:
        The extracted and cleaned target language chunk, or empty string if not found.
    """
    # If title has proper bracket format [Source > Target], extract from within brackets
    if "[" in title and "]" in title:
        bracket_content: str = title[title.index("[") + 1 : title.index("]")]
        if ">" in bracket_content:
            # Get everything after the last > within brackets
            parts: list[str] = bracket_content.split(">")
            # Preserve separators like &, /, and commas for language parsing
            return _clean_text(parts[-1], preserve_separators=True)
        elif " to " in bracket_content:
            parts = bracket_content.split(" to ")
            # Preserve separators like &, /, and commas for language parsing
            return _clean_text(parts[-1], preserve_separators=True)

    # Fallback to original logic for malformed titles
    for sep in [">", " to ", "-", "<"]:
        if sep in title:
            chunk: str = title.split(sep, 1)[1]
            # Stop at the closing bracket
            if "]" in chunk:
                chunk = chunk.split("]", 1)[0]
            # Preserve separators like &, /, and commas for language parsing
            return _clean_text(chunk, preserve_separators=True)
    return ""


def _clean_chunk(chunk: str) -> str:
    """
    Clean a language chunk by removing brackets, whitespace, and trailing punctuation.

    Args:
        chunk: The chunk string to clean.

    Returns:
        Cleaned chunk in lowercase with brackets and trailing punctuation removed.
    """
    # Strip brackets and spaces
    chunk = chunk.strip()
    chunk = chunk.lstrip("[").rstrip("]")
    chunk = chunk.strip()
    # Remove trailing punctuation like '-' or ':' or spaces again
    chunk = re.sub(r"\W+$", "", chunk.lower())
    return chunk


def _resolve_languages(chunk, is_source):
    """
    Resolve language objects from a text chunk extracted from a post title.

    Handles various formats including:
    - Single languages: "Spanish", "Arabic", "en", "fra"
    - Multiple languages with separators: "English OR German", "Spanish/French", "Korean & Japanese"
    - Comma-separated lists: "Spanish, French, Italian"
    - Unknown language indicators: "unknown", "unk", "???"
    - Language codes (ISO 639-1, 639-3) and language names

    :param chunk: Text extracted from title containing language information (e.g., "English OR German")
    :param is_source: Boolean indicating if this is the source language chunk (affects word limit for processing)
    :return: List of Lingvo objects representing resolved languages, or empty list if none found
    """
    cleaned = _clean_chunk(chunk)
    logger.debug(f"Cleaned Chunk: {cleaned}")

    if cleaned in {"unknown", "unk", "???", "n/a"}:
        logger.debug("Handling 'unknown' chunk explicitly.")
        return [converter("unknown")]

    if "]" in chunk:
        chunk = chunk.split("]", 1)[0]

    # NEW: Handle OR/AND/slash/ampersand/comma separators - split and process each part separately
    # Check for separators: "or", "and", "&", "/", ","
    separator_pattern = r"\s+(?:or|and)\s+|[&/,]"
    if re.search(separator_pattern, chunk, flags=re.IGNORECASE):
        logger.debug(f"Found separator in chunk: {chunk}")
        parts = re.split(separator_pattern, chunk, flags=re.IGNORECASE)
        logger.debug(f"Split into parts: {parts}")

        all_languages = []
        for part in parts:
            part = part.strip()
            if part:
                # Recursively resolve each part
                part_languages = _resolve_languages(part, is_source)
                if part_languages:
                    all_languages.extend(part_languages)

        if all_languages:
            # Deduplicate by preferred_code
            unique = {}
            for lang in all_languages:
                key = lang.name if hasattr(lang, "name") else lang.language_code_3
                unique[key] = lang
            logger.debug(f"Resolved languages from separators: {list(unique.values())}")
            return list(unique.values())
        # If no languages found after split, continue with normal processing

    # ORIGINAL LOGIC CONTINUES HERE (but comma handling removed since it's now in separator pattern)
    words = chunk.split()
    words = [w for w in words if not _is_punctuation_only(w)]

    if 2 <= len(words) <= 3:
        joined = " ".join(words)
        words.insert(0, joined)

    logger.debug(f"Words before cleanup: {words}")
    # Convert strings to sets for O(1) lookup
    english_2_words = set(title_settings["ENGLISH_2_WORDS"])
    english_3_words = set(title_settings["ENGLISH_3_WORDS"].split())

    # Filter words
    cleaned_words = [
        w
        for w in words
        if not (
            (len(w) == 2 and w.title() in english_2_words)
            or (len(w) == 3 and w.title() in english_3_words)
        )
    ]

    logger.debug(f"Cleaned words: {cleaned_words}")

    # Limit words checked to as long as we have
    max_words_to_check = max(5, len(cleaned_words))

    resolved = []
    for word in cleaned_words[:max_words_to_check]:
        # **FIX: Strip trailing punctuation before conversion**
        word = word.rstrip("-_.,;:!?")

        if "Eng" in word and len(word) <= 8:
            word = "English"
        converter_result = converter(word)

        if " " in word:
            logger.debug(f"Converted full phrase: {word} -> {converter_result}")
        else:
            logger.debug(f"Converted {word} -> {converter_result}")

        if converter_result:
            resolved.append(converter_result)
            if " " in word:
                break

    unique = {}
    for lang in resolved:
        key = lang.name if hasattr(lang, "name") else lang.language_code_3
        unique[key] = lang

    final = list(unique.values()) or []
    logger.debug(f"{'Source' if is_source else 'Target'} Language Strings: {resolved}")

    return final


def _extract_actual_title(title):
    """Return the post title content after language tag is stripped."""
    actual = title.split("]", 1)[1] if "]" in title else ""
    return actual.strip("].> ,:.") if actual else ""


def _determine_title_direction(source_languages, target_languages):
    """
    Determine the direction of English language usage based on source and target language lists.
    This info is used for statistics in Ajos and Wenyuan.

    :param source_languages: List of source languages.
    :param target_languages: List of target languages.
    :return: One of 'english_from', 'english_to', 'english_both', or 'english_none'.
    """

    # Work on copies to avoid mutating input lists
    src = source_languages[:]
    tgt = target_languages[:]

    # Remove 'English' from lists if all entries contain 'English' (like 'Middle English'),
    # and list length > 1 to avoid always returning 'english_both'
    if all("English" in lang.name for lang in src) and len(src) > 1:
        if "English" in src:
            src = [lang for lang in src if lang.name != "English"]
    elif all("English" in lang.name for lang in tgt) and len(tgt) > 1:
        if "English" in tgt:
            tgt = [lang for lang in tgt if lang.name != "English"]

    # If 'English' appears in both source and target
    src_names = [lang.name for lang in src]
    tgt_names = [lang.name for lang in tgt]

    if "English" in src_names and "English" in tgt_names:
        combined_len = len(src) + len(tgt)
        # If combined list is long, try to remove 'English' from the longer list to avoid bias
        if combined_len >= 3:
            if len(src) >= 2 and "English" in src_names:
                src = [lang for lang in src if lang.name != "English"]
                src_names = [lang.name for lang in src]
            elif len(tgt) >= 2 and "English" in tgt_names:
                tgt = [lang for lang in tgt if lang.name != "English"]
                tgt_names = [lang.name for lang in tgt]

    # Determine direction based on presence of 'English'
    if "English" in src_names and "English" not in tgt_names:
        return "english_from"
    elif "English" in tgt_names and "English" not in src_names:
        return "english_to"
    elif "English" in src_names and "English" in tgt_names:
        return "english_both"
    else:
        return "english_none"


def _get_notification_languages(assess_request):
    """
    Determine if the language request involves *only* non-English languages across
    source and target lists. If English appears in either, return None since it's
    not a pure non-English request.

    This helps Ziwen decide whether to notify both languages.

    :param assess_request: A Titolo object.
    :return: List of unique non-English languages to notify users for.
    """
    source_languages = assess_request.source
    target_languages = assess_request.target
    direction = assess_request.direction

    # No need to waste time if the languages are both English.
    if direction == "english_both":
        logger.error("Both English. Not sending notifications.")
        return None

    # Combine unique languages from both lists
    combined = set(source_languages) | set(target_languages)

    # Remove English lingvo objects, as we do not notify for English.
    combined = [x for x in combined if x.name != "English"]

    # Deduplicate by Lingvo code or another unique attribute
    unique = {}
    for lang in combined:
        key = lang.code if hasattr(lang, "code") else lang.name
        unique[key] = lang

    combined = list(unique.values())

    # Return combined list only if a language exists
    return list(combined) if len(combined) >= 1 else None


def _determine_flair(titolo_object):
    """
    Sets the final flair code and text on the titolo_object based on
    direction and language support. Handles multiple-language targets.
    Prioritizes non-English languages when English is present in either source or target.
    """

    def resolve_flair_code(lang_obj):
        # Add null check
        if lang_obj is None:
            return "generic"
        if lang_obj.language_code_1 and lang_obj.supported:
            return lang_obj.language_code_1
        elif lang_obj.language_code_3 and lang_obj.supported:
            return lang_obj.language_code_3
        return "generic"

    def generate_final_text(language_codes, max_length=64):
        """Generate final_text with a character limit, abbreviating if needed."""
        sorted_codes = sorted(language_codes)
        full_text = f"Multiple Languages [{', '.join(sorted_codes)}]"

        if len(full_text) <= max_length:
            return full_text

        # Abbreviate to fit within limit
        prefix = "Multiple Languages ["
        suffix = "]"
        max_content_length = max_length - len(prefix) - len(suffix)

        included_codes = []
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

    def get_non_english_language(language_list):
        """Extract the first non-English language from a list, or None if all are English."""
        for lang in language_list:
            if lang and lang.name != "English":
                return lang
        return None

    # NEW: Handle cases where English is present in source or target
    # Priority: Use the non-English language for the flair
    source_languages = titolo_object.source or []
    target_languages = titolo_object.target or []

    # Check if English appears in source
    source_has_english = any(lang.name == "English" for lang in source_languages)
    target_has_english = any(lang.name == "English" for lang in target_languages)

    # If English is in target, prioritize source language (translating FROM something TO English)
    if target_has_english and source_languages:
        non_english_source = get_non_english_language(source_languages)
        if non_english_source:
            flair_code = resolve_flair_code(non_english_source)
            titolo_object.add_final_code(flair_code)
            titolo_object.add_final_text(non_english_source.name)
            return

    # If English is in source, prioritize target language (translating TO something FROM English)
    if source_has_english and target_languages:
        non_english_target = get_non_english_language(target_languages)
        if non_english_target:
            flair_code = resolve_flair_code(non_english_target)
            titolo_object.add_final_code(flair_code)
            titolo_object.add_final_text(non_english_target.name)
            return

    # ORIGINAL LOGIC BELOW (fallback when above cases don't apply)
    if titolo_object.direction == "english_to":
        if not titolo_object.source:
            return  # No source language to base flair on
        lang = titolo_object.source[0]

    elif titolo_object.direction in ("english_from", "english_none"):
        targets = titolo_object.target
        if len(targets) == 1:
            lang = targets[0]
            if getattr(lang, "preferred_code", "") == "multiple":
                titolo_object.add_final_code("multiple")
                titolo_object.add_final_text("Multiple Languages")
                return
            else:
                # proceed normally for single, non-multiple language
                flair_code = resolve_flair_code(lang)
                titolo_object.add_final_code(flair_code)
                titolo_object.add_final_text(lang.name if lang else "Unknown")
                return
        elif len(targets) > 1:  # Defined multiple post
            preferred_codes = [
                lang.preferred_code.upper()
                for lang in targets
                if hasattr(lang, "preferred_code") and lang.preferred_code
            ]

            titolo_object.add_final_code("multiple")
            titolo_object.add_final_text(generate_final_text(preferred_codes))
            return
        elif len(targets) == 0:
            # No target languages, try to use source language
            if titolo_object.source and len(titolo_object.source) > 0:
                lang = titolo_object.source[0]
                flair_code = resolve_flair_code(lang)
                titolo_object.add_final_code(flair_code)
                titolo_object.add_final_text(lang.name if lang else "Unknown")
                return
            else:
                # Set generic flair when no languages found. This
                # should ideally be extremely rare.
                titolo_object.add_final_code("generic")
                titolo_object.add_final_text("Generic")
                logger.warning(
                    f"Determine Flair: Set completely generic: {titolo_object}"
                )
                return

        else:
            return  # No valid target languages

    else:
        return  # Unsupported or ambiguous direction

    flair_code = resolve_flair_code(lang)
    titolo_object.add_final_code(flair_code)
    titolo_object.add_final_text(lang.name)


def process_title(title, post=None, discord_notify=True):
    """
    Main function to process a Reddit post title, extract language info,
    assign flair metadata, detect direction and output a structured Titolo object.

    Args:
        title (str): The post title from r/translator.
        post (PRAW): A PRAW object. Unused unless we ask AI.
        discord_notify (bool): Whether to send a Discord notification
                               if AI is asked.

    Returns:
        Titolo: An object representing the parsed structure and flair decisions.
    """
    processed = _preprocess_title(title)
    if isinstance(processed, Titolo):  # Returned early due to bad input
        return processed

    logger.debug(f"Title as Processed: {processed}")

    result = Titolo()
    result.title_original = str(title)
    result.title_processed = processed
    result.title_actual = _extract_actual_title(processed)

    # Check the language before a separator.
    source_chunk = _extract_source_chunk(processed)
    logger.debug(f"Source chunk: {source_chunk}")
    result.source = _resolve_languages(source_chunk, is_source=True)

    target_chunk = _extract_target_chunk(processed)
    logger.debug(f"Target chunk: {target_chunk}")
    result.target = _resolve_languages(target_chunk, is_source=False)

    result.direction = _determine_title_direction(result.source, result.target)

    # Figure out which languages we wish to notify people for.
    result.notify_languages = _get_notification_languages(result) or []

    # Last chance. If there are no matched languages, pass it on
    # to our AI assessor.
    # Combine source and target, remove English lingvos, then assess
    combined_languages = (result.source or []) + (result.target or [])
    combined_languages = [x for x in combined_languages if x.preferred_code != "en"]
    logger.debug(
        "Combined languages before filtering: "
        + str([x.preferred_code for x in combined_languages])
    )
    logger.debug("Language names: " + str([x.name for x in combined_languages]))
    if not combined_languages:
        logger.info(
            f"> Could not make sense of this title ({title}) at all. Asking AI..."
        )
        ai_result = title_ai_parser(title, post)
        if isinstance(ai_result, dict):
            _update_titolo_from_ai_result(result, ai_result)

            # Only construct Discord message if post object exists
            if post:
                updating_subject = "AI Parsed Title and Assigned Language to Post"
                updating_reason = (
                    f"Passed to AI service; AI assessed it as **{result.final_text}** (`{result.final_code}`). "
                    f"If incorrect, please assign [this post](https://www.reddit.com{post.permalink}) "
                    f"a different and accurate language category."
                    f"\n\n**Post Title**: [{post.title}](https://www.reddit.com{post.permalink})"
                )
                logger.info(
                    f"[ZW] Title: AI assessment of title performed for '{post.title}' | `{post.id}`."
                )
            else:
                updating_subject = "AI Parsed Title and Assigned Language (Test Mode)"
                updating_reason = (
                    f"Passed to AI service; AI assessed it as **{result.final_text}** (`{result.final_code}`). "
                    f"Test mode - no post object available."
                )
                logger.info(
                    "[ZW] Title: AI assessment of title performed for test title."
                )

        else:
            # AI parsing failed. Assign generic categories.
            result.add_final_code("generic")
            result.add_final_text("Generic")

            # Only construct Discord message if post object exists
            if post:
                updating_subject = "AI Unable to Parse Title; No Language Assigned"
                updating_reason = (
                    "Completely unable to parse this post's language; assigned a generic category. "
                    f"Please check and assign [this post](https://www.reddit.com{post.permalink}) a language category."
                    f"\n\n**Post Title**: [{post.title}](https://www.reddit.com{post.permalink})"
                )
                logger.info(
                    f"[ZW] Posts: AI assessment of title failed for '{post.title}' | `{post.id}`. "
                    "Assigned completely generic category."
                )
            else:
                updating_subject = "AI Unable to Parse Title (Test Mode)"
                updating_reason = (
                    "Completely unable to parse this post's language; assigned a generic category. "
                    "Test mode - no post object available."
                )
                logger.info(
                    "[ZW] Posts: AI assessment of title failed for test title. "
                    "Assigned completely generic category."
                )

        if discord_notify and post:  # Only send Discord alert if post exists
            send_discord_alert(updating_subject, updating_reason, "report")

    # Update the Titolo with the best selection for flair.
    _determine_flair(result)

    return result


"""AI PROCESSING"""


def _update_titolo_from_ai_result(result: Titolo, ai_result: dict[str, Any]) -> None:
    """
    Update a Titolo object based on AI parser output.

    Extracts source and target language information from the AI result and
    updates the Titolo object's language fields, direction, and notification
    languages. Marks the object as AI-assessed upon successful update.

    Args:
        result: The Titolo object to be updated.
        ai_result: The AI's parsed result with language codes and names.
                   Expected keys: 'source_language', 'target_language',
                   each containing a 'code' field.

    Side effects:
        - Updates result.source, result.target, result.direction
        - Updates result.notify_languages and result.ai_assessed flag
        - Logs the update operation
    """
    try:
        src: Optional[dict[str, Any]] = ai_result.get("source_language")
        tgt: Optional[dict[str, Any]] = ai_result.get("target_language")

        if src and "code" in src:
            result.source = [converter(src["code"])]
        if tgt and "code" in tgt:
            result.target = [converter(tgt["code"])]

        result.direction = _determine_title_direction(result.source, result.target)
        result.notify_languages = _get_notification_languages(result) or []
        result.ai_assessed = True  # Mark the Titolo as AI-assisted

        logger.info(
            f"AI updated source: {result.source}, target: {result.target}, direction: {result.direction}"
        )

        _determine_flair(result)
        logger.info(f"AI determined flair: {result.final_code=}; {result.final_text=}")
    except Exception as e:
        logger.error(f"Failed to update Titolo from AI result: {e}")


def title_ai_parser(
    title: str, post: Optional[Submission] = None
) -> Union[dict[str, Any], tuple[str, str]]:
    """
    Passes a malformed title to an AI to assess, and returns the non-English language
    (code and name) if confidence is sufficient.

    Optionally includes image data from the post (direct image or first gallery image)
    to improve AI assessment accuracy.

    Args:
        title: Title of a Reddit post to be parsed.
        post: A PRAW submission object containing optional image data, or None.

    Returns:
        On success: A dictionary containing:
            - 'source_language': dict with 'code' and 'name' keys
            - 'target_language': dict with 'code' and 'name' keys
            - 'confidence': float between 0.0 and 1.0
        On failure: A tuple of ("error", error_message_string)

    Note:
        Returns an error tuple if AI confidence is below 0.7 threshold.
    """
    logger.info(f"AI Parser: AI service is now assessing title: {title}")
    image_url: Optional[str] = None

    if post:
        # Check if post has an image (gallery or direct image)
        if hasattr(post, "post_hint") and post.post_hint == "image":
            image_url = post.url
        elif hasattr(post, "is_gallery") and post.is_gallery:
            # Get first image from gallery
            media_metadata: dict[str, Any] = getattr(post, "media_metadata", {})
            if media_metadata:
                first_item = next(iter(media_metadata.values()))
                if "s" in first_item and "u" in first_item["s"]:
                    image_url = first_item["s"]["u"].replace("&amp;", "&")

    # Prepare the query input (text only)
    query_input: str = RESPONSE.TITLE_PARSING_QUERY + title

    # Construct query kwargs
    logger.info("Passing information to AI service...")
    query_kwargs: dict[str, Any] = {
        "service": "openai",
        "behavior": "You are assessing a technical identification",
        "query": query_input,
        "client_object": openai_access(),
    }

    # Add image URL only if it's available
    if image_url:
        query_kwargs["image_url"] = image_url

    # Send to AI
    query_data: str = ai_query(**query_kwargs)

    # Parse AI response
    try:
        query_dict: dict[str, Any] = json.loads(query_data)
    except json.decoder.JSONDecodeError:
        logger.error(f"Failed to parse query data: `{query_data}`")
        return "error", "Service returned invalid JSON"

    confidence: float = query_dict.get("confidence", 0.0)
    if confidence < 0.7:
        logger.warning("AI confidence value too low for title.")
        return "error", "Confidence value too low"

    logger.info(f"AI Parser: AI service returned data: {query_dict}")
    return query_dict


def format_title_correction_comment(title_text: str, author: str) -> str:
    """
    Constructs a comment suggesting a new, properly formatted post title, along with a resubmit link
    that includes the revised title. This helps streamline the process of resubmitting a post to r/translator.

    :param title_text: The filtered title that lacked required keywords.
    :param author: The OP of the post.
    :return: A formatted comment for `ziwen_posts` to reply with.
    """

    # Prepare the query input (text only)
    query_input = RESPONSE.TITLE_REFORMATTING_QUERY + title_text

    # Construct query kwargs
    query_kwargs = {
        "service": "openai",
        "behavior": "You are checking data entry",
        "query": query_input,
        "client_object": openai_access(),
    }

    # Send to AI
    query_data = ai_query(**query_kwargs)

    # Parse AI response
    suggested_title = query_data

    # Build a URL-safe version of the suggested title
    url_safe_title = (
        suggested_title.replace(" ", "%20").replace(")", r"\)").replace(">", "%3E")
    )

    reformat_comment = RESPONSE.COMMENT_BAD_TITLE.format(
        author=author, new_url=url_safe_title, new_title=suggested_title
    )

    return reformat_comment


def is_english_only(titolo_content: dict) -> bool:
    """
    Returns True if BOTH source and target contain only Lingvo objects
    whose preferred_code is 'en'.
    """
    source = getattr(titolo_content, "source", []) or []
    target = getattr(titolo_content, "target", []) or []
    if not source or not target:
        return False

    return all(
        getattr(lang, "preferred_code", None) == "en" for lang in source
    ) and all(getattr(lang, "preferred_code", None) == "en" for lang in target)


"""INQUIRY SECTION"""


def _show_menu():
    print("\nSelect a search to run:")
    print("1. Title testing (enter your own title to test)")
    print("2. Reddit titles (retrieve the last few Reddit posts to test against)")
    print("3. AI title testing (test AI output for a malformed title)")
    print("4. Test filtration against a title")
    print("x. Exit")


if __name__ == "__main__":
    while True:
        _show_menu()
        choice = input("Enter your choice (1-4): ")

        if choice == "x":
            print("Exiting...")
            break

        if choice not in ["1", "2", "3", "4"]:
            print("Invalid choice, please try again.")
            continue

        if choice == "1":
            logger.setLevel(logging.DEBUG)
            my_test = input("Enter the string you wish to test: ")
            titolo_output = process_title(my_test, None, False)
            pprint(vars(titolo_output))
        elif choice == "2":
            logger.setLevel(logging.INFO)
            submissions = list(
                REDDIT_HELPER.subreddit(SETTINGS["subreddit"]).new(limit=50)
            )
            for submission in submissions:
                print(f"POST TITLE: {submission.title}")
                titolo_output = process_title(submission.title, submission, False)
                pprint(vars(titolo_output))
                print("\n\n")
        elif choice == "3":
            my_test = input("Enter the string you wish to test: ")
            print(title_ai_parser(my_test))

        elif choice == "4":
            my_test = input("Enter the title you wish to test: ")
            print(main_posts_filter(my_test))
