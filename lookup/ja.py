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
from selenium.webdriver.firefox.options import Options

from config import logger
from connection import get_random_useragent

from .async_helpers import call_sync_async, fetch_json
from .zh import calligraphy_search

useragent = get_random_useragent()

"""ROMANIZATION HELPER"""


def _to_hepburn(input_text):
    """Returns a Hepburn romanization of the input."""
    kks = pykakasi.kakasi()
    result = kks.convert(input_text)
    return " ".join([item["hepburn"] for item in result])


def _format_kun_on_readings(tree):
    """
    Extract and format kun and on readings from the parsed HTML tree.

    Returns:
        kun_chunk (str): formatted kun readings, e.g. "よみ (*yomi*)"
        on_chunk (str): formatted on readings, e.g. "ヨミ (*yomi*)"
    """
    kun_readings = tree.xpath(
        '//div[contains(@class,"kanji-details__main-readings")]/dl[1]/dd/a/text()'
    )

    if not kun_readings:
        on_readings = tree.xpath(
            '//*[@id="result_area"]/div/div[1]/div[2]/div/div[1]/div[2]/dl/dd/a/text()'
        )
    else:
        on_readings = tree.xpath(
            '//div[contains(@class,"kanji-details__main-readings")]/dl[2]/dd/a/text()'
        )

    kun_chunk = ", ".join(f"{r} (*{_to_hepburn(r)}*)" for r in kun_readings)
    on_chunk = ", ".join(f"{r} (*{_to_hepburn(r)}*)" for r in on_readings)

    return kun_chunk, on_chunk


"""CHARACTER FUNCTIONS"""


def ja_character(character):
    """
    Looks up a Japanese kanji or hiragana character's readings and meanings.

    :param character: A kanji or single hiragana. This function will not
                      work with individual katakana.
    :return: A formatted string with readings, meanings, and resource links.
    """
    is_kana = False
    multi_mode = len(character) > 1
    multi_character_dict = {}

    kana_test = re.search("[\u3040-\u309f]", character)  # Hiragana Unicode block

    if kana_test:
        kana = kana_test.group(0)
        response = requests.get(
            f"https://jisho.org/search/{character}%20%23particle", headers=useragent
        )
        tree = html.fromstring(response.content)
        meaning_list = tree.xpath('//span[contains(@class,"meaning-meaning")]/text()')
        meaning = " / ".join(meaning_list)
        is_kana = True

        total_data = f"# [{kana}](https://en.wiktionary.org/wiki/{kana}#Japanese)"
        total_data += f" (*{_to_hepburn(kana)}*)"
        total_data += f'\n\n**Meanings**: "{meaning}."'

    elif not multi_mode:
        # Single kanji mode
        response = requests.get(
            f"https://jisho.org/search/{character}%20%23kanji", headers=useragent
        )
        tree = html.fromstring(response.content)

        meanings = tree.xpath(
            '//div[contains(@class,"kanji-details__main-meanings")]/text()'
        )
        meaning = " / ".join(meanings).strip()

        if not meaning:
            logger.info(f"[ZW] JA-Character: No results for {character}")
            return (
                f"There were no results for {character}. Please check to make sure it is a valid "
                "Japanese character or word."
            )

        kun_chunk, on_chunk = _format_kun_on_readings(tree)

        lookup_line_1 = (
            f"# [{character}](https://en.wiktionary.org/wiki/{character}#Japanese)\n\n"
        )
        lookup_line_1 += f"**Kun-readings:** {kun_chunk}\n\n**On-readings:** {on_chunk}"

        # Attempt to include calligraphy image
        calligraphy_image = calligraphy_search(character)
        if calligraphy_image:
            lookup_line_1 += calligraphy_image

        lookup_line_2 = f'\n\n**Meanings**: "{meaning}."'
        total_data = lookup_line_1 + lookup_line_2

    else:
        # Multi-kanji mode
        ooi_key = f"# {character}"
        ooi_header = "\n\nCharacter"
        ooi_separator = "\n---|"
        ooi_kun = "\n**Kun-readings**"
        ooi_on = "\n**On-readings**"
        ooi_meaning = "\n**Meanings**"

        for moji in character:
            response = requests.get(
                f"https://jisho.org/search/{moji}%20%23kanji", headers=useragent
            )
            tree = html.fromstring(response.content)

            kun_chunk, on_chunk = _format_kun_on_readings(tree)

            meanings = tree.xpath(
                '//div[contains(@class,"kanji-details__main-meanings")]/text()'
            )
            meaning = f'"{" / ".join(meanings).strip()}."'

            multi_character_dict[moji] = {
                "kun": kun_chunk,
                "on": on_chunk,
                "meaning": meaning,
            }

        # Construct Markdown table from individual kanji
        for moji in character:
            data = multi_character_dict[moji]
            ooi_header += f" | [{moji}](https://en.wiktionary.org/wiki/{moji}#Japanese)"
            ooi_separator += "---|"
            ooi_kun += f" | {data['kun']}"
            ooi_on += f" | {data['on']}"
            ooi_meaning += f" | {data['meaning']}"

        total_data = (
            ooi_key + ooi_header + ooi_separator + ooi_kun + ooi_on + ooi_meaning
        )

    # Append resource links
    if is_kana:
        lookup_line_3 = (
            f"\n\n^Information ^from [^(Jisho)](https://jisho.org/search/{character}%20%23particle) ^| "
            f"[^(Tangorin)](https://tangorin.com/general/{character}%20particle) ^| "
            f"[^(Weblio EJJE)](https://ejje.weblio.jp/content/{character})"
        )
    else:
        lookup_line_3 = (
            f"\n\n^Information ^from [^(Jisho)](https://jisho.org/search/{character}%20%23kanji) ^| "
            f"[^(Tangorin)](https://tangorin.com/kanji/{character}) ^| "
            f"[^(Weblio EJJE)](https://ejje.weblio.jp/content/{character})"
        )

    logger.info(
        f"[ZW] JA-Character: Received lookup command for {character} in Japanese. Returned results."
    )
    return total_data + lookup_line_3


"""WORD FUNCTIONS"""


def _sfx_search(katakana_string):
    if not re.search(r"[\u30A0-\u30FF]", katakana_string):
        return None

    search_url = f"https://nsk.sh/tools/jp-onomatopoeia/?term={katakana_string}"
    options = Options()
    options.headless = True
    driver = webdriver.Firefox(options=options)

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

        match_text = tree.xpath(
            "/html/body/main/div/div/div[1]/div/div/div[1]/h3/text()"
        )
        match_text = match_text[0].strip() if match_text else None
        meanings = [
            li.text_content().strip()
            for li in ul_elem[0].xpath("./li")
            if li.text_content().strip()
        ]

        if not meanings:
            return None

        if katakana_string not in match_text:
            logger.info("Match not found in entry header.")

        # Format the Hepburn reading.
        katakana_reading = _to_hepburn(katakana_string)

        # Format the output message
        meanings_formatted = "\n".join(f"* {m}" for m in meanings)
        formatted_line = (
            f"\n\n**Explanation**: \n{meanings_formatted}"
            f"\n\n\n^Information ^from ^[JOS]({search_url})"
        )
        header = (
            f"# [{katakana_string}](https://en.wiktionary.org/wiki/{katakana_string}#Japanese)"
            f"\n\n##### *Sound effect*\n\n**Reading:** *{katakana_reading}*"
        )
        finished_comment = f"{header}{formatted_line}"
        logger.info(
            f"[ZW] JA-Word-SFX: Found a dictionary entry for {katakana_string} at {search_url}"
        )

        return finished_comment

    finally:
        driver.quit()


def _ja_name_search(ja_given_name):
    """
    Gets the kanji readings of Japanese given names, including names not in dictionaries.
    Also returns readings for place names such as temples.

    :param ja_given_name: A Japanese given name, in kanji only.
    :return: A formatted Markdown section with readings and a placeholder
             meaning if valid. Otherwise, returns None.
    """

    names_with_readings = []

    # Conduct the web search
    url = f"https://kanji.reader.bz/{ja_given_name}"
    eth_page = requests.get(url, headers=useragent)
    tree = html.fromstring(eth_page.content)

    name_content = tree.xpath('//div[contains(@id,"main")]/p[1]/text()')
    hiragana_content = tree.xpath('//div[contains(@id,"main")]/p[1]/a/text()')

    logger.debug(name_content)
    logger.debug(hiragana_content)

    # Check for error message: "見つかりませんでした" = "Not found"
    if "見つかりませんでした" in str(name_content):
        return None

    # Clean and split romaji readings
    name_content = [x for x in name_content if x != "\xa0\xa0"]
    if name_content:
        name_content = name_content[0].split()

    # Pair hiragana and romaji readings
    for i, hira in enumerate(hiragana_content):
        hira_clean = hira.strip()
        romaji = name_content[i].title() if i < len(name_content) else ""
        names_with_readings.append(f"{hira_clean} (*{romaji}*)")

    readings_str = ", ".join(names_with_readings)

    # Build the final Markdown output
    formatted_section = (
        f"# [{ja_given_name}](https://en.wiktionary.org/wiki/{ja_given_name}#Japanese)\n\n"
        f"**Readings:** {readings_str}\n\n"
        f"**Meanings**: A Japanese name.\n\n\n"
        f"^(Information from) [^(Jinmei Kanji Jisho)](https://kanji.reader.bz/{ja_given_name}) "
        f"^| [^(Weblio EJJE)](https://ejje.weblio.jp/content/{ja_given_name})"
    )

    return formatted_section


def _ja_word_yojijukugo(yojijukugo):
    """
    Retrieves meaning and explanation for a four-kanji Japanese idiom (yojijukugo).
    Examples of such idioms can be found at this website:
    https://www.edrdg.org/projects/yojijukugo.html

    :param yojijukugo: Four-kanji Japanese idiom.
    :return: Formatted string with explanation and source,
             or None if not found.
    """

    try:
        search_url = f"https://yoji.jitenon.jp/cat/search.php?getdata={yojijukugo}&search=part&page=1"
        logger.debug(f"Searching Yojijukugo at: {search_url}")

        search_resp = requests.get(search_url, headers=useragent, allow_redirects=True)
        search_resp.encoding = search_resp.apparent_encoding

        entry_url = search_resp.url
        logger.debug(f"Redirected to entry page: {entry_url}")

        tree = html.fromstring(search_resp.text)

        # Extract reading.
        reading_xpath = (
            "/html/body/div/div[1]/div[1]/div[1]/div[2]/table/tbody/tr[2]/td"
        )
        reading_nodes = tree.xpath(reading_xpath)
        reading = None
        if reading_nodes:
            reading_raw = reading_nodes[0].text_content()
            reading = reading_raw.replace("\r", "\n").strip()
            reading = "\n".join(
                line.strip() for line in reading.splitlines() if line.strip()
            )

        # Extract Japanese Explanation
        explanation_xpath = (
            "/html/body/div/div[1]/div[1]/div[1]/div[2]/table/tbody/tr[3]/td"
        )
        explanation_nodes = tree.xpath(explanation_xpath)
        if not explanation_nodes:
            logger.warning(f"No explanation found for {yojijukugo} at {entry_url}")
            return None

        explanation_raw = explanation_nodes[0].text_content()
        # Normalize line breaks and clean empty lines
        explanation = explanation_raw.replace("\r", "\n").strip()
        explanation = " ".join(
            line.strip() for line in explanation.splitlines() if line.strip()
        )

        # Check if the 4th row's <th> is 出典, then get literary source
        th_xpath = "/html/body/div/div[1]/div[1]/div[1]/div[2]/table/tbody/tr[4]/th"
        th_nodes = tree.xpath(th_xpath)
        source = None
        if th_nodes and th_nodes[0].text_content().strip() == "出典":
            source_xpath = (
                "/html/body/div/div[1]/div[1]/div[1]/div[2]/table/tbody/tr[4]/td"
            )
            source_nodes = tree.xpath(source_xpath)
            if source_nodes:
                source_raw = source_nodes[0].text_content()
                source = "\n".join(
                    line.strip() for line in source_raw.splitlines() if line.strip()
                )

        logger.debug(f"Retrieved explanation and literary source for {yojijukugo}")

        # Build the final Markdown output
        formatted_section = (
            f"# [{yojijukugo}](https://en.wiktionary.org/wiki/{yojijukugo}#Japanese)\n\n"
            f"**Reading:** {reading} (*{_to_hepburn(reading)}*)\n\n"
            f"**Japanese Explanation**: {explanation}.\n\n"
        )
        if source:
            formatted_section += f"**Literary Source**: {source}\n\n\n"
        formatted_section += (
            f"^(Information from) [^Jitenon]({entry_url}) "
            f"^| [^(Weblio EJJE)](https://ejje.weblio.jp/content/{yojijukugo})"
        )

        return formatted_section

    except requests.RequestException as e:
        logger.error(f"Network error retrieving {yojijukugo}: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error processing {yojijukugo}: {e}")
        return None


async def ja_word(japanese_word):
    """
    Async version of ja_word. Uses Jisho's unlisted API to fetch Japanese word data.
    Falls back to other functions if no word data found.
    """
    japanese_word = japanese_word.strip()
    url = f"https://jisho.org/api/v1/search/words?keyword={japanese_word}%20%23words"

    async with aiohttp.ClientSession() as session:
        word_data = await fetch_json(session, url)

    if not word_data or not word_data.get("data"):
        logger.error("[ZW] JA-Word: No JSON or empty data.")
        word_reading = ""
        main_data = None
    else:
        main_data = word_data["data"][0]
        word_reading = main_data.get("japanese", [{}])[0].get("reading", "")

    # If Jisho returned nothing useful
    if not word_reading:
        logger.info(f"[ZW] JA-Word: No results for '{japanese_word}' on Jisho.")

        katakana_test = re.search(r"[\u30a0-\u30ff]", japanese_word)
        # Execute some searches asynchronously.
        name_data = None
        yojijukugo_data = None
        if len(japanese_word) == 2:
            name_data = await call_sync_async(_ja_name_search, japanese_word)
        elif len(japanese_word) == 4:
            yojijukugo_data = await call_sync_async(_ja_word_yojijukugo, japanese_word)
        sfx_data = await call_sync_async(_sfx_search, japanese_word)

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
        word_reading_chunk = f"{word_reading} (*{_to_hepburn(word_reading)}*)"
        word_meaning = f'"{", ".join(main_data["senses"][0]["english_definitions"])}."'
        word_type = f"*{', '.join(main_data['senses'][0]['parts_of_speech'])}*"

        return_comment = (
            f"# [{japanese_word}](https://en.wiktionary.org/wiki/{japanese_word}#Japanese)\n\n"
            f"##### {word_type}\n\n"
            f"**Reading:** {word_reading_chunk}\n\n"
            f"**Meanings**: {word_meaning}"
        )

        # Add sources
        footer = (
            f"\n\n^Information ^from ^[Jisho](https://jisho.org/search/{japanese_word}%23words) ^| "
            f"[^Kotobank](https://kotobank.jp/word/{japanese_word}) ^| "
            f"[^Tangorin](https://tangorin.com/general/{japanese_word}) ^| "
            f"[^(Weblio EJJE)](https://ejje.weblio.jp/content/{japanese_word})"
        )

        logger.info(f"[ZW] JA-Word: Final result for '{japanese_word}' returned.")
        return return_comment + footer
    else:
        return None


if __name__ == "__main__":
    while True:
        my_input = input("Please enter a string: ")
        print(asyncio.run(ja_word(my_input)))
