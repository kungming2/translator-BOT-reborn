#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
Main runtime for Wenyuan. (under construction)
Uses a Pythonic menu system using command registry pattern.
Easily extensible - just add @register_command decorator to new functions.
"""

import calendar
import time
from dataclasses import dataclass
from datetime import date
from typing import Callable, Dict

from config import SETTINGS
from connection import REDDIT, logger
from discord_utils import send_discord_alert
from processes.wenyuan_stats import Lumo
from time_handling import time_convert_to_string_seconds
from usage_statistics import get_month_points_summary
from wenyuan.challenge_poster import translation_challenge_poster
from wenyuan.data_validator import data_validator
from wenyuan.title_full_retrieval import retrieve_titles_test


@dataclass
class MenuOption:
    """Represents a menu option."""

    key: str
    description: str
    function: Callable
    category: str = "general"


class CommandRegistry:
    """Registry for menu options with automatic display generation."""

    def __init__(self):
        self.commands: Dict[str, MenuOption] = {}
        self.categories = {
            "request": "Request Formatting",
            "test": "Testing Functions",
            "data": "Data Retrieval",
            "admin": "Administrative",
            "system": "System",
        }

    def register(self, key: str, description: str, category: str = "general"):
        """Decorator to register a menu option."""

        def decorator(func: Callable) -> Callable:
            self.commands[key] = MenuOption(key, description, func, category)
            return func

        return decorator

    def display_menu(self) -> str:
        """Generate formatted menu display from registered commands."""
        lines = ["\n" + "=" * 70, "WENYUAN COMMAND MENU", "=" * 70]

        # Group commands by category
        categorized = {}
        for cmd in self.commands.values():
            categorized.setdefault(cmd.category, []).append(cmd)

        # Display each category
        for category_key in ["request", "test", "data", "admin", "system"]:
            if category_key in categorized:
                lines.append(
                    f"\n{self.categories.get(category_key, category_key).upper()}"
                )
                lines.append("-" * 70)
                for cmd in sorted(categorized[category_key], key=lambda x: x.key):
                    lines.append(f"  {cmd.key:<10} {cmd.description}")

        lines.append("=" * 70)
        return "\n".join(lines)

    def execute(self, key: str) -> bool:
        """Execute a command by key. Returns False if should exit."""
        if key == "x":
            return False

        cmd = self.commands.get(key)
        if cmd:
            try:
                cmd.function()
            except Exception as e:
                print(f"\n❌ Error executing command: {e}")
        else:
            print(f"\n⚠️  Unknown command: '{key}'")

        return True


# Create global registry
registry = CommandRegistry()


# ============================================================================
# COMMAND DEFINITIONS - Just add @registry.register decorator to new functions
# ============================================================================


@registry.register("challenge", "Post the weekly translation challenge", "request")
def post_challenge():
    """Post the weekly translation challenge."""
    translation_challenge_poster()


@registry.register("retrieval", "Test bulk title testing data", "test")
def title_full_retrieval():
    """Test full retrieval."""
    num_retrieve = input("\n  Enter the number of posts you wish to test: ").strip()
    retrieve_titles_test(int(num_retrieve))


"""MONTHLY STATISTICS UPDATE"""


def format_lumo_stats_for_reddit(lumo, month_year: str) -> str:
    """
    Format Lumo statistics into Reddit markdown for posting.

    Args:
        lumo: Lumo instance with loaded data
        month_year: Month in YYYY-MM format

    Returns:
        Formatted markdown string
    """
    # Parse date for header
    year_number, month_number = month_year.split("-")
    month_english_name = date(1900, int(month_number), 1).strftime("%B")

    # Get all statistics
    overall = lumo.get_overall_stats()
    directions = lumo.get_direction_stats()
    top_langs = lumo.get_language_rankings(by="total")
    fastest = lumo.get_fastest_translations()
    identification = lumo.get_identification_stats()

    # Start building the markdown content
    content = f"# Statistics for {month_english_name} {year_number}\n\n"
    content += f"*Analysis of {overall['total_requests']} translation requests*\n\n"
    content += "---\n\n"

    # Overall Statistics Section
    content += "## Overall Statistics\n\n"
    content += f"* **Total Requests:** {overall['total_requests']}\n"
    content += f"* **Translated:** {overall['translated']} ({overall['translation_percentage']}%)\n"
    content += f"* **Needs Review:** {overall['needs_review']}\n"
    content += f"* **Untranslated:** {overall['untranslated']}\n"
    content += f"* **In Progress:** {overall['in_progress']}\n"
    content += f"* **Missing Assets:** {overall['missing_assets']}\n"
    content += f"* **Unique Languages:** {overall['unique_languages']}\n\n"

    # Translation Direction Statistics
    content += "## Translation Directions\n\n"
    content += (
        f"* **To English:** {directions['to_english']['count']} "
        f"({directions['to_english']['percentage']}%)\n"
    )
    content += (
        f"* **From English:** {directions['from_english']['count']} "
        f"({directions['from_english']['percentage']}%)\n"
    )
    content += (
        f"* **Non-English:** {directions['non_english']['count']} "
        f"({directions['non_english']['percentage']}%)\n\n"
    )

    # Top Languages Section
    content += "## Top Languages\n\n"
    content += "| Rank | Language | Requests | Translated |\n"
    content += "|------|----------|----------|------------|\n"

    for i, (lang, count) in enumerate(top_langs[:20], 1):  # Top 20
        stats = lumo.get_language_stats(lang)
        if stats:
            content += (
                f"| {i} | {lang} | {count} | {stats['translation_percentage']}% |\n"
            )

    content += "\n"

    # Fastest Translations
    content += "## Processing Speed\n\n"

    if "average_translation_hours" in fastest:
        content += f"* **Average Translation Time:** {fastest['average_translation_hours']} hours\n"

    if fastest["to_translated"]["id"]:
        time_str = time_convert_to_string_seconds(fastest["to_translated"]["time"])
        content += f"* **Fastest Translation:** {time_str} ([link](https://redd.it/{fastest['to_translated']['id']}))\n"

    if fastest["to_claimed"]["id"]:
        time_str = time_convert_to_string_seconds(fastest["to_claimed"]["time"])
        content += f"* **Fastest Claim:** {time_str} ([link](https://redd.it/{fastest['to_claimed']['id']}))\n"

    content += "\n"

    # Identification Statistics
    if identification["identified_from_unknown"]:
        content += "## Language Identification\n\n"
        content += "Posts successfully identified from 'Unknown':\n\n"

        sorted_identified = sorted(
            identification["identified_from_unknown"].items(),
            key=lambda x: x[1],
            reverse=True,
        )

        for lang, count in sorted_identified[:10]:  # Top 10
            content += f"* **{lang}:** {count}\n"

        content += "\n"

    # Footer
    content += "---\n\n"
    content += "*Statistics generated using the Lumo analyzer. "
    content += f"Data from {month_english_name} 1 - {month_english_name} "

    # Get last day of month
    last_day = calendar.monthrange(int(year_number), int(month_number))[1]
    content += f"{last_day}, {year_number}.*\n"

    return content


@registry.register("stats", "Retrieve post statistics", "data")
def retrieve_post_stats():
    """Retrieve post statistics using the Lumo analyzer."""
    month = input("\n  Enter month (YYYY-MM) or press Enter for last 30 days: ").strip()

    # Initialize Lumo
    lumo = Lumo()

    # Load data based on input
    if month:
        try:
            # Parse YYYY-MM format
            year, month_num = map(int, month.split("-"))
            lumo.load_month(year, month_num)
            period_desc = f"{year}-{month_num:02d}"
        except (ValueError, IndexError):
            print("Invalid date format. Please use YYYY-MM format.")
            return None
    else:
        # Load last 30 days
        lumo.load_last_days(30)
        period_desc = "last 30 days"

    # Get and display statistics
    print(f"\n=== Statistics for {period_desc} ===")
    print(f"Total posts loaded: {len(lumo)}\n")

    # Overall statistics
    overall = lumo.get_overall_stats()
    print("--- Overall Statistics ---")
    print(f"Total requests: {overall['total_requests']}")
    print(f"Translated: {overall['translated']} ({overall['translation_percentage']}%)")
    print(f"Needs review: {overall['needs_review']}")
    print(f"Untranslated: {overall['untranslated']}")
    print(f"In progress: {overall['in_progress']}")
    print(f"Missing assets: {overall['missing_assets']}")
    print(f"Unique languages: {overall['unique_languages']}\n")

    # Direction statistics
    directions = lumo.get_direction_stats()
    print("--- Translation Directions ---")
    print(
        f"To English: {directions['to_english']['count']} ({directions['to_english']['percentage']}%)"
    )
    print(
        f"From English: {directions['from_english']['count']} ({directions['from_english']['percentage']}%)"
    )
    print(
        f"Non-English: {directions['non_english']['count']} ({directions['non_english']['percentage']}%)\n"
    )

    # Top languages
    top_langs = lumo.get_language_rankings(by="total")[:10]
    if top_langs:
        print("--- Top 10 Languages ---")
        for i, (lang, count) in enumerate(top_langs, 1):
            stats = lumo.get_language_stats(lang)
            if stats:
                print(
                    f"{i}. {lang}: {count} requests ({stats['translation_percentage']}% translated)"
                )

    return lumo  # Return the Lumo instance for further use


def post_monthly_statistics(month_year: str):
    """
    Post monthly statistics to Reddit using Lumo analyzer.

    Args:
        month_year: The month and year in YYYY-MM format

    Returns:
        None
    """
    # Parse the date
    r = REDDIT.subreddit(SETTINGS["subreddit"])

    year_number, month_number = month_year.split("-")
    month_english_name = date(1900, int(month_number), 1).strftime("%B")

    # Generate the post title
    post_title = f"[META] r/translator Statistics — {month_english_name} {year_number}"

    # Initialize Lumo and load data for the specified month
    print(f"Loading statistics for {month_english_name} {year_number}...")
    lumo = Lumo()
    year_int, month_int = int(year_number), int(month_number)
    lumo.load_month(year_int, month_int)

    if len(lumo) == 0:
        print(f"No data found for {month_year}")
        return

    print(f"Loaded {len(lumo)} requests. Generating statistics...")

    # Format the statistics post
    new_page_content = format_lumo_stats_for_reddit(lumo, month_year)

    # Conduct a search check to see if there's already been a post
    previous_stats_post_check = []
    for submission in r.search(f'title:"{post_title}"', sort="new", time_filter="year"):
        previous_stats_post_check.append(submission.id)

    if len(previous_stats_post_check) == 0:
        okay_to_post = True
    else:
        okay_to_post = False

    # There's no prior content. We can submit.
    if okay_to_post:
        # Check to see if there's a specific text we wish to include in the post
        monthly_commentary = input(
            "Do you want to include a note in the monthly post? Type the note or 's' to skip: "
        )

        if monthly_commentary.lower() != "s":
            part_1, part_2 = new_page_content.split("## Overall Statistics")
            new_page_content = (
                f"{part_1}{monthly_commentary}\n\n## Overall Statistics{part_2}"
            )

        # Replace the image placeholder for the post
        new_page_content = new_page_content.replace("![](%%statistics-h%%)", "")

        # Submit the post
        monthly_post = r.submit(
            title=post_title, selftext=new_page_content, send_replies=True
        )
        monthly_post.mod.sticky(state=True, bottom=True)
        monthly_post.mod.distinguish()

        logger.info(
            "[WY] Created a monthly entry page for the last month and posted a text post."
        )

        # Calculate previous month for points
        if month_number != "01":  # January would reset so...
            points_use_month = str(int(month_number))
            if len(points_use_month) < 2:
                points_use_month = "0" + points_use_month
        else:  # It's January. Get the month and year from last.
            points_use_month = "12"
            year_number = str(int(year_number) - 1)

        # Format the points comment
        month_use_string = f"{year_number}-{points_use_month}"
        points_summary = get_month_points_summary(month_use_string)
        points_comment = monthly_post.reply(points_summary)
        points_comment.mod.distinguish(sticky=True)
        print(">> Also added a comment with the points data.")

        # Send a Discord notification
        subject_line = (
            f"r/translator Statistics for {month_english_name} {year_number} Posted"
        )
        message = (
            f"The translation statistics for **{month_english_name} {year_number}** "
            f"may be viewed [here](https://www.reddit.com{monthly_post.permalink})."
        )
        send_discord_alert(subject_line, message, "notification")

        print(
            f"✓ Successfully posted statistics for {month_english_name} {year_number}"
        )
        print(f"  URL: https://redd.it/{monthly_post.id}")
    else:
        previous_post = previous_stats_post_check[0]
        print(
            f"> It seems that there is already a statistics post for this month "
            f"at https://redd.it/{previous_post}."
        )

    return


# ============================================================================
# MAIN APPLICATION LOOP
# ============================================================================


def main():
    """Main application loop."""
    data_validator()

    while True:
        print("\n" + "=" * 70)
        print("Logging in as u/translator-BOT...")
        print("=" * 70)

        print(registry.display_menu())

        user_input = input("\n  Enter command (or 'x' to quit): ").strip().lower()

        start_time = time.time()
        should_continue = registry.execute(user_input)
        elapsed = time.time() - start_time

        if not should_continue:
            print("\n👋 Goodbye!")
            break

        if elapsed > 0.1:  # Only show timing for substantial operations
            print(f"\n⏱️  Completed in {elapsed:.2f}s")


if __name__ == "__main__":
    main()
