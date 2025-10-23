#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
import json
import re
import time
from pathlib import Path
from typing import Dict, Union

import orjson
import prawcore
import yaml
from praw.models import WikiPage

from config import SETTINGS, Paths, logger
from connection import REDDIT, REDDIT_HELPER, USERNAME
from database import db
from discord_utils import send_discord_alert
from languages import converter, validate_lingvo_dataset
from points import points_worth_determiner
from tasks import WENJU_SETTINGS, task
from time_handling import (
    get_current_month,
    get_previous_month,
    messaging_months_elapsed,
)
from wiki import fetch_most_requested_languages


@task(schedule="daily")
def log_trimmer():
    """
    Trims the events log to keep only the last X entries,
    preventing the file from growing indefinitely.
    Also trims the activity CSV to keep only the last X entries (plus header).
    """
    lines_to_keep = WENJU_SETTINGS["lines_to_keep"]

    # Trim events log
    events_path = Path(Paths.LOGS["EVENTS"])
    with events_path.open("r", encoding="utf-8", errors="ignore") as f:
        lines_entries = f.read().splitlines()

    if len(lines_entries) > lines_to_keep:
        trimmed = "\n".join(lines_entries[-lines_to_keep:]) + "\n"
        with events_path.open("w", encoding="utf-8") as f:
            f.write(trimmed)
        logger.debug(
            f"[WJ] Trimmed the events log to keep the last {lines_to_keep} entries."
        )
    else:
        logger.debug("[WJ] Events log within limits; no trimming needed.")

    # Trim activity CSV
    activity_path = Path(Paths.LOGS["ACTIVITY"])
    csv_lines_to_keep = lines_to_keep // 5
    with activity_path.open("r", encoding="utf-8", errors="ignore") as f:
        csv_lines = f.read().splitlines()

    if len(csv_lines) > csv_lines_to_keep + 1:  # +1 for header
        header = csv_lines[0]
        trimmed_data = csv_lines[-csv_lines_to_keep:]
        trimmed_csv = "\n".join([header] + trimmed_data) + "\n"
        with activity_path.open("w", encoding="utf-8") as f:
            f.write(trimmed_csv)
        logger.debug(
            f"[WJ] Trimmed the activity CSV to keep the last {csv_lines_to_keep} entries (plus header)."
        )
    else:
        logger.debug("[WJ] Activity CSV within limits; no trimming needed.")

    return


@task(schedule="daily")
def validate_data_files():
    """
    Scans the given Paths class for all attributes containing YAML and JSON file paths
    and validates them.

    :return: Tuple of (all_valid: bool, failed_files: list of str)
    """
    config_files = []
    paths_class = Paths

    # Collect all paths ending with .yaml or .json from dictionaries in the Paths class
    for attr_name in dir(paths_class):
        attr_value = getattr(paths_class, attr_name)
        if isinstance(attr_value, dict):
            for key, path in attr_value.items():
                if isinstance(path, str) and (
                    path.lower().endswith(".yaml") or path.lower().endswith(".json")
                ):
                    config_files.append(path)

    if not config_files:
        logger.warning("[Config Validation] No YAML or JSON files found in Paths.")
        return True, []

    logger.info(f"[Config Validation] Found {len(config_files)} config files to check.")

    all_valid = True
    failed_files = []

    for file_path in config_files:
        path_obj = Path(file_path)

        if not path_obj.exists():
            logger.error(f"[Config Validation] File not found: {file_path}")
            all_valid = False
            failed_files.append(file_path)
            continue

        try:
            with open(path_obj, "r", encoding="utf-8") as f:
                if file_path.lower().endswith(".yaml"):
                    yaml.safe_load(f)
                    logger.debug(f"[Config Validation] Valid YAML: {file_path}")
                elif file_path.lower().endswith(".json"):
                    try:
                        content = f.read()
                        orjson.loads(content)
                    except ImportError:
                        f.seek(0)
                        json.load(f)
                    logger.debug(f"[Config Validation] Valid JSON: {file_path}")
        except yaml.YAMLError as e:
            logger.error(f"[Config Validation] Invalid YAML in {file_path}: {e}")
            all_valid = False
            failed_files.append(path_obj.name)
        except (orjson.JSONDecodeError, json.JSONDecodeError, ValueError) as e:
            logger.error(f"[Config Validation] Invalid JSON in {file_path}: {e}")
            all_valid = False
            failed_files.append(path_obj.name)
        except Exception as e:
            logger.error(f"[Config Validation] Error reading {file_path}: {e}")
            all_valid = False
            failed_files.append(path_obj.name)

    # Test and validate the general Lingvo dataset.
    try:
        problematic_langs = validate_lingvo_dataset()
        if problematic_langs:
            logger.error(
                f"[Config Validation] Lingvo dataset validation failed "
                f"for {len(problematic_langs)} language(s): {problematic_langs}"
            )
            all_valid = False
        else:
            logger.info("[Config Validation] Lingvo dataset validated successfully.")
    except Exception as e:
        logger.error(f"[Config Validation] Error running validate_lingvo_dataset: {e}")
        all_valid = False
        problematic_langs = ["<validation error>"]

    if all_valid:
        logger.info("[Config Validation] All config files validated successfully.")
    else:
        details = []
        if failed_files:
            details.append(
                f"The following {len(failed_files)} files failed validation:\n\n"
                + "\n".join(f"* `{file_name}`" for file_name in failed_files)
            )

        if problematic_langs:
            details.append(
                f"The following {len(problematic_langs)} language codes failed Lingvo dataset validation:\n\n"
                + "\n".join(f"* `{code}`" for code in problematic_langs)
            )

        information_msg = "\n\n".join(details)
        send_discord_alert("Data Files Failed Validation", information_msg, "alert")
        logger.info("Messaged mods on Discord about validation failure.")

    return all_valid


def clean_processed_database():
    """
    Cleans up old entries in old_comments and old_posts,
    keeping only entries from the last 180 days based on the
    created_utc column in each table.
    """
    max_age_days = SETTINGS["max_old_age"]
    cursor = db.cursor_main

    # Calculate the cutoff timestamp (current time - max_age_days)
    cutoff_timestamp = int(time.time()) - (max_age_days * 24 * 60 * 60)

    # Clean old_comments
    logger.info(
        f"Starting cleanup of 'old_comments' table (removing "
        f"entries older than {max_age_days} days)..."
    )
    query_comments = """
                     DELETE \
                     FROM old_comments
                     WHERE created_utc < ?; \
                     """
    cursor.execute(query_comments, (cutoff_timestamp,))
    deleted_comments = cursor.rowcount
    logger.info(
        f"Cleanup complete. Deleted {deleted_comments} entries from 'old_comments'."
    )

    # Clean old_posts
    logger.info(
        f"Starting cleanup of 'old_posts' table (removing entries older than {max_age_days} days)..."
    )
    query_posts = """
                  DELETE \
                  FROM old_posts
                  WHERE created_utc < ?; \
                  """
    cursor.execute(query_posts, (cutoff_timestamp,))
    deleted_posts = cursor.rowcount
    logger.info(f"Cleanup complete. Deleted {deleted_posts} entries from 'old_posts'.")

    db.conn_main.commit()


"""STATISTICS WIKIPAGE MAINTAINER"""


def wikipage_statistics_parser(page_content: Union[str, "WikiPage"]) -> Dict:
    """
    Parse a language wiki page or language name to extract statistics
    for a single language. Returns a JSON-compatible dictionary.

    :param page_content: Language name (str) or PRAW WikiPage object.
    :return: Dictionary containing language statistics.
    """
    r = REDDIT_HELPER.subreddit(SETTINGS["subreddit"])
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
    r = REDDIT.subreddit(SETTINGS["subreddit"])
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
    r = REDDIT_HELPER.subreddit(SETTINGS["subreddit"])

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
    month_entry = get_current_month()

    # Check if cache already contains entries for the current month
    query = "SELECT * FROM multiplier_cache WHERE month_year = ?"
    db.cursor_cache.execute(query, (month_entry,))
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
    less actively used since the rewrite.
    """
    r = REDDIT.subreddit(SETTINGS["subreddit"])
    splitter = "|-------"

    # Helper function to process a single wiki page
    def archive_page(wiki_page, file_path, page_name):
        content = wiki_page.content_md
        top, lines = content.rsplit(splitter, 1)
        top += splitter

        if lines.strip():
            with open(file_path, "a+", encoding="utf-8") as f:
                f.write(lines.strip() + "\n")  # Add newline for separation

            wiki_page.edit(
                content=top, reason=f"Archived tabular data for {get_current_month()}."
            )
            logger.info(f"[WJ] {page_name} page archived.")

    # Process both pages
    archive_page(r.wiki["identified"], Paths.ARCHIVAL["ALL_IDENTIFIED"], "Identified")
    archive_page(r.wiki["saved"], Paths.ARCHIVAL["ALL_SAVED"], "Saved")

    return


@task(schedule="monthly")
def monthly_statistics_unpinner():
    """Unpins the statistics posts if it is still pinned when
    the monthly routine runs."""

    sub = REDDIT.subreddit(SETTINGS["subreddit"])
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
            and sticky.author.name == USERNAME
        ):
            sticky.mod.sticky(state=False)
            logger.info("Monthly Statistics Unpinner: Unpinned monthly post.")

    return


if __name__ == "__main__":
    print(validate_data_files())
