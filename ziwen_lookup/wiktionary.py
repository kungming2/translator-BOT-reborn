#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
Unused Wiktionary parser (not feature-complete).
...

Logger tag: [L:WT]
"""

import pprint
import re

import requests

from lang.languages import converter
from reddit.connection import get_random_useragent

# ─── Wiktionary parser ────────────────────────────────────────────────────────


def parse_wiktionary(text: str, search_language: str | None = None) -> dict | None:
    """
    Parse Wiktionary MediaWiki content and extract key information.

    Args:
        text: String containing Wiktionary MediaWiki syntax
        search_language: Optional language name (e.g., 'English', 'Malay').
                        If None, defaults to 'English'.

    Returns:
        Dictionary with keys: word, etymology, pronunciation, definition
        Returns None if the specified language is not found.
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
    current_section = None
    etymology_lines = []
    pronunciation_lines = []
    definition_lines = []
    in_definition = False

    for _i, line in enumerate(lines):
        line_stripped = line.strip()

        if line_stripped.startswith("==") and line_stripped.endswith("=="):
            level = len(line_stripped) - len(line_stripped.lstrip("="))

            if level == 2:  # Top-level language section
                lang_name = line_stripped.strip("= ").strip()

                if lang_name.lower() == search_language.lower():
                    in_target_language = True
                elif in_target_language:
                    break
                else:
                    in_target_language = False

            elif level == 3 and in_target_language:  # === Section ===
                current_section = line_stripped.strip("= ").lower()
                in_definition = False

            elif level == 4 and in_target_language:  # ==== Subsection ====
                if in_definition:
                    in_definition = False

        elif in_target_language:
            if line_stripped.startswith("====") and line_stripped.endswith("===="):
                in_definition = False

            if current_section == "etymology" or (
                current_section and current_section.startswith("etymology")
            ):
                if line_stripped and not line_stripped.startswith("==="):
                    etymology_lines.append(line_stripped)

            elif current_section == "pronunciation":
                if line_stripped and not line_stripped.startswith("==="):
                    pronunciation_lines.append(line_stripped)

            elif current_section in [
                "noun",
                "verb",
                "adjective",
                "adverb",
                "pronoun",
                "preposition",
                "conjunction",
                "interjection",
                "article",
                "romanization",
            ]:
                if (
                    not in_definition
                    and line_stripped
                    and not line_stripped.startswith("====")
                ):
                    if (
                        "(" in line_stripped
                        and ")" in line_stripped
                        or re.match(
                            r"^[a-zA-Z]+$",
                            line_stripped.split()[0] if line_stripped.split() else "",
                        )
                    ):
                        word_match = re.match(r"^(\S+)", line_stripped)
                        if word_match and not result["word"]:
                            result["word"] = word_match.group(1)
                        in_definition = True
                elif (
                    in_definition
                    and line_stripped
                    and not line_stripped.startswith("====")
                ):
                    if line_stripped.startswith(
                        (
                            "Synonym",
                            "Antonym",
                            "Descendant",
                            "See also",
                            "Derived term",
                            "Related term",
                            "Alternative form",
                            "Coordinate term",
                        )
                    ):
                        in_definition = False
                    else:
                        definition_lines.append(line_stripped)

    if not in_target_language:
        return None

    if not result["word"]:
        for line in lines:
            match = re.match(r"^([a-zA-Z]+)\s*\(", line.strip())
            if match:
                result["word"] = match.group(1)
                break

    if etymology_lines:
        result["etymology"] = etymology_lines

    if pronunciation_lines:
        result["pronunciation"] = pronunciation_lines

    if definition_lines:
        result["definition"] = definition_lines

    return result


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
        print(f"{language_name.title()} does not appear to be a valid language.")
        raise ValueError
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
    print(extract.strip())
    parsed_information = parse_wiktionary(extract.strip(), language_name)

    return parsed_information


if __name__ == "__main__":
    while True:
        test_input = input("Enter a word to look up in Wiktionary: ")
        test_language = input("Enter a language to look up the previous word for: ")
        pprint.pp(wiktionary_search(test_input, test_language))
