#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
Contains functions that deal with retrieving data about specific
languages from Wikipedia and Ethnologue. This is usually called
'reference' data. This data is used to populate the main
language data YAML file, among other things.
"""
import re
import requests

import waybackpy
import wikipedia
import yaml
from lxml import html
from waybackpy import exceptions

from config import Paths
from connection import logger, get_random_useragent
from languages import converter, load_lingvo_dataset, select_random_language


def get_archived_ethnologue_page(language_code: str) -> str | None:
    """
    Retrieve an archived Ethnologue page for a given language code
    from the Wayback Machine.

    This accesses a snapshot from a time when Ethnologue still had public data.

    :param language_code: ISO 639-3 language code of the language
    :return: URL of the archived page, or None if unavailable
    """
    ethnologue_url = f"https://www.ethnologue.com/language/{language_code}"
    user_agent = "Wenyuan, looking up old language data"
    cdx_api = waybackpy.WaybackMachineCDXServerAPI(ethnologue_url, user_agent)

    try:
        archived_snapshot = cdx_api.near(year=2019, month=6, day=6, hour=12, minute=0)
    except (
        waybackpy.exceptions.NoCDXRecordFound,
        waybackpy.exceptions.WaybackError,
        requests.exceptions.ConnectTimeout,
    ):
        logger.error(f"[WY] Could not retrieve archived data for `{language_code}`.")
        return None
    except requests.exceptions.RetryError:
        logger.error("[WY] Wayback Machine is currently unavailable.")
        return None

    return archived_snapshot.archive_url


def fetch_language_reference_data(lookup_url: str, language_code: str) -> dict | None:
    """
    Fetch reference data for a language from Ethnologue and Wikipedia.

    :param lookup_url: URL of the Ethnologue page (typically from Web Archive)
    :param language_code: ISO 639-1/3 language code of the language
    :return: Dictionary containing language reference data, or None if unavailable
    """
    language_data = load_lingvo_dataset()  # Provides Lingvos
    useragent = get_random_useragent()
    lingvo_object = language_data.get(language_code)

    if not lookup_url:
        return None

    # Extract ISO 639-3 language code from URL
    try:
        language_code = lookup_url.rsplit("/", 1)[-1].lower()
        if len(language_code) == 2:
            language_code = lingvo_object.language_code_3  # Fetch the 639-3 version
        logger.info(f"Now searching for: `{language_code}` at {lookup_url}.")
    except Exception as e:
        logger.error(f"Error extracting language code from URL `{lookup_url}`: {e}")
        return None

    ref_data: dict = {"language_code_3": language_code}

    # Fetch the Ethnologue page
    try:
        response = requests.get(lookup_url, headers=useragent)
        response.raise_for_status()
        tree = html.fromstring(response.content)
    except requests.RequestException as e:
        logger.error(f"[Reference] Could not fetch Ethnologue page for `{language_code}`: {e}")
        return None

    # Check if the language exists on the page
    try:
        language_exist = tree.xpath('//div[contains(@class,"view-display-id-page")]/div/text()')[0]
        if not language_exist:
            return None
    except IndexError:
        return None

    # Language names
    ref_data["name"] = converter(language_code).name
    try:
        alt_names_raw = tree.xpath('//div[contains(@class,"alternate-names")]/div[2]/div/text()')[0]
        alt_names = [name.strip() for name in alt_names_raw.split(",") if "pej." not in name]
        ref_data["name_alternates"] = alt_names
    except IndexError:
        ref_data["name_alternates"] = []

    # Population
    try:
        population_text = tree.xpath('//div[contains(@class,"field-population")]/div[2]/div/p/text()')[0]
        numbers = [int(n.replace(",", "")) for n in re.findall(r'\d{1,3}(?:,\d{3})*(?:\.\d+)?', population_text)]
        ref_data["population"] = max(numbers) if numbers else 0
    except IndexError:
        logger.warning(f"[Reference] Problem fetching population for `{language_code}`, defaulting to 0.")
        ref_data["population"] = 0

    # Country
    try:
        country_list = tree.xpath('//div[contains(@class,"a-language-of")]/div/div/h2/a/text()')
        if country_list:
            ref_data["country"] = str(country_list[0]).strip()
        else:
            logger.warning(f"[Reference] Could not find country for `{language_code}`.")
            ref_data["country"] = ""
    except Exception as e:
        logger.warning(f"[Reference] Error retrieving country for `{language_code}`: {e}")
        ref_data["country"] = ""

    # Language family
    try:
        family_data = tree.xpath('//div[contains(@class,"field-name-language-classification-link")]//a/text()')[0]
        ref_data["family"] = family_data.split(",")[0].strip() if family_data else "Unknown"
    except IndexError:
        ref_data["family"] = "Unknown"

    # Wikipedia link
    try:
        wk_page = wikipedia.page(title=f"ISO 639:{language_code}", auto_suggest=False, redirect=True, preload=False)
        ref_data["link_wikipedia"] = wk_page.url
    except (wikipedia.exceptions.PageError, wikipedia.exceptions.DisambiguationError):
        ref_data["link_wikipedia"] = ""

    # Ethnologue link
    ref_data["link_ethnologue"] = f"https://www.ethnologue.com/language/{language_code}"

    logger.info(f"Final reference data for `{language_code}`: {ref_data}")

    # Save new data if not already stored
    language_data_path = Paths.DATASETS["LANGUAGE_DATA"]
    with open(language_data_path, "r", encoding="utf-8") as f:
        existing_data = yaml.safe_load(f) or {}
    # Check and update if key doesn't exist
    if language_code not in existing_data:
        existing_data[language_code] = ref_data

        # Write updated YAML back to file
        with open(language_data_path, "w", encoding="utf-8") as f:
            yaml.dump(existing_data, f, allow_unicode=True, sort_keys=True)
            logger.info(f"[Reference] Data for `{language_code}` has been added.")

    return ref_data


def get_language_reference(language_code: str) -> dict | None:
    """
    Retrieve reference data for a language by first fetching its archived
    Ethnologue page and then parsing the reference information.

    :param language_code: ISO 639-3 (or ISO 639-1) language code
    :return: Dictionary containing reference data, or None if unavailable
    """
    # Step 1: Get archived Ethnologue page URL
    archived_url = get_archived_ethnologue_page(language_code)
    if not archived_url:
        logger.error(f"[Reference] Could not retrieve archived URL for `{language_code}`.")
        return None

    # Step 2: Fetch and parse reference data from the archived page
    reference_data = fetch_language_reference_data(archived_url, language_code)
    if not reference_data:
        logger.error(f"[Reference] Could not retrieve reference data for `{language_code}`.")
        return None

    return reference_data


def show_menu():
    print("\nSelect a search to run:")
    print("1. Language selection (enter your own language code)")
    print("2. Random (retrieve information for a random language code)")


if __name__ == "__main__":
    while True:
        show_menu()
        choice = input("Enter your choice (1-2): ")

        if choice == "x":
            print("Exiting...")
            break

        if choice not in ["1", "2"]:
            print("Invalid choice, please try again.")
            continue

        if choice == "1":
            my_input = input("Enter a language code to search for: ")
            print(get_language_reference(my_input))
        elif choice == "2":
            random_selection = select_random_language()
            logger.info(f"[Reference] Randomly selected {random_selection.name} (`{random_selection.preferred_code}`).")
            print(get_language_reference(random_selection.language_code_3))
