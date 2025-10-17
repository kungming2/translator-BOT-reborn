#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
import datetime
import json
import re
import time
from pathlib import Path
from typing import Dict, Union

import prawcore
import yaml
from praw.models import WikiPage

from config import SETTINGS, Paths, logger
from connection import REDDIT, REDDIT_HELPER
from database import db
from languages import converter
from points import points_worth_determiner
from tasks import WENJU_SETTINGS, task
from time_handling import get_previous_month, messaging_months_elapsed
from wiki import fetch_most_requested_languages


@task(schedule="daily")
def log_trimmer():
    """
    Trims the events log to keep only the last X entries,
    preventing the file from growing indefinitely.
    """
    events_path = Path(Paths.LOGS["EVENTS"])
    lines_to_keep = WENJU_SETTINGS["lines_to_keep"]

    # Read all lines safely.
    with events_path.open("r", encoding="utf-8", errors="ignore") as f:
        lines_entries = f.read().splitlines()

    # Truncate if necessary.
    if len(lines_entries) > lines_to_keep:
        trimmed = "\n".join(lines_entries[-lines_to_keep:])
        with events_path.open("w", encoding="utf-8") as f:
            f.write(trimmed)
        logger.debug(
            f"[WJ] Trimmed the events log to keep the last {lines_to_keep} entries."
        )
    else:
        logger.debug("[WJ] Events log within limits; no trimming needed.")

    return


@task(schedule="daily")
def validate_all_yaml_files():
    """
    Scans the given Paths class for all attributes containing YAML file paths
    and validates them.

    :return: True if all YAML files are valid, False otherwise.
    """
    yaml_files = []
    paths_class = Paths

    # Collect all paths ending with .yaml from dictionaries in the Paths class
    for attr_name in dir(paths_class):
        attr_value = getattr(paths_class, attr_name)
        if isinstance(attr_value, dict):
            for key, path in attr_value.items():
                if isinstance(path, str) and path.lower().endswith(".yaml"):
                    yaml_files.append(path)

    if not yaml_files:
        logger.warning("[YAML Validation] No YAML files found in Paths.")
        return True

    logger.info(f"[YAML Validation] Found {len(yaml_files)} YAML files to check.")

    all_valid = True
    for file_path in yaml_files:
        path_obj = Path(file_path)

        if not path_obj.exists():
            logger.error(f"[YAML Validation] File not found: {file_path}")
            all_valid = False
            continue

        try:
            with open(path_obj, "r", encoding="utf-8") as f:
                yaml.safe_load(f)
            logger.debug(f"[YAML Validation] Valid YAML: {file_path}")
        except yaml.YAMLError as e:
            logger.error(f"[YAML Validation] Invalid YAML in {file_path}: {e}")
            all_valid = False
        except Exception as e:
            logger.error(f"[YAML Validation] Error reading {file_path}: {e}")
            all_valid = False

    if all_valid:
        logger.info("All YAML files validated.")

    return all_valid


@task(schedule="daily")
def clean_processed_database():
    """
    Cleans up the processed comments and posts in the database by
    pruning old entries from the 'old_comments' and 'old_posts' tables,
    keeping only the most recent ones.

    :return: None
    """
    max_posts = SETTINGS["max_posts"]

    cursor = db.cursor_main

    # Clean old_comments
    logger.info("Starting cleanup of 'old_comments' table...")
    query_comments = """
        DELETE FROM old_comments
        WHERE id NOT IN (
            SELECT id FROM old_comments ORDER BY id DESC LIMIT ?
        )
    """
    cursor.execute(query_comments, (max_posts * 100,))
    logger.info(
        f"Cleanup complete. Kept latest {max_posts * 100} entries in 'old_comments'."
    )

    # Clean old_posts
    logger.info("Starting cleanup of 'old_posts' table...")
    query_posts = """
        DELETE FROM old_posts
        WHERE id NOT IN (
            SELECT id FROM old_posts ORDER BY id DESC LIMIT ?
        )
    """
    cursor.execute(query_posts, (max_posts * 100,))
    logger.info(
        f"Cleanup complete. Kept latest {max_posts * 100} entries in 'old_posts'."
    )

    # Commit once after both operations
    db.conn_main.commit()

    return


"""STATISTICS WIKIPAGE MAINTAINER"""


def wikipage_statistics_parser(page_content: Union[str, "WikiPage"]) -> Dict:
    """
    Parse a language wiki page or language name to extract statistics
    for a single language. Returns a JSON-compatible dictionary.

    :param page_content: Language name (str) or PRAW WikiPage object.
    :return: Dictionary containing language statistics.
    """
    r = REDDIT_HELPER.subreddit("translator")
    language_data = {}
    monthly_totals = []
    months_elapsed = messaging_months_elapsed()

    # Resolve page_content to a WikiPage object
    if isinstance(page_content, str):
        page_content = r.wiki[page_content.lower()]
    page_body = page_content.content_md

    # Extract the table content after the header separator
    try:
        table_content = page_body.split("---|---", 1)[1]
    except IndexError:
        return {}  # Table not found, return empty dictionary

    # Filter lines that start with a year
    entries = [
        line
        for line in table_content.split("\n")
        if line.startswith("20") and not line.startswith("~~")
    ]
    language_data["num_months"] = len(entries)

    for entry in entries:
        cols = [col.strip() for col in entry.split("|")]
        year, month = cols[0], cols[1]

        total = int(re.search(r"\[(.*?)]", cols[2]).group(1))
        monthly_totals.append(total)
        percentage_total = round(float(cols[3].rstrip("%")) * 0.01, 4)
        num_untranslated = int(
            re.search(r"\[(.*?)]", cols[4]).group(1) if "[" in cols[4] else cols[4]
        )
        percentage_translated = round(float(cols[5].rstrip("%")) * 0.01, 4)
        ri = None
        try:
            ri = float(cols[6])
        except (ValueError, IndexError):
            pass

        key = f"{year}-{month}"
        language_data[key] = {
            "num_total": total,
            "percentage_total": percentage_total,
            "num_untranslated": num_untranslated,
            "percentage_translated": percentage_translated,
            "num_translated": total - num_untranslated,
            "ri": ri,
        }

        # Compute month-over-month changes
        if months_elapsed == language_data["num_months"] and key != "2016-06":
            prev_key = get_previous_month(key)
            prev_data = language_data.get(prev_key)
            if prev_data:
                diff = total - prev_data["num_total"]
                language_data[key]["previous_num_change"] = diff
                language_data[key]["previous_percentage_change"] = round(
                    diff / prev_data["num_total"], 4
                )

    if language_data["num_months"] == 0:
        return language_data

    # Helper to get max/min statistics
    def get_extremes(key_name, field):
        max_val = max_val_month = min_val = min_val_month = None
        for k, v in language_data.items():
            if "20" not in k:  # Skip metadata
                continue
            val = v[field]
            if max_val is None or val > max_val:
                max_val, max_val_month = val, k
            if min_val is None or val < min_val:
                min_val, min_val_month = val, k
        language_data[f"maximum_{key_name}"] = (max_val_month, max_val)
        language_data[f"minimum_{key_name}"] = (min_val_month, min_val)

    get_extremes("num_total", "num_total")
    get_extremes("percentage_total", "percentage_total")
    get_extremes("percentage_translated", "percentage_translated")

    # Compute average post rates
    months_to_calc = (
        6 if months_elapsed == language_data["num_months"] else months_elapsed
    )
    total_recent_posts = sum(monthly_totals[-months_to_calc:])
    language_data["rate_monthly"] = round(total_recent_posts / months_to_calc, 2)
    language_data["rate_daily"] = round(language_data["rate_monthly"] / 30, 2)
    language_data["rate_yearly"] = round(language_data["rate_monthly"] * 12, 2)

    return language_data


def statistics_list_updater(input_data: Dict[str, list]):
    """
    Generate a Markdown list for wiki/statistics, grouped by language family,
    and update the wiki page.
    """
    r = REDDIT.subreddit("translator")
    total_data = []
    for family in sorted(input_data.keys()):
        total_data.append(f"\n###### {family}")
        for language, page_name, code in input_data[family]:
            wiki_link = (
                ""
                if "qaa" <= code <= "qtz"
                else f"([WP](https://en.wikipedia.org/wiki/ISO 639:{code}))"
            )
            total_data.append(
                f"* [{language}](https://www.reddit.com/r/translator/wiki/{page_name}) {wiki_link}"
            )

    new_content = (
        r.wiki["statistics"]
        .content_md.split("## Individual Language Statistics")[0]
        .strip()
        + "\n\n## Individual Language Statistics\n\n"
        + "\n".join(total_data)
        + "\n\n"
    )

    r.wiki["statistics"].edit(
        content=new_content, reason="Updating the language statistics main table."
    )
    logger.info("[WJ] > Statistics table on the wiki updated.")


@task(schedule="monthly")
def get_language_pages() -> None:
    """
    Collect all language wiki pages, parse statistics, and generate JSON.
    Updates the 'statistics' wiki page as well with a list of all links
    to the individual languages' wiki page.
    See: https://www.reddit.com/r/translator/wiki/statistics

    :return: Nothing.
    """
    r = REDDIT_HELPER.subreddit("translator")

    # The following pages have different formatting and should not be
    # assessed.
    ignore_pages = {"app", "conlang", "multiple", "nonlanguage", "unknown"}
    total_data = {}
    language_family_dict = {}

    for page in r.wiki:
        if page.name in ignore_pages or "20" in page.name or "config" in page.name:
            continue

        body = page.content_md
        if "%%statistics-x%%" in body:
            logger.info(f"[WJ] Skipping deprecated language page {page.name}...")
            continue
        if "%%statistics-h%%" not in body:
            logger.info(f"[WJ] Skipping non-language page {page.name}...")
            continue

        try:
            language_name = (
                re.search(r"##(.*?)\(", body).group(1).strip().replace("_", " ")
            )
        except AttributeError:
            logger.error(f"[WJ] Problem with {page.name} header.")
            continue
        try:
            language_family = re.search(r" \((.*?)\)", body).group(1).strip()
        except AttributeError:
            language_family = None

        logger.info(f'Assessing the "{language_name}" wikipage.')
        language_lingvo = converter(language_name, False)
        if not language_lingvo:
            logger.error(f"Issue with {page.name} header.")
            continue
        language_code = language_lingvo.preferred_code

        # Update language family dictionary
        language_family_dict.setdefault(language_family, []).append(
            (language_name, page.name, language_code)
        )

        # Parse statistics
        stats = wikipage_statistics_parser(page)
        stats.update(
            {
                "name": language_lingvo.name,
                "code": language_code,
                "family": language_family,
                "permalink": f"https://www.reddit.com/r/translator/wiki/{language_name.lower().replace(' ', '_')}",
            }
        )
        total_data[language_code] = stats

    # Save JSON and update wiki
    with open(Paths.DATASETS["STATISTICS"], "w") as fp:
        json.dump(total_data, fp, sort_keys=True, indent=4)

    logger.info("[WJ] Statistics JSON file generated.")
    statistics_list_updater(language_family_dict)

    return


# noinspection SqlWithoutWhere
@task(schedule="monthly")
def points_worth_cacher():
    """
    Caches the point values of frequently used languages into a local
    database for fast access. This is run occasionally every week and at
    the start of every month to populate the point values initially.
    If the current month does not have entries, it'll purge the entries
    from the previous month and replace it.
    """
    # Get this month's representation.
    current_month = datetime.datetime.fromtimestamp(time.time()).strftime("%Y-%m")

    # Check if cache already contains entries for the current month
    query = "SELECT * FROM multiplier_cache WHERE month_year = ?"
    db.cursor_cache.execute(query, (current_month,))
    cached_entries = db.cursor_cache.fetchall()

    # There is no cached points data.
    if not cached_entries:
        # No up-to-date cache; clear old entries
        db.cursor_cache.execute("DELETE FROM multiplier_cache")
        db.conn_cache.commit()

        most_requested = fetch_most_requested_languages()

        # Retrieve point values and update the cache
        for language_code in most_requested:
            # This also handles inserting and committing to the DB
            try:
                points_worth_determiner(converter(language_code))
            except ValueError:
                continue

    return


@task(schedule="monthly")
def archive_identified_saved():
    """
    Archive the wikipages of 'identified' and 'saved' to local Markdown
    files to prevent the wikipages from getting too large. 'Saved' is
    no longer actively used since the rewrite, but the code is kept
    here in case it is brought back.
    """
    r = REDDIT.subreddit("translator")
    splitter = "|-------"

    # Helper function to process a single wiki page
    def archive_page(wiki_page, file_path, page_name):
        content = wiki_page.content_md
        top, lines = content.rsplit(splitter, 1)
        top += splitter

        if lines.strip():
            with open(file_path, "a+", encoding="utf-8") as f:
                f.write(lines.strip() + "\n")  # Add newline for separation

            wiki_page.edit(content=top, reason="Archived tabular data.")
            logger.info(f"[WJ] {page_name} page archived.")

    # Process both pages
    archive_page(r.wiki["identified"], Paths.ARCHIVAL["ALL_IDENTIFIED"], "Identified")
    archive_page(r.wiki["saved"], Paths.ARCHIVAL["ALL_SAVED"], "Saved")

    return


@task(schedule="monthly")
def monthly_statistics_unpinner():
    """Unpins the statistics posts if it is still pinned when
    the monthly routine runs."""

    sub = REDDIT.subreddit("translator")
    stickies = []

    # Iterate and check for the stickies.
    for i in range(1, 3):  # Try sticky 1 and sticky 2
        try:
            sticky = sub.sticky(number=i)
            stickies.append(sticky)
        except prawcore.exceptions.NotFound:
            # Sticky number 'i' doesn't exist
            continue

    # Print stickied post titles, then unsticky if any match.
    for sticky in stickies:
        print(sticky.title)
        if (
            "[META] r/translator Statistics" in sticky.title
            and sticky.author  # In case the author is deleted or missing
            and sticky.author.name == "translator-BOT"
        ):
            sticky.mod.sticky(state=False)
            logger.info("Monthly Statistics Unpinner: Unpinned monthly post.")

    return


if __name__ == "__main__":
    print(get_language_pages())
