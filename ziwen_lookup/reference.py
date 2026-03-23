#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
Contains functions that deal with retrieving data about specific
languages from Wikipedia and Ethnologue. This is usually called
'reference' data. This data is used to populate the main
language data YAML file, among other things.
...

Logger tag: [L:REF]
"""

import logging
import re

import requests
import waybackpy
import wikipedia
import yaml
from lxml import html
from waybackpy import exceptions

from config import Paths
from config import logger as _base_logger
from lang.languages import converter, get_lingvos
from reddit.connection import get_random_useragent

logger = logging.LoggerAdapter(_base_logger, {"tag": "L:REF"})


# ─── Internal fetch helpers ───────────────────────────────────────────────────


def _fetch_sil_language_data(language_code: str) -> dict | None:
    """
    Fetch language reference data from SIL ISO 639-3 as a fallback.
    Raises a ValueError if the language code is in ISO 639-2 instead.

    :param language_code: ISO 639-3 language code
    :return: Dictionary with basic SIL data, or None if invalid
    """
    url = f"https://iso639-3.sil.org/code/{language_code.lower()}"
    logger.debug(f"Fetching URL: {url}")

    try:
        response = requests.get(url, headers=get_random_useragent(), timeout=10)
        response.raise_for_status()
        logger.debug(f"Response status: {response.status_code}")
    except requests.RequestException as e:
        logger.error(f"Could not fetch page for `{language_code}`: {e}")
        return None

    tree = html.fromstring(response.content)

    header_elements = tree.xpath('//div[contains(@class,"region-content")]//h2/text()')
    logger.debug(f"Header elements found: {header_elements}")

    if not header_elements:
        logger.warning(f"Could not find header for `{language_code}`")
        return None

    header_text = header_elements[0].strip()
    logger.debug(f"Found header: {header_text}")
    name = header_text.split("[")[0].strip()

    code_sets_elements = tree.xpath("//table//tr/td[4]/text()")
    logger.debug(f"Code sets found: {code_sets_elements}")

    if not code_sets_elements:
        logger.warning(f"Could not find code sets for `{language_code}`")
        return None

    code_sets_text = code_sets_elements[0].strip()
    logger.debug(f"Found code sets: {code_sets_text}")
    if "639-2" in code_sets_text and "639-3" not in code_sets_text:
        raise ValueError(f"[SIL] Code `{language_code}` is only 639-2, not 639-3")

    sil_data = {"language_code_3": language_code.lower(), "name": name, "link_sil": url}

    logger.info(f"Fetched SIL data for `{language_code}`: {sil_data}")
    return sil_data


def _get_archived_ethnologue_page(language_code: str) -> str | None:
    """
    Retrieve an archived Ethnologue page for a given language code
    from the Wayback Machine.

    This accesses a snapshot from a time when Ethnologue still had public data.

    :param language_code: ISO 639-3 language code of the language
    :return: URL of the archived page, or None if unavailable
    """
    ethnologue_url = f"https://www.ethnologue.com/language/{language_code}"
    user_agent = get_random_useragent()

    cdx_api = waybackpy.WaybackMachineCDXServerAPI(ethnologue_url, str(user_agent))

    try:
        archived_snapshot = cdx_api.near(year=2019, month=6, day=6, hour=12, minute=0)
    except exceptions.NoCDXRecordFound:
        logger.warning(
            f"No archived Ethnologue page found for `{language_code}` "
            f"(URL: {ethnologue_url})."
        )
        return None
    except exceptions.WaybackError as e:
        logger.error(
            f"Wayback Machine error while retrieving `{language_code}` "
            f"(URL: {ethnologue_url}): {e}"
        )
        return None
    except requests.exceptions.ConnectTimeout:
        logger.error(
            f"Connection timed out when accessing Wayback Machine for `{language_code}`."
        )
        return None
    except requests.exceptions.RetryError:
        logger.error(
            "Wayback Machine service unavailable — RetryError raised "
            f"while retrieving `{language_code}`."
        )
        return None
    except Exception as e:
        logger.exception(
            f"Unexpected error occurred while retrieving archived page for `{language_code}` "
            f"(URL: {ethnologue_url}) | Error {e}."
        )
        return None

    return archived_snapshot.archive_url


def _fetch_language_reference_data(lookup_url: str, language_code: str) -> dict | None:
    """
    Fetch reference data for a language from Ethnologue and Wikipedia.

    :param lookup_url: URL of the Ethnologue page (typically from Web Archive)
    :param language_code: ISO 639-1/3 language code of the language
    :return: Dictionary containing language reference data, or None if unavailable
    """
    language_data = get_lingvos()  # Provides Lingvos
    useragent = get_random_useragent()
    lingvo_object = language_data.get(language_code)

    if not lookup_url:
        return None

    try:
        language_code = lookup_url.rsplit("/", 1)[-1].lower()
        if len(language_code) == 2:
            if lingvo_object is None:
                logger.error(f"No lingvo data found for `{language_code}`.")
                return None
            if lingvo_object.language_code_3 is None:
                logger.error(f"No ISO 639-3 code found for `{language_code}`.")
                return None
            language_code = lingvo_object.language_code_3
        logger.info(f"Now searching for: `{language_code}` at {lookup_url}.")
    except Exception as e:
        logger.error(f"Error extracting language code from URL `{lookup_url}`: {e}")
        return None

    ref_data: dict = {"language_code_3": language_code}

    try:
        response = requests.get(lookup_url, headers=useragent)
        response.raise_for_status()
        tree = html.fromstring(response.content)
    except requests.RequestException as e:
        logger.error(f"Could not fetch Ethnologue page for `{language_code}`: {e}")

        # SIL backup for historical/extinct languages like Tangut.
        sil_data = _fetch_sil_language_data(language_code)
        if sil_data:
            logger.info(
                f"No Ethnologue entry. Found SIL data for `{language_code}`: {sil_data}"
            )
            ref_data.update(sil_data)
            return ref_data

        return None

    try:
        language_exist = tree.xpath(
            '//div[contains(@class,"view-display-id-page")]/div/text()'
        )[0]
        if not language_exist:
            return None
    except IndexError:
        return None

    _lingvo = converter(language_code)
    ref_data["name"] = _lingvo.name if _lingvo is not None else language_code
    try:
        alt_names_raw = tree.xpath(
            '//div[contains(@class,"alternate-names")]/div[2]/div/text()'
        )[0]
        alt_names = [
            name.strip() for name in alt_names_raw.split(",") if "pej." not in name
        ]
        alt_names = [x for x in alt_names if len(x) > 4]
        ref_data["name_alternates"] = alt_names
    except IndexError:
        ref_data["name_alternates"] = []

    try:
        population_text = tree.xpath(
            '//div[contains(@class,"field-population")]/div[2]/div/p/text()'
        )[0]
        numbers = [
            int(n.replace(",", ""))
            for n in re.findall(r"\d{1,3}(?:,\d{3})*(?:\.\d+)?", population_text)
        ]
        ref_data["population"] = max(numbers) if numbers else 0
    except IndexError:
        logger.warning(
            f"Problem fetching population for `{language_code}`, defaulting to 0."
        )
        ref_data["population"] = 0

    try:
        country_list = (
            tree.xpath('//div[contains(@class,"a-language-of")]/div/div/h2/a/text()')
            or tree.xpath(
                '//div[contains(@class,"field-ethnologue-language-of")]//h2/a/text()'
            )
            or tree.xpath(
                '//div[contains(text(), "A language of")]/..//a[contains(@href, "/country/")]/text()'
            )
            or tree.xpath('//h2[contains(., "A language of")]/a/text()')
        )

        if country_list:
            ref_data["country"] = str(country_list[0]).strip()
        else:
            logger.warning(f"Could not find country for `{language_code}`.")
            ref_data["country"] = ""
    except Exception as e:
        logger.warning(f"Error retrieving country for `{language_code}`: {e}")
        ref_data["country"] = ""

    try:
        family_data = tree.xpath(
            '//div[contains(@class,"field-name-language-classification-link")]//a/text()'
        )[0]
        ref_data["family"] = (
            family_data.split(",")[0].strip() if family_data else "Unknown"
        )
    except IndexError:
        ref_data["family"] = "Unknown"

    try:
        wk_page = wikipedia.page(
            title=f"ISO 639:{language_code}",
            auto_suggest=False,
            redirect=True,
            preload=False,
        )
        ref_data["link_wikipedia"] = wk_page.url
    except (wikipedia.exceptions.PageError, wikipedia.exceptions.DisambiguationError):
        ref_data["link_wikipedia"] = ""

    ref_data["link_ethnologue"] = f"https://www.ethnologue.com/language/{language_code}"

    logger.info(f"Final reference data for `{language_code}`: {ref_data}")

    # Save new data if not already stored.
    language_data_path = Paths.DATASETS["LANGUAGE_DATA"]
    with open(language_data_path, "r", encoding="utf-8") as f:
        existing_data = yaml.safe_load(f) or {}
    if language_code not in existing_data:
        existing_data[language_code] = ref_data

        with open(language_data_path, "w", encoding="utf-8") as f:
            yaml.dump(existing_data, f, allow_unicode=True, sort_keys=True)
            logger.info(f"Data for `{language_code}` has been added.")

    return ref_data


# ─── Public API ───────────────────────────────────────────────────────────────


def get_language_reference(language_code: str) -> dict | None:
    """
    Retrieve reference data for a language by first fetching its archived
    Ethnologue page and then parsing the reference information.

    :param language_code: ISO 639-3 (or ISO 639-1) language code
    :return: Dictionary containing reference data, or None if unavailable
    """
    archived_url = _get_archived_ethnologue_page(language_code)
    if not archived_url:
        logger.error(f"Could not retrieve archived URL for `{language_code}`.")
        return None

    reference_data = _fetch_language_reference_data(archived_url, language_code)
    if not reference_data:
        logger.error(f"Could not retrieve reference data for `{language_code}`.")
        return None

    return reference_data
