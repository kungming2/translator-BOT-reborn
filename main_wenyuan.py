#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
Main runtime for Wenyuan - Translation Statistics & Analytics System

Uses a Pythonic menu system with command registry pattern.
Easily extensible - just add @register_command decorator to new functions.

Compatible with refactored Lumo analyzer (wenyuan_stats.py).
"""

import calendar
import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date

from rich import box
from rich.console import Console
from rich.markdown import Markdown
from rich.table import Table
from wasabi import Printer

from config import SETTINGS, logger
from integrations.discord_utils import send_discord_alert
from lang.languages import converter
from monitoring.usage_statistics import get_month_points_summary
from processes.wenyuan_stats import FastestEntry, Lumo
from reddit.connection import REDDIT
from time_handling import time_convert_to_string_seconds
from wenyuan.challenge_poster import translation_challenge_poster
from wenyuan.data_validator import data_validator
from wenyuan.title_full_retrieval import retrieve_titles_test
from wenyuan.update_wiki_stats import (
    calculate_ri,
    update_language_wiki_pages,
    update_monthly_wiki_page,
    update_statistics_index_page,
)
from ziwen_lookup.reference import get_language_reference

# Utility codes that get special handling
UTILITY_CODES = [
    "Unknown",
    "Generic",
    "Nonlanguage",
    "Conlang",
    "Multiple Languages",
]
msg = Printer()
_console = Console()


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


# ─── Menu infrastructure ──────────────────────────────────────────────────────


@dataclass
class MenuOption:
    """Represents a menu option."""

    key: str
    description: str
    function: Callable
    category: str = "general"


class CommandRegistry:
    """Registry for menu options with automatic display generation."""

    def __init__(self) -> None:
        """Initialize the registry with an empty command map and default
        categories."""
        self.commands: dict[str, MenuOption] = {}
        self.categories = {
            "posts": "Create Posts",
            "test": "Testing Functions",
            "data": "Data Retrieval",
            "admin": "Administrative",
            "system": "System",
        }

    def register(
        self, key: str, description: str, category: str = "general"
    ) -> Callable[[Callable], Callable]:
        """Decorator to register a menu option."""

        def decorator(func: Callable) -> Callable:
            self.commands[key] = MenuOption(key, description, func, category)
            return func

        return decorator

    def display_menu(self) -> None:
        """Render the command menu as a Rich table."""
        categorized: dict[str, list] = {}
        for cmd in self.commands.values():
            categorized.setdefault(cmd.category, []).append(cmd)

        table = Table(
            title="WENYUAN COMMAND MENU",
            box=box.SIMPLE_HEAD,
            show_header=True,
            header_style="bold sandy_brown",
            title_style="bold sandy_brown",
            show_edge=True,
            padding=(0, 1),
        )
        table.add_column("Command", style="cyan", no_wrap=True)
        table.add_column("Description", style="white")
        table.add_column("Category", style="dim")

        for category_key in ["posts", "test", "data", "admin", "system"]:
            if category_key not in categorized:
                continue
            category_label = self.categories.get(category_key, category_key)
            first = True
            for cmd in sorted(categorized[category_key], key=lambda x: x.key):
                table.add_row(
                    cmd.key,
                    cmd.description,
                    category_label if first else "",
                )
                first = False

        _console.print()
        _console.print(table)
        _console.print()

    def execute(self, key: str) -> bool:
        """Execute a command by key. Returns False if should exit."""
        if key == "x":
            return False

        cmd = self.commands.get(key)
        if cmd:
            try:
                cmd.function()
            except Exception as e:
                msg.fail(f"Error executing command: {e}")
                logger.error(f"Command execution error: {e}", exc_info=True)
        else:
            msg.warn(f"Unknown command: '{key}'")

        return True


registry = CommandRegistry()


# ─── Statistics formatting ────────────────────────────────────────────────────


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
            family = "N/A"
            missing_family.append(lang)

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


# ─── Display helpers ──────────────────────────────────────────────────────────


def _print_language_stats(stats: dict[str, object]) -> None:
    """Pretty-print language statistics as a Rich table."""
    if not stats:
        msg.warn("No data available for this language.")
        return

    lang_name = str(stats.get("language", "Unknown Language"))
    table = Table(
        title=lang_name,
        box=box.SIMPLE_HEAD,
        show_header=False,
        title_style="bold sandy_brown",
        padding=(0, 1),
    )
    table.add_column("Field", style="dim", no_wrap=True)
    table.add_column("Value", style="white")

    table.add_row("Total requests", str(stats.get("total_requests", 0)))
    table.add_row(
        "Translated",
        f"{stats.get('translated', 0)} ({stats.get('translation_percentage', 0)}%)",
    )
    table.add_row("Needs review", str(stats.get("needs_review", 0)))
    table.add_row("Untranslated", str(stats.get("untranslated", 0)))
    table.add_row("% of all requests", f"{stats.get('percent_of_all_requests', 0)}%")
    table.add_row("Direction ratio", str(stats.get("directions", "N/A")))

    _console.print()
    _console.print(table)


# ─── Command definitions ──────────────────────────────────────────────────────


@registry.register("challenge", "Post the weekly translation challenge", "posts")
def post_challenge() -> None:
    """Post the weekly translation challenge."""
    translation_challenge_poster()


@registry.register("title_retrieval", "Test bulk title testing data", "test")
def title_full_retrieval() -> None:
    """Test full retrieval."""
    num_retrieve = input("\n  Enter the number of posts you wish to test: ").strip()
    try:
        retrieve_titles_test(int(num_retrieve))
    except ValueError:
        msg.fail("Invalid number. Please enter a valid integer.")


@registry.register(
    "lang_reference",
    "Fetch reference data for a language from Ethnologue/Wikipedia",
    "data",
)
def fetch_language_reference() -> None:
    """Fetch reference data for a language from archived Ethnologue and Wikipedia."""
    language_input = input("\n  Enter language code (ISO 639-1 or ISO 639-3): ").strip()

    if not language_input:
        msg.warn("No language code specified.")
        return

    msg.info(f"Fetching reference data for '{language_input}'...")
    msg.info("(This may take a moment as it accesses archived web pages)\n")

    reference_data = get_language_reference(language_input)

    if not reference_data:
        msg.fail(
            f"Could not retrieve reference data for '{language_input}'",
            "Possible reasons: invalid language code, no archived Ethnologue page, or network error.",
        )
        return

    ref_table = Table(
        title=f"Reference Data — {reference_data.get('name', 'Unknown')}",
        box=box.SIMPLE_HEAD,
        show_header=False,
        title_style="bold sandy_brown",
        padding=(0, 1),
    )
    ref_table.add_column("Field", style="dim", no_wrap=True)
    ref_table.add_column("Value", style="white")

    ref_table.add_row("ISO 639-3 Code", reference_data.get("language_code_3", "N/A"))
    ref_table.add_row("Primary Name", reference_data.get("name", "N/A"))

    alt_names = reference_data.get("name_alternates", [])
    if alt_names:
        ref_table.add_row("Alternate Names", ", ".join(alt_names))

    ref_table.add_row("Country", reference_data.get("country", "N/A"))
    ref_table.add_row("Language Family", reference_data.get("family", "N/A"))

    population = reference_data.get("population", 0)
    ref_table.add_row(
        "Population",
        f"{population:,} speakers" if population and population > 0 else "Unknown",
    )

    links = []
    if reference_data.get("link_wikipedia"):
        links.append(f"Wikipedia: {reference_data['link_wikipedia']}")
    if reference_data.get("link_ethnologue"):
        links.append(f"Ethnologue: {reference_data['link_ethnologue']}")
    if reference_data.get("link_sil"):
        links.append(f"SIL: {reference_data['link_sil']}")
    if links:
        ref_table.add_row("Links", "\n".join(links))

    _console.print()
    _console.print(ref_table)
    _console.print()

    msg.good("Reference data retrieval complete")


@registry.register(
    "period_stats",
    "Retrieve abbreviated language statistics from a time period as a list",
    "data",
)
def retrieve_post_stats() -> None:
    """Retrieve post statistics using the Lumo analyzer."""
    month = input("\n  Enter month (YYYY-MM) or press Enter for last 30 days: ").strip()

    lumo = Lumo()

    if month:
        try:
            year, month_num = map(int, month.split("-"))
            lumo.load_month(year, month_num)
            period_desc = f"{year}-{month_num:02d}"
        except (ValueError, IndexError):
            msg.fail("Invalid date format. Please use YYYY-MM format.")
            return None
    else:
        lumo.load_last_days(30)
        period_desc = "last 30 days"

    msg.divider(f"Statistics for {period_desc}")

    overall = lumo.get_overall_stats()

    overall_table = Table(
        title=f"Overall Statistics — {period_desc} ({len(lumo)} posts)",
        box=box.SIMPLE_HEAD,
        show_header=False,
        title_style="bold sandy_brown",
        padding=(0, 1),
    )
    overall_table.add_column("Field", style="dim", no_wrap=True)
    overall_table.add_column("Value", style="white")
    overall_table.add_row("Total requests", str(overall["total_requests"]))
    overall_table.add_row(
        "Translated", f"{overall['translated']} ({overall['translation_percentage']}%)"
    )
    overall_table.add_row("Needs review", str(overall["needs_review"]))
    overall_table.add_row("Untranslated", str(overall["untranslated"]))
    overall_table.add_row("In progress", str(overall["in_progress"]))
    overall_table.add_row("Missing assets", str(overall["missing_assets"]))
    overall_table.add_row("Unique languages", str(overall["unique_languages"]))
    _console.print()
    _console.print(overall_table)

    directions = lumo.get_direction_stats()
    dir_table = Table(
        title="Translation Directions",
        box=box.SIMPLE_HEAD,
        show_header=False,
        title_style="bold sandy_brown",
        padding=(0, 1),
    )
    dir_table.add_column("Direction", style="dim", no_wrap=True)
    dir_table.add_column("Value", style="white")
    dir_table.add_row(
        "To English",
        f"{directions['to_english']['count']} ({directions['to_english']['percentage']}%)",
    )
    dir_table.add_row(
        "From English",
        f"{directions['from_english']['count']} ({directions['from_english']['percentage']}%)",
    )
    dir_table.add_row(
        "Non-English",
        f"{directions['non_english']['count']} ({directions['non_english']['percentage']}%)",
    )
    _console.print()
    _console.print(dir_table)

    top_langs = lumo.get_language_rankings(by="total")[:10]
    if top_langs:
        lang_table = Table(
            title="Top 10 Languages",
            box=box.SIMPLE_HEAD,
            show_header=True,
            header_style="bold",
            title_style="bold sandy_brown",
            padding=(0, 1),
        )
        lang_table.add_column("#", style="dim", no_wrap=True)
        lang_table.add_column("Language", style="cyan")
        lang_table.add_column("Requests", style="white", justify="right")
        lang_table.add_column("% Translated", style="white", justify="right")
        for i, (lang, count) in enumerate(top_langs, 1):
            stats = lumo.get_language_stats(lang)
            pct = f"{stats['translation_percentage']}%" if stats else "—"
            lang_table.add_row(str(i), lang, str(count), pct)
        _console.print()
        _console.print(lang_table)

    msg.good("Statistics retrieval complete")
    return None


@registry.register(
    "lang_stats", "Get detailed statistics for specific language(s)", "data"
)
def get_language_details() -> None:
    """Get detailed statistics for a specific language or multiple languages."""
    language_input = input(
        "\n  Enter language(s) (name/code, comma-separated for multiple): "
    ).strip()

    if not language_input:
        msg.warn("No language specified.")
        return

    period = input("  Time period (YYYY-MM or press Enter for last 30 days): ").strip()

    lumo = Lumo()

    if period:
        try:
            year, month_num = map(int, period.split("-"))
            lumo.load_month(year, month_num)
            period_desc = f"{year}-{month_num:02d}"
        except (ValueError, IndexError):
            msg.warn("Invalid date format. Using last 30 days.")
            lumo.load_last_days(30)
            period_desc = "last 30 days"
    else:
        lumo.load_last_days(30)
        period_desc = "last 30 days"

    msg.divider(f"Language Statistics for {period_desc}")

    if "," in language_input or "+" in language_input:
        stats_dict = lumo.get_stats_for_languages(language_input)

        for lang_name, stats in stats_dict.items():
            if stats:
                _print_language_stats(stats)

                freq_info = Lumo.get_language_frequency_info(lang_name)
                if freq_info:
                    msg.text(
                        f"Typical frequency: {freq_info['rate_monthly']:.2f} posts/month"
                    )
            else:
                msg.warn(
                    f"{lang_name}: No data found for this language in the specified period."
                )
    else:
        stats = lumo.get_language_stats(language_input)

        if stats:
            _print_language_stats(stats)

            freq_info = Lumo.get_language_frequency_info(language_input)
            if freq_info:
                msg.text("Typical frequency data:")
                msg.text(f"  Daily: {freq_info['rate_daily']:.2f} posts/day")
                msg.text(f"  Monthly: {freq_info['rate_monthly']:.2f} posts/month")
                msg.text(f"  Yearly: {freq_info['rate_yearly']:.2f} posts/year")
        else:
            msg.warn(f"No data found for '{language_input}' in {period_desc}")


@registry.register(
    "post_monthly", "Analyze and post full monthly statistics to Reddit", "admin"
)
def post_monthly_statistics_menu() -> None:
    """Menu wrapper for posting monthly statistics."""
    month_year = input("\n  Enter month (YYYY-MM) to post statistics for: ").strip()

    if not month_year or len(month_year) != 7 or month_year[4] != "-":
        msg.fail("Invalid format. Please use YYYY-MM format (e.g., 2024-09)")
        return

    confirm = input(f"  Analyze statistics for {month_year}? (y/n): ").strip().lower()
    if confirm != "y":
        msg.warn("Cancelled.")
        return

    post_monthly_statistics(month_year)


# ─── Monthly statistics pipeline ──────────────────────────────────────────────


def post_monthly_statistics(month_year: str) -> None:
    """
    Post monthly statistics to Reddit and update wiki pages using Lumo analyzer.

    This function:
    1. Creates the monthly wiki page (e.g., /wiki/2025_05)
    2. Posts a text submission to the subreddit
    3. Updates individual language wiki pages
    4. Updates the statistics index page
    5. Adds a points summary comment

    Args:
        month_year: The month and year in YYYY-MM format

    Returns:
        None
    """
    r = REDDIT.subreddit(SETTINGS["subreddit"])

    try:
        year_number, month_number = month_year.split("-")
        year_int, month_int = int(year_number), int(month_number)
        month_english_name = date(1900, month_int, 1).strftime("%B")
    except (ValueError, IndexError):
        msg.fail("Invalid date format. Please use YYYY-MM format.")
        return

    post_title = f"[Meta] r/translator Statistics – {month_english_name} {year_number}"

    msg.info(f"Loading statistics for {month_english_name} {year_number}...")
    lumo = Lumo()
    lumo.load_month(year_int, month_int)

    if len(lumo) == 0:
        msg.fail(f"No data found for {month_year}")
        return

    msg.good(f"Loaded {len(lumo)} requests. Generating statistics...")

    new_page_content = format_lumo_stats_for_reddit(lumo, month_year)

    msg.divider("GENERATED STATISTICS CONTENT")
    _console.print()
    _console.print(Markdown(new_page_content), style="sandy_brown")
    _console.print()
    msg.divider()

    approval = (
        input(
            "Review the content above. Continue with posting and wiki updates? (y/n): "
        )
        .strip()
        .lower()
    )
    if approval != "y":
        msg.warn("Operation cancelled by user.")
        return

    # Check if a post for this month already exists.
    previous_stats_post_check = []
    for submission in r.search(f'title:"{post_title}"', sort="new", time_filter="year"):
        previous_stats_post_check.append(submission.id)

    if len(previous_stats_post_check) > 0:
        previous_post = previous_stats_post_check[0]
        msg.warn(
            f"A statistics post for this month already exists: https://redd.it/{previous_post}"
        )

        continue_anyway = (
            input("  Continue with wiki updates only? (y/n): ").strip().lower()
        )
        if continue_anyway != "y":
            msg.warn("Cancelled.")
            return

        okay_to_post = False
    else:
        okay_to_post = True

    # Step 1: Create/Update the monthly wiki page.
    msg.info("[1/5] Creating monthly wiki page...")
    wiki_url = update_monthly_wiki_page(month_year, new_page_content)

    if wiki_url:
        msg.good(f"Wiki page created/updated: {wiki_url}")
    else:
        msg.warn("Could not create/update wiki page")

    # Step 2: Post to Reddit (if no previous post exists).
    monthly_post = None
    if okay_to_post:
        monthly_commentary = input(
            "\n[2/5] Include a note in the post? (Type note or press Enter to skip): "
        )

        if monthly_commentary.strip():
            part_1, part_2 = new_page_content.split("## Overall Statistics")
            new_page_content = (
                f"{part_1}{monthly_commentary}\n\n## Overall Statistics{part_2}"
            )

        new_page_content = new_page_content.replace("![](%%statistics-h%%)", "")

        msg.info("Submitting post to Reddit...")
        monthly_post = r.submit(
            title=post_title, selftext=new_page_content, send_replies=True
        )
        monthly_post.mod.distinguish()

        logger.info(
            "Created a monthly entry page for the last month and posted a text post."
        )
        msg.good(f"Posted to Reddit: https://redd.it/{monthly_post.id}")
    else:
        msg.info("[2/5] Skipping Reddit post (already exists)")

    # Step 3-4: Update wiki pages.
    msg.info("[3/5] Updating individual language wiki pages...")
    update_language_wiki_pages(lumo, month_year)

    msg.info("[4/5] Updating statistics index page...")
    update_statistics_index_page(month_year)

    # Step 5: Add points summary comment.
    if okay_to_post and monthly_post:
        msg.info("[5/5] Adding points summary comment...")

        # Points use the previous month (handles January → December of prior year).
        if month_int == 1:
            points_year = year_int - 1
            points_month = 12
        else:
            points_year = year_int
            points_month = month_int - 1
        month_use_string = f"{points_year}-{points_month:02d}"

        points_summary = get_month_points_summary(month_use_string)
        points_comment = monthly_post.reply(points_summary)
        points_comment.mod.distinguish(sticky=True)
        msg.good("Added points data comment")

        subject_line = (
            f"r/translator Statistics for {month_english_name} {year_number} Posted"
        )
        message = (
            f"The translation statistics for **{month_english_name} {year_number}** "
            f"may be viewed [here](https://www.reddit.com{monthly_post.permalink})."
        )
        send_discord_alert(subject_line, message, "notification")

        msg.good(
            f"Successfully posted statistics for {month_english_name} {year_number}",
            f"Post URL: https://redd.it/{monthly_post.id}"
            + (f"\n\nWiki URL: {wiki_url}" if wiki_url else ""),
        )
    else:
        msg.info("[5/5] Skipping points comment (no new post)")
        msg.good(
            f"Wiki updates complete for {month_english_name} {year_number}",
            f"Wiki URL: {wiki_url}" if wiki_url else "",
        )

    return


# ─── Main application loop ────────────────────────────────────────────────────


def main() -> None:
    """Main application loop."""
    msg.divider("WENYUAN - Translation Statistics & Analytics System for r/translator")
    msg.divider("Logged in as u/translator-BOT")

    msg.info("Validating data files...")
    data_validator()
    msg.good("Data validation complete")

    while True:
        registry.display_menu()

        user_input = input("\n  Enter command (or 'x' to quit): ").strip().lower()

        start_time = time.time()
        should_continue = registry.execute(user_input)
        elapsed = time.time() - start_time

        if not should_continue:
            msg.text("Goodbye!")
            break

        if elapsed > 0.1:  # Only show timing for substantial operations
            msg.text(f"Completed in {elapsed:.2f}s")


if __name__ == "__main__":
    main()
