#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
Main runtime for Wenyuan - Translation Statistics & Analytics System

Uses a Pythonic menu system with command registry pattern.
Easily extensible - just add @register_command decorator to new functions.

Compatible with refactored Lumo analyzer (wenyuan_stats.py).
"""

import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import cast

from praw.models import Comment
from rich import box
from rich.console import Console
from rich.markdown import Markdown
from rich.table import Table
from wasabi import Printer

from config import SETTINGS, logger
from integrations.discord_utils import send_discord_alert
from lang.languages import converter
from monitoring.points import get_month_points_summary
from processes.wenyuan_stats import Lumo
from reddit.connection import REDDIT
from wenyuan.challenge_poster import translation_challenge_poster
from wenyuan.data_validator import data_validator
from wenyuan.monthly_reporting import format_lumo_stats_for_reddit
from wenyuan.update_wiki_stats import (
    update_language_wiki_pages,
    update_monthly_wiki_page,
    update_overall_statistics_page,
    update_statistics_index_page,
)
from ziwen_lookup.reference import get_language_reference

msg = Printer()
_console = Console()

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
            "posts": "Reddit Posts",
            "stats": "Statistics",
            "reference": "Reference Data",
            "test": "Testing",
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
        table.add_column("Command", style="cyan", no_wrap=True, min_width=18)
        table.add_column("Description", style="white", min_width=32)
        table.add_column("Category", style="dim", no_wrap=True, min_width=14)

        for category_key in ["stats", "reference", "posts", "test", "system"]:
            if category_key not in categorized:
                continue
            category_label = self.categories.get(category_key, category_key)
            for cmd in sorted(categorized[category_key], key=lambda x: x.key):
                table.add_row(
                    cmd.key,
                    cmd.description,
                    category_label,
                )

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


def _format_ajo_date(created_utc: int | None) -> str:
    """Return a compact UTC date for an Ajo timestamp."""
    if created_utc is None:
        return "Unknown"
    return datetime.fromtimestamp(created_utc, UTC).strftime("%Y-%m-%d")


def _format_ajo_direction(direction: str | None) -> str:
    """Return a readable compact direction label."""
    direction_labels = {
        "english_to": "To English",
        "english_from": "From English",
        "english_none": "Non-English",
        "english_both": "English both",
    }
    if direction is None:
        return "Unknown"
    return direction_labels.get(direction, direction)


def _created_utc_sort_key(candidate: object) -> int:
    """Return an Ajo-like object's created timestamp for newest-first sorting."""
    created_utc = getattr(candidate, "created_utc", None)
    return created_utc if isinstance(created_utc, int) else 0


def _parse_recent_ajo_limit() -> int:
    """Prompt for how many recent Ajos to show with language statistics."""
    limit_input = input(
        "  Number of recent matching Ajos to show (press Enter for 5, 0 for none): "
    ).strip()

    if not limit_input:
        return 5

    try:
        limit = int(limit_input)
    except ValueError:
        msg.warn("Invalid Ajo count. Skipping recent Ajo list.")
        return 0

    if limit < 0:
        msg.warn("Ajo count cannot be negative. Skipping recent Ajo list.")
        return 0

    return limit


def _print_recent_language_ajos(lumo: Lumo, language: str, limit: int) -> None:
    """Print the newest loaded Ajos matching a language."""
    if limit < 1:
        return

    matching_ajos = sorted(
        lumo.filter_by_language(language),
        key=_created_utc_sort_key,
        reverse=True,
    )

    if not matching_ajos:
        return

    lingvo = converter(language)
    language_name = lingvo.name if lingvo and lingvo.name else language
    table = Table(
        title=f"Last {min(limit, len(matching_ajos))} {language_name} Ajos",
        box=box.SIMPLE_HEAD,
        show_header=True,
        header_style="bold",
        title_style="bold sandy_brown",
        padding=(0, 1),
    )
    table.add_column("Date", style="dim", no_wrap=True, width=10)
    table.add_column("Post", style="cyan", no_wrap=True, min_width=14)
    table.add_column("Status", style="white", no_wrap=True, min_width=12)
    table.add_column("Direction", style="white", no_wrap=True, min_width=12)

    for recent_match in matching_ajos[:limit]:
        post_id = recent_match.id or "Unknown"
        table.add_row(
            _format_ajo_date(recent_match.created_utc),
            f"redd.it/{post_id}" if recent_match.id else post_id,
            str(recent_match.status),
            _format_ajo_direction(recent_match.direction),
        )

    _console.print()
    _console.print(table)


# ─── Command definitions ──────────────────────────────────────────────────────


@registry.register("post_challenge", "Post weekly challenge", "posts")
def post_challenge() -> None:
    """Post the weekly translation challenge."""
    translation_challenge_poster()


@registry.register(
    "language_reference",
    "Fetch language reference data",
    "reference",
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


@registry.register("language_stats", "Show stats for selected languages", "stats")
def get_language_details() -> None:
    """Get detailed statistics for a specific language or multiple languages."""
    language_input = input(
        "\n  Enter language(s) (name/code, comma-separated for multiple): "
    ).strip()

    if not language_input:
        msg.warn("No language specified.")
        return

    period = input("  Time period (YYYY-MM or press Enter for last 30 days): ").strip()
    recent_ajo_limit = _parse_recent_ajo_limit()

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
                _print_recent_language_ajos(lumo, lang_name, recent_ajo_limit)
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
            _print_recent_language_ajos(lumo, language_input, recent_ajo_limit)
        else:
            msg.warn(f"No data found for '{language_input}' in {period_desc}")


@registry.register("post_monthly_stats", "Post monthly statistics report", "stats")
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
    4. Updates the statistics index and overall statistics pages
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

    msg.info("[4/5] Updating statistics index and overall statistics pages...")
    update_statistics_index_page(month_year)
    update_overall_statistics_page(lumo, month_year)

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
        points_comment = cast(Comment, monthly_post.reply(points_summary))
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
