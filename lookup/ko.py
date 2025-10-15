#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
Contains functions that deal with Korean-language content.
"""
import asyncio

import krdict
from korean_romanizer.romanizer import Romanizer

from connection import credentials_source

# Set the API key to use.
krdict.set_key(credentials_source['KRDICT_API_KEY'])


def translate_part_of_speech(korean_pos):
    mapping = {
        '명사': 'noun',
        '동사': 'verb',
        '형용사': 'adjective',
        '부사': 'adverb',
        '대명사': 'pronoun',
        '전치사': 'preposition',
        '접속사': 'conjunction',
        '감탄사': 'interjection',
        '조사': 'particle',
        '수사': 'numeral',
        '관형사': 'determiner',
        '의존 명사': 'dependent noun',
    }
    return mapping.get(korean_pos, korean_pos)


'''WORD LOOKUP'''


async def ko_search_raw_async(target_word):
    """
    Async wrapper for ko_search_raw that runs the blocking call in a thread pool.

    :param target_word: Word in Korean we're looking for.
    :return:
    """
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, ko_search_raw, target_word)


def ko_search_raw(target_word):
    """
    This function returns a list containing machine-readable
    dictionaries of data from the Korean look-up.

    :param target_word: Word in Korean we're looking for.
    :return:
    """
    filtered_data = []
    korean_input = krdict.search(query=target_word.strip(),
                                 search_type=krdict.SearchType.WORD,
                                 translation_language=krdict.TranslationLanguage.ENGLISH,
                                 raise_api_errors=True)

    for entry in korean_input.data.results:
        if entry.word == target_word:
            simplified_entry = {
                "word": entry.word,
                "origin": entry.origin,
                "part_of_speech": entry.part_of_speech,
                "definitions": []
            }
            for definition in entry.definitions:
                simplified_definition = {
                    "definition": definition.definition,
                    "translations": [
                        {
                            "word": t.word,
                            "definition": t.definition,
                            "language": t.language
                        }
                        for t in definition.translations
                    ]
                }
                simplified_entry["definitions"].append(simplified_definition)

            filtered_data.append(simplified_entry)

    return filtered_data


def ko_word(korean_word):
    """
    This function passes on a search for a Korean word, and then
    if there is a result, formats in Markdown.

    :param korean_word: A word in Korean.
    :return: A Markdown formatted string, or None.
    """
    entries = []
    korean_word = korean_word.strip()
    data = ko_search_raw(korean_word)
    hangul_romanization = Romanizer(korean_word).romanize()

    # No valid results.
    if not data:
        return None

    lookup_header = f'# [{korean_word}](https://en.wiktionary.org/wiki/{korean_word}#Korean)'

    for entry in data:
        definitions = []
        for x in entry['definitions']:
            for t in x.get('translations', []):
                if t.get('language') == '영어':
                    definitions.append(t.get('definition'))
        definitions = '\n* '.join(definitions)

        entry_text = (
                f"\n\n##### *{translate_part_of_speech(entry['part_of_speech']).title()}*\n\n"
                + (
                    f"**Origin:** [{entry['origin']}](https://en.wiktionary.org/wiki/{entry['origin']})\n\n" if entry.get(
                        'origin') else "")
                + f"**Romanization:** *{hangul_romanization}*\n\n"
                + f"**Meanings**:\n* {definitions}"
        )
        entries.append(entry_text)

    footer = (
        f"\n\n^Information ^from [^KRDict](https://krdict.korean.go.kr/eng/dicMarinerSearch/search?nation=eng&nationCode=6&ParaWordNo=&mainSearchWord={korean_word}&lang=eng) ^| "
        f"[^Naver](https://korean.dict.naver.com/koendict/#/search?query={korean_word}) ^| "
        f"[^Collins](https://www.collinsdictionary.com/dictionary/korean-english/{korean_word})"
    )

    final_comment = lookup_header + '\n'.join(entries) + footer

    return final_comment


if __name__ == "__main__":
    while True:
        my_input = input("Enter a Korean word to search for: ")
        print(ko_word(my_input))
