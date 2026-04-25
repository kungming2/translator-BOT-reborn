#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
This module contains tasks related to maintaining the data files used
by the bot, including cleaning out old entries and updating some
databases.
...

Logger tag: [WJ:DATA]
"""

# ─── Imports ──────────────────────────────────────────────────────────────────

import contextlib
import json
import logging
import re
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Union

import orjson
import prawcore
import yaml
from praw.models import WikiPage

from config import SETTINGS, Paths
from config import logger as _base_logger
from database import db
from integrations.discord_utils import send_discord_alert
from lang.languages import converter, validate_lingvo_dataset
from monitoring.points import points_worth_determiner
from reddit.connection import REDDIT, REDDIT_HELPER, USERNAME
from reddit.wiki import fetch_most_requested_languages
from time_handling import (
    get_current_month,
    get_previous_month,
    messaging_months_elapsed,
    time_convert_to_string_seconds,
)
from wenju import WENJU_SETTINGS, task

# ─── Module-level constants ───────────────────────────────────────────────────

logger = logging.LoggerAdapter(_base_logger, {"tag": "WJ:DATA"})


# ─── Log & data trimming ──────────────────────────────────────────────────────


@task(schedule="daily")
def log_trimmer() -> None:
    """
    Trim the various events log to keep only the last X entries,
    preventing the files from growing indefinitely.
    Also trims the activity CSVs to keep only the last X entries (plus header).
    """
    lines_to_keep = WENJU_SETTINGS["lines_to_keep"]

    for events_path in [
        Path(Paths.LOGS["EVENTS"]),
        Path(Paths.CR["CR_EVENTS"]),
        Path(Paths.HERMES["HERMES_EVENTS"]),
    ]:
        if not events_path.exists():
            logger.debug(f"Events log not found, skipping: {events_path.name}")
            continue

        with events_path.open("r", encoding="utf-8", errors="ignore") as f:
            lines_entries = f.read().splitlines()

        if len(lines_entries) > lines_to_keep:
            trimmed = "\n".join(lines_entries[-lines_to_keep:]) + "\n"
            with events_path.open("w", encoding="utf-8") as f:
                f.write(trimmed)
            logger.debug(
                f"Trimmed {events_path.name} to keep the last {lines_to_keep} entries."
            )
        else:
            logger.debug(f"{events_path.name} within limits; no trimming needed.")

    csv_lines_to_keep = lines_to_keep // 5
    for activity_path in [Path(Paths.LOGS["ACTIVITY"]), Path(Paths.LOGS["MESSAGING"])]:
        if not activity_path.exists():
            logger.debug(f"Activity CSV not found, skipping: {activity_path.name}")
            continue

        with activity_path.open("r", encoding="utf-8", errors="ignore") as f:
            csv_lines = f.read().splitlines()

        if len(csv_lines) > csv_lines_to_keep + 1:  # +1 for header
            header = csv_lines[0]
            trimmed_data = csv_lines[-csv_lines_to_keep:]
            trimmed_csv = "\n".join([header] + trimmed_data) + "\n"
            with activity_path.open("w", encoding="utf-8") as f:
                f.write(trimmed_csv)
            logger.debug(
                f"Trimmed {activity_path.name} to keep the last "
                f"{csv_lines_to_keep} entries (plus header)."
            )
        else:
            logger.debug(f"{activity_path.name} within limits; no trimming needed.")

    return


@task(schedule="daily")
def error_log_trimmer() -> None:
    """Remove resolved errors older than one week from the error log."""
    error_log_path = Paths.LOGS["ERROR"]

    with open(error_log_path, encoding="utf-8") as f:
        entries = yaml.safe_load(f) or []

    retention_weeks = WENJU_SETTINGS["resolved_error_log_retention_weeks"]
    cutoff = datetime.now(UTC) - timedelta(weeks=retention_weeks)

    trimmed = [
        entry
        for entry in entries
        if not (
            entry.get("resolved", False)
            and datetime.fromisoformat(entry["timestamp"]) < cutoff
        )
    ]

    with open(error_log_path, "w", encoding="utf-8") as f:
        if trimmed:
            yaml.dump(trimmed, f, allow_unicode=True, sort_keys=False)

    removed = len(entries) - len(trimmed)
    if removed:
        logger.info(
            f"Removed {removed} resolved error(s) older than {retention_weeks} weeks."
        )
    else:
        logger.info("No resolved errors to remove.")


# ─── Data validation ──────────────────────────────────────────────────────────


@task(schedule="daily")
def validate_data_files() -> bool:
    """
    Scan the Paths class for all attributes containing YAML and JSON file
    paths and validate them.

    :return: all_valid: bool
    """
    config_files = []
    paths_class = Paths

    for attr_name in dir(paths_class):
        attr_value = getattr(paths_class, attr_name)
        if isinstance(attr_value, dict):
            for _key, path in attr_value.items():
                if isinstance(path, str) and (
                    path.lower().endswith(".yaml") or path.lower().endswith(".json")
                ):
                    config_files.append(path)

    if not config_files:
        logger.warning("[Config Validation] No YAML or JSON files found in Paths.")
        return True

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
            with open(path_obj, encoding="utf-8") as f:
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


# ─── Database cleanup ─────────────────────────────────────────────────────────


@task(schedule="weekly")
def clean_processed_database() -> None:
    """
    Clean up old entries in old_comments and old_posts,
    keeping only entries from the last 180 days based on the
    created_utc column in each table.
    """
    max_age_days = SETTINGS["max_old_age"]
    cursor = db.cursor_main

    cutoff_timestamp = int(time.time()) - (max_age_days * 24 * 60 * 60)

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


# ─── Statistics wiki page maintenance ────────────────────────────────────────


def _wikipage_statistics_parser(page_content: Union[str, "WikiPage"]) -> dict:
    """
    Parse a language wiki page or language name to extract statistics
    for a single language. Returns a JSON-compatible dictionary.

    :param page_content: Language name (str) or PRAW WikiPage object.
    :return: Dictionary containing language statistics.
    """
    r = REDDIT_HELPER.subreddit(SETTINGS["subreddit"])
    language_data: dict[str, Any] = {}
    monthly_totals = []
    months_elapsed = messaging_months_elapsed()

    if isinstance(page_content, str):
        page_content = r.wiki[page_content.lower()]
    page_body = page_content.content_md

    try:
        table_content = page_body.split("---|---", 1)[1]
    except IndexError:
        return {}

    entries = [
        line
        for line in table_content.split("\n")
        if line.startswith("20") and not line.startswith("~~")
    ]
    language_data["num_months"] = len(entries)

    for entry in entries:
        cols = [col.strip() for col in entry.split("|")]
        year, month = cols[0], cols[1]

        total_match = re.search(r"\[(.*?)]", cols[2])
        total = int(total_match.group(1)) if total_match else 0
        monthly_totals.append(total)
        percentage_total = round(float(cols[3].rstrip("%")) * 0.01, 4)
        untranslated_match = re.search(r"\[(.*?)]", cols[4]) if "[" in cols[4] else None
        num_untranslated = int(
            untranslated_match.group(1) if untranslated_match else cols[4]
        )
        percentage_translated = round(float(cols[5].rstrip("%")) * 0.01, 4)
        ri = None
        with contextlib.suppress(ValueError, IndexError):
            ri = float(cols[6])

        key = f"{year}-{month}"
        language_data[key] = {
            "num_total": total,
            "percentage_total": percentage_total,
            "num_untranslated": num_untranslated,
            "percentage_translated": percentage_translated,
            "num_translated": total - num_untranslated,
            "ri": ri,
        }

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

    def get_extremes(key_name: str, field: str) -> None:
        max_val = max_val_month = min_val = min_val_month = None
        for k, v in language_data.items():
            if "20" not in k:  # Skip metadata keys
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

    months_to_calc = (
        6 if months_elapsed == language_data["num_months"] else months_elapsed
    )
    total_recent_posts = sum(monthly_totals[-months_to_calc:])
    language_data["rate_monthly"] = round(total_recent_posts / months_to_calc, 2)
    language_data["rate_daily"] = round(language_data["rate_monthly"] / 30, 2)
    language_data["rate_yearly"] = round(language_data["rate_monthly"] * 12, 2)

    return language_data


def _statistics_list_updater(input_data: dict[str, list]) -> None:
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
    logger.info("> Statistics table on the wiki updated.")


@task(schedule="monthly")
def refresh_language_statistics() -> None:
    """
    Collect all language wiki pages, parse statistics, and generate JSON.
    Updates the 'statistics' wiki page as well with a list of all links
    to the individual languages' wiki page.
    See: https://www.reddit.com/r/translator/wiki/statistics

    :return: Nothing.
    """
    r = REDDIT_HELPER.subreddit(SETTINGS["subreddit"])

    # Pages with different formatting that should not be assessed.
    ignore_pages = {"app", "conlang", "multiple", "nonlanguage", "unknown"}
    total_data: dict[str, Any] = {}
    language_family_dict: dict[str, list[tuple[str, str, str]]] = {}

    for page in r.wiki:
        if page.name in ignore_pages or "20" in page.name or "config" in page.name:
            continue

        body = page.content_md
        if "%%statistics-x%%" in body:
            logger.info(f"Skipping deprecated language page {page.name}...")
            continue
        if "%%statistics-h%%" not in body:
            logger.info(f"Skipping non-language page {page.name}...")
            continue

        try:
            name_match = re.search(r"##(.*?)\(", body)
            language_name = (
                name_match.group(1).strip().replace("_", " ") if name_match else None
            )
            if not language_name:
                raise AttributeError
        except AttributeError:
            logger.error(f"Problem with {page.name} header.")
            continue
        try:
            family_match = re.search(r" \((.*?)\)", body)
            language_family = family_match.group(1).strip() if family_match else None
        except AttributeError:
            language_family = None

        logger.info(f'Assessing the "{language_name}" wikipage.')
        language_lingvo = converter(language_name, False)
        if not language_lingvo:
            logger.error(f"Issue with {page.name} header.")
            continue
        language_code = language_lingvo.preferred_code

        family_key: str = language_family if language_family is not None else "Unknown"
        language_family_dict.setdefault(family_key, []).append(
            (language_name, page.name, language_code)
        )

        stats = _wikipage_statistics_parser(page)
        stats.update(
            {
                "name": language_lingvo.name,
                "code": language_code,
                "family": language_family,
                "permalink": f"https://www.reddit.com/r/translator/wiki/{language_name.lower().replace(' ', '_')}",
            }
        )
        total_data[language_code] = stats

    with open(Paths.STATES["STATISTICS"], "w") as fp:
        json.dump(total_data, fp, sort_keys=True, indent=4)

    logger.info("Statistics JSON file generated.")
    _statistics_list_updater(language_family_dict)

    return


# ─── Point value caching ──────────────────────────────────────────────────────


# noinspection SqlWithoutWhere
@task(schedule="daily")
def points_worth_cacher() -> None:
    """
    Cache the point values of frequently used languages into a local
    database for fast access. Run daily to populate point values initially.
    If the current month does not have entries, purges the previous month's
    entries and replaces them.
    """
    month_entry = get_current_month()
    logger.debug(f"Starting. Current month entry: '{month_entry}'")

    # Note: cursor_cache is a property that creates a new cursor each time,
    # so we must save it to a variable before calling execute() + fetchall().
    query = "SELECT * FROM multiplier_cache WHERE month_year = ?"
    cursor = db.cursor_cache
    cursor.execute(query, (month_entry,))
    cached_entries = cursor.fetchall()
    logger.debug(f"Found {len(cached_entries)} cached entries for '{month_entry}'.")
    if cached_entries:
        logger.debug(f"Cached entries: {[tuple(r) for r in cached_entries]}")

    if not cached_entries:
        logger.info(
            "No up-to-date cache found. Clearing old entries and repopulating..."
        )
        db.cursor_cache.execute("DELETE FROM multiplier_cache")
        deleted = db.cursor_cache.rowcount
        db.conn_cache.commit()
        logger.info(f"Deleted {deleted} old cache entries.")

        most_requested = fetch_most_requested_languages()
        logger.info(
            f"Fetched {len(most_requested)} most-requested languages: {most_requested}"
        )

        succeeded = []
        failed = []

        for language_code in most_requested:
            try:
                converted = converter(language_code)
                logger.debug(
                    f"Processing '{language_code}' -> converter result: {converted}"
                )
                if converted is None:
                    logger.warning(
                        f"Could not resolve language code '{language_code}'. Skipping."
                    )
                    failed.append(language_code)
                    continue
                result = points_worth_determiner(converted)
                logger.debug(
                    f"points_worth_determiner('{language_code}') returned: {result}"
                )
                succeeded.append(language_code)
            except ValueError as e:
                logger.warning(f"ValueError for language '{language_code}': {e}")
                failed.append(language_code)
                continue

        logger.info(f"Done. {len(succeeded)} succeeded, {len(failed)} failed.")
        if failed:
            logger.warning(f"Failed languages: {failed}")

        verify_cursor = db.cursor_cache
        verify_cursor.execute(
            "SELECT * FROM multiplier_cache WHERE month_year = ?", (month_entry,)
        )
        final_entries = verify_cursor.fetchall()
        logger.info(
            f"Cache now contains {len(final_entries)} entries for '{month_entry}'."
        )
        logger.debug(f"Final cache state: {final_entries}")
    else:
        logger.debug("Cache is already populated for this month. Nothing to do.")

    return


# ─── Subreddit organization & cleanup ────────────────────────────────────────


@task(schedule="monthly")
def archive_identified_saved() -> None:
    """
    Archive the wikipages of 'identified' and 'saved' to local Markdown
    files to prevent the wikipages from getting too large. 'Saved' is
    less actively used since the rewrite.
    """
    r = REDDIT.subreddit(SETTINGS["subreddit"])
    splitter = "|-------"

    def archive_page(wiki_page: WikiPage, file_path: str, page_name: str) -> None:
        content = wiki_page.content_md
        top, lines = content.rsplit(splitter, 1)
        top += splitter

        if lines.strip():
            with open(file_path, "a+", encoding="utf-8") as f:
                f.write(lines.strip() + "\n")

            wiki_page.edit(
                content=top, reason=f"Archived tabular data for {get_current_month()}."
            )
            logger.info(f"{page_name} page archived.")

    archive_page(r.wiki["identified"], Paths.ARCHIVAL["ALL_IDENTIFIED"], "Identified")
    archive_page(r.wiki["saved"], Paths.ARCHIVAL["ALL_SAVED"], "Saved")

    return


@task(schedule="monthly")
def monthly_statistics_unpinner() -> None:
    """Unpin the statistics posts if still pinned when the monthly routine runs."""
    sub = REDDIT.subreddit(SETTINGS["subreddit"])
    stickies = []

    for i in range(1, 3):  # Try sticky 1 and sticky 2
        try:
            sticky = sub.sticky(number=i)
            stickies.append(sticky)
        except prawcore.exceptions.NotFound:
            continue

    for sticky in stickies:
        print(sticky.title)
        if (
            "[META] r/translator Statistics" in sticky.title
            and sticky.author
            and sticky.author.name == USERNAME
        ):
            sticky.mod.sticky(state=False)
            logger.info("Monthly Statistics Unpinner: Unpinned monthly post.")

    return


@task(schedule="daily")
def archive_modmail() -> None:
    """Archive modmail conversations older than days_max days where a
    moderator has participated in the conversation."""
    days_max = WENJU_SETTINGS["modmail_archival_age"]

    logger.debug("Assessing modmail...")
    subreddit = REDDIT.subreddit(SETTINGS["subreddit"])

    mod_names = [mod.name.lower() for mod in subreddit.moderator()]
    logger.debug(f"Moderators: {mod_names}")

    unread_counts = subreddit.modmail.unread_count()
    for key, count in unread_counts.items():
        if count > 0:
            logger.debug(f"Current '{key}' in modmail: {count}")

    current_time = datetime.now(UTC)
    max_age_seconds = days_max * 86400

    for convo in subreddit.modmail.conversations():
        convo.read()

        last_updated = datetime.fromisoformat(convo.last_updated)
        convo_age = (current_time - last_updated).total_seconds()
        readable_age = time_convert_to_string_seconds(int(convo_age))

        participants = (
            [author.name for author in convo.authors] if convo.authors else []
        )
        mod_participant = next(
            (name for name in participants if name.lower() in mod_names), None
        )
        logger.debug(
            f"Conversation '{convo.subject}' | Age: {readable_age} | "
            f"Authors: {participants} | Mod participant: {mod_participant}"
        )

        if convo_age > max_age_seconds and mod_participant:
            convo.archive()
            logger.info(
                f"Conversation by u/{convo.participant} archived. "
                f"({readable_age} old, mod u/{mod_participant} participated)."
            )
        else:
            skip_reason = (
                "not old enough"
                if convo_age <= max_age_seconds
                else "no moderator participated"
            )
            logger.debug(
                f"Conversation by u/{convo.participant} not archived. "
                f"({readable_age}, {skip_reason.title()})."
            )
