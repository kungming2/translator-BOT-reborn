#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
Wiktionary parser for non-CJK lookup.
...

Logger tag: [L:WT]
"""

import pprint
import re

import requests

from config import SETTINGS
from lang.languages import converter
from reddit.connection import get_random_useragent

# ─── Wiktionary parser ────────────────────────────────────────────────────────

# Section names that contain definitions (level-3 or level-4 headers).
_DEFINITION_SECTIONS = frozenset(
    [
        "adjective",
        "adverb",
        "article",
        "classifier",
        "conjunction",
        "determiner",
        "idiom",
        "interjection",
        "noun",
        "numeral",
        "participle",
        "particle",
        "preposition",
        "pronoun",
        "romanization",
        "verb",
    ]
)

# Section names at level 5+ that should suppress definition collection entirely
# until the next level ≤ 4 header.  These are sub-subsections inside a POS
# block that contain only metadata, not definitions.
_SKIP_SUBSECTIONS = frozenset(
    [
        "descendants",
        "derived terms",
        "related terms",
        "alternative forms",
        "synonyms",
        "antonyms",
        "see also",
        "further reading",
        "references",
        "declension",
        "conjugation",
        "inflection",
        "usage notes",
        "coordinate terms",
        "hypernyms",
        "hyponyms",
        "holonyms",
        "meronyms",
        "troponyms",
        "translations",
        "anagrams",
        "quotations",
    ]
)

# Lines that signal the end of the actual definitions inside a POS block
# (appear as plain-text subheadings within the extract, not as == headers).
_DEFINITION_STOPWORDS = (
    "Synonym",
    "Antonym",
    "Descendant",
    "See also",
    "Derived term",
    "Related term",
    "Alternative form",
    "Coordinate term",
    "Hypernym",
    "Hyponym",
    "Holonym",
    "Meronym",
    "Usage note",
    "Further reading",
    "Reference",
    "Declension",
    "Conjugation",
    "Inflection",
    "Semi-learned",
    "Learned borrowing",
)

# Boilerplate redirect line that appears on inflected/lemma-form entries.
_LEMMA_REDIRECT_RE = re.compile(r"^See the etymology of the corresponding lemma form\.")

# Lines that look like dated quotation attributions, e.g. "1925, Author Name, …"
_DATED_QUOTE_RE = re.compile(r"^\d{4},\s")

# Lines that look like: "Author Name (year), Title, …" — bibliographic references.
_BIBLIO_RE = re.compile(r"^[A-ZÄÖÜ][a-zäöü]+,\s+[A-Z][a-z]+\s+\(\d{4}\)")

# Lines that should never appear in etymology output.
_IPA_RE = re.compile(r"^IPA\(key\)")
_HEADWORD_LINE_RE = re.compile(
    r"^[\w\u0080-\uFFFF•]+\s*[•·]?\s*\(.*?\)\s*(m|f|n|mf|c)\b"
)


def _section_level(line: str) -> int | None:
    """Return the == level of a section header line, or None if not a header."""
    s = line.strip()
    if s.startswith("==") and s.endswith("==") and len(s) >= 5:
        level = 0
        for ch in s:
            if ch == "=":
                level += 1
            else:
                break
        # Verify the right side matches (e.g. not ===Foo==).
        right = 0
        for ch in reversed(s):
            if ch == "=":
                right += 1
            else:
                break
        if level == right:
            return level
    return None


def _section_name(line: str) -> str:
    """Strip = signs and whitespace from a header line."""
    return line.strip().strip("=").strip().lower()


def _is_clean_etymology_line(line: str) -> bool:
    """
    Return True if a line is genuine etymology prose — i.e. not an IPA
    transcription, not a headword line, not a boilerplate redirect, and not empty.
    """
    if not line:
        return False
    if _IPA_RE.match(line):
        return False
    if _LEMMA_REDIRECT_RE.match(line):
        return False
    # Headword lines look like:  كِتَاب • (kitāb) m (plural …)
    # or:  Buch n (strong, genitive …)
    # They start with the word, optional bullet, then a parenthesised grammar note.
    return not re.match(
        r"^.+\(.*(plural|genitive|feminine|masculine|neuter|strong|weak)", line
    )


def _is_clean_definition_line(line: str) -> bool:
    """
    Return True if a line is a genuine definition or usage example rather than
    metadata that leaked past the section-header guards.
    """
    # Dated quotation attributions: "1840, Author, Title …"
    if _DATED_QUOTE_RE.match(line):
        return False
    # Bibliographic references in definitions (rare but seen in German, Latin).
    if _BIBLIO_RE.match(line):
        return False
    # Boilerplate lemma redirect.
    if _LEMMA_REDIRECT_RE.match(line):
        return False
    # Descendant / borrowed-form lines like "→ Ottoman Turkish: …" or "> Turkish: …"
    if re.match(r"^[→>]\s", line):
        return False
    # Language-name cross-reference lines like "Gulf Arabic: …", "Maltese: …"
    # These start with a capitalized language name followed by a colon.
    return not re.match(r"^[A-Z][a-zA-Z\s]+:\s", line)


def parse_wiktionary(text: str, search_language: str | None = None) -> dict | None:
    """
    Parse Wiktionary MediaWiki content and extract key information.

    Args:
        text: String containing Wiktionary MediaWiki syntax (plain-text
              ``explaintext`` format returned by the MediaWiki API).
        search_language: Optional language name (e.g., 'English', 'Malay').
                        If None, defaults to 'English'.

    Returns:
        Dictionary with keys: word, etymology, pronunciation, definition.
        Returns None if the specified language section is not found.
    """
    if search_language is None:
        search_language = "English"

    result: dict[str, str | list[str] | None] = {
        "word": None,
        "etymology": None,
        "pronunciation": None,
        "definition": None,
    }

    lines = text.strip().split("\n")

    in_target_language = False
    # current_section tracks the *effective* section regardless of header level.
    current_section: str | None = None
    in_etymology_block = False  # True while inside any === Etymology … === block
    in_definition = False  # True after we've seen the headword line in a POS block
    in_skip_block = False  # True inside a level-5+ subsection (descendants, etc.)

    etymology_lines: list[str] = []
    pronunciation_lines: list[str] = []
    definition_lines: list[str] = []

    for line in lines:
        line_stripped = line.strip()
        level = _section_level(line_stripped)

        if level is not None:
            # ── Header line ──────────────────────────────────────────────────
            name = _section_name(line_stripped)

            if level == 2:
                # Top-level language block.
                if name.lower() == search_language.lower():
                    in_target_language = True
                elif in_target_language:
                    # Entered a new language — we're done.
                    break
                else:
                    in_target_language = False
                current_section = None
                in_etymology_block = False
                in_definition = False
                in_skip_block = False

            elif level == 3 and in_target_language:
                in_definition = False
                in_skip_block = False
                if name.startswith("etymology"):
                    in_etymology_block = True
                    current_section = "etymology"
                else:
                    in_etymology_block = False
                    current_section = name

            elif level == 4 and in_target_language:
                # Level-4 subsections override current_section within an
                # Etymology block (e.g. ==== Pronunciation ====, ==== Noun ====).
                in_definition = False
                in_skip_block = False
                if name == "pronunciation":
                    current_section = "pronunciation"
                elif name in _DEFINITION_SECTIONS:
                    current_section = name
                elif name.startswith("etymology"):
                    current_section = "etymology"
                else:
                    # Descendants, Declension, Further reading, etc. — stop
                    # collecting definitions but don't reset to etymology.
                    current_section = name

            elif level >= 5 and in_target_language:
                # ===== Derived terms =====, ===== Descendants ===== etc.
                # Suppress content collection until the next level ≤ 4 header.
                in_definition = False
                in_skip_block = name in _SKIP_SUBSECTIONS

            continue  # Header lines are never collected as content.

        if not in_target_language:
            continue
        if not line_stripped:
            continue
        if in_skip_block:
            continue

        # ── Content line ──────────────────────────────────────────────────────

        if current_section == "etymology" and in_etymology_block:
            if _is_clean_etymology_line(line_stripped):
                etymology_lines.append(line_stripped)

        elif current_section == "pronunciation":
            # Keep only actual IPA lines, not headword lines or blank noise.
            if (
                "IPA" in line_stripped
                or "Rhymes" in line_stripped
                or "Homophone" in line_stripped
            ):
                pronunciation_lines.append(line_stripped)

        elif current_section in _DEFINITION_SECTIONS:
            if not in_definition:
                # Look for the headword line: it contains "•" or has
                # parenthesised grammar info and is not an IPA line.
                if _IPA_RE.match(line_stripped):
                    continue
                is_headword = (
                    "•" in line_stripped
                    or re.search(
                        r"\([^)]*(?:plural|genitive|feminine|masculine|neuter)\b",
                        line_stripped,
                    )
                    or (
                        "(" in line_stripped
                        and ")" in line_stripped
                        and re.match(r"^[\w\u0080-\uFFFF]+", line_stripped)
                        and not line_stripped.startswith("(")
                    )
                )
                if is_headword:
                    # Extract the word: everything before " •" or " (" or end.
                    word_match = re.match(r"^([\w\u0080-\uFFFF]+)", line_stripped)
                    if word_match and not result["word"]:
                        result["word"] = word_match.group(1)
                    in_definition = True
            else:
                # We're past the headword — collect definitions until a stop word.
                if line_stripped.startswith(_DEFINITION_STOPWORDS):
                    in_definition = False
                elif line_stripped.startswith(("=", "{")):
                    # Template lines or stray headers — skip.
                    pass
                elif _is_clean_definition_line(line_stripped):
                    definition_lines.append(line_stripped)

    if not in_target_language:
        return None

    # ── Fallback word extraction ───────────────────────────────────────────────
    if not result["word"]:
        for line in lines:
            # Match a plain Latin-script word before a parenthesis, excluding IPA.
            match = re.match(r"^([a-zA-ZÀ-ÖØ-öø-ÿ]+)\s*\(", line.strip())
            if match and not line.strip().startswith("IPA"):
                result["word"] = match.group(1)
                break

    if etymology_lines:
        result["etymology"] = etymology_lines
    if pronunciation_lines:
        result["pronunciation"] = pronunciation_lines
    if definition_lines:
        result["definition"] = definition_lines

    return result


def format_wiktionary_markdown(
    data: dict,
    search_term: str,
    language_name: str,
) -> str:
    """
    Format a ``parse_wiktionary`` result dict as a human-readable Markdown string.

    Args:
        data: The dict returned by ``wiktionary_search`` / ``parse_wiktionary``.
        search_term: The original search term, used as the header text if no
                     ``word`` key is present in *data*.
        language_name: The language name or string.

    Returns:
        A Markdown string with the following structure (each section is omitted
        if no data is available):

            # word (link to Wiktionary entry)
            **Pronunciation:** …
            **Etymology:** …
            **Definitions:**
            - …
            - …
    """
    parts: list[str] = []

    # ── Header ────────────────────────────────────────────────────────────────
    word = data.get("word") or search_term
    lingvo_obj = converter(language_name)
    if lingvo_obj is None or lingvo_obj.name is None:
        raise ValueError("Language name or object is not valid.")

    anchor = lingvo_obj.name.replace(" ", "_")
    url = f"https://en.wiktionary.org/wiki/{word}#{anchor.title()}"
    parts.append(f"# [{word}]({url})")

    # ── Pronunciation ─────────────────────────────────────────────────────────
    pronunciation = data.get("pronunciation")
    if pronunciation:
        if isinstance(pronunciation, list):
            # Join multiple IPA/Rhymes lines with a separator for compactness.
            pron_text = " · ".join(pronunciation)
        else:
            pron_text = pronunciation
        parts.append(f"**Pronunciation:** {pron_text}")

    # ── Etymology ─────────────────────────────────────────────────────────────
    etymology = data.get("etymology")
    if etymology:
        if isinstance(etymology, list):
            if len(etymology) == 1:
                parts.append(f"**Etymology:** {etymology[0]}")
            else:
                etym_lines = ["**Etymology:**"]
                etym_lines.extend(f"- {line}" for line in etymology)
                parts.append("\n".join(etym_lines))
        else:
            parts.append(f"**Etymology:** {etymology}")

    # ── Definitions ───────────────────────────────────────────────────────────
    max_definition_lines = SETTINGS["max_num_definition_lines"]
    definition = data.get("definition")
    if not definition:
        raise ValueError("No definition listed for term.")
    else:
        if isinstance(definition, list):
            def_lines = ["**Definitions:**", ""]
            def_lines.extend(f"* {line}" for line in definition)
            parts.append(
                "\n".join(def_lines[:max_definition_lines])
            )  # Trim excessively long definition sections
        else:
            parts.append(f"**Definitions:**\n\n{definition}")

    return "\n\n".join(parts)


def wiktionary_search(search_term: str, language_name: str) -> dict | None:
    """
    Look up a word in Wiktionary using the MediaWiki API.
    Works for all non-CJK languages.

    :param search_term: The word to look up.
    :param language_name: The language name for the lookup for the term.
    :return: A dict containing the page title and extract, or None if not found.
    """
    _lingvo = converter(language_name)
    if not _lingvo:
        raise ValueError(
            f"{language_name.title()} does not appear to be a valid language."
        )
    else:
        language_name = _lingvo.name or language_name

    api_url = "https://en.wiktionary.org/w/api.php"

    params: dict[str, str | int] = {
        "action": "query",
        "format": "json",
        "prop": "extracts",
        "explaintext": 1,
        "titles": search_term,
    }

    response = requests.get(api_url, headers=get_random_useragent(), params=params)
    response.raise_for_status()

    data = response.json()
    pages = data.get("query", {}).get("pages", {})
    if not pages:
        return None

    page = next(iter(pages.values()))
    extract = page.get("extract", "")

    if not extract:
        return None

    parsed_information = parse_wiktionary(extract.strip(), language_name)

    return parsed_information


if __name__ == "__main__":
    while True:
        test_input = input("Enter a word to look up in Wiktionary: ")
        test_language = input("Enter a language to look up the previous word in: ")
        test_result = wiktionary_search(test_input, test_language)
        pprint.pp(test_result)
        if test_result:
            print("\n--- Markdown output ---")
            print(format_wiktionary_markdown(test_result, test_input, test_language))
