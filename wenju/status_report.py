#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""Generate scheduled Reddit status and database reports."""

import json
import logging
import time
from collections import Counter

from praw.models import Comment

from config import SETTINGS, get_reports_directory
from config import logger as _base_logger
from database import db
from integrations.discord_utils import send_discord_alert
from lang.languages import converter, define_language_lists
from models.ajo import Ajo
from reddit.connection import (
    REDDIT,
    REDDIT_HELPER,
    reddit_status_check,
    submit_translatorbot_post,
)
from time_handling import (
    get_current_month,
    get_current_month_name,
    get_current_utc_date,
    time_convert_to_utc,
)
from utility import format_markdown_table_with_padding
from wenju import WENJU_SETTINGS, task

logger = logging.LoggerAdapter(_base_logger, {"tag": "WJ:REPORT"})


@task(schedule="hourly")
def reddit_status_report() -> None:
    """Call the Reddit Status API and alert Discord about active incidents."""
    incidents = reddit_status_check()

    if incidents is None:
        logger.warning("Unable to reach Reddit Status API.")
        return

    if not incidents:
        logger.debug("No Reddit Status incidents found.")
        return

    lines = ["### ⚠️ Active Reddit Incidents\n"]
    for incident in incidents:
        name = incident.get("name", "Unknown")
        status = incident.get("status", "N/A")
        impact = incident.get("impact", "unknown")
        if impact.lower() == "minor":
            logger.info(f"Skipping incident {name} (minor incident).")
            continue
        created = time_convert_to_utc(incident.get("created_at", "N/A"))
        updated = time_convert_to_utc(incident.get("updated_at", "N/A"))
        shortlink = incident.get("shortlink") or incident.get("shortlink_url") or ""

        latest_update = None
        updates = incident.get("incident_updates") or []
        if updates:
            latest_update = (
                sorted(updates, key=lambda u: u.get("created_at", ""), reverse=True)[0]
                .get("body", "")
                .strip()
            )

        logger.info(
            f"[Reddit Incident] {name} — {status.upper()} ({impact})\n"
            f"Created: {created} | "
            f"Updated: {updated}\n"
            f"{('Latest update: ' + latest_update) if latest_update else 'No update text.'}\n"
            f"Link: {shortlink or 'N/A'}"
        )

        title = f"**[{name}]({shortlink})**" if shortlink else f"**{name}**"

        lines.append(
            f"- {title}  \n"
            f"  - **Status:** {status.title()} ({impact})  \n"
            f"  - **Created:** [{created}](https://time.lol/#{created})  \n"
            f"  - **Updated:** [{updated}](https://time.lol/#{updated})"
        )

    if len(lines) > 1:
        alert_text = "\n".join(lines)
        send_discord_alert("Reddit Status", alert_text, "reddit_status")

    return


@task(schedule="weekly")
def deleted_posts_assessor(
    start_time: int | None = None, end_time: int | None = None
) -> None:
    """Generate a report about recently deleted translation requests."""
    reports_directory = get_reports_directory()
    today = get_current_utc_date()

    if start_time is None or end_time is None:
        end_time = int(time.time())
        start_time = end_time - 604800

    query = "SELECT * FROM ajo_database WHERE created_utc BETWEEN ? AND ?"
    stored_ajos = db.fetchall_ajo(query, (start_time, end_time))
    logger.debug(f"Fetched {len(stored_ajos)} entries from local_database.")

    relevant_ajos = {row[0]: Ajo.from_dict(json.loads(row[2])) for row in stored_ajos}

    submission_fullnames = [f"t3_{pid}" for pid in relevant_ajos]
    submissions = list(REDDIT_HELPER.info(fullnames=submission_fullnames))

    deleted_submissions = {}
    for submission in submissions:
        author_name = getattr(submission.author, "name", None)
        if author_name:
            logger.debug(f"Author u/{author_name} is active.")
        else:
            deleted_submissions[submission.id] = submission
            logger.debug("Author is deleted.")

    deleted_percentage = (
        len(deleted_submissions) / len(submissions) if submissions else 0
    )
    logger.info(f"Deleted percentage: {deleted_percentage:.2%}")

    authors = []
    translated_deleted = []

    for post_id, submission in deleted_submissions.items():
        cached = relevant_ajos.get(post_id)
        if not cached:
            continue

        author = cached.author or "[unknown]"
        authors.append(author)

        if isinstance(cached.status, str):
            if cached.status in {"translated", "doublecheck"}:
                translated_deleted.append((submission, author))
        elif isinstance(cached.status, dict) and any(
            s in {"translated", "doublecheck"} for s in cached.status.values()
        ):
            translated_deleted.append((submission, author))

    impolite_entries = []
    for submission, original_author in translated_deleted:
        comments = submission.comments.list()
        if not any(
            isinstance(comment, Comment)
            and getattr(comment.author, "name", None) == original_author
            for comment in comments
        ):
            impolite_entries.append((submission, original_author))

    active_authors = [a for a in authors if a not in ("[deleted]", "[unknown]")]
    offender_counts = Counter(active_authors)
    top_offenders = offender_counts.most_common(5)

    offenders_text = "#### Most Frequent Deleters\n\n" + "\n".join(
        f"* u/{name}: {count}" for name, count in top_offenders
    )

    if impolite_entries:
        impolite_table = "\n".join(
            f"| u/{author} | [{submission.title}]"
            f"(https://www.reddit.com{submission.permalink}) |"
            for submission, author in impolite_entries
        )
        impolite_text = (
            "\n\n#### Deleted Without Thanks (Impolite)\n\n"
            "| Username | Link |\n|----------|------|\n" + impolite_table
        )
    else:
        impolite_text = "\n\n#### Deleted Without Thanks (Impolite)\n\n_None_"

    report = (
        f"## Deleted Posts Data for {today}\n\n"
        f"**Deleted Posts Percentage:** {deleted_percentage:.2%} "
        f"({len(deleted_submissions)}/{len(submissions)})\n\n"
        f"{offenders_text}"
        f"{impolite_text}"
    )

    reports_directory.mkdir(parents=True, exist_ok=True)
    log_path = reports_directory / f"{today}_Deleted.md"

    with open(log_path, "w", encoding="utf-8") as f:
        f.write(report)

    logger.info(f"weekly_deleted_posts_assessor: Report saved to {log_path}.")

    return


@task(schedule="monthly")
def notify_db_statistics_calculator(post_to_reddit: bool = True) -> None:
    """Generate notification-database statistics and optionally post them."""
    reports_directory = get_reports_directory()
    this_month_digits = get_current_month()
    this_month_name = get_current_month_name()

    iso_639_1_languages_raw = define_language_lists().get("ISO_639_1", [])
    iso_639_1_languages: list[str] = [
        str(code) for code in iso_639_1_languages_raw if code is not None
    ]

    all_subscriptions = db.fetchall_main("SELECT * FROM notify_users", ())

    if not all_subscriptions:
        logger.warning("No subscriptions found in notify_users.")
        return

    all_lang_codes = sorted(
        {str(row[0]) for row in all_subscriptions if row[0] is not None}
    )

    format_lines = []
    for code in all_lang_codes:
        if code in SETTINGS["internal_post_types"]:
            continue
        row = db.fetch_main(
            "SELECT COUNT(*) FROM notify_users WHERE language_code = ?",
            (code,),
        )
        code_count = row[0] if row else 0
        _lingvo = converter(code)
        if _lingvo is None:
            logger.warning(f"Could not resolve language code '{code}'. Skipping.")
            continue
        name = _lingvo.name
        format_lines.append(f"| {name} | `{code}` | {code_count} |")

    unique_langs = len(all_lang_codes)
    total_subs = len(all_subscriptions)
    average_per = total_subs / unique_langs if unique_langs else 0

    duplicates = [
        item for item, count in Counter(all_subscriptions).items() if count > 1
    ]
    dupe_subs = duplicates or ""

    summary = (
        f"## Notifications Database Data for {this_month_name}\n\n"
        f"* Unique entries in notifications database: {unique_langs:,} languages\n"
        f"* Total subscriptions in notifications database: {total_subs:,} subscriptions\n"
        f"* Average notification subscriptions per entry: {average_per:.2f} subscribers\n"
    )

    header = "\n\n| Language | Code | Subscribers |\n|------|------|-----|\n"
    total_table_raw = header + "\n".join(format_lines)
    total_table_padded = format_markdown_table_with_padding(total_table_raw)
    logger.debug(f"notify_db_statistics_calculator: Total = {total_subs:,}")

    ignore_codes = set(WENJU_SETTINGS["ignored_notification_database_codes"])
    iso_sorted = sorted(iso_639_1_languages, key=lambda x: x.lower())
    missing_codes = [
        f"| `{code}` | {_l.name} |"
        for code in iso_sorted
        if (_l := converter(code)) is not None
        and code not in all_lang_codes
        and len(code) == 2
        and code not in ignore_codes
    ]
    missing_num = len(missing_codes)

    missing_section_raw = (
        f"\n\n### No Subscribers ({missing_num} ISO 639-1 languages)\n"
        "| Code | Language Name |\n|---|----|\n" + "\n".join(missing_codes)
    )
    missing_section_padded = format_markdown_table_with_padding(missing_section_raw)

    file_text = (
        f"{summary}\n{total_table_padded}\n{missing_section_padded}\n\n{dupe_subs}"
    )
    reddit_text = f"{summary}\n{total_table_raw}\n{missing_section_raw}\n\n{dupe_subs}"

    output_path = f"{reports_directory}/{this_month_digits}_Notifications.md"
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(file_text)

    logger.info(f"notify_db_statistics_calculator: Report saved to {output_path}.")

    if not post_to_reddit:
        logger.info("notify_db_statistics_calculator: Skipping Reddit post.")
        return

    title = f"r/translator Notification Database Statistics - {this_month_name}"
    submission = submit_translatorbot_post(
        title,
        selftext=reddit_text,
        send_replies=False,
        reddit=REDDIT,
    )
    logger.info(
        "notify_db_statistics_calculator: "
        f"Notifications Database Report posted to Reddit: https://redd.it/{submission.id}"
    )

    return
