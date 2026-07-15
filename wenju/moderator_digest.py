#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
Formerly posted to a wiki "dashboard", this provides a daily digest of
information and statistics to moderators via Discord, plus a separate hourly
public statistics snapshot.
...

Logger tag: [WJ:MODDIG]
"""

# ─── Imports ──────────────────────────────────────────────────────────────────

import csv
import json
import logging
import os
import secrets
import time
from datetime import UTC, date, datetime
from pathlib import Path
from typing import TypedDict

import yaml

from config import SETTINGS, Paths, get_reports_directory, load_settings
from config import logger as _base_logger
from integrations.discord_utils import send_discord_alert
from monitoring.usage_statistics import generate_command_usage_report
from reddit.connection import REDDIT_HELPER
from time_handling import convert_to_day, get_current_utc_date
from utility import format_markdown_table_with_padding
from wenju import WENJU_SETTINGS, task

# ─── Module-level constants ───────────────────────────────────────────────────

logger = logging.LoggerAdapter(_base_logger, {"tag": "WJ:MODDIG"})


class _ActionEntry(TypedDict):
    """A parsed action row from the command usage report."""

    name: str
    count: float


class _SharedStatistics(TypedDict):
    """Statistics used by both the private and public dashboards."""

    filter_markdown: str
    filter_data: dict[str, object]
    command_markdown: str
    actions: list[_ActionEntry]
    new_posts: float
    notifications: float
    wenyuan_markdown: str | None
    wenyuan_data: dict[str, object] | None


# ─── Report writers ───────────────────────────────────────────────────────────


def _write_markdown_digest(md_path: Path, digest_summary: str) -> Path | None:
    """
    Save the Markdown archive for the digest.

    The Markdown report is archival; the HTML dashboard is the moderator-facing
    output. If an existing daily Markdown file cannot be overwritten, try a
    same-day fallback filename so the daily digest can still complete.
    """
    md_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        md_path.write_text(digest_summary, encoding="utf-8")
        return md_path
    except OSError as err:
        fallback_path = md_path.with_name(
            f"{md_path.stem}-{datetime.now(UTC).strftime('%H%M%S')}{md_path.suffix}"
        )
        try:
            fallback_path.write_text(digest_summary, encoding="utf-8")
        except OSError as fallback_err:
            logger.error(
                "Moderator digest Markdown archive was not written. "
                "Failed to write %s (%s); fallback %s also failed (%s).",
                md_path,
                err,
                fallback_path,
                fallback_err,
            )
            return None

        logger.warning(
            "Could not overwrite Markdown moderator digest at %s (%s); "
            "saved fallback archive to %s.",
            md_path,
            err,
            fallback_path,
        )
        return fallback_path


# ─── Digest data collectors ───────────────────────────────────────────────────


def _activity_csv_handler() -> tuple[str, dict[str, object]]:
    """
    Manage and summarize the log_activity.csv file.

    Trims the CSV to retain only the last LINES_TO_KEEP entries
    and computes summary statistics including:
    - Average API calls per cycle
    - Average memory usage (in MB)
    - Average and longest cycle run times

    :return: A Markdown-formatted string with the calculated averages.
    """
    csv_address = Paths.LOGS["ACTIVITY"]

    try:
        with open(csv_address, newline="") as f_input:
            reader = csv.reader(f_input)
            header = next(reader, None)
            main_lines = list(reader)
    except FileNotFoundError:
        logger.warning("Activity log file not found.")
        return "* **Activity log**: File missing", {}
    except Exception as e:
        logger.error(f"Failed to read CSV file — {e}")
        return "* **Activity log**: Error reading file", {}

    if not main_lines:
        logger.info("No data found in activity log.")
        return "* **Activity log**: No data available", {}

    api_calls = [int(row[2]) for row in main_lines if row[2].strip()]
    average_api_calls = round(sum(api_calls) / len(api_calls), 2) if api_calls else 0.0

    memory_data = []
    for row in main_lines:
        cell = row[3].strip()
        if cell.endswith(" MB"):
            cell = cell[:-3]
        if cell:
            try:
                memory_data.append(float(cell))
            except ValueError:
                continue
    average_memory = (
        round(sum(memory_data) / len(memory_data), 2) if memory_data else 0.0
    )

    cycle_times = [
        float(row[4]) for row in main_lines if len(row) > 4 and row[4].strip()
    ]
    average_cycle = (
        round(sum(cycle_times) / len(cycle_times), 2) if cycle_times else 0.0
    )
    longest_cycles = sorted(cycle_times, reverse=True)[:3]
    longest_cycles = [round(x, 2) for x in longest_cycles]

    longest_cycles_str = ", ".join(f"{x:.2f}" for x in longest_cycles)
    summary = (
        f"* **Average API Calls**: {average_api_calls}/cycle"
        f"\n* **Average Memory Used**: {average_memory} MB"
        f"\n* **Average Cycle Length**: {average_cycle} minutes"
        f"\n* **Longest Cycles**: {longest_cycles_str} minutes"
    )

    try:
        with open(csv_address, "w", newline="") as f_output:
            writer = csv.writer(f_output)
            if header:
                writer.writerow(header)
            writer.writerows(main_lines[-WENJU_SETTINGS["lines_to_keep"] :])
    except Exception as e:
        logger.error(f"Failed to write trimmed CSV — {e}")
        summary += "\n*Warning: Failed to trim log file.*"
        return summary, {}

    logger.debug(
        f"Trimmed activity CSV to last "
        f"{WENJU_SETTINGS['lines_to_keep']} entries. "
        f"Averages — API: {average_api_calls}, "
        f"Memory: {average_memory}, Cycle: {average_cycle}"
    )

    data = {
        "avgApiCalls": average_api_calls,
        "avgMemoryMB": average_memory,
        "avgCycleMin": average_cycle,
        "longestCycles": longest_cycles,
    }
    return summary, data


def _error_log_count() -> tuple[str, dict[str, object]]:
    """
    Count how many entries exist in the YAML-formatted error log.

    Reads a YAML file containing error log entries, each with a timestamp,
    bot_version, context, error traceback, and resolved status. Returns a
    Markdown-formatted summary with the total count and details about the
    most recent entry.

    :return: A Markdown-formatted snippet detailing how many entries
             are in the error log, including the timestamp and resolved
             status of the most recent entry.
    """
    header: str = "\n# General Information\n"

    try:
        with open(Paths.LOGS["ERROR"], encoding="utf-8") as f:
            error_logs: list[dict] | None = yaml.safe_load(f) or []
    except FileNotFoundError:
        logger.warning("Error log file not found.")
        return f"{header}\n* **Error log entries**: 0 (file missing)", {
            "count": 0,
            "lastEntry": "N/A",
            "resolved": True,
        }
    except yaml.YAMLError as e:
        logger.error(f"Failed to parse YAML — {e}")
        return f"{header}\n* **Error log entries**: Unknown (YAML parse error)", {
            "count": 0,
            "lastEntry": "N/A",
            "resolved": True,
        }

    if not isinstance(error_logs, list) or not error_logs:
        return f"{header}\n* **Error log entries**: 0", {
            "count": 0,
            "lastEntry": "N/A",
            "resolved": True,
        }

    num_entries: int = len(error_logs)

    last_entry: dict = error_logs[-1]
    last_timestamp: str = last_entry.get("timestamp", "Unknown time")
    last_resolved: bool = last_entry.get("resolved", False)
    last_entry_resolved_status: str = " (resolved)" if last_resolved else ""

    # Display-only: convert to readable local format if possible.
    try:
        last_entry_time: str = datetime.fromisoformat(
            last_timestamp.replace("Z", "+00:00")
        ).strftime("%Y-%m-%d %H:%M:%S UTC")
    except (ValueError, TypeError, AttributeError):
        last_entry_time = last_timestamp

    formatted_template: str = (
        f"{header}\n"
        f"* **Error log entries**: {num_entries}\n"
        f"* **Last entry from**: {last_entry_time}{last_entry_resolved_status}"
    )

    logger.debug(f"Found {num_entries} entries in the error log.")

    data = {
        "count": num_entries,
        "lastEntry": last_entry_time + last_entry_resolved_status,
        "resolved": last_resolved,
    }
    return formatted_template, data


def _filter_entries_by_date_range(
    entries: list[str],
    start_date: date | int | float,
    end_date: date | int | float,
) -> tuple[list[str], date, date]:
    """
    Filter log entries to those within the specified date range.

    Args:
        entries: List of log entry strings
        start_date: datetime.date or Unix timestamp
        end_date: datetime.date or Unix timestamp

    Returns:
        tuple: (filtered_entries, start_date_obj, end_date_obj)
    """
    if isinstance(start_date, (int, float)):
        start_date = datetime.fromtimestamp(start_date, tz=UTC).date()
    if isinstance(end_date, (int, float)):
        end_date = datetime.fromtimestamp(end_date, tz=UTC).date()

    filtered = []
    for line_num, entry in enumerate(entries, start=1):
        try:
            parts = [p.strip() for p in entry.split("|") if p.strip()]

            if not parts:
                raise ValueError("No valid parts found in entry")

            entry_date_str = parts[0]
            entry_date = datetime.strptime(entry_date_str, "%Y-%m-%d").date()

        except Exception as e:
            logger.error(f"Encountered entry error at line {line_num}: {e}")
            logger.error(f"ENTRY: {entry}")
            continue

        if entry_date is not None and start_date <= entry_date <= end_date:
            filtered.append(entry)

    return filtered, start_date, end_date


def _filter_log_tabulator(
    start_date: date | int | float | None = None,
    end_date: date | int | float | None = None,
    include_detailed_stats: bool = False,
) -> tuple[str, dict[str, object]]:
    """
    Calculate the filtration rate of bad titles for a specified time period.

    Reads the filter log and calculates statistics for either:
    - A custom date range (if start_date/end_date provided)
    - The last LINES_TO_KEEP entries (default behavior)

    Args:
        start_date: Optional datetime.date or Unix timestamp for range start
        end_date: Optional datetime.date or Unix timestamp for range end (defaults to today)
        include_detailed_stats: If True, includes comparison with total log statistics

    Returns:
        str: Markdown formatted filter statistics
    """
    today = datetime.now(UTC).date()

    try:
        with open(Paths.LOGS["FILTER"], encoding="utf-8") as f:
            filter_logs = f.read().strip()
    except FileNotFoundError:
        logger.warning("Filter log file not found.")
        return "* **Filter rate**: Unknown (file missing)", {}

    all_entries = filter_logs.splitlines()[2:]

    if len(all_entries) < 2:
        logger.info("Not enough data in filter log.")
        return "* **Filter rate**: Insufficient data", {}

    if start_date is not None:
        entries, period_start, period_end = _filter_entries_by_date_range(
            all_entries, start_date, end_date or today
        )
        if not entries:
            logger.warning("No entries found in specified date range.")
            return "* **Filter rate**: No data in specified range", {}

        days_elapsed = (period_end - period_start).days or 1
        entry_count = len(entries)
        period_label = f"{period_start} to {period_end}"
    else:
        entries = all_entries[-WENJU_SETTINGS["lines_to_keep"] :]
        entry_count = len(entries)

        try:
            first_date_str = entries[0].split("|")[0].strip()
            period_start = datetime.strptime(first_date_str, "%Y-%m-%d").date()
        except Exception as e:
            logger.error(f"Failed to parse first date — {e}")
            return "* **Filter rate**: Unknown (date parse error)", {}

        period_end = today
        days_elapsed = (period_end - period_start).days or 1
        period_label = f"recent {days_elapsed} days"

    rate_per_day = round(entry_count / days_elapsed, 2)
    filter_string = f"* **Filter rate**: {rate_per_day}/day ({period_label})"

    logger.debug(
        f"Average filtered posts: {rate_per_day}/day "
        f"over {days_elapsed} days ({entry_count} entries)."
    )

    if include_detailed_stats:
        try:
            oldest_date_str = all_entries[0].split("|")[0].strip()
            oldest_date = datetime.strptime(oldest_date_str, "%Y-%m-%d").date()

            total_days = (today - oldest_date).days or 1
            total_count = len(all_entries)
            total_rate = round(total_count / total_days, 2)

            if total_rate > 0:
                rate_diff = round(((rate_per_day - total_rate) / total_rate) * 100, 1)
                trend = "↑" if rate_diff > 0 else "↓" if rate_diff < 0 else "→"

                filter_string += (
                    f"\n* **Overall rate**: {total_rate}/day (all-time: {total_count} entries, {total_days} days)"
                    f"\n* **Trend**: {trend} {abs(rate_diff)}% vs. all-time average"
                )

                logger.debug(
                    f"All-time average: {total_rate}/day. "
                    f"Period comparison: {rate_diff:+.1f}%"
                )
            else:
                filter_string += f"\n* **Overall rate**: {total_rate}/day (all-time: {total_count} entries)"
                logger.debug(
                    f"All-time average: {total_rate}/day. Period comparison: N/A"
                )

        except Exception as e:
            logger.error(f"Failed to calculate detailed stats — {e}")

    data = {
        "ratePerDay": rate_per_day,
        "startDate": str(period_start),
        "endDate": str(period_end),
    }
    return filter_string, data


def _note_language_tags() -> tuple[str | None, list[dict[str, str | int]]]:
    """
    Identify recent posts that have temporary or missing language tags.

    Temporary tags include "[--]". Posts with these or blank tags
    should be reviewed and assigned proper language flair.

    Scans the latest 1000 posts, filters those with malformed
    or missing tags, and returns a Markdown-formatted table summarizing them.
    """
    header = "\n# Entries with Tags to Note\n"

    malformed_tags = {"[--]", "[]"}
    flagged_submissions = []

    for submission in REDDIT_HELPER.subreddit(SETTINGS["subreddit"]).new(limit=1000):
        flair = submission.link_flair_text
        if flair is None or any(tag in flair for tag in malformed_tags):
            flagged_submissions.append(submission)

    flagged_submissions.sort(key=lambda s: s.created_utc)

    logger.debug(
        f"note_language_tags: Found {len(flagged_submissions)} posts with temporary or missing tags."
    )

    if not flagged_submissions:
        return None, []

    rows = []
    for post in flagged_submissions:
        submission_date = convert_to_day(post.created_utc)

        title = post.title.strip()
        if len(title) > 30:
            title = title[:30].rstrip() + "..."

        flair_display = post.link_flair_text or "(none)"
        post_url = f"https://redd.it/{post.id}"

        rows.append(
            f"* [{title}]({post_url}) ({submission_date}) • "
            f"`{flair_display}` • {post.num_comments} comments"
        )

    formatted_output = header + "\n".join(rows)

    flagged_data = [
        {
            "title": post.title.strip()[:30].rstrip()
            + ("..." if len(post.title.strip()) > 30 else ""),
            "url": f"https://redd.it/{post.id}",
            "date": convert_to_day(post.created_utc),
            "flair": post.link_flair_text or "(none)",
            "comments": post.num_comments,
        }
        for post in flagged_submissions
    ]

    return formatted_output, flagged_data


def _wenyuan_period_stats(
    days: int = 30,
) -> tuple[str | None, dict[str, object] | None]:
    """Collect Wenyuan period statistics for the moderator digest."""
    try:
        from main_wenyuan import build_period_stats_data

        stats_data = build_period_stats_data(days, include_comparison=True)
    except Exception as e:
        logger.error("Failed to collect Wenyuan period statistics — %s", e)
        return None, None

    overall = stats_data.get("overall", {})
    if not isinstance(overall, dict):
        return None, stats_data

    period_label = stats_data.get("periodLabel", f"last {days} days")
    timing = stats_data.get("timing", {})
    median_display = None
    if isinstance(timing, dict):
        median_display = timing.get("medianTranslationDisplay")

    summary = (
        "\n# Wenyuan Statistics\n"
        f"* **Period**: {period_label}\n"
        f"* **Total requests**: {overall.get('total_requests', 0)}\n"
        f"* **Translated**: {overall.get('translated', 0)} "
        f"({overall.get('translation_percentage', 0)}%)\n"
        f"* **Unique languages**: {overall.get('unique_languages', 0)}"
    )
    if median_display:
        summary += f"\n* **Median translation time**: {median_display}"

    return summary, stats_data


def _parse_command_actions(command_report: str) -> list[_ActionEntry]:
    """Parse action/count rows from a command-usage Markdown table."""
    actions: list[_ActionEntry] = []
    for line in command_report.splitlines():
        line = line.strip()
        if (
            not line.startswith("|")
            or line.startswith("| Action")
            or line.startswith("|---")
        ):
            continue
        parts = [part.strip() for part in line.strip("|").split("|")]
        if len(parts) == 2:
            try:
                actions.append({"name": parts[0], "count": float(parts[1])})
            except ValueError:
                continue
    return actions


def _collect_shared_statistics(
    today_date: date, current_time: int, days_ago: int
) -> _SharedStatistics:
    """Collect the statistics shared by the daily and hourly dashboards."""
    back_start_date = current_time - (86400 * days_ago)
    filter_markdown, filter_data = _filter_log_tabulator(
        start_date=back_start_date, end_date=today_date
    )
    command_report = generate_command_usage_report(
        back_start_date, current_time, days_ago
    )
    actions = _parse_command_actions(command_report)
    wenyuan_markdown, wenyuan_data = _wenyuan_period_stats(30)

    return {
        "filter_markdown": filter_markdown,
        "filter_data": filter_data,
        "command_markdown": format_markdown_table_with_padding(command_report),
        "actions": actions,
        "new_posts": next(
            (
                action["count"]
                for action in actions
                if action["name"].lower() == "new posts"
            ),
            0.0,
        ),
        "notifications": next(
            (
                action["count"]
                for action in actions
                if action["name"].lower() == "notifications"
            ),
            0.0,
        ),
        "wenyuan_markdown": wenyuan_markdown,
        "wenyuan_data": wenyuan_data,
    }


# ─── HTML rendering ───────────────────────────────────────────────────────────


def _render_html_dashboard(date_str: str, data: dict) -> str:
    """
    Render the moderator digest data as a self-contained HTML dashboard.

    Loads the HTML template from Paths.TEMPLATES["MODERATOR_DIGEST"] and
    substitutes the __DATE_STR__ and __DATA_JSON__ placeholders.

    :param date_str: The date string for the report (YYYY-MM-DD).
    :param data: A dict matching the dashboard DATA schema.
    :return: A complete HTML string.
    """
    with open(Paths.TEMPLATES["MODERATOR_DIGEST"], encoding="utf-8") as f:
        template = f.read()

    return template.replace("__DATE_STR__", date_str).replace(
        "__DATA_JSON__", json.dumps(data, indent=2)
    )


def _json_for_html(data: dict) -> str:
    """Serialize JSON for safe inclusion in an HTML script-data element."""
    return (
        json.dumps(data, indent=2)
        .replace("&", "\\u0026")
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )


def _build_public_dashboard_data(
    date_str: str, statistics: _SharedStatistics
) -> dict[str, object]:
    """Return the explicit allowlist of shared statistics safe to publish."""
    return {
        "date": date_str,
        "generatedAt": datetime.now(UTC).isoformat(timespec="seconds"),
        "filter": statistics["filter_data"]
        or {"ratePerDay": 0, "startDate": date_str, "endDate": date_str},
        "newPosts": statistics["new_posts"],
        "notifications": statistics["notifications"],
        "actions": statistics["actions"],
        "wenyuanPeriodStats": statistics["wenyuan_data"],
    }


def _render_public_stats_dashboard(date_str: str, data: dict) -> str:
    """Render the allowlisted public statistics as a self-contained HTML page."""
    with open(Paths.TEMPLATES["PUBLIC_STATS"], encoding="utf-8") as f:
        template = f.read()

    csp_nonce = secrets.token_urlsafe(24)
    return (
        template.replace("__DATE_STR__", date_str)
        .replace('"__DATA_JSON__"', _json_for_html(data))
        .replace("__CSP_NONCE__", csp_nonce)
    )


def _atomic_write_text(path: Path, content: str) -> None:
    """Replace a generated page atomically so readers never see a partial file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        temporary_path.write_text(content, encoding="utf-8")
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)


# ─── Scheduled tasks ──────────────────────────────────────────────────────────


@task(schedule="hourly")
def generate_public_statistics() -> None:
    """Generate the isolated public statistics snapshot without notifications."""
    logger.info("Generating public statistics snapshot...")
    today_date_str = get_current_utc_date()
    today_date = datetime.strptime(today_date_str, "%Y-%m-%d").date()
    statistics = _collect_shared_statistics(
        today_date,
        int(time.time()),
        WENJU_SETTINGS["report_command_average"],
    )
    public_data = _build_public_dashboard_data(today_date_str, statistics)
    public_html = _render_public_stats_dashboard(today_date_str, public_data)
    public_html_path = Path(Paths.PUBLIC["STATS"])
    _atomic_write_text(public_html_path, public_html)
    logger.info("Public statistics snapshot saved to %s", public_html_path)


@task(schedule="daily")
def collate_moderator_digest() -> None:
    """
    Send out an overall digest of the subreddit's state and things for
    moderators to note. Uses Discord. The daily information is also
    saved to both a Markdown file and an HTML dashboard for archival purposes.

    :return: None
    """
    logger.info("Collating moderator digest...")
    today_date_str = get_current_utc_date()
    today_date = datetime.strptime(today_date_str, "%Y-%m-%d").date()
    days_ago = WENJU_SETTINGS["report_command_average"]
    current_time = int(time.time())
    shared_statistics = _collect_shared_statistics(today_date, current_time, days_ago)

    error_log_md, error_data = _error_log_count()
    activity_md, activity_data = _activity_csv_handler()
    noted_entries_md, flagged_data = _note_language_tags()

    mod_page_address = load_settings(Paths.AUTH["CREDENTIALS"])[
        "MODERATOR_DIGEST_URL"
    ].rstrip("/")
    sections = [
        error_log_md,
        shared_statistics["filter_markdown"],
        activity_md,
        shared_statistics["command_markdown"],
    ]
    if shared_statistics["wenyuan_markdown"] is not None:
        sections.append(shared_statistics["wenyuan_markdown"])
    if noted_entries_md is not None:
        sections.append(noted_entries_md)
    total_data = "\n".join(sections)
    subject_line = f"Moderator Digest for {today_date} Compiled"
    notification_body = (
        f"The [digest dashboard]({mod_page_address}/moderator_digest.html) "
        "has been updated."
    )

    digest_summary = f"# {subject_line}\n{total_data}"

    dashboard_data = {
        "date": today_date_str,
        "errors": error_data
        if error_data
        else {"count": 0, "lastEntry": "N/A", "resolved": True},
        "filter": shared_statistics["filter_data"]
        if shared_statistics["filter_data"]
        else {"ratePerDay": 0, "startDate": today_date_str, "endDate": today_date_str},
        "activity": activity_data
        if activity_data
        else {
            "avgApiCalls": 0,
            "avgMemoryMB": 0,
            "avgCycleMin": 0,
            "longestCycles": [],
        },
        "newPosts": shared_statistics["new_posts"],
        "notifications": shared_statistics["notifications"],
        "actions": shared_statistics["actions"],
        "flaggedPosts": flagged_data,
        "wenyuanPeriodStats": shared_statistics["wenyuan_data"],
    }

    folder_to_save = get_reports_directory()
    md_path = Path(folder_to_save) / f"{today_date}.md"
    # HTML is a single fixed file, overwritten each run, so it can be
    # bookmarked or referenced from a single stable path.
    html_path = Path(folder_to_save).parent / "moderator_digest.html"
    written_md_path = _write_markdown_digest(md_path, digest_summary)

    html_content = _render_html_dashboard(today_date_str, dashboard_data)
    html_path.parent.mkdir(parents=True, exist_ok=True)
    with html_path.open("w", encoding="utf-8") as f:
        f.write(html_content)

    if written_md_path is None:
        logger.info("Daily administrative report completed and saved to %s", html_path)
    else:
        logger.info(
            "Daily administrative report completed and saved to "
            f"{written_md_path} and {html_path}"
        )

    send_discord_alert(subject_line, notification_body, "alert")
    logger.info("Daily moderator digest completed.")

    return
