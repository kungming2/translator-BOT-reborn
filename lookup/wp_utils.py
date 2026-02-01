#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
Contains functions that deal with Wikipedia access.
"""

import re

import wikipedia

from config import logger
from languages import converter
from lookup.osm import search_nominatim


"""WIKIPEDIA DETECTOR (COMMENTS)"""


def wikipedia_lookup(terms: str | list[str], language_code: str = "en") -> str | None:
    """
    Basic function to look up terms on Wikipedia.

    :param terms: A list of strings to look up. Alternatively, accepts
                  a single string for compatability.
    :param language_code: Which Wikipedia language to look up in.
    :return: A properly formatted paragraph of entries if there are
             results, otherwise `None`.
    """
    entries: list[str] = []
    if isinstance(terms, str):
        terms = [terms]
    elif not isinstance(terms, list):
        raise TypeError(
            "Wikipedia lookup: 'terms' must be a string or a list of strings."
        )

    # Code for searching non-English Wikipedia, currently not needed.
    if language_code != "en":
        lang_code: str = converter(language_code).preferred_code
        wikipedia.set_lang(lang_code)
    logger.info(f"Looking up term {terms} on the `{language_code}` Wikipedia.")

    # Look up the terms and format them appropriately.
    for term in terms[:5]:  # Limit to five terms.
        term_entry: str | None = None
        term: str = re.sub(r"[^\w\s:]", "", term)  # Strip punctuation but allow colons
        logger.info(f"> Now searching for '{term}'...")

        # By default, turn off auto suggest.
        try:
            term_summary: str = wikipedia.summary(
                term, auto_suggest=False, redirect=True, sentences=3
            )
            wikipage_obj = wikipedia.page(term, auto_suggest=False, redirect=True)
        except (
            wikipedia.exceptions.DisambiguationError,
            wikipedia.exceptions.PageError,
        ):
            # No direct matches, try auto suggest.
            try:
                term_summary: str = wikipedia.summary(term.strip(), sentences=3)
                wikipage_obj = wikipedia.page(term.strip())
                term_entry: str = wikipage_obj.url
            except (
                wikipedia.exceptions.DisambiguationError,
                wikipedia.exceptions.PageError,
            ):
                # Still no dice.
                logger.error(f">> Unable to resolve '{term}' on Wikipedia. Skipping.")
                continue  # Exit.

        # Clean up the text for the entry.
        term_format: str = term.replace(" ", "_")
        if "\n" in term_summary:
            term_summary = term_summary.split("\n")[0].strip()
        if "==" in term_summary:
            term_summary = term_summary.split("==")[0].strip()
        if not term_entry:
            term_entry = f"https://en.wikipedia.org/wiki/{term_format}"
        term_entry = term_entry.replace(")", r"\)")
        logger.info(f">> Text for {term} to be obtained from `{term_entry}`.")

        # Form the entry text.
        entry_text = f"\n**[{term.title()}]({term_entry})**\n\n> {term_summary}\n\n"

        # Try to get location data if we have a page object
        if wikipage_obj:
            location_data = get_page_location_data(wikipage_obj)
            if location_data:
                entry_text += location_data + "\n"

        entries.append(entry_text)
        logger.info(f">> Information for '{term}' retrieved.")

    if entries:
        body_text: str = "\n".join(entries)
        logger.info("> Wikipedia entry data obtained.")
        return body_text

    return None


def get_page_location_data(wikipage_obj: wikipedia.WikipediaPage) -> str | None:
    """
    Fetch Wikipedia page coordinates and search for matching OSM locations.

    Args:
        wikipage_obj: Wikipedia page object to search for

    Returns:
        Formatted Markdown string with OSM search results, or None if no coordinates

    Raises:
        AttributeError: If the Wikipedia page contains no coordinates
    """

    # Debug: print page attributes
    logger.debug(f"Wikipedia page: {wikipage_obj.title} at {wikipage_obj.url}")

    # Extract and format coordinates
    try:
        coords = wikipage_obj.coordinates
        if not coords:
            logger.warning("Wikipedia page contains no coordinates.")
            return None
    except (KeyError, AttributeError):
        logger.warning("Wikipedia page contains no coordinates.")
        return None

    logger.debug(f"Original detailed coordinates: {wikipage_obj.coordinates}")

    lat_rounded: float = round(float(wikipage_obj.coordinates[0]), 4)
    lon_rounded: float = round(float(wikipage_obj.coordinates[1]), 4)
    formatted_coords: str = f" {lat_rounded},{lon_rounded}"

    logger.info(f"> Searching for rounded coordinates:{formatted_coords}")

    # Search OSM with the formatted coordinates
    osm_query: str = wikipage_obj.title + formatted_coords
    osm_results: list[str] = search_nominatim(
        osm_query, coords=[lat_rounded, lon_rounded]
    )

    # Format results as markdown
    markdown_output: str = "*Location results*:\n\n"
    for result in osm_results[:1]:  # Avoid outputting too many results.
        markdown_output += f"* {result}\n"
        logger.debug(markdown_output)

    return markdown_output


if "__main__" == __name__:
    while True:
        my_search = input("What would you like to search Wikipedia for? ")
        print(wikipedia_lookup([my_search], "en"))
