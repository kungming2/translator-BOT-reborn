#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""Build monthly Wenyuan statistics reports for Reddit and wiki publication."""

import calendar
import re
from datetime import date

from wasabi import Printer

from config import SETTINGS, logger
from lang.languages import converter
from processes.wenyuan_stats import FastestEntry, Lumo
from reddit.connection import REDDIT
from time_handling import time_convert_to_string_seconds
from wenyuan import WENYUAN_SETTINGS
from wenyuan.update_wiki_stats import calculate_ri
from ziwen_lookup.reference import get_language_reference

UTILITY_CODES = WENYUAN_SETTINGS["utility_codes"]
msg = Printer()


def _previous_month_wiki_key(month_year: str) -> str:
    """Return the wiki page key for the month before a YYYY-MM report."""
    year_text, month_text = month_year.split("-")
    year = int(year_text)
    month = int(month_text)

    if month == 1:
        return f"{year - 1}_12"
    return f"{year}_{month - 1:02d}"


def _fetch_previous_month_language_percentages(
    month_year: str,
) -> dict[str, float] | None:
    """Fetch and parse the previous monthly report's language percentages."""
    wiki_key = _previous_month_wiki_key(month_year)

    try:
        subreddit = REDDIT.subreddit(SETTINGS["subreddit"])
        wiki_page = subreddit.wiki[wiki_key]
        percentages = _parse_monthly_language_percentages(wiki_page.content_md)
    except Exception as e:
        logger.warning(
            "Could not fetch previous monthly statistics wiki page `%s`: %s",
            wiki_key,
            e,
        )
        return None

    if not percentages:
        logger.warning(
            "Previous monthly statistics wiki page `%s` had no parseable "
            "single-language percentage data.",
            wiki_key,
        )
        return None

    return percentages


def _parse_monthly_language_percentages(markdown: str) -> dict[str, float]:
    """Parse language percentage values from a monthly statistics markdown page."""
    percentages: dict[str, float] = {}
    in_single_language_section = False
    language_index: int | None = None
    percent_index: int | None = None

    for raw_line in markdown.splitlines():
        line = raw_line.strip()

        if line == "### Single-Language Requests":
            in_single_language_section = True
            continue

        if not in_single_language_section:
            continue

        if line.startswith("###") or line.startswith("#####"):
            break

        if not line or "|" not in line:
            continue

        cells = [cell.strip() for cell in line.strip("|").split("|")]
        normalized_cells = [cell.lower() for cell in cells]

        if (
            "language" in normalized_cells
            and "percent of all requests" in normalized_cells
        ):
            language_index = normalized_cells.index("language")
            percent_index = normalized_cells.index("percent of all requests")
            continue

        if set(cells) <= {"", "---", "----", "-----", "--"}:
            continue

        if language_index is None or percent_index is None:
            continue

        if len(cells) <= max(language_index, percent_index):
            continue

        language = _extract_markdown_link_text(cells[language_index])
        percent_match = re.search(r"(-?\d+(?:\.\d+)?)\s*%", cells[percent_index])

        if language and percent_match:
            percentages[language] = float(percent_match.group(1))

    return percentages


def _extract_markdown_link_text(value: str) -> str:
    """Return display text from a markdown link cell, or the stripped cell text."""
    match = re.search(r"\[([^]]+)]\(", value)
    if match:
        return match.group(1).strip()
    return value.strip()


def _language_has_recorded_statistics(lingvo: object) -> bool:
    """Return whether this language has historical statistics.json data."""
    num_months = getattr(lingvo, "num_months", None)
    if isinstance(num_months, int) and num_months > 0:
        return True

    return any(
        getattr(lingvo, attr, None)
        for attr in (
            "link_statistics",
            "rate_daily",
            "rate_monthly",
            "rate_yearly",
        )
    )


def _language_percentage_trend(
    language: str,
    current_percentage: float,
    previous_percentages: dict[str, float],
    has_recorded_statistics: bool,
) -> str:
    """Return a trend symbol comparing current and previous language share."""
    previous_percentage = previous_percentages.get(language)

    if previous_percentage is None:
        if not has_recorded_statistics:
            return "🆕"
        previous_percentage = 0.0

    if current_percentage > previous_percentage:
        return "⬆️"
    if current_percentage < previous_percentage:
        return "⬇️"
    return "➡️"


# ─── Statistics formatting ────────────────────────────────────────────────────


def _lookup_missing_family(language_name: str, language_code: str) -> str | None:
    """Fetch reference data for a missing language family and return it if found."""
    msg.info(
        f"Fetching reference data for missing family: "
        f"{language_name} ({language_code})..."
    )

    try:
        reference_data = get_language_reference(language_code)
    except Exception as e:
        logger.exception(
            "Could not fetch reference data for missing family `%s` (`%s`): %s",
            language_name,
            language_code,
            e,
        )
        msg.warn(
            f"Reference lookup failed for {language_name} ({language_code}); "
            "leaving family as N/A."
        )
        return None

    if not reference_data:
        msg.warn(
            f"Reference lookup found no data for {language_name} ({language_code}); "
            "leaving family as N/A."
        )
        return None

    family = reference_data.get("family")
    if isinstance(family, str):
        family = family.strip()

    if family and family.lower() != "unknown":
        msg.good(f"Found family for {language_name} ({language_code}): {family}")
        return family

    msg.warn(
        f"Reference lookup for {language_name} ({language_code}) did not include "
        "family data; leaving family as N/A."
    )
    return None


def format_lumo_stats_for_reddit(lumo: Lumo, month_year: str) -> str:
    """
    Format Lumo statistics into Reddit markdown for posting.

    Args:
        lumo: Lumo instance with loaded data
        month_year: Month in YYYY-MM format

    Returns:
        Formatted markdown string matching monthly_output.md structure
    """
    year_number, month_number = month_year.split("-")
    month_english_name = date(1900, int(month_number), 1).strftime("%B")

    overall = lumo.get_overall_stats()
    directions = lumo.get_direction_stats()
    identification = lumo.get_identification_stats()
    fastest = lumo.get_fastest_translations()
    notifications = lumo.get_notification_stats()
    images = lumo.get_image_stats()
    source_target_pairs = lumo.get_source_target_pairs(10)
    unique_translators = lumo.get_unique_translator_count()
    previous_language_percentages = _fetch_previous_month_language_percentages(
        month_year
    )

    multiple_language_count = len(lumo.filter_by_type("multiple"))

    content = (
        f"# [{month_english_name} {year_number}](https://www.reddit.com/r/translator/wiki/"
        f"{year_number}_{month_number}) \n"
    )
    content += (
        "*[Statistics](https://www.reddit.com/r/translator/wiki/statistics) for r/translator "
        "provided by [Wenyuan](https://www.reddit.com/r/translatorBOT/wiki/wenyuan)*\n\n"
    )
    content += f"Here are the statistics for {month_english_name} {year_number}.\n\n"

    content += "## Overall Statistics\n"
    content += "Category | Post Count \n"
    content += "----|----\n"
    content += "*Single-Language* | \n"
    content += f"Untranslated requests | {overall['untranslated']}\n"
    content += f"Requests missing assets | {overall['missing_assets']}\n"
    content += f"Requests in progress | {overall['in_progress']}\n"
    content += f"Requests needing review | {overall['needs_review']}\n"
    content += f"Translated requests | {overall['translated']}\n"
    content += " | \n"
    content += f"*Multiple-Language* | {multiple_language_count}\n"
    content += "---|---\n"
    content += f"**Total requests** | **{overall['total_requests']}**\n"
    content += f"**Overall percentage** | **{overall['translation_percentage']}% translated**\n"
    content += f"*Represented languages* | *{overall['unique_languages']}*\n"
    content += f"*Unique translators* | *{unique_translators}*\n"
    content += (
        f"*Average notified users per request* | "
        f"*{notifications['average_notified_per_request']}*\n"
    )
    content += (
        f"*Image posts* | *{images['image_requests']} ({images['percentage']}%)*\n"
    )
    content += (
        "*Meta/Community Posts* | *8*\n\n"  # This would need to be tracked separately
    )

    content += "### Language Families\n"
    content += "Language Family | Total Requests | Percent of All Requests\n"
    content += "----|----|----\n"

    family_counts: dict[str, int] = {}
    all_languages = sorted(lumo.get_all_languages())

    for lang in all_languages:
        if lang in UTILITY_CODES:
            continue

        lingvo = converter(lang)
        if not lingvo:
            continue

        if len(lingvo.preferred_code) == 4 or lingvo.script_code:
            continue

        if lingvo.family:
            family = lingvo.family
            stats = lumo.get_language_stats(lang)
            if stats:
                family_counts[family] = (
                    family_counts.get(family, 0) + stats["total_requests"]
                )

    sorted_families = sorted(family_counts.items(), key=lambda x: x[1], reverse=True)

    for family, count in sorted_families:
        percent = round((count / overall["total_requests"]) * 100, 2)
        content += f"{family} | {count} | {percent}%\n"

    content += "\n"

    content += "### Single-Language Requests\n"
    content += (
        "Language | Language Family | Total Requests | Percent of All Requests | "
    )
    if previous_language_percentages is not None:
        content += "Change | "
    content += "Untranslated Requests | Translation Percentage | Ratio | "
    content += "Identified from 'Unknown' | RI | Wikipedia Link\n"
    content += "-----|-----|--|----|"
    if previous_language_percentages is not None:
        content += "---|"
    content += "-----|---|-----|---|---|-----\n"

    identified_from_unknown = identification.get("identified_from_unknown", {})
    missing_family: list[str] = []
    missing_family_reference_cache: dict[str, str | None] = {}

    for lang in all_languages:
        if lang in UTILITY_CODES:
            continue

        stats = lumo.get_language_stats(lang)
        if not stats:
            continue

        lingvo = converter(lang)
        if not lingvo:
            continue

        if len(lingvo.preferred_code) == 4 or lingvo.script_code:
            continue

        total = stats["total_requests"]
        percent_all = stats["percent_of_all_requests"]
        untranslated = stats["untranslated"]
        trans_pct = stats["translation_percentage"]
        ratio = stats["directions"]

        identified_count = identified_from_unknown.get(lang, 0)
        if lingvo.family:
            family = lingvo.family
        else:
            language_code = lingvo.preferred_code.lower()
            if language_code not in missing_family_reference_cache:
                missing_family_reference_cache[language_code] = _lookup_missing_family(
                    lang, language_code
                )
            cached_family = missing_family_reference_cache[language_code]
            if cached_family:
                family = cached_family
            else:
                family = "N/A"
                missing_family.append(f"{lang} ({language_code})")

        ri_value = "---"
        if lingvo.population and lingvo.population > 0:
            ri = calculate_ri(
                language_posts=total,
                total_posts=overall["total_requests"],
                native_speakers=lingvo.population,
            )
            if ri is not None:
                ri_value = str(ri)

        wp_link = f"[WP](https://en.wikipedia.org/wiki/ISO_639:{lingvo.preferred_code})"
        wiki_name = lang.replace(" ", "_").lower()
        lang_link = f"[{lang}](https://www.reddit.com/r/translator/wiki/{wiki_name})"
        search_link = (
            f'[{total}](/r/translator/search?q=flair:"{lang.replace(" ", "_")}"'
            f'+OR+flair:"[{lingvo.preferred_code.upper()}]"&sort=new&restrict_sr=on)'
        )

        trend_cell = ""
        if previous_language_percentages is not None:
            trend = _language_percentage_trend(
                lang,
                float(percent_all),
                previous_language_percentages,
                _language_has_recorded_statistics(lingvo),
            )
            trend_cell = f"{trend} | "

        row = (
            f"| {lang_link} | {family} | {search_link} | {percent_all}% | "
            f"{trend_cell}{untranslated} | {trans_pct}% | {ratio} | "
            f"{identified_count} | {ri_value} | {wp_link} |"
        )
        content += row + "\n"

    if missing_family:
        msg.warn(
            f"{len(missing_family)} lingvo(s) missing family data: "
            + ", ".join(missing_family)
        )

    content += "\n"

    content += "##### Translation Direction\n\n"
    content += (
        f"* **To English**: {directions['to_english']['count']} "
        f"({directions['to_english']['percentage']}%)\n"
    )
    content += (
        f"* **From English**: {directions['from_english']['count']} "
        f"({directions['from_english']['percentage']}%)\n"
    )
    content += (
        f"* **Both Non-English**: {directions['non_english']['count']} "
        f"({directions['non_english']['percentage']}%)\n\n"
    )

    if source_target_pairs:
        content += "##### Top Source-Target Pairs\n\n"
        content += "Source → Target | Requests\n"
        content += "---|---\n"

        for pair, count in source_target_pairs:
            content += f"{pair} | {count}\n"

        content += "\n"

    if identified_from_unknown:
        content += "##### 'Unknown' Identifications\n\n"
        content += (
            "| Language | Requests Identified | "
            "Percentage of Total 'Unknown' Posts | "
            "'Unknown' Misidentification Percentage |\n"
        )
        content += "---|---|---|---\n"

        total_identified = sum(identified_from_unknown.values())
        sorted_identified = sorted(
            identified_from_unknown.items(), key=lambda x: x[1], reverse=True
        )

        for lang, count in sorted_identified[:13]:  # Top 13
            percent_of_unknown = round((count / total_identified) * 100, 2)

            lang_stats = lumo.get_language_stats(lang)
            if lang_stats and lang_stats["total_requests"] > 0:
                misidentification_pct = round(
                    (count / lang_stats["total_requests"]) * 100, 2
                )
                content += f"{lang} | {count} | {percent_of_unknown}% | {misidentification_pct}%\n"
            else:
                content += f"{lang} | {count} | {percent_of_unknown}% | ---\n"

        content += "\n"

    misidentified = identification.get("misidentified_pairs", {})
    if misidentified:
        content += "##### Commonly Misidentified Language Pairs\n\n"
        content += "Language Pair | Requests Identified\n"
        content += "---|---\n"

        sorted_misidentified = sorted(
            misidentified.items(), key=lambda x: x[1], reverse=True
        )

        for pair, count in sorted_misidentified[:5]:  # Top 5
            content += f"Submitted as {pair} | {count}\n"

        content += "\n"

    def _format_fastest_post(
        post_data: FastestEntry | None, post_label: str, post_action: str
    ) -> str | None:
        """
        Helper to format a fastest post entry.

        Args:
            post_data: Dict with 'id' and 'time' keys
            post_label: Display label (e.g., '"Needs Review" request')
            post_action: Action verb (e.g., 'was marked for review')

        Returns:
            Formatted string or None if data is invalid
        """
        if not post_data or not post_data.get("id") or post_data.get("time") is None:
            return None

        time_val = post_data["time"]
        if not isinstance(time_val, (int, float)) or time_val < 0:
            return None

        time_str = time_convert_to_string_seconds(int(time_val))
        return f"* The quickest [{post_label}](https://redd.it/{post_data['id']}) {post_action} in {time_str}.\n"

    content += "##### Quickest Processed Posts\n\n"

    post_types = [
        (fastest.get("to_review"), '"Needs Review" request', "was marked for review"),
        (fastest.get("to_translated"), '"Translated" request', "was translated"),
        (fastest.get("to_claimed"), "claimed request", "was claimed"),
    ]

    has_any_data = False

    for data, label, action in post_types:
        if formatted := _format_fastest_post(data, label, action):
            content += formatted
            has_any_data = True

    if (
        (avg_hours := fastest.get("average_translation_hours")) is not None
        and isinstance(avg_hours, (int, float))
        and avg_hours > 0
    ):
        content += f"* The average request was translated in {avg_hours:.1f} hours.\n"
        has_any_data = True

    if (
        (median_seconds := fastest.get("median_translation_seconds")) is not None
        and isinstance(median_seconds, (int, float))
        and median_seconds > 0
    ):
        median_time = time_convert_to_string_seconds(int(median_seconds))
        count = fastest.get("timed_translation_count", 0)
        content += (
            f"* The median request was translated in {median_time} "
            f"({count} requests with timing data).\n"
        )
        has_any_data = True

    if not has_any_data:
        content += "* No data available for this period.\n"

    content += "\n"

    content += "#### Other Single-Language Requests/Posts\n\n"
    content += "Category | Total Requests\n"
    content += "---|---\n"

    for utility_code in [c for c in UTILITY_CODES if c != "Multiple Languages"]:
        utility_ajos = lumo.filter_by_language(utility_code)
        count = len(utility_ajos)

        if utility_code == "Generic":
            search_flair = "GENERIC"
            code = "GENERIC"
        elif utility_code == "Unknown":
            search_flair = "Unknown"
            code = "UNKNOWN"
        elif utility_code == "Nonlanguage":
            search_flair = "Nonlanguage"
            code = "ZXX"
        elif utility_code == "Conlang":
            search_flair = "Conlang"
            code = "ART"
        else:
            logger.warning(f"No flair mapping for utility code: {utility_code}")
            continue

        search_url = (
            f"[{count}](https://www.reddit.com/r/translator/search?q=flair:%22{search_flair}%22+"
            f"OR+flair:%22{code}%22&sort=new&restrict_sr=on)"
        )

        content += f"{utility_code} | {search_url}\n"

    content += "\n##### Unknown Requests with Identified Scripts\n\n"
    content += "Script (Unknown) | Total Requests\n"
    content += "---|---\n"

    unknown_scripts = {}
    for lang in all_languages:
        lingvo = converter(lang)
        if lingvo and (len(lingvo.preferred_code) == 4 or lingvo.script_code):
            stats = lumo.get_language_stats(lang)
            if stats:
                unknown_scripts[lang] = stats["total_requests"]

    if unknown_scripts:
        for script, count in sorted(
            unknown_scripts.items(), key=lambda x: x[1], reverse=True
        ):
            content += f"{script} | {count}\n"
    else:
        content += "None | 0\n"

    content += "\n"

    content += "### Multiple-Language Requests\n\n"
    content += f"* For any and all languages: {multiple_language_count}\n"
    content += "* *The count for defined 'Multiple' requests are integrated into the table above.*\n\n"

    content += "---\n\n"
    content += "*Statistics generated using the Lumo analyzer. "
    content += f"Data from {month_english_name} 1 - "

    last_day = calendar.monthrange(int(year_number), int(month_number))[1]
    content += f"{month_english_name} {last_day}, {year_number}.*\n"

    return content
