#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
Contains functions pertaining to updating the statistics on the
subreddit wiki.
...

Logger tag: [WY:WIKI]
"""

import logging
from datetime import date

import prawcore
from praw.exceptions import RedditAPIException

from config import SETTINGS
from config import logger as _base_logger
from lang.languages import converter
from processes.wenyuan_stats import Lumo
from reddit.connection import REDDIT
from wenyuan import WENYUAN_SETTINGS

logger = logging.LoggerAdapter(_base_logger, {"tag": "WY:WIKI"})


# ─── Constants ────────────────────────────────────────────────────────────────

# Template for new wiki pages - matches existing format
WY_NEW_HEADER = (
    "## {language_name} ({language_family}) ![](%%statistics-h%%)\n"
    "*[Statistics](https://www.reddit.com/r/translator/wiki/statistics) for "
    "/r/translator provided by "
    "[Wenyuan](https://www.reddit.com/r/translator/wiki/wenyuan)*\n\n"
    "Year | Month | Total Requests | Percent of All Requests | Untranslated "
    "Requests | Translation Percentage | RI | View Translated Requests\n"
    "|:-----|------|---------------|-----------------------|-----------------------"
    "|-----------------------|----|-------------------------|\n"
)

# Utility codes that get special handling
UTILITY_CODES = [
    "Unknown",
    "Nonlanguage",
    "Conlang",
    "Multiple Languages",
]


# ─── Helpers ──────────────────────────────────────────────────────────────────


def calculate_ri(
    language_posts: int, total_posts: int, native_speakers: int
) -> float | None:
    """
    Calculate the Representation Index for a language.

    Args:
        language_posts: Number of posts for this language on r/translator
        total_posts: Total number of posts on r/translator
        native_speakers: Number of native speakers worldwide

    Returns:
        RI value or None if calculation not possible
    """
    world_population = WENYUAN_SETTINGS["world_population"] * 1000000

    if total_posts == 0 or native_speakers == 0:
        return None

    percent_posts = (language_posts / total_posts) * 100
    percent_speakers = (native_speakers / world_population) * 100
    ri = percent_posts / percent_speakers

    return round(ri, 2)


# ─── Wiki editors ─────────────────────────────────────────────────────────────


def cerbo_wiki_editor(
    language_name: str,
    language_family: str,
    wiki_language_line: str,
    month_year_chunk: str,
) -> None:
    """
    A function that writes to the specific wiki page for a language.
    Adapted for backwards compatibility with existing wiki structure.

    :param language_name: The name of the language.
    :param language_family: Its language family.
    :param wiki_language_line: The line containing the information we wish to edit.
    :param month_year_chunk: The month and year to check for (e.g., "2025-05").
    :return: Nothing.
    """
    r = REDDIT.subreddit(SETTINGS["subreddit"])

    # Format the name nicely for wiki URL
    underscore_name = language_name.lower()
    underscore_name = underscore_name.replace(" ", "_")
    underscore_name = underscore_name.replace("'", "_")
    underscore_name = underscore_name.replace("<", "")
    underscore_name = underscore_name.replace(">", "")

    # Special case: "Multiple Languages" wiki page is at /wiki/multiple
    if language_name == "Multiple Languages":
        underscore_name = "multiple"

    page_content = r.wiki[underscore_name]

    if language_name not in UTILITY_CODES:  # Regular languages
        try:
            if month_year_chunk not in str(page_content.content_md):
                page_content_new = (
                    str(page_content.content_md).rstrip("\n") + wiki_language_line
                )
                page_content.edit(
                    content=page_content_new,
                    reason=f"Updating with data from {month_year_chunk}",
                )
                logger.info(
                    f"Updated wiki entry for {language_name} statistics "
                    f"for the month of {month_year_chunk}."
                )
            else:
                logger.info(
                    f"Wiki entry exists for {language_name} in {month_year_chunk}."
                )
        except prawcore.exceptions.NotFound:
            # Page doesn't exist — create it from template then append the new line
            template_content = WY_NEW_HEADER.format(
                language_name=language_name, language_family=language_family
            )
            r.wiki.create(
                name=underscore_name,
                content=template_content,
                reason=f"Creating a new statistics wiki page for {language_name}",
            )
            logger.info(f"Created a new wiki page for {language_name}")
            page_content_new = template_content + wiki_language_line
            page_content.edit(
                content=page_content_new,
                reason=f"Updating with data from {month_year_chunk}",
            )
            logger.info(f"Updated wiki entry for {language_name} in {month_year_chunk}")
        except RedditAPIException:
            logger.warning(f"Error with {language_name}")
    else:
        # Utility pages (Unknown, Conlang, etc.)
        try:
            if month_year_chunk not in str(page_content.content_md):
                page_content_new = str(page_content.content_md) + wiki_language_line
                page_content.edit(
                    content=page_content_new,
                    reason=f"Updating with data from {month_year_chunk}",
                )
                logger.info(
                    f"Updated wiki function entry for {language_name} in {month_year_chunk}"
                )
            else:
                logger.info(
                    f"Wiki function entry exists for {language_name} in {month_year_chunk}"
                )
        except prawcore.exceptions.NotFound:
            logger.warning(f"Wiki page not found for utility code {language_name}")


# ─── Orchestration ────────────────────────────────────────────────────────────


def update_language_wiki_pages(lumo: Lumo, month_year: str) -> int:
    """
    Update individual language wiki pages with monthly statistics.
    Now uses table format matching existing wiki structure.

    :param lumo: Lumo instance with loaded data.
    :param month_year: The month and year in YYYY-MM format (e.g., "2025-05").
    :return: Number of pages updated.
    """
    all_languages = sorted(lumo.get_all_languages())
    updated_count = 0

    overall_stats = lumo.get_overall_stats()
    total_posts = overall_stats["total_requests"]

    for lang in all_languages:
        stats = lumo.get_language_stats(lang)
        if not stats:
            continue

        lingvo = converter(lang)
        if not lingvo:
            continue

        year, month = month_year.split("-")
        search_lang = lang.replace(" ", "_")
        lang_code = lingvo.preferred_code.upper()

        total_link = (
            f"[{stats['total_requests']}]"
            f'(/r/translator/search?q=flair:"{search_lang}"+OR+flair:"[{lang_code}]"'
            "&sort=new&restrict_sr=on)"
        )

        untranslated = stats["untranslated"]

        ri_value = "---"
        if lingvo.population and lingvo.population > 0:
            ri = calculate_ri(
                language_posts=stats["total_requests"],
                total_posts=total_posts,
                native_speakers=lingvo.population,
            )
            if ri is not None:
                ri_value = str(ri)

        wiki_line = (
            f"\n| {year} | {month} | {total_link} | {stats['percent_of_all_requests']}% | "
            f"{untranslated} | {stats['translation_percentage']}% | {ri_value} | --- |"
        )

        if len(lang_code) != 4:
            cerbo_wiki_editor(
                language_name=lang,
                language_family=lingvo.family if lingvo.family else "Unknown",
                wiki_language_line=wiki_line,
                month_year_chunk=month_year,
            )
            updated_count += 1
        else:
            logger.info(f"Skipping {lang} because it's a script code.")

    logger.info(f"Updated {updated_count} language wiki pages")
    return updated_count


def update_monthly_wiki_page(month_year: str, formatted_content: str) -> str | None:
    """
    Create or update the monthly statistics wiki page (e.g., /r/translator/wiki/2025_05).

    :param month_year: The month and year in YYYY-MM format (e.g., "2025-05").
    :param formatted_content: The full Markdown content for the page.
    :return: The wiki page URL if successful, None otherwise.
    """
    r = REDDIT.subreddit(SETTINGS["subreddit"])
    wiki_page_name = month_year.replace("-", "_")

    try:
        page_content = r.wiki[wiki_page_name]

        if "## Overall Statistics" in str(page_content.content_md):
            logger.info(f"Wiki page already exists for {month_year}")
            return f"https://www.reddit.com/r/translator/wiki/{wiki_page_name}"
        else:
            page_content.edit(
                content=formatted_content, reason=f"Monthly statistics for {month_year}"
            )
            logger.info(f"Updated wiki page for {month_year}")
            return f"https://www.reddit.com/r/translator/wiki/{wiki_page_name}"

    except prawcore.exceptions.NotFound:
        try:
            r.wiki.create(
                name=wiki_page_name,
                content=formatted_content,
                reason=f"Creating monthly statistics page for {month_year}",
            )
            logger.info(f"Created new wiki page for {month_year}")
            return f"https://www.reddit.com/r/translator/wiki/{wiki_page_name}"
        except Exception as e:
            logger.error(f"Error creating wiki page for {month_year}: {e}")
            return None
    except Exception as e:
        logger.error(f"Error updating wiki page for {month_year}: {e}")
        return None


def update_statistics_index_page(month_year: str) -> bool:
    """
    Update the main statistics index page with a link to the new monthly page.

    :param month_year: The month and year in YYYY-MM format (e.g., "2025-05").
    :return: True if successful, False otherwise.
    """
    r = REDDIT.subreddit(SETTINGS["subreddit"])

    year, month = month_year.split("-")
    month_name = date(1900, int(month), 1).strftime("%B")
    wiki_page_name = month_year.replace("-", "_")

    new_entry = f"* [{month_name} {year}](https://www.reddit.com/r/translator/wiki/{wiki_page_name})\n"

    try:
        page_content = r.wiki["statistics"]

        if wiki_page_name in str(page_content.content_md):
            logger.info(f"Statistics index already contains entry for {month_year}")
            return True

        content = str(page_content.content_md)

        if f"## {year}" in content:
            insertion_point = content.find(f"## {year}") + len(f"## {year}\n\n")
            new_content = (
                content[:insertion_point] + new_entry + content[insertion_point:]
            )
        else:
            new_content = content + f"\n## {year}\n\n" + new_entry

        page_content.edit(
            content=new_content, reason=f"Adding {month_name} {year} statistics"
        )
        logger.info(f"Updated statistics index page with {month_year}")
        return True

    except Exception as e:
        logger.error(f"Error updating statistics index page: {e}")
        return False
