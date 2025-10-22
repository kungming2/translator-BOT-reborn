#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
Contains functions that deal with Wikipedia access.
"""

import re

import wikipedia

from config import logger
from languages import converter
from usage_statistics import action_counter

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
        except (
            wikipedia.exceptions.DisambiguationError,
            wikipedia.exceptions.PageError,
        ):
            # No direct matches, try auto suggest.
            try:
                term_summary: str = wikipedia.summary(term.strip(), sentences=3)
                term_entry: str = wikipedia.page(term).url
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
        entries.append(f"\n**[{term}]({term_entry})**\n\n> {term_summary}\n\n")
        logger.info(f">> Information for '{term}' retrieved.")

    if entries:
        body_text: str = "\n".join(entries)
        logger.info("> Wikipedia entry data obtained.")
        action_counter(len(entries), "Wikipedia lookup")
        return body_text

    return None


if "__main__" == __name__:
    while True:
        my_search = input("What would you like to search Wikipedia for? ")
        print(wikipedia_lookup([my_search], "en"))
