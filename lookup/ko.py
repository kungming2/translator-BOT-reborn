#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
Contains functions that deal with Korean-language content.
"""

import krdict
from korean_romanizer.romanizer import Romanizer

from connection import credentials_source, logger
from lookup.cache_helpers import parse_ko_output_to_json, save_to_cache

# Set the API key to use.
krdict.set_key(credentials_source["KRDICT_API_KEY"])


def _translate_part_of_speech(korean_pos: str) -> str:
    mapping: dict[str, str] = {
        "명사": "noun",
        "동사": "verb",
        "형용사": "adjective",
        "부사": "adverb",
        "대명사": "pronoun",
        "전치사": "preposition",
        "접속사": "conjunction",
        "감탄사": "interjection",
        "조사": "particle",
        "수사": "numeral",
        "관형사": "determiner",
        "의존 명사": "dependent noun",
    }
    return mapping.get(korean_pos, korean_pos)


"""WORD LOOKUP"""


def _ko_search_raw(target_word: str) -> list[dict]:
    """
    This function returns a list containing machine-readable
    dictionaries of data from the Korean look-up.

    :param target_word: Word in Korean we're looking for.
    :return: List of simplified entry dictionaries.
    """
    filtered_data: list[dict] = []
    try:
        korean_input = krdict.search(
            query=target_word.strip(),
            search_type=krdict.SearchType.WORD,
            translation_language=krdict.TranslationLanguage.ENGLISH,
            raise_api_errors=True,
        )
    except (krdict.types.exceptions.KRDictException, Exception) as e:
        # Catch 404s and other API errors - just return empty list
        logger.warning(f"Korean lookup failed for '{target_word}': {e}")
        return []

    for entry in korean_input.data.results:
        if entry.word == target_word:
            simplified_entry: dict = {
                "word": entry.word,
                "origin": entry.origin,
                "part_of_speech": entry.part_of_speech,
                "definitions": [],
            }
            for definition in entry.definitions:
                simplified_definition: dict = {
                    "definition": definition.definition,
                    "translations": [
                        {
                            "word": t.word,
                            "definition": t.definition,
                            "language": t.language,
                        }
                        for t in definition.translations
                    ],
                }
                simplified_entry["definitions"].append(simplified_definition)

            filtered_data.append(simplified_entry)

    return filtered_data


def ko_word(korean_word: str) -> str | None:
    """
    This function passes on a search for a Korean word, and then
    if there is a result, formats in Markdown.

    :param korean_word: A word in Korean.
    :return: A Markdown formatted string, or None.
    """
    korean_word = korean_word.strip()
    data: list[dict] = _ko_search_raw(korean_word)
    hangul_romanization: str = Romanizer(korean_word).romanize()

    # No valid results.
    if not data:
        return None

    lookup_header: str = (
        f"# [{korean_word}](https://en.wiktionary.org/wiki/{korean_word}#Korean)"
    )

    # Group entries by part of speech
    pos_groups: dict[str, list[dict]] = {}
    for entry in data:
        pos: str = _translate_part_of_speech(entry["part_of_speech"]).title()
        if pos not in pos_groups:
            pos_groups[pos] = []
        pos_groups[pos].append(entry)

    # Build output for each POS group
    entries: list[str] = []
    for pos, group in pos_groups.items():
        pos_section: str = f"\n\n##### *{pos}*\n\n"

        definitions_list: list[str] = []
        for entry in group:
            for x in entry["definitions"]:
                for t in x.get("translations", []):
                    if t.get("language") == "영어":
                        definition_text: str = t.get("definition")
                        origin: str | None = entry.get("origin")
                        if origin:
                            definition_text = f"[{origin}](https://en.wiktionary.org/wiki/{origin}): {definition_text}"
                        definitions_list.append(definition_text)

        definitions: str = "\n* ".join(definitions_list)
        pos_section += f"**Romanization:** *{hangul_romanization}*\n\n**Meanings**:\n* {definitions}"
        entries.append(pos_section)

    footer: str = (
        "\n\n^Information ^from "
        f"^[KRDict](https://krdict.korean.go.kr/eng/dicMarinerSearch/search"
        f"?nation=eng&nationCode=6&ParaWordNo=&mainSearchWord={korean_word}&lang=eng) ^| "
        f"^[Naver](https://korean.dict.naver.com/koendict/#/search?query={korean_word}) ^| "
        f"^[Collins](https://www.collinsdictionary.com/dictionary/korean-english/{korean_word})"
    )

    final_comment: str = lookup_header + "".join(entries) + footer

    # Cache the result before returning
    try:
        parsed_data = parse_ko_output_to_json(final_comment)
        save_to_cache(parsed_data, "ko", "ko_word")
    except Exception as ex:
        # Silently fail if caching doesn't work
        logger.error(f"Encountered issue: {ex}")
        pass

    return final_comment


if __name__ == "__main__":
    while True:
        my_input = input("Enter a Korean word to search for: ")
        print(ko_word(my_input))
