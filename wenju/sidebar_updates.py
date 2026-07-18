#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""Update r/translator sidebar statistics and language-of-the-day content."""

import logging
import random
import sqlite3
import time
from datetime import date

from praw.exceptions import RedditAPIException
from praw.models import TextArea

from config import SETTINGS
from config import logger as _base_logger
from database import db
from integrations.discord_utils import send_discord_alert
from lang.countries import get_country_emoji
from lang.languages import (
    converter,
    define_language_lists,
    get_lingvos,
    select_random_language,
)
from models.ajo import ajo_loader
from models.lingvo import Lingvo
from reddit.connection import REDDIT, widget_update
from time_handling import get_current_utc_time
from wenju import WENJU_SETTINGS, task
from ziwen_lookup.reference import get_language_reference
from ziwen_lookup.wp_utils import wikipedia_lookup

logger = logging.LoggerAdapter(_base_logger, {"tag": "WJ:SIDEBAR"})

LOTD_ISO_639_1_EPOCH = date(2026, 1, 1)
LOTD_ISO_639_1_SEED = "translatorbot:lotd:iso6391"


def _generate_24h_statistics_snippet() -> str | None:
    """Retrieve and summarize post statistics from the last 24 hours."""
    cutoff_timestamp = time.time() - 86400

    try:
        stored_ajos = db.fetchall_ajo(
            "SELECT * FROM ajo_database WHERE created_utc >= ?", (cutoff_timestamp,)
        )
    except sqlite3.Error as e:
        logger.error(f"Database error: {e}")
        return None

    if not stored_ajos:
        logger.info("No posts found in the last 24 hours.")
        return None

    statuses = []
    for post_id, _, data, *_rest in stored_ajos:
        try:
            ajo_data = ajo_loader(post_id)
            if ajo_data is not None:
                statuses.append(ajo_data.status)
            else:
                logger.warning(f"Ajo `{post_id}` could not be loaded, skipping")
        except Exception as e:
            logger.warning(f"Skipping malformed entry: {e}: {data}")

    if not statuses:
        logger.info("No valid statuses found.")
        return None

    count_untranslated = statuses.count("untranslated")
    count_review = statuses.count("doublecheck")
    count_translated = statuses.count("translated")
    total = len(statuses)

    translated_percentage = round(((count_translated + count_review) / total) * 100)

    snippet = (
        f"### Last 24H: "
        f"✗: **{count_untranslated}** "
        f"✓: **{count_review}** "
        f"✔: **{count_translated}** "
        f"({translated_percentage}%)"
    )

    logger.debug(f"{snippet}")
    return snippet


@task(schedule="hourly")
def update_sidebar_statistics() -> None:
    """Update the Old and New Reddit sidebars with the latest 24-hour statistics."""
    current_time_str = get_current_utc_time()

    try:
        sidebar_bit = _generate_24h_statistics_snippet()
    except sqlite3.OperationalError:
        return

    if not sidebar_bit:
        logger.error("No posts found in the last 24 hours — sidebar not updated.")
        return

    try:
        sidebar_wikipage = REDDIT.subreddit(SETTINGS["subreddit"]).wiki[
            "config/sidebar"
        ]
        sidebar_contents = sidebar_wikipage.content_md.rsplit("\n", 1)[0]
        new_sidebar_contents = f"{sidebar_contents}\n{sidebar_bit}"

        sidebar_wikipage.edit(
            content=new_sidebar_contents,
            reason=f"Updating sidebar at {current_time_str}",
        )

        prefix = "### Last 24H: "
        logger.info(
            f"Updated Old Reddit sidebar with 24-hour stats: {sidebar_bit[len(prefix) :]}"
        )
    except Exception as e:
        logger.error(f"Failed to update Old Reddit sidebar: {e}")
        return

    widgets = REDDIT.subreddit(SETTINGS["subreddit"]).widgets
    target_widget_id = "widget_13r63qu7r63we"

    active_widget = next(
        (
            w
            for w in widgets.sidebar
            if isinstance(w, TextArea) and w.id == target_widget_id
        ),
        None,
    )

    if not active_widget:
        logger.warning("Sidebar text widget not found — skipping widget update.")
        return

    widget_text = sidebar_bit.replace("Last 24H", "Posts").strip()

    try:
        active_widget.mod.update(text=widget_text)
        logger.debug("Updated New Reddit sidebar widget with latest statistics.")
    except RedditAPIException:
        logger.error("Reddit API error: failed to update New Reddit sidebar widget.")

    return


def _is_iso_639_1_lotd_day(day: date) -> bool:
    """Return whether the LOTD schedule should use the ISO 639-1 pool."""
    return day.day % 2 == 0


def _iso_639_1_lotd_slots_before(day: date) -> int:
    """Count ISO 639-1 LOTD slots from the fixed epoch before day."""
    if day <= LOTD_ISO_639_1_EPOCH:
        return 0

    return sum(
        1
        for ordinal in range(LOTD_ISO_639_1_EPOCH.toordinal(), day.toordinal())
        if _is_iso_639_1_lotd_day(date.fromordinal(ordinal))
    )


def _deterministic_iso_639_1_lotd_code(
    candidates: list[str] | set[str], day: date
) -> str | None:
    """Select an ISO 639-1 LOTD code from a deterministic shuffled cycle."""
    codes = sorted({code.lower() for code in candidates if code})
    if not codes:
        return None

    slot_count = _iso_639_1_lotd_slots_before(day)
    cycle_number, index_in_cycle = divmod(slot_count, len(codes))
    cycle_codes = codes.copy()
    rng = random.Random(f"{LOTD_ISO_639_1_SEED}:{cycle_number}")
    rng.shuffle(cycle_codes)
    return cycle_codes[index_in_cycle]


def _select_iso_639_1_language_of_the_day(day: date) -> Lingvo | None:
    """Select the ISO 639-1 LOTD Lingvo without persisted selection state."""
    iso_639_1_languages = define_language_lists().get("ISO_639_1", set())
    selected_code = _deterministic_iso_639_1_lotd_code(iso_639_1_languages, day)
    if not selected_code:
        return None

    logger.info(f"Selecting an ISO 639-1 language today: `{selected_code}`.")
    return converter(selected_code)


@task(schedule="daily")
def language_of_the_day(selected_language: str | None = None) -> str | None:
    """Build and publish the language-of-the-day sidebar widget."""
    today = date.today()

    iso_639_1_day = _is_iso_639_1_lotd_day(today)

    if not selected_language and not iso_639_1_day:
        today_language = select_random_language()
    elif not selected_language and iso_639_1_day:
        today_language = _select_iso_639_1_language_of_the_day(today)
    else:
        assert selected_language is not None
        today_language = converter(selected_language, preserve_country=True)

    if not today_language:
        logger.warning(
            f"Selection was {today_language}, which was invalid. No LOTD selected."
        )
        return None

    wikipedia_search_term = f"ISO_639:{today_language.language_code_3}"
    wikipedia_redirect_link = f"https://en.wikipedia.org/wiki/{wikipedia_search_term}"
    logger.info(
        f"Language of the day is: {today_language.name} "
        f"(`{today_language.language_code_3}`)."
    )

    if iso_639_1_day:
        language_subreddit = today_language.subreddit
        if language_subreddit:
            logger.info(f"> Subreddit for the language is {language_subreddit}.")
    else:
        language_subreddit = None

    wikipedia_entry = wikipedia_lookup(wikipedia_search_term)
    if not wikipedia_entry:
        return None

    language_entry_summary = wikipedia_entry
    if "\n\n> " in language_entry_summary:
        language_entry_summary = language_entry_summary.split("\n\n> ")[1]
    if "\n\n" in language_entry_summary:
        language_entry_summary = language_entry_summary.split("\n\n")[0]
    language_entry_summary = language_entry_summary.strip()

    if not today_language.language_code_1:
        if today_language.language_code_3 is None:
            logger.warning("No ISO 639-3 code available, skipping reference fetch.")
        else:
            reference_result = get_language_reference(today_language.language_code_3)
            if reference_result is not None:
                language_data = get_lingvos(force_refresh=True)
                logger.debug("Variable refreshed.")
                refreshed = language_data.get(today_language.language_code_3)
                if refreshed is not None:
                    today_language = refreshed
                else:
                    logger.warning(
                        f"`{today_language.language_code_3}` not found in refreshed data "
                        f"— keeping original Lingvo."
                    )
            else:
                logger.warning(
                    f"Could not retrieve Ethnologue reference for "
                    f"`{today_language.language_code_3}` — proceeding without it."
                )

    country_emoji = None
    country_for_emoji = getattr(today_language, "country", None)
    if country_for_emoji:
        country_emoji = get_country_emoji(country_for_emoji) or None
    if country_emoji is None:
        country_emoji = today_language.country_emoji or None

    language_family = today_language.family or "Unknown"
    language_family_link = (
        f"https://en.wikipedia.org/wiki/{language_family.replace('_', ' ')}_languages"
    )

    header = f"#### **[{today_language.name}]({wikipedia_redirect_link})** "
    if today_language.language_code_1:
        header += f"`({today_language.language_code_1}`/`{today_language.language_code_3})`\n\n"
    else:
        header += f"`({today_language.preferred_code})`\n\n"

    country_line = ""
    if country_emoji is not None:
        country_line = f"* **Country**: {country_emoji}\n"

    body = (
        f"* **Family**: [{language_family}]({language_family_link})\n"
        f"{country_line}"
        f"* **Population**: {today_language.population:,}"
    )

    if language_subreddit:
        body += f"\n* **Subreddit**: r/{language_subreddit}"
    summary = f"\n\n{language_entry_summary}"
    full_text = header + body + summary

    update_success = widget_update(WENJU_SETTINGS["lotd_widget_ids"], full_text)
    if update_success:
        article = "an" if language_family[0].lower() in "aeiou" else "a"
        code_string = f"`{today_language.preferred_code}`"

        language_blurb = (
            f"The language of the day is **[{today_language.name}]"
            f"({wikipedia_redirect_link})** ({code_string}), "
            f"{article} {language_family} language. {language_entry_summary}"
        )

        if country_emoji is not None:
            title = f"Language of the Day: {country_emoji} {today_language.name}"
        else:
            title = f"Language of the Day: {today_language.name}"

        send_discord_alert(title, language_blurb, "lotd")

    return full_text
