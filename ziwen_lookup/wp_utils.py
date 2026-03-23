#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
Contains functions that deal with Wikipedia access.
...

Logger tag: [L:WP]
"""

import logging
import re

import wikipedia

from config import logger as _base_logger
from lang.languages import converter
from ziwen_lookup.osm import search_nominatim

logger = logging.LoggerAdapter(_base_logger, {"tag": "L:WP"})


# ─── Location helpers ─────────────────────────────────────────────────────────


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
    logger.debug(f"Wikipedia page: {wikipage_obj.title} at {wikipage_obj.url}")

    try:
        coords = wikipage_obj.coordinates
        if not coords:
            logger.debug("Wikipedia page contains no coordinates.")
            return None
    except (KeyError, AttributeError):
        logger.debug("Wikipedia page error: Contains no coordinates.")
        return None

    logger.debug(f"Original detailed coordinates: {wikipage_obj.coordinates}")

    lat_rounded: float = round(float(wikipage_obj.coordinates[0]), 4)
    lon_rounded: float = round(float(wikipage_obj.coordinates[1]), 4)
    formatted_coords: str = f" {lat_rounded},{lon_rounded}"

    logger.info(f"> Searching for rounded coordinates:{formatted_coords}")

    osm_query: str = wikipage_obj.title + formatted_coords
    osm_results: list[str] = search_nominatim(
        osm_query, coords=[lat_rounded, lon_rounded]
    )

    markdown_output: str = "*Location results*:\n\n"
    for result in osm_results[:1]:  # Avoid outputting too many results.
        markdown_output += f"* {result}\n"
        logger.debug(markdown_output)

    return markdown_output


# ─── Wikipedia lookup ─────────────────────────────────────────────────────────


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

    if language_code != "en":
        lingvo = converter(language_code)
        lang_code: str = lingvo.preferred_code if lingvo is not None else language_code
        wikipedia.set_lang(lang_code)
    logger.info(f"Looking up term {terms} on the `{language_code}` Wikipedia.")

    for term in terms[:5]:  # Limit to five terms.
        term_entry: str | None = None
        term = re.sub(r"[^\w\s:]", "", term)  # Strip punctuation but allow colons
        logger.info(f"> Now searching for '{term}'...")

        try:
            term_summary: str = wikipedia.summary(
                term, auto_suggest=False, redirect=True, sentences=3
            )
            wikipage_obj = wikipedia.page(term, auto_suggest=False, redirect=True)
        except (
            wikipedia.exceptions.DisambiguationError,
            wikipedia.exceptions.PageError,
        ):
            try:
                term_summary = wikipedia.summary(term.strip(), sentences=3)
                wikipage_obj = wikipedia.page(term.strip())
                term_entry = wikipage_obj.url
            except (
                wikipedia.exceptions.DisambiguationError,
                wikipedia.exceptions.PageError,
            ):
                logger.error(f">> Unable to resolve '{term}' on Wikipedia. Skipping.")
                continue

        term_format: str = term.replace(" ", "_")
        if "\n" in term_summary:
            term_summary = term_summary.split("\n")[0].strip()
        if "==" in term_summary:
            term_summary = term_summary.split("==")[0].strip()
        if not term_entry:
            term_entry = f"https://en.wikipedia.org/wiki/{term_format}"
        term_entry = term_entry.replace(")", r"\)")
        logger.info(f">> Text for {term} to be obtained from `{term_entry}`.")

        entry_text = f"\n**[{term.title()}]({term_entry})**\n\n> {term_summary}\n\n"

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
