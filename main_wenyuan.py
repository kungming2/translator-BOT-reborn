#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
Main runtime for Wenyuan - Translation Statistics & Analytics System

Uses a Pythonic menu system with command registry pattern.
Easily extensible - just add @register_command decorator to new functions.

Compatible with refactored Lumo analyzer (wenyuan_stats.py).
"""

import calendar
import time
from dataclasses import dataclass
from datetime import date
from typing import Callable

from config import SETTINGS
from connection import REDDIT, logger
from discord_utils import send_discord_alert
from languages import converter
from lookup.reference import get_language_reference
from processes.wenyuan_stats import Lumo
from time_handling import time_convert_to_string_seconds
from usage_statistics import get_month_points_summary
from wenyuan.challenge_poster import translation_challenge_poster
from wenyuan.data_validator import data_validator
from wenyuan.title_full_retrieval import retrieve_titles_test
from wenyuan.update_wiki_stats import (
    calculate_ri,
    update_language_wiki_pages,
    update_statistics_index_page,
    update_monthly_wiki_page,
)

# Utility codes that get special handling
UTILITY_CODES = [
    "Unknown",
    "Generic",
    "Nonlanguage",
    "Conlang",
    "App",
    "Multiple Languages",
]


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
        self.commands: dict[str, MenuOption] = {}
        self.categories = {
            "posts": "Create Posts",
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
        for category_key in ["posts", "test", "data", "admin", "system"]:
            if category_key in categorized:
                lines.append(
                    f"\n{self.categories.get(category_key, category_key).upper()}"
                )
                lines.append("-" * 70)
                for cmd in sorted(categorized[category_key], key=lambda x: x.key):
                    lines.append(f"  {cmd.key:<20} {cmd.description}")

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
                logger.error(f"[WY] Command execution error: {e}", exc_info=True)
        else:
            print(f"\n⚠️  Unknown command: '{key}'")

        return True


# Create global registry
registry = CommandRegistry()


# ============================================================================
# COMMAND DEFINITIONS - Note: Add @registry.register decorator to new functions
# ============================================================================


@registry.register("challenge", "Post the weekly translation challenge", "posts")
def post_challenge():
    """Post the weekly translation challenge."""
    translation_challenge_poster()


@registry.register("title_retrieval", "Test bulk title testing data", "test")
def title_full_retrieval():
    """Test full retrieval."""
    num_retrieve = input("\n  Enter the number of posts you wish to test: ").strip()
    try:
        retrieve_titles_test(int(num_retrieve))
    except ValueError:
        print("Invalid number. Please enter a valid integer.")


@registry.register(
    "lang_reference",
    "Fetch reference data for a language from Ethnologue/Wikipedia",
    "data",
)
def fetch_language_reference():
    """Fetch reference data for a language from archived Ethnologue and Wikipedia."""

    language_input = input("\n  Enter language code (ISO 639-1 or ISO 639-3): ").strip()

    if not language_input:
        print("No language code specified.")
        return

    print(f"\nFetching reference data for '{language_input}'...")
    print("(This may take a moment as it accesses archived web pages)\n")

    reference_data = get_language_reference(language_input)

    if not reference_data:
        print(f"❌ Could not retrieve reference data for '{language_input}'")
        print("   This could mean:")
        print("   - The language code is invalid")
        print("   - No archived Ethnologue page exists")
        print("   - There was a network error")
        return

    # Display the retrieved data
    print("=" * 70)
    print(f"REFERENCE DATA FOR: {reference_data.get('name', 'Unknown')}")
    print("=" * 70)
    print(
        f"\nLanguage Code (ISO 639-3): {reference_data.get('language_code_3', 'N/A')}"
    )
    print(f"Primary Name: {reference_data.get('name', 'N/A')}")

    alt_names = reference_data.get("name_alternates", [])
    if alt_names:
        print(f"Alternate Names: {', '.join(alt_names)}")

    print(f"\nCountry: {reference_data.get('country', 'N/A')}")
    print(f"Language Family: {reference_data.get('family', 'N/A')}")

    population = reference_data.get("population", 0)
    if population > 0:
        print(f"Population: {population:,} speakers")
    else:
        print("Population: Unknown")

    print("\nLinks:")
    if reference_data.get("link_wikipedia"):
        print(f"  Wikipedia: {reference_data['link_wikipedia']}")
    if reference_data.get("link_ethnologue"):
        print(f"  Ethnologue: {reference_data['link_ethnologue']}")
    if reference_data.get("link_sil"):
        print(f"  SIL: {reference_data['link_sil']}")

    print("\n✓ Reference data retrieval complete")


# ============================================================================
# MONTHLY STATISTICS FUNCTIONS
# ============================================================================


def format_lumo_stats_for_reddit(lumo: Lumo, month_year: str) -> str:
    """
    Format Lumo statistics into Reddit markdown for posting.

    Args:
        lumo: Lumo instance with loaded data
        month_year: Month in YYYY-MM format

    Returns:
        Formatted markdown string matching monthly_output.md structure
    """
    # Parse date for header
    year_number, month_number = month_year.split("-")
    month_english_name = date(1900, int(month_number), 1).strftime("%B")

    # Get all statistics
    overall = lumo.get_overall_stats()
    directions = lumo.get_direction_stats()
    identification = lumo.get_identification_stats()
    fastest = lumo.get_fastest_translations()

    # Count multiple language posts by type
    multiple_language_count = len(lumo.filter_by_type("multiple"))

    # Start building the markdown content
    content = (
        f"# [{month_english_name} {year_number}](https://www.reddit.com/r/translator/wiki/"
        f"{year_number}_{month_number}) \n"
    )
    content += (
        "*[Statistics](https://www.reddit.com/r/translator/wiki/statistics) for r/translator "
        "provided by [Wenyuan](https://www.reddit.com/r/translatorBOT/wiki/wenyuan)*\n\n"
    )
    content += f"Here are the statistics for {month_english_name} {year_number}.\n\n"

    # Overall Statistics Section
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
    content += (
        "*Meta/Community Posts* | *8*\n\n"  # This would need to be tracked separately
    )

    # Language Families Section
    content += "### Language Families\n"
    content += "Language Family | Total Requests | Percent of All Requests\n"
    content += "----|----|----\n"

    # Group languages by family (excluding utility codes and scripts)
    family_counts = {}
    all_languages = sorted(lumo.get_all_languages())

    for lang in all_languages:
        # Skip utility codes
        if lang in UTILITY_CODES:
            continue

        lingvo = converter(lang)
        if not lingvo:
            continue

        # Skip Unknown scripts
        if len(lingvo.preferred_code) == 4 or lingvo.script_code:
            continue

        if lingvo.family:
            family = lingvo.family
            stats = lumo.get_language_stats(lang)
            if stats:
                family_counts[family] = (
                    family_counts.get(family, 0) + stats["total_requests"]
                )

    # Sort families by count
    sorted_families = sorted(family_counts.items(), key=lambda x: x[1], reverse=True)

    for family, count in sorted_families:
        percent = round((count / overall["total_requests"]) * 100, 2)
        content += f"{family} | {count} | {percent}%\n"

    content += "\n"

    # Single-Language Requests Table
    content += "### Single-Language Requests\n"
    content += (
        "Language | Language Family | Total Requests | Percent of All Requests | "
    )
    content += "Untranslated Requests | Translation Percentage | Ratio | "
    content += "Identified from 'Unknown' | RI | Wikipedia Link\n"
    content += "-----|-----|--|----|-----|---|-----|---|---|-----\n"

    # Get identification data
    identified_from_unknown = identification.get("identified_from_unknown", {})

    for lang in all_languages:
        # Skip utility codes
        if lang in UTILITY_CODES:
            continue

        stats = lumo.get_language_stats(lang)
        if not stats:
            continue

        # Get the Lingvo object for additional data
        lingvo = converter(lang)
        if not lingvo:
            continue

        # Skip Unknown scripts
        if len(lingvo.preferred_code) == 4 or lingvo.script_code:
            continue

        # Basic stats
        total = stats["total_requests"]
        percent_all = stats["percent_of_all_requests"]
        untranslated = stats["untranslated"]
        trans_pct = stats["translation_percentage"]
        ratio = stats["directions"]

        # Identification count
        identified_count = identified_from_unknown.get(lang, 0)

        # Language family (use "N/A" if not available)
        family = lingvo.family if lingvo.family else "N/A"

        # RI (Representation Index) - calculate using the calculate_ri function
        ri_value = "---"
        if lingvo.population and lingvo.population > 0:
            # lingvo.population is already the actual speaker count
            ri = calculate_ri(
                language_posts=total,
                total_posts=overall["total_requests"],
                native_speakers=lingvo.population,
            )
            if ri is not None:
                ri_value = str(ri)

        # Wikipedia link using preferred code
        wp_link = f"[WP](https://en.wikipedia.org/wiki/ISO_639:{lingvo.preferred_code})"

        # Wiki link for language name (convert to lowercase with underscores)
        wiki_name = lang.replace(" ", "_").lower()
        lang_link = f"[{lang}](https://www.reddit.com/r/translator/wiki/{wiki_name})"

        # Search link with Reddit search URL
        search_link = (
            f'[{total}](/r/translator/search?q=flair:"{lang.replace(" ", "_")}"'
            f'+OR+flair:"[{lingvo.preferred_code.upper()}]"&sort=new&restrict_sr=on)'
        )

        # Build the row
        row = (
            f"| {lang_link} | {family} | {search_link} | {percent_all}% | "
            f"{untranslated} | {trans_pct}% | {ratio} | {identified_count} | "
            f"{ri_value} | {wp_link} |"
        )

        content += row + "\n"

    content += "\n"

    # Translation Direction Statistics
    # Translation Direction Statistics
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

    # 'Unknown' Identifications
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

        # Calculate misidentification percentages for each language
        # This is: (posts identified from Unknown as this language) / (total posts for this language) * 100
        for lang, count in sorted_identified[:13]:  # Top 13 like in the example
            percent_of_unknown = round((count / total_identified) * 100, 2)

            # Get total requests for this language to calculate misidentification rate
            lang_stats = lumo.get_language_stats(lang)
            if lang_stats and lang_stats["total_requests"] > 0:
                misidentification_pct = round(
                    (count / lang_stats["total_requests"]) * 100, 2
                )
                content += f"{lang} | {count} | {percent_of_unknown}% | {misidentification_pct}%\n"
            else:
                content += f"{lang} | {count} | {percent_of_unknown}% | ---\n"

        content += "\n"

    # Commonly Misidentified Language Pairs
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
        post_data: dict, post_label: str, post_action: str
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

    # Quickest Processed Posts
    content += "##### Quickest Processed Posts\n\n"

    # Define the post types to check
    post_types = [
        (fastest.get("to_review"), '"Needs Review" request', "was marked for review"),
        (fastest.get("to_translated"), '"Translated" request', "was translated"),
        (fastest.get("to_claimed"), "claimed request", "was claimed"),
    ]

    has_any_data = False

    # Process each post type
    for data, label, action in post_types:
        if formatted := _format_fastest_post(data, label, action):
            content += formatted
            has_any_data = True

    # Add average translation time if available
    if (avg_hours := fastest.get("average_translation_hours")) is not None:
        if isinstance(avg_hours, (int, float)) and avg_hours > 0:
            content += (
                f"* The average request was translated in {avg_hours:.1f} hours.\n"
            )
            has_any_data = True

    # If no data was found, add a message
    if not has_any_data:
        content += "* No data available for this period.\n"

    content += "\n"

    # Other Single-Language Requests/Posts section
    # Now get actual counts for utility codes
    content += "#### Other Single-Language Requests/Posts\n\n"
    content += "Category | Total Requests\n"
    content += "---|---\n"

    # Get counts for each utility code
    for utility_code in ["Generic", "Unknown", "Nonlanguage", "Conlang"]:
        utility_ajos = lumo.filter_by_language(utility_code)
        count = len(utility_ajos)

        # Format the flair for search URL
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
            search_flair = utility_code
            code = utility_code.upper()

        search_url = (
            f"[{count}](https://www.reddit.com/r/translator/search?q=flair:%22{search_flair}%22+"
            f"OR+flair:%22{code}%22&sort=new&restrict_sr=on)"
        )

        content += f"{utility_code} | {search_url}\n"

    # Check for Unknown scripts
    content += "\n##### Unknown Requests with Identified Scripts\n\n"
    content += "Script (Unknown) | Total Requests\n"
    content += "---|---\n"

    unknown_scripts = {}
    for lang in all_languages:
        lingvo = converter(lang)
        if lingvo and len(lingvo.preferred_code) == 4 and lingvo.script_code:
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

    # Multiple-Language/App Requests
    content += "### Multiple-Language/App Requests\n\n"
    content += f"* For any and all languages: {multiple_language_count}\n"
    content += "* *The count for defined 'Multiple' requests are integrated into the table above.*\n\n"

    # Footer
    content += "---\n\n"
    content += "*Statistics generated using the Lumo analyzer. "
    content += f"Data from {month_english_name} 1 - "

    # Get last day of month
    last_day = calendar.monthrange(int(year_number), int(month_number))[1]
    content += f"{month_english_name} {last_day}, {year_number}.*\n"

    return content


@registry.register(
    "period_stats",
    "Retrieve abbreviated language statistics from a time period as a list",
    "data",
)
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

    print("\n✓ Statistics retrieval complete")
    return lumo  # Return the Lumo instance for further use


@registry.register(
    "post_monthly", "Analyze and post full monthly statistics to Reddit", "admin"
)
def post_monthly_statistics_menu():
    """Menu wrapper for posting monthly statistics."""
    month_year = input("\n  Enter month (YYYY-MM) to post statistics for: ").strip()

    if not month_year or len(month_year) != 7 or month_year[4] != "-":
        print("Invalid format. Please use YYYY-MM format (e.g., 2024-09)")
        return

    confirm = input(f"  Analyze statistics for {month_year}? (y/n): ").strip().lower()
    if confirm != "y":
        print("Cancelled.")
        return

    post_monthly_statistics(month_year)


def post_monthly_statistics(month_year: str):
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
        print("Invalid date format. Please use YYYY-MM format.")
        return

    # Generate the post title
    post_title = f"[META] r/translator Statistics – {month_english_name} {year_number}"

    # Initialize Lumo and load data for the specified month
    print(f"Loading statistics for {month_english_name} {year_number}...")
    lumo = Lumo()
    lumo.load_month(year_int, month_int)

    if len(lumo) == 0:
        print(f"❌ No data found for {month_year}")
        return

    print(f"✓ Loaded {len(lumo)} requests. Generating statistics...")

    # Format the statistics content
    new_page_content = format_lumo_stats_for_reddit(lumo, month_year)

    # Display the generated content for review
    print("\n" + "=" * 70)
    print("GENERATED STATISTICS CONTENT")
    print("=" * 70)
    print(new_page_content)
    print("=" * 70)
    print()

    # Manual approval check
    approval = (
        input(
            "Review the content above. Continue with posting and wiki updates? (y/n): "
        )
        .strip()
        .lower()
    )
    if approval != "y":
        print("\n❌ Operation cancelled by user.")
        return

    # Check if there's already been a post for this month
    previous_stats_post_check = []
    for submission in r.search(f'title:"{post_title}"', sort="new", time_filter="year"):
        previous_stats_post_check.append(submission.id)

    if len(previous_stats_post_check) > 0:
        previous_post = previous_stats_post_check[0]
        print("\n⚠️  A statistics post for this month already exists:")
        print(f"  https://redd.it/{previous_post}")

        # Ask if they want to continue anyway
        continue_anyway = (
            input("  Continue with wiki updates only? (y/n): ").strip().lower()
        )
        if continue_anyway != "y":
            return

        okay_to_post = False
    else:
        okay_to_post = True

    # Step 1: Create/Update the monthly wiki page
    print("\n[1/5] Creating monthly wiki page...")
    wiki_url = update_monthly_wiki_page(month_year, new_page_content)

    if wiki_url:
        print(f"✓ Wiki page created/updated: {wiki_url}")
    else:
        print("⚠️  Warning: Could not create/update wiki page")

    # Step 2: Post to Reddit (if no previous post exists)
    monthly_post = None
    if okay_to_post:
        # Check to see if there's a specific text we wish to include in the post
        monthly_commentary = input(
            "\n[2/5] Include a note in the post? (Type note or press Enter to skip): "
        )

        if monthly_commentary.strip():
            part_1, part_2 = new_page_content.split("## Overall Statistics")
            new_page_content = (
                f"{part_1}{monthly_commentary}\n\n## Overall Statistics{part_2}"
            )

        # Replace the image placeholder for the post
        new_page_content = new_page_content.replace("![](%%statistics-h%%)", "")

        # Submit the post
        print("Submitting post to Reddit...")
        monthly_post = r.submit(
            title=post_title, selftext=new_page_content, send_replies=True
        )
        monthly_post.mod.sticky(state=True, bottom=True)
        monthly_post.mod.distinguish()

        logger.info(
            "[WY] Created a monthly entry page for the last month and posted a text post."
        )
        print(f"✓ Posted to Reddit: https://redd.it/{monthly_post.id}")
    else:
        print("\n[2/5] Skipping Reddit post (already exists)")

    # Step 3: Update individual language wiki pages
    print("\n[3/5] Updating individual language wiki pages...")
    update_language_wiki_pages(lumo, month_year)

    # Step 4: Update the statistics index page
    print("\n[4/5] Updating statistics index page...")
    update_statistics_index_page(month_year)

    # Step 5: Add points comment (only if we posted)
    if okay_to_post and monthly_post:
        print("\n[5/5] Adding points summary comment...")

        # Calculate previous month for points
        if month_number != "01":  # January would reset so...
            points_use_month = str(month_int)
            if len(points_use_month) < 2:
                points_use_month = "0" + points_use_month
        else:  # It's January. Get the month and year from last.
            points_use_month = "12"
            year_number = str(year_int - 1)

        # Format the points comment
        month_use_string = f"{year_number}-{points_use_month}"
        points_summary = get_month_points_summary(month_use_string)
        points_comment = monthly_post.reply(points_summary)
        points_comment.mod.distinguish(sticky=True)
        print("✓ Added points data comment")

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
            f"\n✓ Successfully posted statistics for {month_english_name} {year_number}"
        )
        print(f"  Post URL: https://redd.it/{monthly_post.id}")
        if wiki_url:
            print(f"  Wiki URL: {wiki_url}")
    else:
        print("\n[5/5] Skipping points comment (no new post)")
        print(f"\n✓ Wiki updates complete for {month_english_name} {year_number}")
        if wiki_url:
            print(f"  Wiki URL: {wiki_url}")

    return


def _print_language_stats(stats: dict[str, object]) -> None:
    """Pretty-print language statistics in a consistent format."""
    if not stats:
        print("No data available for this language.\n")
        return

    print(f"--- {stats.get('language', 'Unknown Language')} ---")
    print(f"Total requests: {stats.get('total_requests', 0)}")
    print(
        f"Translated: {stats.get('translated', 0)} ({stats.get('translation_percentage', 0)}%)"
    )
    print(f"Needs review: {stats.get('needs_review', 0)}")
    print(f"Untranslated: {stats.get('untranslated', 0)}")
    print(f"% of all requests: {stats.get('percent_of_all_requests', 0)}%")
    print(f"Direction ratio: {stats.get('directions', 'N/A')}")
    print()


@registry.register(
    "lang_stats", "Get detailed statistics for specific language(s)", "data"
)
def get_language_details():
    """Get detailed statistics for a specific language or multiple languages."""
    language_input = input(
        "\n  Enter language(s) (name/code, comma-separated for multiple): "
    ).strip()

    if not language_input:
        print("No language specified.")
        return

    # Ask for time period
    period = input("  Time period (YYYY-MM or press Enter for last 30 days): ").strip()

    # Initialize and load Lumo
    lumo = Lumo()

    if period:
        try:
            year, month_num = map(int, period.split("-"))
            lumo.load_month(year, month_num)
            period_desc = f"{year}-{month_num:02d}"
        except (ValueError, IndexError):
            print("Invalid date format. Using last 30 days.")
            lumo.load_last_days(30)
            period_desc = "last 30 days"
    else:
        lumo.load_last_days(30)
        period_desc = "last 30 days"

    print(f"\n=== Language Statistics for {period_desc} ===\n")

    # Check if multiple languages requested
    if "," in language_input or "+" in language_input:
        # Multiple languages - use the new method
        stats_dict = lumo.get_stats_for_languages(language_input)

        for lang_name, stats in stats_dict.items():
            if stats:
                _print_language_stats(stats)

                # Try to get frequency info
                freq_info = Lumo.get_language_frequency_info(lang_name)
                if freq_info:
                    print(
                        f"Typical frequency: {freq_info['rate_monthly']:.2f} posts/month"
                    )
                print()
            else:
                print(f"--- {lang_name} ---")
                print("No data found for this language in the specified period.\n")
    else:
        # Single language
        stats = lumo.get_language_stats(language_input)

        if stats:
            _print_language_stats(stats)

            # Try to get frequency info
            freq_info = Lumo.get_language_frequency_info(language_input)
            if freq_info:
                print("\nTypical frequency data:")
                print(f"  Daily: {freq_info['rate_daily']:.2f} posts/day")
                print(f"  Monthly: {freq_info['rate_monthly']:.2f} posts/month")
                print(f"  Yearly: {freq_info['rate_yearly']:.2f} posts/year")
        else:
            print(f"No data found for '{language_input}' in {period_desc}")


# ============================================================================
# MAIN APPLICATION LOOP
# ============================================================================


def main():
    """Main application loop."""
    print("\n" + "=" * 70)
    print("WENYUAN - Translation Statistics & Analytics System for r/translator")
    print("=" * 70)

    # Validate data on startup
    print("\nValidating data files...")
    data_validator()
    print("✓ Data validation complete")

    while True:
        print("\n" + "=" * 70)
        print("Logged in as u/translator-BOT")
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
