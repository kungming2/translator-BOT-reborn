#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
Contains functions that deal with Japanese-language content.
"""

import asyncio
import re
from time import sleep

import aiohttp
import pykakasi
import requests
from lxml import html
from selenium import webdriver
from selenium.webdriver.chrome.options import Options as ChromeOptions

from config import logger
from connection import get_random_useragent
from lookup.async_helpers import call_sync_async, fetch_json
from lookup.cache_helpers import (
    format_ja_character_from_cache,
    format_ja_word_from_cache,
    get_from_cache,
    parse_ja_output_to_json,
    save_to_cache,
)
from lookup.zh import calligraphy_search

useragent = get_random_useragent()

"""ROMANIZATION HELPER"""

_kks = pykakasi.kakasi()


def _to_hepburn(input_text: str) -> str:
    """Returns a Hepburn romanization of the input."""
    result = _kks.convert(input_text)
    return " ".join([item["hepburn"] for item in result])


def _format_kun_on_readings(tree) -> tuple[str, str]:
    """
    Extract and format kun and on readings from the parsed HTML tree.

    Returns:
        kun_chunk (str): formatted kun readings, e.g. "よみ (*yomi*)"
        on_chunk (str): formatted on readings, e.g. "ヨミ (*yomi*)"
    """
    kun_readings: list[str] = tree.xpath(
        '//div[contains(@class,"kanji-details__main-readings")]/dl[1]/dd/a/text()'
    )

    if not kun_readings:
        on_readings: list[str] = tree.xpath(
            '//*[@id="result_area"]/div/div[1]/div[2]/div/div[1]/div[2]/dl/dd/a/text()'
        )
    else:
        on_readings: list[str] = tree.xpath(
            '//div[contains(@class,"kanji-details__main-readings")]/dl[2]/dd/a/text()'
        )

    kun_chunk: str = ", ".join(f"{r} (*{_to_hepburn(r)}*)" for r in kun_readings)
    on_chunk: str = ", ".join(f"{r} (*{_to_hepburn(r)}*)" for r in on_readings)

    return kun_chunk, on_chunk


"""CHARACTER FUNCTIONS"""


def _ja_character_fetch(character: str) -> str:
    """
    Internal function to fetch Japanese character data from web sources.
    This is called by ja_character when cache miss occurs.

    :param character: A kanji or single hiragana. This function will not
                      work with individual katakana.
    :return: A formatted string with readings, meanings, and resource links.
    """
    is_kana: bool = False
    multi_mode: bool = len(character) > 1
    multi_character_dict: dict[str, dict[str, str]] = {}

    kana_test: re.Match | None = re.search(
        "[\u3040-\u309f]", character
    )  # Hiragana Unicode block

    if kana_test:
        kana: str = kana_test.group(0)
        response = requests.get(
            f"https://jisho.org/search/{character}%20%23particle", headers=useragent
        )
        tree = html.fromstring(response.content)
        meaning_list: list[str] = tree.xpath(
            '//span[contains(@class,"meaning-meaning")]/text()'
        )
        meaning: str = " / ".join(meaning_list)
        is_kana = True

        total_data: str = f"# [{kana}](https://en.wiktionary.org/wiki/{kana}#Japanese)"
        total_data += f" (*{_to_hepburn(kana)}*)"
        total_data += f'\n\n**Meanings**: "{meaning}."'

    elif not multi_mode:
        # Single kanji mode
        response = requests.get(
            f"https://jisho.org/search/{character}%20%23kanji", headers=useragent
        )
        tree = html.fromstring(response.content)

        meanings: list[str] = tree.xpath(
            '//div[contains(@class,"kanji-details__main-meanings")]/text()'
        )
        meaning: str = " / ".join(meanings).strip()

        if not meaning:
            logger.info(f"[ZW] JA-Character: No results for {character}")
            return (
                f"There were no results for {character}. Please check to make sure it is a valid "
                "Japanese character or word."
            )

        kun_chunk, on_chunk = _format_kun_on_readings(tree)

        lookup_line_1: str = (
            f"# [{character}](https://en.wiktionary.org/wiki/{character}#Japanese)\n\n"
        )
        lookup_line_1 += f"**Kun-readings:** {kun_chunk}\n\n**On-readings:** {on_chunk}"

        # Attempt to include calligraphy image
        calligraphy_image: str | None = calligraphy_search(character)
        if calligraphy_image:
            lookup_line_1 += calligraphy_image

        lookup_line_2: str = f'\n\n**Meanings**: "{meaning}."'
        total_data: str = lookup_line_1 + lookup_line_2

    else:
        # Multi-kanji mode
        ooi_key: str = f"# {character}"
        ooi_header: str = "\n\n| Character"
        ooi_separator: str = "\n| ---"
        ooi_kun: str = "\n| **Kun-readings**"
        ooi_on: str = "\n| **On-readings**"
        ooi_meaning: str = "\n| **Meanings**"

        for moji in character:
            response = requests.get(
                f"https://jisho.org/search/{moji}%20%23kanji", headers=useragent
            )
            tree = html.fromstring(response.content)

            kun_chunk, on_chunk = _format_kun_on_readings(tree)

            meanings: list[str] = tree.xpath(
                '//div[contains(@class,"kanji-details__main-meanings")]/text()'
            )
            meaning: str = f'"{" / ".join(meanings).strip()}."'

            multi_character_dict[moji] = {
                "kun": kun_chunk,
                "on": on_chunk,
                "meaning": meaning,
            }

        # Construct Markdown table from individual kanji
        for moji in character:
            data = multi_character_dict[moji]
            ooi_header += f" | [{moji}](https://en.wiktionary.org/wiki/{moji}#Japanese)"
            ooi_separator += " | ---"
            ooi_kun += f" | {data['kun']}"
            ooi_on += f" | {data['on']}"
            ooi_meaning += f" | {data['meaning']}"

        # Add closing pipes to all rows
        ooi_header += " |"
        ooi_separator += " |"
        ooi_kun += " |"
        ooi_on += " |"
        ooi_meaning += " |"

        total_data: str = (
            ooi_key + ooi_header + ooi_separator + ooi_kun + ooi_on + ooi_meaning
        )

    # Append resource links
    if is_kana:
        lookup_line_3: str = (
            f"\n\n^Information ^from ^[Jisho](https://jisho.org/search/{character}%20%23particle) ^| "
            f"^[Tangorin](https://tangorin.com/general/{character}%20particle) ^| "
            f"^[Weblio](https://ejje.weblio.jp/content/{character})"
        )
    else:
        lookup_line_3: str = (
            f"\n\n^Information ^from ^[Jisho](https://jisho.org/search/{character}%20%23kanji) ^| "
            f"^[Tangorin](https://tangorin.com/kanji/{character}) ^| "
            f"^[Weblio](https://ejje.weblio.jp/content/{character})"
        )

    logger.info(
        f"[ZW] JA-Character: Received lookup command for {character} in Japanese. Returned results."
    )

    # Cache the result before returning
    try:
        parsed_data = parse_ja_output_to_json(total_data)
        save_to_cache(parsed_data, "ja", "ja_character")
        logger.debug(f"[ZW] JA-Character: Cached result for '{character}'")
    except Exception as ex:
        logger.error(
            f"[ZW] JA-Character: Failed to cache result for '{character}': {ex}"
        )

    return total_data + lookup_line_3


def ja_character(character: str) -> str:
    """
    Looks up a Japanese kanji or hiragana character's readings and meanings with caching support.
    Checks cache first, falls back to web fetch if not found.

    :param character: A kanji or single hiragana. This function will not
                      work with individual katakana.
    :return: A formatted string with readings, meanings, and resource links.
    """
    # Check cache first
    cached = get_from_cache(character, "ja", "ja_character")

    if cached and cached.get("word"):  # Check it's not empty dict
        logger.info(f"[ZW] JA-Character: Retrieved '{character}' from cache.")
        return format_ja_character_from_cache(cached) + " ^⚡"

    # Cache miss - fetch from web
    logger.info(
        f"[ZW] JA-Character: '{character}' not found in cache, fetching from web."
    )
    return _ja_character_fetch(character)


"""WORD FUNCTIONS"""


def _sfx_search(katakana_string: str) -> str | None:
    if not re.search(r"[\u30A0-\u30FF]", katakana_string):
        return None

    search_url: str = f"https://nsk.sh/tools/jp-onomatopoeia/?term={katakana_string}"

    options = ChromeOptions()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-software-rasterizer")

    driver = webdriver.Chrome(options=options)

    try:
        driver.get(search_url)
        sleep(2)  # Let JS render

        tree = html.fromstring(driver.page_source)

        # Scope only to the first result container
        container = tree.xpath("//main/div/div/div[1]/div")[0]

        # Find the first <h3> and the following <ul> only within that container
        h3_elem = container.xpath(".//h3[1]")
        ul_elem = container.xpath(".//ul[1]")

        if not h3_elem or not ul_elem:
            return None

        match_text: list[str] = tree.xpath(
            "/html/body/main/div/div/div[1]/div/div/div[1]/h3/text()"
        )
        match_text_str: str | None = match_text[0].strip() if match_text else None
        meanings: list[str] = [
            li.text_content().strip()
            for li in ul_elem[0].xpath("./li")
            if li.text_content().strip()
        ]

        if not meanings:
            return None

        if katakana_string not in (match_text_str or ""):
            logger.info("Match not found in entry header.")

        # Format the Hepburn reading.
        katakana_reading: str = _to_hepburn(katakana_string)

        # Format the output message
        meanings_formatted: str = "\n".join(f"* {m}" for m in meanings)
        formatted_line: str = (
            f"\n\n**Explanation**: \n{meanings_formatted}"
            f"\n\n\n^Information ^from ^[JOS]({search_url})"
        )
        header: str = (
            f"# [{katakana_string}](https://en.wiktionary.org/wiki/{katakana_string}#Japanese)"
            f"\n\n##### *Sound effect*\n\n**Reading:** *{katakana_reading}*"
        )
        finished_comment: str = f"{header}{formatted_line}"
        logger.info(
            f"[ZW] JA-Word-SFX: Found a dictionary entry for {katakana_string} at {search_url}"
        )

        return finished_comment

    except Exception as e:
        logger.warning(f"[ZW] JA-Word-SFX: Error searching for {katakana_string}: {e}")
        return None
    finally:
        driver.quit()


def _ja_name_search(ja_given_name: str) -> str | None:
    """
    Gets the kanji readings of Japanese given names, including names not in dictionaries.
    Also returns readings for place names such as temples.

    :param ja_given_name: A Japanese given name, in kanji only.
    :return: A formatted Markdown section with readings and a placeholder
             meaning if valid. Otherwise, returns None.
    """

    names_with_readings: list[str] = []

    # Conduct the web search
    url: str = f"https://kanji.reader.bz/{ja_given_name}"
    eth_page = requests.get(url, headers=useragent)
    tree = html.fromstring(eth_page.content)

    name_content: list[str] = tree.xpath('//div[contains(@id,"main")]/p[1]/text()')
    hiragana_content: list[str] = tree.xpath(
        '//div[contains(@id,"main")]/p[1]/a/text()'
    )

    logger.debug(name_content)
    logger.info(f"Name lookup: {hiragana_content=}")
    if not hiragana_content:
        return None  # no readings found

    # Check for error message: "見つかりませんでした" = "Not found"
    if "見つかりませんでした" in str(name_content):
        return None

    # Father and format readings.
    for hira in hiragana_content:
        hira_clean = hira.strip()
        romaji = _to_hepburn(hira_clean).title()
        names_with_readings.append(f"{hira_clean} (*{romaji}*)")

    readings_str: str = ", ".join(names_with_readings)

    # Build the final Markdown output
    formatted_section: str = (
        f"# [{ja_given_name}](https://en.wiktionary.org/wiki/{ja_given_name}#Japanese)\n\n"
        f"**Readings:** {readings_str}\n\n"
        f"**Meanings**: A Japanese name.\n\n\n"
        f"^(Information from) ^[JinmeiKanjiJisho)](https://kanji.reader.bz/{ja_given_name}) "
        f"^| ^[Weblio](https://ejje.weblio.jp/content/{ja_given_name})"
    )

    return formatted_section


def _ja_word_yojijukugo(yojijukugo: str) -> str | None:
    """
    Retrieves meaning and explanation for a four-kanji Japanese idiom (yojijukugo).
    Examples of such idioms can be found at this website:
    https://www.edrdg.org/projects/yojijukugo.html

    :param yojijukugo: Four-kanji Japanese idiom.
    :return: Formatted string with explanation and source,
             or None if not found.
    """

    try:
        search_url: str = f"https://yoji.jitenon.jp/cat/search.php?getdata={yojijukugo}&search=part&page=1"
        logger.debug(f"Searching Yojijukugo at: {search_url}")

        search_resp = requests.get(search_url, headers=useragent, allow_redirects=True)
        search_resp.encoding = search_resp.apparent_encoding

        entry_url: str = search_resp.url
        logger.debug(f"Redirected to entry page: {entry_url}")

        tree = html.fromstring(search_resp.text)

        # Extract reading.
        reading_xpath: str = (
            "/html/body/div/div[1]/div[1]/div[1]/div[2]/table/tbody/tr[2]/td"
        )
        reading_nodes = tree.xpath(reading_xpath)
        reading: str | None = None
        if reading_nodes:
            reading_raw: str = reading_nodes[0].text_content()
            reading = reading_raw.replace("\r", "\n").strip()
            reading = "\n".join(
                line.strip() for line in reading.splitlines() if line.strip()
            )

        # Extract Japanese Explanation
        explanation_xpath: str = (
            "/html/body/div/div[1]/div[1]/div[1]/div[2]/table/tbody/tr[3]/td"
        )
        explanation_nodes = tree.xpath(explanation_xpath)
        if not explanation_nodes:
            logger.warning(f"No explanation found for {yojijukugo} at {entry_url}")
            return None

        explanation_raw: str = explanation_nodes[0].text_content()
        # Normalize line breaks and clean empty lines
        explanation: str = explanation_raw.replace("\r", "\n").strip()
        explanation = " ".join(
            line.strip() for line in explanation.splitlines() if line.strip()
        )

        # Check if the 4th row's <th> is 出典, then get literary source
        th_xpath: str = (
            "/html/body/div/div[1]/div[1]/div[1]/div[2]/table/tbody/tr[4]/th"
        )
        th_nodes = tree.xpath(th_xpath)
        source: str | None = None
        if th_nodes and th_nodes[0].text_content().strip() == "出典":
            source_xpath: str = (
                "/html/body/div/div[1]/div[1]/div[1]/div[2]/table/tbody/tr[4]/td"
            )
            source_nodes = tree.xpath(source_xpath)
            if source_nodes:
                source_raw: str = source_nodes[0].text_content()
                source = "\n".join(
                    line.strip() for line in source_raw.splitlines() if line.strip()
                )

        logger.debug(f"Retrieved explanation and literary source for {yojijukugo}")

        # Build the final Markdown output
        formatted_section: str = (
            f"# [{yojijukugo}](https://en.wiktionary.org/wiki/{yojijukugo}#Japanese)\n\n"
            f"**Reading:** {reading} (*{_to_hepburn(reading)}*)\n\n"
            f"**Japanese Explanation**: {explanation}.\n\n"
        )
        if source:
            formatted_section += f"**Literary Source**: {source}\n\n\n"
        formatted_section += (
            f"^(Information from) ^[Jitenon]({entry_url}) "
            f"^| ^[Weblio](https://ejje.weblio.jp/content/{yojijukugo})"
        )

        return formatted_section

    except requests.RequestException as e:
        logger.error(f"Network error retrieving {yojijukugo}: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error processing {yojijukugo}: {e}")
        return None


async def _ja_word_fetch(japanese_word: str) -> str | None:
    """
    Internal function to fetch Japanese word data from web sources.
    This is called by ja_word when cache miss occurs.

    :param japanese_word: A Japanese word.
    :return: Formatted string with readings and meanings, or None.
    """
    japanese_word = japanese_word.strip()
    url: str = (
        f"https://jisho.org/api/v1/search/words?keyword={japanese_word}%20%23words"
    )

    async with aiohttp.ClientSession() as session:
        word_data: dict | list | None = await fetch_json(session, url)

    if not word_data or not word_data.get("data"):
        logger.warning(f"[ZW] JA-Word: No JSON or empty data for `{japanese_word}`.")
        word_reading: str = ""
        main_data = None
    else:
        main_data = word_data["data"][0]
        word_reading: str = main_data.get("japanese", [{}])[0].get("reading", "")

    # If Jisho returned nothing useful
    if not word_reading:
        logger.info(f"[ZW] JA-Word: No results for '{japanese_word}' on Jisho.")

        katakana_test: re.Match | None = re.search(r"[\u30a0-\u30ff]", japanese_word)
        # Execute some searches asynchronously.
        name_data: str | None = None
        yojijukugo_data: str | None = None
        if len(japanese_word) == 2:
            name_data = await call_sync_async(_ja_name_search, japanese_word)
        elif len(japanese_word) == 4:
            yojijukugo_data = await call_sync_async(_ja_word_yojijukugo, japanese_word)
        sfx_data: str | None = await call_sync_async(_sfx_search, japanese_word)

        if not any([name_data, sfx_data, yojijukugo_data]):
            if not katakana_test:
                logger.info(
                    "[ZW] JA-Word: No matches. Falling back to single-character lookup."
                )
                return await call_sync_async(ja_character, japanese_word)
            else:
                logger.info("[ZW] JA-Word: Unknown katakana word.")
                return None

        if name_data:
            logger.info("[ZW] JA-Word: Found a Japanese name/surname.")
            return name_data

        if yojijukugo_data:
            logger.info("[ZW] JA-Word: Found a Japanese yojijukugo (proverb).")
            return yojijukugo_data

        if sfx_data:
            logger.info("[ZW] JA-Word: Found a Japanese sound effect.")
            return sfx_data

    if main_data:
        # Format valid Jisho result
        word_reading_chunk: str = f"{word_reading} (*{_to_hepburn(word_reading)}*)"
        word_meaning: str = (
            f'"{", ".join(main_data["senses"][0]["english_definitions"])}."'
        )
        word_type: str = f"*{', '.join(main_data['senses'][0]['parts_of_speech'])}*"

        return_comment: str = (
            f"# [{japanese_word}](https://en.wiktionary.org/wiki/{japanese_word}#Japanese)\n\n"
            f"##### {word_type}\n\n"
            f"**Reading:** {word_reading_chunk}\n\n"
            f"**Meanings**: {word_meaning}"
        )

        # Add sources
        footer: str = (
            f"\n\n^Information ^from ^[Jisho](https://jisho.org/search/{japanese_word}%23words) ^| "
            f"^[Kotobank](https://kotobank.jp/word/{japanese_word}) ^| "
            f"^[Tangorin](https://tangorin.com/general/{japanese_word}) ^| "
            f"^[Weblio](https://ejje.weblio.jp/content/{japanese_word})"
        )

        logger.info(f"[ZW] JA-Word: Final result for '{japanese_word}' returned.")

        # Cache the result before returning
        try:
            parsed_data = parse_ja_output_to_json(return_comment)
            save_to_cache(parsed_data, "ja", "ja_word")
            logger.debug(f"[ZW] JA-Word: Cached result for '{japanese_word}'")
        except Exception as ex:
            logger.error(
                f"[ZW] JA-Word: Failed to cache result for '{japanese_word}': {ex}"
            )

        return return_comment + footer
    else:
        return None


async def ja_word(japanese_word: str) -> str | None:
    """
    Async version of ja_word with caching support.
    Uses Jisho's unlisted API to fetch Japanese word data.
    Falls back to other functions if no word data found.
    Checks cache first, falls back to web fetch if not found.

    :param japanese_word: A Japanese word.
    :return: Formatted string with readings and meanings, or None.
    """
    japanese_word = japanese_word.strip()

    # Check cache first
    cached = get_from_cache(japanese_word, "ja", "ja_word")

    if cached and cached.get("word"):  # Check it's not empty dict
        logger.info(f"[ZW] JA-Word: Retrieved '{japanese_word}' from cache.")
        return format_ja_word_from_cache(cached) + " ^⚡"

    # Cache miss - fetch from web
    logger.info(
        f"[ZW] JA-Word: '{japanese_word}' not found in cache, fetching from web."
    )
    return await _ja_word_fetch(japanese_word)


if __name__ == "__main__":
    import logging

    # Configure logging to DEBUG level
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    # Also set the module logger to DEBUG explicitly
    logger.setLevel(logging.DEBUG)

    def show_menu():
        print("\nSelect a search to run:")
        print("1. ja_character (search for a single Japanese character)")
        print("2. ja_word (search for a Japanese word)")
        print("x. Exit")

    while True:
        show_menu()
        choice = input("Enter your choice (1-2, or x): ")

        if choice == "x":
            print("Exiting...")
            break

        if choice not in ["1", "2"]:
            print("Invalid choice, please try again.")
            continue

        my_input = input("Enter the string you wish to test: ")

        if choice == "1":
            print(ja_character(my_input))
        elif choice == "2":
            print(asyncio.run(ja_word(my_input)))
