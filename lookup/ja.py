#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
Contains functions that deal with Japanese-language content.
"""
import aiohttp
import asyncio
import re
import requests
import time

from selenium import webdriver
from selenium.webdriver.firefox.options import Options
import pykakasi
from lxml import html, etree

from config import logger
from connection import get_random_useragent
from async_helpers import fetch_json, maybe_async
from zh import calligraphy_search

useragent = get_random_useragent()

"""PINYIN/ROMANIZATION HELPER"""


def to_hepburn(input_text):
    """Returns a Hepburn romanization of the input."""
    kks = pykakasi.kakasi()
    result = kks.convert(input_text)
    return ' '.join([item['hepburn'] for item in result])


"""CHARACTER FUNCTIONS"""


def ja_character(character):
    """
    Looks up a Japanese kanji or hiragana character's readings and meanings.

    :param character: A kanji or single hiragana. This function will not work with individual katakana.
    :return: A formatted string with readings, meanings, and resource links.
    """
    is_kana = False
    multi_mode = len(character) > 1
    multi_character_dict = {}

    kana_test = re.search('[\u3040-\u309f]', character)  # Hiragana Unicode block

    if kana_test:
        kana = kana_test.group(0)
        response = requests.get(f'https://jisho.org/search/{character}%20%23particle', headers=useragent)
        tree = html.fromstring(response.content)
        meaning_list = tree.xpath('//span[contains(@class,"meaning-meaning")]/text()')
        meaning = ' / '.join(meaning_list)
        is_kana = True

        total_data = f'# [{kana}](https://en.wiktionary.org/wiki/{kana}#Japanese)'
        total_data += f" (*{to_hepburn(kana)}*)"
        total_data += f'\n\n**Meanings**: "{meaning}."'

    elif not multi_mode:
        # Single kanji mode
        response = requests.get(f'https://jisho.org/search/{character}%20%23kanji', headers=useragent)
        tree = html.fromstring(response.content)

        kun_readings = tree.xpath('//dl[contains(@class,"kun_yomi")]/dd/a/text()')
        meanings = tree.xpath('//div[contains(@class,"kanji-details__main-meanings")]/text()')
        meaning = ' / '.join(meanings).strip()

        if not meaning:
            logger.info(f"[ZW] JA-Character: No results for {character}")
            return (f"There were no results for {character}. Please check to make sure it is a valid "
                    "Japanese character or word.")

        if not kun_readings:
            on_readings = tree.xpath('//*[@id="result_area"]/div/div[1]/div[2]/div/div[1]/div[2]/dl/dd/a/text()')
        else:
            on_readings = tree.xpath('//div[contains(@class,"kanji-details__main-readings")]/dl[2]/dd/a/text()')

        # Format readings
        kun_chunk = ', '.join(f"{r} (*{to_hepburn(r)}*)" for r in kun_readings)
        on_chunk = ', '.join(f"{r} (*{to_hepburn(r)}*)" for r in on_readings)

        lookup_line_1 = f'# [{character}](https://en.wiktionary.org/wiki/{character}#Japanese)\n\n'
        lookup_line_1 += f'**Kun-readings:** {kun_chunk}\n\n**On-readings:** {on_chunk}'

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
            response = requests.get(f'https://jisho.org/search/{moji}%20%23kanji', headers=useragent)
            tree = html.fromstring(response.content)

            kun_readings = tree.xpath('//dl[contains(@class,"kun_yomi")]/dd/a/text()')
            if not kun_readings:
                on_readings = tree.xpath('//*[@id="result_area"]/div/div[1]/div[2]/div/div[1]/div[2]/dl/dd/a/text()')
            else:
                on_readings = tree.xpath('//div[contains(@class,"kanji-details__main-readings")]/dl[2]/dd/a/text()')

            kun_chunk = ', '.join(f"{r} (*{to_hepburn(r)}*)" for r in kun_readings)
            on_chunk = ', '.join(f"{r} (*{to_hepburn(r)}*)" for r in on_readings)

            meanings = tree.xpath('//div[contains(@class,"kanji-details__main-meanings")]/text()')
            meaning = f'"{" / ".join(meanings).strip()}."'

            multi_character_dict[moji] = {
                "kun": kun_chunk,
                "on": on_chunk,
                "meaning": meaning
            }

        # Construct Markdown table from individual kanji
        for moji in character:
            data = multi_character_dict[moji]
            ooi_header += f" | [{moji}](https://en.wiktionary.org/wiki/{moji}#Japanese)"
            ooi_separator += "---|"
            ooi_kun += f" | {data['kun']}"
            ooi_on += f" | {data['on']}"
            ooi_meaning += f" | {data['meaning']}"

        total_data = ooi_key + ooi_header + ooi_separator + ooi_kun + ooi_on + ooi_meaning

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
            f"[^(Goo Dictionary)](https://dictionary.goo.ne.jp/word/en/{character}) ^| "
            f"[^(Tangorin)](https://tangorin.com/kanji/{character}) ^| "
            f"[^(Weblio EJJE)](https://ejje.weblio.jp/content/{character})"
        )

    logger.info(f"[ZW] JA-Character: Received lookup command for {character} in Japanese. Returned results.")
    return total_data + lookup_line_3


"""WORD FUNCTIONS"""


def sfx_search(katakana_string):
    """
    Consults the SFX Dictionary to provide explanations for katakana
    sound effects, often found in manga.
    For more information, visit: http://thejadednetwork.com/sfx

    :param katakana_string: Any string of katakana. Returns None if non-katakana characters are detected.
    :return: None if no results; otherwise, a formatted string with the result.
    """
    # Ensure the input contains katakana characters (Unicode block: U+30A0–U+30FF)
    if not re.search(r'[\u30A0-\u30FF]', katakana_string):
        return None

    # Format the search URL
    search_url = f"https://nsk.sh/tools/jp-onomatopoeia/?term={katakana_string}"
    logger.info(f"[SFX] Searching: {search_url}")

    # Perform the search request
    try:
        response = requests.get(search_url, headers=useragent)
        response.raise_for_status()
    except requests.RequestException as e:
        logger.error(f"[SFX] Request failed: {e}")
        return None

    tree = html.fromstring(response.content)

    # Optional: print the HTML for debugging
    print(etree.tostring(tree, pretty_print=True, encoding='unicode'))

    # Extract the matched term (confirmation string)
    try:
        match_header = tree.xpath('/html/body/main/div/div/div/div/div/div[1]/h3/text()')
        match_text = match_header[0].strip() if match_header else None
    except Exception as e:
        logger.warning(f"[SFX] Failed to extract match text: {e}")
        match_text = None
    print(match_text)

    # Extract the list of meanings
    try:
        meanings_list = tree.xpath('/html/body/main/div/div/div/div/div/div[1]/ul/li/text()')
        meanings = [m.strip() for m in meanings_list if m.strip()]
    except Exception as e:
        logger.warning(f"[SFX] Failed to extract meanings: {e}")
        meanings = []

    if not meanings:
        return None

    # Format the Hepburn reading.
    katakana_reading = to_hepburn(katakana_string)

    # Format the output message
    formatted_line = (
        f"\n\n**Explanation**: {meanings}"
        f"\n\n\n^Information ^from [JOS]({search_url})"
    )
    header = (
        f"# [{katakana_string}](https://en.wiktionary.org/wiki/{katakana_string}#Japanese)"
        f"\n\n##### *Sound effect*\n\n**Reading:** {katakana_reading}"
    )
    finished_comment = f"{header}{formatted_line}"

    logger.info(f"[ZW] JA-Word-SFX: Found a dictionary entry for {katakana_string} at {search_url}")

    return finished_comment


def sfx_search(katakana_string):
    if not re.search(r'[\u30A0-\u30FF]', katakana_string):
        return None

    search_url = f"https://nsk.sh/tools/jp-onomatopoeia/?term={katakana_string}"
    options = Options()
    options.headless = True
    driver = webdriver.Firefox(options=options)

    try:
        driver.get(search_url)
        time.sleep(2)  # Let JS render

        tree = html.fromstring(driver.page_source)

        # Scope only to the first result container
        container = tree.xpath('//main/div/div/div[1]/div')[0]

        # Find the first <h3> and the following <ul> only within that container
        h3_elem = container.xpath('.//h3[1]')
        ul_elem = container.xpath('.//ul[1]')

        if not h3_elem or not ul_elem:
            return None

        match_text = tree.xpath('/html/body/main/div/div/div[1]/div/div/div[1]/h3/text()')
        match_text = match_text[0].strip() if match_text else None
        meanings = [li.text_content().strip() for li in ul_elem[0].xpath('./li') if li.text_content().strip()]

        if not meanings:
            return None

        if katakana_string not in match_text:
            logger.info("Match not found in entry header.")

        # Format the Hepburn reading.
        katakana_reading = to_hepburn(katakana_string)

        # Format the output message
        meanings_formatted = "\n".join(f"* {m}" for m in meanings)
        formatted_line = (
            f"\n\n**Explanation**: \n{meanings_formatted}"
            f"\n\n\n^Information ^from ^[JOS]({search_url})"
        )
        header = (
            f"# [{katakana_string}](https://en.wiktionary.org/wiki/{katakana_string}#Japanese)"
            f"\n\n##### *Sound effect*\n\n**Reading:** {katakana_reading}"
        )
        finished_comment = f"{header}{formatted_line}"
        logger.info(f"[ZW] JA-Word-SFX: Found a dictionary entry for {katakana_string} at {search_url}")

        return finished_comment

    finally:
        driver.quit()


def ja_name_search(ja_given_name):
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
    name_content = [x for x in name_content if x != '\xa0\xa0']
    if name_content:
        name_content = name_content[0].split()
        print(name_content)

    # Pair hiragana and romaji readings
    for i, hira in enumerate(hiragana_content):
        hira_clean = hira.strip()
        romaji = name_content[i].title() if i < len(name_content) else ''
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


def ja_word_yojijukugo(yojijukugo):
    """
    Retrieves meaning and explanation for a four-kanji Japanese idiom (yojijukugo).
    Example resource: https://www.edrdg.org/projects/yojijukugo.html

    :param yojijukugo: Four-kanji Japanese idiom.
    :return: Formatted string with explanation and source, or None if not found.
    """

    url_search = f'https://yoji.jitenon.jp/cat/search.php?getdata={yojijukugo}&search=part&page=1'
    logger.info(url_search)
    eth_page = requests.get(url_search, headers=useragent)
    tree = html.fromstring(eth_page.content)

    urls = tree.xpath('//th[contains(@scope,"row")]/a/@href')
    if not urls:
        return None

    url_entry = urls[0]
    entry_page = requests.get(url_entry, headers=useragent)
    entry_tree = html.fromstring(entry_page.content)
    print(etree.tostring(entry_tree))

    # Validate that the entry matches the requested yojijukugo
    entry_title = entry_tree.xpath('//h1/text()')[0]
    entry_title = entry_title.split('」', 1)[0][1:]  # Extract main title (remove leading bracket and trailing parts)
    if entry_title != yojijukugo:
        logger.debug(f"[ZW] JA-Yojijukugo: Title mismatch for {yojijukugo} vs {entry_title}.")
        return None

    # Extract and format explanation and literary source
    row_data = [td.text_content().strip() for td in entry_tree.xpath('//td')]
    y_meaning = f"\n\n**Japanese Explanation**: {row_data[1]}\n\n"
    y_source = f"**Literary Source**: {row_data[2]}"

    logger.info(f"[ZW] JA-Yojijukugo: Retrieved information on {yojijukugo} from {url_entry}.")

    return y_meaning + y_source


async def ja_word(japanese_word):
    """
    Async version of ja_word. Uses Jisho's unlisted API to fetch Japanese word data.
    Falls back to other functions if no word data found.
    """
    y_data = None
    url = f'https://jisho.org/api/v1/search/words?keyword={japanese_word}%20%23words'

    async with aiohttp.ClientSession() as session:
        word_data = await fetch_json(session, url)

    if not word_data or not word_data.get("data"):
        logger.error("[ZW] JA-Word: No JSON or empty data.")
        word_reading = ""
    else:
        main_data = word_data["data"][0]
        word_reading = main_data.get("japanese", [{}])[0].get("reading", "")

    # If Jisho returned nothing useful
    if not word_reading:
        logger.info(f"[ZW] JA-Word: No results for '{japanese_word}' on Jisho.")

        katakana_test = re.search(r'[\u30a0-\u30ff]', japanese_word)
        # Assume these are synchronous. Wrap in executor if not.
        name_data = await maybe_async(ja_name_search(), japanese_word)
        sfx_data = await maybe_async(sfx_search(), japanese_word)

        if not any([name_data, sfx_data]):
            if not katakana_test:
                logger.info("[ZW] JA-Word: No matches. Falling back to single-character lookup.")
                return await maybe_async(ja_character, japanese_word)
            else:
                logger.info("[ZW] JA-Word: Unknown katakana word.")
                return f"There were no results for `{japanese_word}`."

        if name_data:
            logger.info("[ZW] JA-Word: Found a Japanese name/surname.")
            return name_data
        if sfx_data:
            logger.info("[ZW] JA-Word: Found a Japanese sound effect.")
            return sfx_data

    # Format valid Jisho result
    word_reading_chunk = f"{word_reading} (*{to_hepburn(word_reading)}*)"
    word_meaning = f'"{", ".join(main_data["senses"][0]["english_definitions"])}."'
    word_type = f'*{", ".join(main_data["senses"][0]["parts_of_speech"])}*'

    return_comment = (
        f"# [{japanese_word}](https://en.wiktionary.org/wiki/{japanese_word}#Japanese)\n\n"
        f"##### {word_type}\n\n"
        f"**Reading:** {word_reading_chunk}\n\n"
        f"**Meanings**: {word_meaning}"
    )

    # TODO reintegrate in the future
    """ 
    # Yojijukugo check
    if len(japanese_word) == 4:
        y_data = await maybe_async(ja_word_yojijukugo, japanese_word)
        if y_data:
            logger.debug("[ZW] JA-Word: Yojijukugo data added.")
            return_comment += y_data
    """
    # Add sources
    footer = (
        f"\n\n^Information ^from ^[Jisho](https://jisho.org/search/{japanese_word}%23words) ^| "
        f"[^Kotobank](https://kotobank.jp/word/{japanese_word}) ^| "
        f"[^Tangorin](https://tangorin.com/general/{japanese_word}) ^| "
        f"[^(Weblio EJJE)](https://ejje.weblio.jp/content/{japanese_word})"
    )
    if y_data:
        footer += f" ^| [^Yoji ^Jitenon](https://yoji.jitenon.jp/cat/search.php?getdata={japanese_word})"

    logger.info(f"[ZW] JA-Word: Final result for '{japanese_word}' returned.")
    return return_comment + footer


if __name__ == '__main__':
    while True:
        my_input = input("Please enter a string: ")
        print(asyncio.run(ja_word(my_input)))
