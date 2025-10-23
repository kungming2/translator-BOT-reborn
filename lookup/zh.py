#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
Contains functions that deal with Chinese-language content.
"""

import asyncio
import csv
import html as html_stdlib
import random
import re
from contextlib import suppress
from time import sleep

import aiofiles
import aiohttp
import httpx
import opencc
import requests
from bs4 import BeautifulSoup as Bs
from korean_romanizer.romanizer import Romanizer
from lxml import html

from config import Paths, logger
from connection import get_random_useragent
from responses import RESPONSE

from lookup.async_helpers import call_sync_async

useragent = get_random_useragent()

"""TRADITIONAL/SIMPLIFIED CONVERSION"""


def simplify(input_text):
    """Returns a simplified version (if available) of the input."""
    used_converter = opencc.OpenCC("t2s.json")

    return used_converter.convert(input_text)


def tradify(input_text):
    """Returns a traditional version (if available) of the input."""
    used_converter = opencc.OpenCC("s2tw.json")

    return used_converter.convert(input_text)


"""PINYIN/ROMANIZATION HELPERS"""


def _sanitize_pinyin_input(pinyin_string):
    """Fix common issues with pinyin strings and filter out invalid parts.

    Keeps only parts that are at least two characters long and end with a digit (tone number).
    """
    cleaned = pinyin_string.lower().replace("-", " ").replace("\\u00fc", "ü")
    # Split on whitespace, filter out short or tone-missing parts, then join with single spaces
    return " ".join(
        part
        for part in cleaned.strip().split()
        if len(part) >= 2 and part[-1].isdigit()
    )


def _convert_numbered_pinyin(s):
    """
    Function to convert numbered pin1 yin1 into proper tone marks.
    CC-CEDICT's format uses numerical pinyin.
    This code is courtesy of Greg Hewgill on StackOverflow:
    https://stackoverflow.com/questions/8200349/convert-numbered-pinyin-to-pinyin-with-tone-marks

    :param s: A string of numbered pinyin (e.g. pin1 yin1)
    :return result: A string of pinyin with the tone marks properly applied (e.g. pīnyīn)
    """

    pinyin_tone_mark = {
        0: "aoeiuv\u00fc",
        1: "\u0101\u014d\u0113\u012b\u016b\u01d6\u01d6",
        2: "\u00e1\u00f3\u00e9\u00ed\u00fa\u01d8\u01d8",
        3: "\u01ce\u01d2\u011b\u01d0\u01d4\u01da\u01da",
        4: "\u00e0\u00f2\u00e8\u00ec\u00f9\u01dc\u01dc",
    }

    s = s.lower()
    result = ""
    t = ""
    for c in s:
        if "a" <= c <= "z":
            t += c
        elif c == ":":
            assert t[-1] == "u"
            t = t[:-1] + "\u00fc"
        else:
            if "0" <= c <= "5":
                tone = int(c) % 5
                if tone != 0:
                    m = re.search("[aoeiuv\u00fc]+", t)
                    if m is None:
                        t += c
                    elif len(m.group(0)) == 1:
                        t = (
                            t[: m.start(0)]
                            + pinyin_tone_mark[tone][
                                pinyin_tone_mark[0].index(m.group(0))
                            ]
                            + t[m.end(0) :]
                        )
                    else:
                        if "a" in t:
                            t = t.replace("a", pinyin_tone_mark[tone][0])
                        elif "o" in t:
                            t = t.replace("o", pinyin_tone_mark[tone][1])
                        elif "e" in t:
                            t = t.replace("e", pinyin_tone_mark[tone][2])
                        elif t.endswith("ui"):
                            t = t.replace("i", pinyin_tone_mark[tone][3])
                        elif t.endswith("iu"):
                            t = t.replace("u", pinyin_tone_mark[tone][4])
                        else:
                            t += "!"
            result += t
            t = ""
    result += t

    return result


def vowel_neighbor(letter, word):
    """Checks a letter to see if vowels are around it."""
    vowels = "aeiouy"

    for i in range(len(word)):
        if word[i] == letter:
            if i > 0 and word[i - 1] in vowels:
                return True
            if i < len(word) - 1 and word[i + 1] in vowels:
                return True
    return False


def _vowel_preceder(letter, word):
    """Checks a letter to see if vowels precede it."""
    vowels = "aeiouy"

    for i in range(len(word)):
        if word[i] == letter and i > 0 and word[i - 1] in vowels:
            return True
    return False


def _pair_syllables_with_tones(raw_syllables):
    """Pairs Cantonese syllables and tone numbers correctly."""
    pairs = []
    for i in range(0, len(raw_syllables) - 1, 2):
        syllable = raw_syllables[i]
        tone = raw_syllables[i + 1]
        pairs.append(f"{syllable}{tone}")
    return " ".join(pairs)


def _process_gwoyeu_romatzyh(syllables, corresponding_dict):
    """
    Processes the syllables into Gwoyeu Romatzyh romanization.

    :param syllables: List of pinyin syllables with tones.
    :param corresponding_dict: Dict mapping base pinyin to [Yale, Wade-Giles, GYRM].
    :return: List of GYRM syllables as strings.
    """

    def split_initial_final(syllable_to_split):
        if syllable_to_split.startswith(("w", "y")):
            return None, syllable_to_split[1:]
        elif len(syllable_to_split) > 1 and syllable_to_split[1] == "h":
            return syllable_to_split[:1], syllable_to_split[2:]
        else:
            return syllable_to_split[0], syllable_to_split[1:]

    gr_list = []

    for syllable in syllables:
        if len(syllable) < 2:
            logger.error(f"⚠️ Skipping malformed syllable for GYRM: '{syllable}'")
            continue

        try:
            tone = int(syllable[-1])
        except ValueError:
            logger.error(f"⚠️ Invalid tone in syllable: '{syllable}'")
            continue

        base_pinyin = syllable[:-1].lower()

        if base_pinyin not in corresponding_dict:
            logger.error(f"❌ Missing key in dictionary for GYRM: '{base_pinyin}'")
            continue

        initial, final = split_initial_final(base_pinyin)
        gr_base = corresponding_dict[base_pinyin][2]
        gr_equiv = None

        # GYRM tone transformation rules
        if tone == 1:
            if initial in ["l", "m", "n", "r"]:
                gr_equiv = gr_base[0] + "h" + gr_base[1:]
            else:
                gr_equiv = gr_base

        elif tone == 2:
            if initial in ["l", "m", "n", "r"]:
                gr_equiv = gr_base
            elif "i" in gr_base and final[-1] != "i":
                gr_equiv = gr_base.replace("i", "y")
            elif "i" in gr_base and final[-1] == "i":
                gr_equiv = gr_base.replace("i", "y") + "i"
            elif "u" in gr_base and final[-1] != "u":
                gr_equiv = gr_base.replace("u", "w")
            elif "u" in gr_base and final[-1] == "u":
                gr_equiv = gr_base.replace("u", "w") + "u"
            else:
                last_vowel_index = max(
                    (i for i, c in enumerate(gr_base) if c in "aeiou"), default=-1
                )
                if last_vowel_index != -1:
                    gr_equiv = (
                        gr_base[: last_vowel_index + 1]
                        + "r"
                        + gr_base[last_vowel_index + 1 :]
                    )
                else:
                    gr_equiv = gr_base

        elif tone == 3:
            if gr_base[0] in "iu":
                if gr_base.startswith("i"):
                    gr_equiv = gr_base.replace("i", "ye", 1)
                elif gr_base.startswith("u"):
                    gr_equiv = gr_base.replace("u", "wo", 1)
            elif "i" in gr_base and "u" in gr_base:
                if gr_base.index("i") < gr_base.index("u"):
                    gr_equiv = gr_base.replace("i", "e", 1)
                else:
                    gr_equiv = gr_base.replace("u", "o", 1)
            elif (
                "i" in gr_base and vowel_neighbor("i", gr_base) and "ei" not in gr_base
            ):
                gr_equiv = gr_base.replace("i", "e", 1)
            elif (
                "u" in gr_base
                and vowel_neighbor("u", gr_base)
                and "ou" not in gr_base
                and "uo" not in gr_base
            ):
                gr_equiv = gr_base.replace("u", "o", 1)
            else:
                if "uo" not in gr_base:
                    doubled = False
                    result = []
                    for char in gr_base:
                        if char in "aeiouy" and not doubled:
                            result.append(char * 2)
                            doubled = True
                        else:
                            result.append(char)
                    gr_equiv = "".join(result)
                else:
                    gr_equiv = gr_base.replace("o", "oo")

        elif tone == 4:
            if "i" in gr_base and _vowel_preceder("i", gr_base):
                gr_equiv = gr_base.replace("i", "y", 1)
            elif "u" in gr_base and _vowel_preceder("u", gr_base):
                gr_equiv = gr_base.replace("u", "w", 1)
            elif gr_base.endswith("n") or gr_base.endswith("l"):
                gr_equiv = gr_base + gr_base[-1]
            elif gr_base.endswith("ng"):
                gr_equiv = gr_base.replace("ng", "nq")
            else:
                gr_equiv = gr_base + "h"

            # Null-onset handling
            if gr_equiv.startswith("i"):
                if vowel_neighbor("i", gr_base):
                    gr_equiv = gr_equiv.replace("i", "y", 1)
                else:
                    gr_equiv = "y" + gr_equiv
            elif gr_equiv.startswith("u"):
                if vowel_neighbor("u", gr_base):
                    gr_equiv = gr_equiv.replace("u", "w", 1)
                else:
                    gr_equiv = "w" + gr_equiv
            if gr_equiv.endswith("iw"):
                gr_equiv = gr_equiv.replace("iw", "iuh")

        elif tone == 5:
            if base_pinyin in {"me", "ge", "zi"}:
                gr_equiv = base_pinyin[0]
            else:
                gr_equiv = gr_base

        if gr_equiv:
            gr_list.append(gr_equiv)

    return gr_list


def _zh_word_alternate_romanization(pinyin_string):
    """
    Takes a pinyin with tone-number string and returns a version of it in the
    legacy Yale, Wade-Giles, and Gwoyeu Romatzyh romanization schemes.
    This is only used for `zh_word` at the moment.

    Example: Pinyin ri4 guang1 (日光) becomes:
    * jih^4 kuang^1 in Wade Giles.
    * r^4 gwang^1 in Yale.
    * ryhguang in GYRM.

    :param pinyin_string: A numbered pinyin string (e.g. pin1 yin1).
    :return: A tuple (Yale romanization, Wade-Giles, GYRM).
    """

    # Load romanization mappings
    corresponding_dict = {}
    with open(Paths.DATASETS["ZH_ROMANIZATION"], "rt", encoding="utf-8-sig") as f:
        csv_file = csv.reader(f, delimiter=",")
        for row in csv_file:
            pinyin_p, yale_p, wadegiles_p, gr_p = row
            corresponding_dict[pinyin_p.strip().lower()] = [
                yale_p.strip(),
                wadegiles_p.strip(),
                gr_p.strip(),
            ]

    pinyin_string = _sanitize_pinyin_input(pinyin_string)
    syllables = pinyin_string.split()

    yale_list, wadegiles_list = [], []

    # Process Yale and Wade-Giles romanizations
    for syllable in syllables:
        if len(syllable) < 2:
            logger.error(f"⚠️ Skipping malformed syllable: '{syllable}'")
            continue

        tone = syllable[-1]
        base = syllable[:-1].lower().strip()

        if not base:
            logger.error(f"⚠️ Skipping syllable with empty base: '{syllable}'")
            continue

        if base not in corresponding_dict:
            logger.error(
                f"❌ Missing key in dictionary: '{base}' from syllable '{syllable}'"
            )
            continue

        def add_tone(roman):
            return f"{roman}^{tone}" if tone != "5" else roman

        yale_list.append(add_tone(corresponding_dict[base][0]))
        wadegiles_list.append(add_tone(corresponding_dict[base][1]))

    # Process Gwoyeu Romatzyh romanization
    gr_list = _process_gwoyeu_romatzyh(syllables, corresponding_dict)

    yale_post = " ".join(yale_list)
    wadegiles_post = " ".join(wadegiles_list)
    gr_post = "".join(gr_list)

    # Sole spelling exception for GYRM
    if "luomaa" in gr_post:
        gr_post = gr_post.replace("luomaa", "roma")

    return yale_post, wadegiles_post, gr_post


"""CHARACTER FUNCTIONS"""


def _old_chinese_search(character):
    """
    Retrieves Middle and Old Chinese readings for a character from a CSV
    using Baxter-Sagart's reconstruction.

    :param character: A single Chinese character.
    :return: A formatted string with readings if found, None otherwise.
    """
    mc_oc_readings = {}

    with open(Paths.DATASETS["OLD_CHINESE"], "r", encoding="utf-8") as f:
        reader = csv.reader(f)
        for row in reader:
            ch = row[0]
            mc = row[2].strip()
            oc = row[4].split("(", 1)[0].strip()
            mc_oc_readings[ch] = (mc, oc)

    if character not in mc_oc_readings:
        return None

    mc, oc = mc_oc_readings[character]
    result = f"\n| **Middle Chinese** | \\*{mc}* |"
    if oc:  # only include Old Chinese if it exists
        result += f"\n| **Old Chinese** | \\*{oc}* |"
    return result


def variant_character_search(search_term, retries=3):
    """
    Search the MOE dictionary for a link to character variants.
    Returns the full URL if found, else None.
    """
    search_term = search_term.strip()
    base_search_url = (
        f"https://dict.variants.moe.edu.tw/search.jsp?QTP=0&WORD={search_term}#searchL"
    )
    base_site = "https://dict.variants.moe.edu.tw/"

    session = requests.Session()
    timeout_amount = 4

    for attempt in range(retries):
        try:
            response = session.get(base_search_url, timeout=timeout_amount)
            response.raise_for_status()
            tree = html.fromstring(response.content)

            # XPath to the <a> element inside /html/body/main/div/form/div/a
            link_elements = tree.xpath("/html/body/main/div/form/div/a")

            if link_elements:
                href = link_elements[0].get("href")
                if href:
                    full_url = base_site + href
                    return full_url

            # If link not found, no need to retry, return None immediately
            return None

        except (requests.RequestException, IndexError) as e:
            logger.error(f"Encountered an error: {e}")
            # If not last attempt, wait a bit and retry
            if attempt < retries - 1:
                sleep(1)
                continue
            else:
                return None
    return None


def _min_hakka_readings(character):
    """
    Returns Hokkien and Hakka (Sixian) readings for a given Chinese
    character or word using the ROC Ministry of Education dictionary.

    :param character: A single Chinese character or multi-character word.
    :return: A formatted string with available readings.
    """

    def get_min_reading(char):
        url = f"https://www.moedict.tw/'{char}"
        response = requests.get(url, headers=useragent)
        tree = html.fromstring(response.content)

        with suppress(IndexError):
            annotation = tree.xpath(
                '//ru[contains(@class,"rightangle") and contains(@order,"0")]/@annotation'
            )[0]
            return f"\n| **Southern Min** | *{annotation}* |"
        return ""

    def get_hak_reading(char):
        url = f"https://www.moedict.tw/:{char}"
        response = requests.get(url, headers=useragent)
        tree = html.fromstring(response.content)

        reading = tree.xpath(
            'string(//span[contains(@data-reactid,"$0.6.2.1")])'
        ).strip()
        if not reading:
            return ""

        # Normalize and format superscript tones
        reading = re.sub(r"(\d{1,4})([a-z])", r"\1 \2", reading)
        formatted = []
        for word in reading.split():
            word = re.sub(r"([a-z])(\d)", r"\1^(\2)", word)
            formatted.append(word)
        return f"\n|**Hakka (Sixian)** | *{' '.join(formatted)}* |"

    min_reading = get_min_reading(character)
    hak_reading = get_hak_reading(character)

    return min_reading + hak_reading


def _contains_latin(text):
    """Helper function used to help detect Vietnamese readings."""
    return bool(re.search(r"[a-zA-ZÀ-ÿĀ-ž]", text))


def _vietnamese_readings(character, max_readings=4):
    """
    Function to obtain more accurate readings for Chinese characters
    in Vietnamese. Unicode's standard listings include lots of
    problematic entries. What we're looking for in particular, is
    Âm Hán Việt (音漢越).
    Extracts up to `max_readings` readings from span text in the
    main content block.
    """

    character = tradify(character)
    viet_dictionary_url = f"https://hvdic.thivien.net/whv/{character}"
    response = requests.get(viet_dictionary_url, headers=useragent)

    if response.status_code != 200:
        return None

    tree = html.fromstring(response.content)

    # Extract span texts
    raw_spans = tree.xpath(
        '//div[contains(@class,"whv") or contains(@class,"content")]//span/text()'
    )
    decoded_spans = [html_stdlib.unescape(s.strip()) for s in raw_spans if s.strip()]

    # Keep only words that are mostly letters (including Vietnamese)
    han_viet_readings = []
    for word in decoded_spans:
        if re.fullmatch(r"[^\W\d_]+", word, re.UNICODE):  # excludes digits and symbols
            han_viet_readings.append(word)
        if len(han_viet_readings) >= max_readings:
            break

    if not han_viet_readings:
        return None

    han_viet_readings = list(set(han_viet_readings))
    han_viet_readings = [x for x in han_viet_readings if _contains_latin(x)]
    readings_formatted = ", ".join(han_viet_readings)
    logger.info("Looked up Vietnamese readings for Chinese character.")

    return readings_formatted


def calligraphy_search(character):
    """
    Get an overall image of Chinese calligraphic styles from various
    sources. This can also be called by the Japanese character routine.

    :param character: A single Chinese character.
    :return: None if no image found; otherwise a formatted string with URLs and images.
    """
    character = simplify(character)
    unicode_assignment = (
        f"{ord(character):X}"  # Unicode in uppercase hex (no 0x prefix)
    )
    gx_url = f"https://www.sfds.cn/{unicode_assignment}/"

    variant_link = variant_character_search(tradify(character))
    variant_formatted = (
        f"[YTZZD]({variant_link})"
        if variant_link
        else "[YTZZD](https://dict.variants.moe.edu.tw/)"
    )

    formdata = {"sort": "7", "wd": character}
    try:
        with requests.Session() as session:
            response = session.post("https://www.shufazidian.com/", data=formdata)
            response.raise_for_status()
    except requests.RequestException:
        return None

    # Parse the page with BeautifulSoup and then convert to lxml tree for xpath
    soup = Bs(response.content, "lxml")
    tree = html.fromstring(str(soup))

    images = tree.xpath("//img/@src") or []
    complete_image = None

    for url in images:
        if len(url) < 20 or "gif" in url.lower():
            continue
        if "shufa6" in url:
            complete_image = url.replace("shufa6/1", "shufa6")
            break  # Assuming first matching image is enough

    if not complete_image:
        return None

    image_string = (
        f"\n\n**Chinese Calligraphy Variants**: [{character}]({complete_image}) "
        f"(*[SFZD](https://www.shufazidian.com/)*, *[SFDS]({gx_url})*, *{variant_formatted}*)"
    )

    logger.debug(f"[ZW] ZH-Calligraphy: Found calligraphic image for {character}.")
    return image_string


def _zh_character_other_readings(character):
    """
    Get Sino-Xenic (Korean, Vietnamese, Japanese) readings for a Chinese
    character from the Chinese Character Web API. Note that the Chinese
    Character Web API does not currently use HTTPS.

    :param character: A single Chinese character.
    :return: None or a Markdown-formatted string with readings.
    """
    # noinspection HttpUrlsUsage
    url = (
        "http://ccdb.hemiola.com/characters/string/{}"
        "?fields=kHangul,kKorean,kJapaneseKun,kJapaneseOn,kVietnamese"
    )

    try:
        response = requests.get(url.format(character), headers=useragent)
        response.raise_for_status()
        data = response.json()[0]
    except (IndexError, ValueError, requests.RequestException):
        return None

    results = []

    # Japanese readings
    ja_kun = data.get("kJapaneseKun") or ""
    ja_on = data.get("kJapaneseOn") or ""
    if ja_kun or ja_on:
        ja_kun = ja_kun.lower() + " " if ja_kun else ""
        ja_on = ja_on.upper() if ja_on else ""
        ja_combined = ", ".join((ja_kun + ja_on).strip().split())
        results.append(f"**Japanese** | *{ja_combined}*")

    # Korean readings
    ko_hangul = data.get("kHangul")
    if ko_hangul:
        ko_latin = Romanizer(ko_hangul).romanize().lower()
        ko_latin = ko_latin.replace(" ", ", ")
        ko_hangul_fmt = ko_hangul.replace(" ", ", ")
        results.append(f"**Korean** | {ko_hangul_fmt} / *{ko_latin}*")

    # Vietnamese reading
    vi_latin = _vietnamese_readings(character)
    if vi_latin is None:
        vi_latin = data.get("kVietnamese")
    if vi_latin:
        results.append(f"**Vietnamese** | *{vi_latin.lower()}*")

    return "\n".join(results) if results else None


async def zh_character(character):
    """
    Look up a Chinese character's pronunciations and meanings,
    combining multiple reference functions.

    :param character: Any Chinese character or string.
    :return: Formatted string containing the character's information.
    """

    multi_character_list = list(character)
    multi_mode = len(multi_character_list) > 1

    async with aiohttp.ClientSession(headers=useragent) as session:
        resp = await session.get(
            f"https://www.mdbg.net/chinese/dictionary?page=chardict&cdcanoce=0&cdqchi={character}"
        )
        content = await resp.text()
        tree = html.fromstring(content)

        pronunciation = [
            div.text_content() for div in tree.xpath('//div[contains(@class,"pinyin")]')
        ]
        if not pronunciation:
            to_post = RESPONSE.COMMENT_INVALID_ZH_CHARACTER.format(character)
            logger.info(f"[ZW] ZH-Character: No results for {character}")
            return to_post

    # Yue pronunciation alternates with Mandarin in list: even idx Mandarin, odd idx Yue
    cmn_pronunciation = pronunciation[::2]

    if not multi_mode:
        cmn_pronunciation = " / ".join(cmn_pronunciation)
        yue_pronunciation_list = tree.xpath(
            '//a[contains(@onclick,"pronounce-jyutping")]/text()'
        )
        yue_pronunciation = " / ".join(yue_pronunciation_list)

        # Add superscript to numbers (format for Reddit)
        for i in range(10):
            yue_pronunciation = yue_pronunciation.replace(str(i), f"^({i} ")
        for i in range(10):
            yue_pronunciation = yue_pronunciation.replace(str(i), f"{i})")

        meaning = "/ ".join(tree.xpath('//div[contains(@class,"defs")]/text()')).strip()

        if tradify(character) == simplify(character):
            logger.debug(
                f"[ZW] ZH-Character: The two versions of {character} are identical."
            )
            lookup_line_1 = (
                f"# [{character}](https://en.wiktionary.org/wiki/{character}#Chinese)\n\n"
                "| Language | Pronunciation |\n"
                "|----------|---------------|\n"
                f"| **Mandarin** | *{cmn_pronunciation}* |\n"
                f"| **Cantonese** | *{yue_pronunciation[:-1]}* |"
            )
        else:
            trad_char = tradify(character)
            simp_char = simplify(character)
            logger.debug(
                f"[ZW] ZH-Character: The two versions of {character} are *not* identical."
            )
            lookup_line_1 = (
                f"# [{trad_char} / {simp_char}](https://en.wiktionary.org/wiki/{trad_char}#Chinese)\n\n"
                "| Language | Pronunciation |\n"
                "|----------|---------------|\n"
                f"| **Mandarin** | *{cmn_pronunciation}* |\n"
                f"| **Cantonese** | *{yue_pronunciation[:-1]}* |"
            )

        # Add Hokkien and Hakka readings
        lookup_line_1 += (
            await call_sync_async(_min_hakka_readings, tradify(character)) or ""
        )

        # Old Chinese readings
        try:
            ocmc_pronunciation = await call_sync_async(
                _old_chinese_search, tradify(character)
            )
            if ocmc_pronunciation:
                lookup_line_1 += ocmc_pronunciation
        except IndexError:
            pass

        # Other Sino-Xenic readings
        other_readings_data = await call_sync_async(
            _zh_character_other_readings, tradify(character)
        )
        if other_readings_data:
            lookup_line_1 += f"\n{other_readings_data}"

        # Calligraphic examples
        calligraphy_image = await call_sync_async(calligraphy_search, character)
        if calligraphy_image:
            lookup_line_1 += calligraphy_image

        lookup_line_1 += f'\n\n**Meanings**: "{meaning}."'

    else:
        # MULTI CHARACTER MODE: build table
        duo_key = (
            f"# {character}"
            if tradify(character) == simplify(character)
            else f"# {tradify(character)} ({simplify(character)})"
        )
        duo_header = "\n\nCharacter"
        duo_separator = "\n---|"
        duo_mandarin = "\n**Mandarin**"
        duo_cantonese = "\n**Cantonese**"
        duo_meaning = "\n**Meanings**"

        multi_character_dict = {}

        for wenzi in multi_character_list:
            character_url = f"https://www.mdbg.net/chindict/chindict.php?page=chardict&cdcanoce=0&cdqchi={wenzi}"
            resp = await session.get(character_url)
            content = await resp.text()
            new_tree = html.fromstring(content)

            pronunciation = [
                div.text_content()
                for div in new_tree.xpath('//div[contains(@class,"pinyin")]')
            ]
            cmn_pronunciation = "*" + " ".join(pronunciation[::2]) + "*"

            yue_pronunciation_list = new_tree.xpath(
                '//a[contains(@onclick,"pronounce-jyutping")]/text()'
            )
            yue_pronunciation = " ".join(yue_pronunciation_list)
            for i in range(10):
                yue_pronunciation = yue_pronunciation.replace(str(i), f"^{i} ")
            yue_pronunciation = "*" + yue_pronunciation.strip() + "*"

            multi_character_dict[wenzi]["mandarin"] = cmn_pronunciation
            multi_character_dict[wenzi]["cantonese"] = yue_pronunciation

            meaning = "/ ".join(
                new_tree.xpath('//div[contains(@class,"defs")]/text()')
            ).strip()
            multi_character_dict[wenzi]["meaning"] = f'"{meaning}."'

            # Random delay to respect server
            await asyncio.sleep(random.randint(3, 12))

        # Construct Markdown table
        for key in multi_character_list:
            char_data = multi_character_dict[key]
            if tradify(key) == simplify(key):
                duo_header += (
                    f" | [{key}](https://en.wiktionary.org/wiki/{key}#Chinese)"
                )
            else:
                wt_link = f"https://en.wiktionary.org/wiki/{tradify(key)}"
                duo_header += (
                    f" | [{tradify(key)} ({simplify(key)})]({wt_link}#Chinese)"
                )
            duo_separator += "---|"
            duo_mandarin += f" | {char_data['mandarin']}"
            duo_cantonese += f" | {char_data['cantonese']}"
            duo_meaning += f" | {char_data['meaning']}"

        lookup_line_1 = (
            duo_key
            + duo_header
            + duo_separator
            + duo_mandarin
            + duo_cantonese
            + duo_meaning
        )

    lookup_line_2 = (
        f"\n\n\n^Information ^from "
        f"[^(Unihan)](https://www.unicode.org/cgi-bin/GetUnihanData.pl?codepoint={character}) ^| "
        f"[^(CantoDict)](https://www.cantonese.sheik.co.uk/dictionary/characters/{tradify(character)}/) ^| "
        f"[^(Chinese Etymology)](https://hanziyuan.net/#{tradify(character)}) ^| "
        f"[^(CHISE)](https://www.chise.org/est/view/char/{character}) ^| "
        f"[^(CTEXT)](https://ctext.org/dictionary.pl?if=en&char={tradify(character)}) ^| "
        f"[^(MDBG)](https://www.mdbg.net/chinese/dictionary?page=worddict&wdrst=1&wdqb={character}) ^| "
        f"[^(MoE DICT)](https://www.moedict.tw/'{tradify(character)}) ^| "
        f"[^(MFCCD)](https://humanum.arts.cuhk.edu.hk/Lexis/lexi-mf/search.php?word={tradify(character)}) ^| "
        f"[^(ZDIC)](https://www.zdic.net/hans/{simplify(character)}) ^| "
        f"[^(ZI)](https://zi.tools/zi/{tradify(character)})"
    )

    to_post = lookup_line_1 + lookup_line_2
    logger.info(
        f"[ZW] ZH-Character: Received lookup command for {character} in Chinese. Returned search results."
    )
    return to_post


"""WORD FUNCTIONS"""


async def _zh_word_dictionary_search(chinese_word, dictionary_type):
    """Searches the Buddhist and Cantonese local dictionaries for
    definitions."""
    if dictionary_type == "buddhist":
        file_address = Paths.DATASETS["ZH_BUDDHIST"]
    elif dictionary_type == "cantonese":
        file_address = Paths.DATASETS["ZH_CCANTO"]
    else:
        raise ValueError("dictionary_type must be either 'buddhist' or 'cantonese'")

    async with aiofiles.open(file_address, "r", encoding="utf-8") as f:
        lines = await f.read()
    lines = lines.splitlines()

    relevant_line = None
    for entry in lines:
        traditional_headword = entry.split(" ", 1)[0]
        if chinese_word == traditional_headword:
            relevant_line = entry
            break

    if relevant_line is None:
        return None

    meanings = (
        relevant_line.partition("/")[2].replace('"', "'").rstrip("/").strip().split("/")
    )
    pinyin = relevant_line.partition("[")[2].partition("]")[0]

    if dictionary_type == "buddhist":
        if len(meanings) > 2:
            meanings = meanings[:2]
            meanings[-1] += "."
        formatted_meaning = (
            '\n\n**Buddhist Meanings**: "{}"'.format("; ".join(meanings))
            + " ([Soothill-Hodous](https://mahajana.net/en/library/texts/a-dictionary-of-chinese-buddhist-terms))"
        )
        return {"meaning": formatted_meaning, "pinyin": pinyin}

    else:
        jyutping = relevant_line.partition("{")[2].partition("}")[0]
        for digit in map(str, range(10)):
            jyutping = jyutping.replace(digit, f"^{digit} ")
        jyutping = " ".join(jyutping.split())
        formatted_meaning = (
            '\n\n**Cantonese Meanings**: "{}."'.format("; ".join(meanings))
            + f" ([CC-Canto](https://cantonese.org/search.php?q={chinese_word}))"
        )
        return {"meaning": formatted_meaning, "pinyin": pinyin, "jyutping": jyutping}


async def _zh_word_tea_dictionary_search(chinese_word):
    """Searches the Babelcarp dictionary for tea definitions."""
    general_dictionary = {}
    web_search = (
        f"https://babelcarp.org/babelcarp/babelcarp.cgi?phrase={chinese_word}&define=1"
    )

    try:
        async with httpx.AsyncClient() as client:
            eth_page = await client.get(web_search, headers=useragent)
        tree = html.fromstring(eth_page.content)
        text_nodes = tree.xpath('//*[@id="translation"]//text()')
    except httpx.RequestError:
        return None

    text_nodes = [t.strip() for t in text_nodes if t.strip()]
    if not text_nodes:
        return None

    pinyin_line_index = None
    pinyin = None
    for i, line in enumerate(text_nodes):
        match = re.search(r"\(([\w\s]+)\)", line)
        if match:
            pinyin = match.group(1).lower()
            pinyin_line_index = i
            break

    if pinyin_line_index is None or pinyin is None:
        return None

    meaning_parts = text_nodes[pinyin_line_index + 1 :]
    if not meaning_parts:
        return None

    meaning = " ".join(meaning_parts).replace(" )", " ").replace("  ", " ").strip()
    if "Don′t know" in meaning:
        return None

    formatted_line = f'\n\n**Tea Meanings**: "{meaning}." ([Babelcarp]({web_search}))"'

    general_dictionary["meaning"] = formatted_line
    general_dictionary["pinyin"] = _convert_numbered_pinyin(pinyin)

    return general_dictionary


async def zh_word_chengyu_supplement(chengyu):
    """Searches the dictionaries for chengyu definitions to supplement
    zh_word."""
    headers = {
        "Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
        "Accept-Encoding": "gzip, deflate, br",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    }
    headers.update(useragent)

    simplified_chengyu = simplify(chengyu)
    chengyu_gb_bytes = simplified_chengyu.encode("gb2312")
    chengyu_gb_hex = "".join(f"%{b:02X}" for b in chengyu_gb_bytes)

    # noinspection HttpUrlsUsage
    search_url = f"http://cy.5156edu.com/serach.php?f_type=chengyu&f_type2=&f_key={chengyu_gb_hex}"
    logger.debug(f"ZH-Chengyu search URL: {search_url}")

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(search_url, headers=headers)
            response.encoding = "gb2312"
            page_tree = html.fromstring(response.text)
            chengyu_result_texts = page_tree.xpath("//table[2]//td//text()")
    except (UnicodeEncodeError, UnicodeDecodeError, httpx.RequestError) as e:
        logger.error(f"[ZW] ZH-Chengyu: Unicode or connection error: {e}")
        return None

    if "找到 0 个成语" in "".join(chengyu_result_texts):
        logger.info(f"[ZW] ZH-Chengyu: No chengyu results found for {chengyu}.")
        return None

    link_elements = page_tree.xpath('//tr[contains(@bgcolor, "#ffffff")]/td/a')
    if not link_elements:
        return None

    detail_url = link_elements[0].get("href")
    logger.info(f"[ZW] > ZH-Chengyu: Found chengyu detail page at: {detail_url}")

    try:
        detail_response = await client.get(detail_url, headers=headers)
        detail_response.encoding = "gb2312"
        detail_tree = html.fromstring(detail_response.text)
    except httpx.RequestError as e:
        logger.error(f"[ZW] ZH-Chengyu: Error fetching detail page: {e}")
        return None

    meaning_xpath = "//tr[td[1][contains(normalize-space(.), '解释：')]]/td[2]/text()"
    literary_source_xpath = (
        "//tr[td[1][contains(normalize-space(.), '出处：')]]/td[2]/text()"
    )

    meaning_list = detail_tree.xpath(meaning_xpath)
    literary_source_list = detail_tree.xpath(literary_source_xpath)

    meaning = meaning_list[0].strip() if meaning_list else ""
    literary_source = literary_source_list[0].strip() if literary_source_list else ""
    logger.debug(f" Found {meaning}, {literary_source}")

    return (
        f"\n\n**Chinese Meaning**: {meaning}\n\n"
        f"**Literary Source**: {literary_source}"
        f" ([5156edu]({detail_url}), [18Dao](https://tw.18dao.net/成語詞典/{tradify(chengyu)}))"
    )


async def zh_word(word):
    """
    Defines a Chinese word (typically >1 character), returning its readings and meanings.

    :param word: Any Chinese word (usually more than one character).
    :return: Formatted string containing pronunciation and meanings.
    """
    alternate_meanings = []
    alternate_pinyin = ()
    alternate_jyutping = None

    async with httpx.AsyncClient(timeout=10) as client:
        # MDBG dictionary lookup
        mdbg_url = f"https://www.mdbg.net/chinese/dictionary?page=worddict&wdrst=0&wdqb=c:{word}"
        response = await client.get(mdbg_url, headers=useragent)
        tree = html.fromstring(response.content)
        word_exists = str(
            tree.xpath('//p[contains(@class,"nonprintable")]/strong/text()')
        )

        # Basic Mandarin pinyin
        cmn_pronunciation = "".join(
            tree.xpath('//div[contains(@class,"pinyin")]/a/span/text()')[: len(word)]
        )

        if "No results found" in word_exists:
            trad_word, simp_word = tradify(word), simplify(word)
            search_buddhist = await _zh_word_dictionary_search(trad_word, "buddhist")
            search_tea = await _zh_word_tea_dictionary_search(simp_word)
            search_cccanto = await _zh_word_dictionary_search(trad_word, "cantonese")

            if not any([search_buddhist, search_tea, search_cccanto]):
                logger.info(
                    "[ZW] ZH-Word: No results found. Getting individual characters instead."
                )
                if len(word) < 2:
                    return await zh_character(word)
                return "\n\n" + "\n\n".join([await zh_character(char) for char in word])

            for result in [search_buddhist, search_tea, search_cccanto]:
                if result:
                    alternate_meanings.append(result["meaning"])
                    alternate_pinyin = result["pinyin"]
                    if "jyutping" in result:
                        alternate_jyutping = result["jyutping"]

            logger.info(
                f"[ZW] ZH-Word: No results for '{word}', but specialty dictionaries returned matches."
            )

        if not alternate_meanings:
            try:
                onclick = tree.xpath('//div[contains(@class,"pinyin")]/a/@onclick')[0]
                match = re.search(r'\|([^|]*)"', onclick)
                py_split = match.group(1).strip() if match else ""
                logger.info(f">>> Pinyin string to look up: {py_split}")
                alt_romanize = _zh_word_alternate_romanization(py_split)
            except IndexError:
                alt_romanize = ("---", "---", "---")

            # Definitions
            meaning_blocks = [
                div.text_content()
                for div in tree.xpath('//div[contains(@class,"defs")]')
            ]
            meaning = "/ ".join(
                x.strip() for x in meaning_blocks if x.strip() not in {"", ", "}
            ).strip()

            # Cantonese.org pronunciation
            yue_url = f"https://cantonese.org/search.php?q={word}"
            yue_response = await client.get(yue_url, headers=useragent)
            yue_tree = html.fromstring(yue_response.content)
            yue_pronunciation_raw = yue_tree.xpath(
                '//h3[contains(@class,"resulthead")]/small/strong//text()'
            )
            yue_syllables = yue_pronunciation_raw[: len(word) * 2]
            yue_pronunciation = _pair_syllables_with_tones(yue_syllables)
            yue_pronunciation = re.sub(r"(\d)", r"^(\1)", yue_pronunciation)
        else:
            cmn_pronunciation = _convert_numbered_pinyin(alternate_pinyin)
            alt_romanize = _zh_word_alternate_romanization(alternate_pinyin)
            yue_pronunciation = alternate_jyutping or None
            meaning = "\n".join(alternate_meanings)

    is_same_script = tradify(word) == simplify(word)
    lookup_header = (
        f"# [{word}](https://en.wiktionary.org/wiki/{word}#Chinese)"
        if is_same_script
        else f"# [{tradify(word)} / {simplify(word)}](https://en.wiktionary.org/wiki/{tradify(word)}#Chinese)"
    )

    pronunciation_block = (
        "\n\n| Language | Pronunciation |"
        "\n|---------|--------------|"
        f"\n| **Mandarin** (Pinyin) | *{cmn_pronunciation}* |"
        f"\n| **Mandarin** (Wade-Giles) | *{alt_romanize[1]}* |"
        f"\n| **Mandarin** (Yale) | *{alt_romanize[0]}* |"
        f"\n| **Mandarin** (GR) | *{alt_romanize[2]}* |"
    )

    # Only add Cantonese row if we have valid pronunciation
    if yue_pronunciation and yue_pronunciation != "---":
        pronunciation_block += f"\n| **Cantonese** | *{yue_pronunciation}* |"

    min_hak_data = _min_hakka_readings(tradify(word))
    lookup_header += pronunciation_block + min_hak_data

    if not alternate_meanings:
        meaning_section = f'\n\n**Meanings**: "{meaning}."'
        if len(word) == 4:
            chengyu_info = await zh_word_chengyu_supplement(word)
            if chengyu_info:
                logger.info("[ZW] ZH-Word: >> Added additional chengyu data.")
                meaning_section += chengyu_info

        buddhist_main = await _zh_word_dictionary_search(tradify(word), "buddhist")
        if buddhist_main:
            meaning_section += buddhist_main["meaning"]
    else:
        meaning_section = f"\n{meaning}"

    footer = (
        "\n\n^Information ^from "
        f"[^CantoDict](https://www.cantonese.sheik.co.uk/dictionary/search/?searchtype=1&text={tradify(word)}) ^| "
        f"[^MDBG](https://www.mdbg.net/chinese/dictionary?page=worddict&wdrst=0&wdqb=c:{word}) ^| "
        f"[^Yellowbridge](https://yellowbridge.com/chinese/dictionary.php?word={word}) ^| "
        f"[^Youdao](https://dict.youdao.com/w/eng/{word}/#keyfrom=dict2.index) ^| "
        f"[^ZDIC](https://www.zdic.net/hans/{simplify(word)})"
    )

    result = lookup_header + meaning_section + "\n\n" + footer
    logger.info(
        f"[ZW] ZH-Word: Received a lookup command for '{word}'. Returned search results."
    )
    return result


"""INQUIRY SECTION"""


def show_menu():
    print("\nSelect a search to run:")
    print("1. zh_character (search for a single Chinese character)")
    print("2. zh_word (search for a Chinese word)")
    print("3. zh_word_chengyu_supplement (search for a chengyu addition)")
    print("4. variant_character_search (search for a variant character)")
    print("5. tea dictionary search ")
    print("x. Exit")


if __name__ == "__main__":
    while True:
        show_menu()
        choice = input("Enter your choice (0-5): ")

        if choice == "x":
            print("Exiting...")
            break

        if choice not in ["1", "2", "3", "4", "5"]:
            print("Invalid choice, please try again.")
            continue

        my_test = input("Enter the string you wish to test: ")

        if choice == "1":
            print(asyncio.run(zh_character(my_test)))
        elif choice == "2":
            print(asyncio.run(zh_word(my_test)))
        elif choice == "3":
            print(zh_word_chengyu_supplement(my_test))
        elif choice == "4":
            print(variant_character_search(my_test))
        elif choice == "5":
            print(asyncio.run(_zh_word_tea_dictionary_search(my_test)))
