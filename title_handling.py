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
from typing import List

from rapidfuzz import fuzz

from ai import ai_query, openai_access
from config import SETTINGS, Paths, load_settings, logger
from connection import REDDIT_HELPER
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
            f"  direction='{self.direction}'\n",
            f"  ai_assessed={self.ai_assessed}\n)",
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


def _english_fuzz(word):
    """
    A quick function that detects if a word is likely to be "English."
    Used in replace_bad_english_typing below.

    :param word: Any word.
    :return: A boolean. True if it's likely to be a misspelling of the
             word 'English', false otherwise.
    """

    word = word.title()
    closeness = fuzz.ratio("English", word)
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
    Moves the first bracketed tag (e.g., [Tag]) in the title to the front.

    This is useful when titles include tags like "[JP] Title Here" or "Title [FR] Here",
    and you want to normalize them to have the tag at the beginning.

    :param title: The original title, possibly with a bracketed tag.
    :return: The title with the bracketed tag moved to the front.
    """
    match = re.search(r"\[.*?]", title)
    if match:
        tag = match.group(0)
        remainder = title.replace(tag, "").strip()
    else:
        # Handle malformed title with unclosed bracket like "Title [JP"
        parts = title.split("[", 1)
        if len(parts) == 2:
            tag = f"[{parts[1].rstrip(']')}]"
            remainder = parts[0].strip()
        else:
            return title  # Nothing to do

    return f"{tag} {remainder}".strip()


def _reformat_detected_languages_in_title(title: str) -> str | None:
    """
    Attempts to reformat a poorly structured title into a
    standardized format with language tags.

    Example:
        Input:  "English to Chinese Lorem Ipsum"
        Output: "[English > Chinese] Lorem Ipsum"

    :param title: A potentially unstructured title containing language names.
    :return: A reformatted title like "[Lang1 > Lang2] Remainder", or None if reformatting fails.
    """
    title_words = re.findall(r"\w+", title)
    if not title_words:
        return None

    # Track detected languages at the beginning and end of the title
    detected_languages = {}
    first_lang = last_lang = None

    # Scan first ~5 words for languages
    for word in title_words[:5]:
        if word.lower() == "to":
            continue
        match = extract_lingvos_from_text(word.title())
        if match:
            detected_languages[word] = match[0].name
            if not first_lang:
                first_lang = match[0].name

    # Scan last ~5 words (reversed) for target language
    for word in reversed(title_words[-5:]):
        match = extract_lingvos_from_text(word.title(), True)
        if match:
            last_lang = match[0].name
            break

    if not first_lang or not last_lang:
        return None

    # Build the new tag
    lang_tag = f"[{first_lang} > {last_lang}]"

    # Replace the first language with the tag
    reformatted = title
    for original_word, lang_code in detected_languages.items():
        if lang_code == first_lang:
            reformatted = reformatted.replace(original_word, lang_tag, 1)
            break

    # Remove the second language word to avoid duplication
    for original_word, lang_code in detected_languages.items():
        if lang_code == last_lang and lang_code != first_lang:
            reformatted = reformatted.replace(original_word, "", 1)
            break

    # Clean up "to" or "into" if still in the text
    reformatted = re.sub(r"\b(to|into)\b", ">", reformatted, flags=re.IGNORECASE)
    reformatted = re.sub(r"\s{2,}", " ", reformatted).strip()

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
                f"[L] Main_Posts_Filter: > Filtered a post with an incorrect title format. Rule: #{filter_reason}"
            )
            return False, None, filter_reason

    # Rule 1A and 1B: "to LANGUAGE" phrasing issues
    if ">" not in title_lower and any(phrase in title_lower for phrase in to_phrases):
        if not any(phrase in title_lower[:25] for phrase in to_phrases):
            filter_reason = "1A"
            logger.info(
                f"[L] Main_Posts_Filter: > Filtered a post with an incorrect title format. Rule: #{filter_reason}"
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
                    f"[L] Main_Posts_Filter: > Filtered a post with no valid language. Rule: #{filter_reason}"
                )
                return False, None, filter_reason

    # Rule 2: '>' is present but poorly positioned
    if ">" in title and "]" not in title and ">" not in title[:50]:
        filter_reason = "2"
        logger.info(
            f"[L] Main_Posts_Filter: > Filtered a post due to incorrect placement of '>'. Rule: #{filter_reason}"
        )
        return False, None, filter_reason

    # Passed all filters
    return True, title, None


"""ASSESSING (SECOND ROUND)"""


def _preprocess_title(post_title):
    """
    Normalize a Reddit post title by fixing brackets, typos, symbols,
    misused language tags, and removing cross-post markers.
    """
    title = re.sub(r"\(x-post.*", "", post_title).strip()

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

    # Attempt recovery with language reformatter.
    if not any(b in title for b in ["[", "]"]):
        reformatted = _reformat_detected_languages_in_title(title)
        if reformatted:
            title = reformatted

    # Normalize bracketed language tags and country suffixes
    title = re.sub(r"(]\s*[>\\-]\s*\[)", " > ", title)
    if "{" in title and "}" in title and "[" in title:
        match = re.search(r"{(\D+)}", title)
        if match:
            country = match.group(1)
            code = country_converter(country)[0]
            if code:
                title = title.split("{", 1)[0].strip() + title.split("}", 1)[1]
    elif "{" in title and "[" not in title:
        title = title.replace("{", "[").replace("}", "]")

    # Handle special cases and cleanup
    if "-" in title[:20] and any(
        k in title.title() for k in title_settings["ENGLISH_DASHES"]
    ):
        title = title.replace("-", " > ")
    if "[" in title and "[" not in title[:10]:
        title = _move_bracketed_tag_to_front(title.strip())
    title = title.replace("English.", "English] ").replace("_", " ")

    # Fix improperly hyphenated words
    hyphen_match = re.search(r"((?:\w+-)+\w+)", title[:25])
    if hyphen_match:
        converted = converter(hyphen_match.group(0))
        if converted is not None and not converted.name:
            title = title.replace("-", " ")

    # Clean up symbols and duplicate markers
    for ch in ["&", "+", "/", "\\", "|"]:
        title = title.replace(ch, f" {ch} ")
    for compound in [">>>", ">>", "> >"]:
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

    # Fix frequent false matches for "KR"
    if "KR " in title.upper()[:10]:
        title = title.replace("KR ", "Korean ")

    # Handle unknown or unclear entries
    if "[Unknown]" in title.title() or title.lstrip().startswith("?"):
        return Titolo()  # Return empty object

    return title


def _is_punctuation_only(s):
    # Strip whitespace first
    s = s.strip()
    # Check if s is empty or all chars are punctuation
    return len(s) > 0 and all(c in string.punctuation for c in s)


def _clean_text(text, preserve_commas=False):
    """Insert spaces around brackets/parentheses and remove other punctuation with extra spaces."""
    # Insert spaces around brackets and parentheses
    text = re.sub(r"([\[\]()])", r" \1 ", text)

    # Remove other punctuation (excluding brackets/parentheses)
    if preserve_commas:
        text = re.sub(
            r"[.;@#?!&$" "'\"•/]+ *", " ", text
        )  # Remove comma from the pattern
    else:
        text = re.sub(r"[,.;@#?!&$" "'\"•/]+ *", " ", text)

    # Collapse multiple spaces into one
    text = re.sub(r"\s+", " ", text)

    return text.strip()


def _extract_source_chunk(title):
    """Extract the source language chunk from a processed title."""
    for sep in [">", " to ", "-", "<"]:
        if sep in title:
            return _clean_text(title.split(sep)[0])
    return _clean_text(title)


def _extract_target_chunk(title):
    """Extract the target language chunk from a processed title."""
    for sep in [">", " to ", "-", "<"]:
        if sep in title:
            chunk = title.split(sep, 1)[1]
            # Stop at the closing bracket
            if "]" in chunk:
                chunk = chunk.split("]", 1)[0]
            return _clean_text(chunk, True)
    return ""


def _clean_chunk(chunk: str) -> str:
    # Strip brackets and spaces
    chunk = chunk.strip()
    chunk = chunk.lstrip("[").rstrip("]")
    chunk = chunk.strip()
    # Remove trailing punctuation like '-' or ':' or spaces again
    import re

    chunk = re.sub(r"\W+$", "", chunk.lower())
    return chunk


def _resolve_languages(chunk, is_source):
    # Remove trailing punctuation like '-' or ':'
    cleaned = _clean_chunk(chunk)
    logger.debug(f"Cleaned Chunk: {cleaned}")

    if cleaned in {"unknown", "unk", "???", "n/a"}:
        logger.debug("Handling 'unknown' chunk explicitly.")
        return [converter("unknown")]

    # Cut off after ']' if present
    if "]" in chunk:
        chunk = chunk.split("]", 1)[0]

    # Split on commas first to handle multiple languages
    if "," in chunk:
        language_parts = [part.strip() for part in chunk.split(",")]
        resolved = []
        for part in language_parts:
            result = _resolve_languages(part, is_source)  # Recursive call
            if result:
                resolved.extend(result)

        # Deduplicate
        unique = {}
        for lang in resolved:
            key = lang.name if hasattr(lang, "name") else lang.language_code_3
            unique[key] = lang

        return list(unique.values())

    words = chunk.split()
    words = [w for w in words if not _is_punctuation_only(w)]

    if 2 <= len(words) <= 3:
        joined = " ".join(words)
        words.insert(0, joined)

    logger.debug(f"Words before cleanup: {words}")
    cleaned_words = [
        w
        for w in words
        if not (
            (len(w) == 2 and w.title() in title_settings["ENGLISH_2_WORDS"])
            or (len(w) == 3 and w.title() in title_settings["ENGLISH_3_WORDS"])
        )
    ]

    logger.debug(f"Cleaned words: {cleaned_words}")
    resolved = []
    for word in cleaned_words[:5]:
        if "Eng" in word and len(word) <= 8:
            word = "English"
        converter_result = converter(word)

        # Log differently for multi-word phrases
        if " " in word:
            logger.debug(f"Converted full phrase: {word} -> {converter_result}")
        else:
            logger.debug(f"Converted {word} -> {converter_result}")

        if converter_result:
            resolved.append(converter_result)
            # If this was a successful multi-word phrase, stop processing individual words
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
    """

    def resolve_flair_code(lang_obj):
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
                titolo_object.add_final_text(lang.name)
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
                titolo_object.add_final_text(lang.name)
                return
            else:
                return  # No valid languages at all

        else:
            return  # No valid target languages

    else:
        return  # Unsupported or ambiguous direction

    flair_code = resolve_flair_code(lang)
    titolo_object.add_final_code(flair_code)
    titolo_object.add_final_text(lang.name)


def process_title(title, post=None):
    """
    Main function to process a Reddit post title, extract language info,
    assign flair metadata, detect direction and output a structured Titolo object.

    Args:
        title (str): The post title from r/translator.
        post (PRAW): A PRAW object. Unused unless we ask AI.

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
        logger.error("Could not make sense of this title at all. Asking AI...")
        ai_result = title_ai_parser(title, post)
        if isinstance(ai_result, dict):
            _update_titolo_from_ai_result(result, ai_result)

    # Update the Titolo with the best selection for flair.
    _determine_flair(result)

    return result


"""AI PROCESSING"""


def _update_titolo_from_ai_result(result, ai_result):
    """
    Update a Titolo object based on AI parser output.

    Args:
        result (Titolo): The object to be updated.
        ai_result (dict): The AI's parsed result with language codes and names.
    """
    try:
        src = ai_result.get("source_language")
        tgt = ai_result.get("target_language")

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
    except Exception as e:
        logger.error(f"Failed to update Titolo from AI result: {e}")


def title_ai_parser(title, post=None):
    """
    Passes a malformed title to an AI to assess, and returns the non-English language
    (code and name) if confidence is sufficient.

    :param title: Title of a Reddit post.
    :param post: A PRAW submission object, or `None`
    :return: A dictionary (see the responses file for its format)
    """
    image_url = None

    if post:
        # Check if post has an image (gallery or direct image)
        if hasattr(post, "post_hint") and post.post_hint == "image":
            image_url = post.url
        elif hasattr(post, "is_gallery") and post.is_gallery:
            # Get first image from gallery
            media_metadata = getattr(post, "media_metadata", {})
            if media_metadata:
                first_item = next(iter(media_metadata.values()))
                if "s" in first_item and "u" in first_item["s"]:
                    image_url = first_item["s"]["u"].replace("&amp;", "&")

    # Prepare the query input (text only)
    query_input = RESPONSE.TITLE_PARSING_QUERY + title

    # Construct query kwargs
    logger.info("Passing information to AI service...")
    query_kwargs = {
        "service": "openai",
        "behavior": "You are assessing a technical identification",
        "query": query_input,
        "client_object": openai_access(),
    }

    # Add image URL only if it's available
    if image_url:
        query_kwargs["image_url"] = image_url

    # Send to AI
    query_data = ai_query(**query_kwargs)

    # Parse AI response
    query_dict = json.loads(query_data)

    confidence = query_dict.get("confidence", 0.0)
    if confidence < 0.7:
        logger.warning("AI confidence value too low for title.")
        return "error", "Confidence value too low"

    logger.info("AI service returned data.")
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
    print("x. Exit")


if __name__ == "__main__":
    while True:
        _show_menu()
        choice = input("Enter your choice (1-3): ")

        if choice == "x":
            print("Exiting...")
            break

        if choice not in ["1", "2", "3"]:
            print("Invalid choice, please try again.")
            continue

        if choice == "1":
            logger.setLevel(logging.DEBUG)
            my_test = input("Enter the string you wish to test: ")
            titolo_output = process_title(my_test)
            pprint(vars(titolo_output))
        elif choice == "2":
            logger.setLevel(logging.INFO)
            submissions = list(
                REDDIT_HELPER.subreddit(SETTINGS["subreddit"]).new(limit=50)
            )
            for submission in submissions:
                print(submission.title)
                titolo_output = process_title(submission.title)
                pprint(vars(titolo_output))
                print("\n\n")
        elif choice == "3":
            my_test = input("Enter the string you wish to test: ")
            print(title_ai_parser(my_test))
