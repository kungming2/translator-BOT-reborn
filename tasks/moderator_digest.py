#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
Formerly posted to a wiki "dashboard", this provides a daily digest of
information and statistics to moderators via Discord.
"""

import csv
import time
from datetime import datetime, timezone
from pathlib import Path

import yaml

from config import SETTINGS, Paths, get_reports_directory, logger
from connection import REDDIT_HELPER
from discord_utils import send_discord_alert
from tasks import WENJU_SETTINGS, task
from time_handling import convert_to_day, get_current_utc_date
from usage_statistics import generate_command_usage_report
from utility import format_markdown_table_with_padding


def activity_csv_handler():
    """
    Manage and summarize the _log_activity.csv file.

    This function trims the CSV to retain only the last LINES_TO_KEEP entries
    and computes summary statistics including:
    - Average API calls per cycle
    - Average memory usage (in MB)
    - Average and longest cycle run times

    :return: A Markdown-formatted string with the calculated averages.
    """
    csv_address = Paths.LOGS["ACTIVITY"]

    try:
        with open(csv_address, "r", newline="") as f_input:
            reader = csv.reader(f_input)
            header = next(reader, None)
            main_lines = list(reader)
    except FileNotFoundError:
        logger.warning("[WJ] csv_handler: Activity log file not found.")
        return "* **Activity log**: File missing"
    except Exception as e:
        logger.error(f"[WJ] csv_handler: Failed to read CSV file — {e}")
        return "* **Activity log**: Error reading file"

    if not main_lines:
        logger.info("[WJ] csv_handler: No data found in activity log.")
        return "* **Activity log**: No data available"

    # --- Process the data: compute averages and detect outliers ---
    # API calls
    api_calls = [int(row[2]) for row in main_lines if row[2].strip()]
    average_api_calls = round(sum(api_calls) / len(api_calls), 2) if api_calls else 0.0

    # Memory usage (strip " MB" or similar)
    memory_data = []
    for row in main_lines:
        cell = row[4].strip()
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

    # Cycle run time (minutes)
    cycle_times = [
        float(row[6])
        for row in main_lines
        if len(row) > 6 and row[1] == "Cycle run" and row[6].strip()
    ]
    average_cycle = (
        round(sum(cycle_times) / len(cycle_times), 2) if cycle_times else 0.0
    )
    longest_cycles = sorted(cycle_times, reverse=True)[:3]
    longest_cycles = [round(x, 2) for x in longest_cycles]

    # --- Format summary output ---
    longest_cycles_str = ", ".join(f"{x:.2f}" for x in longest_cycles)
    summary = (
        f"* **Average API Calls**: {average_api_calls}/cycle"
        f"\n* **Average Memory Used**: {average_memory} MB"
        f"\n* **Average Cycle Length**: {average_cycle} minutes"
        f"\n* **Longest Cycles**: {longest_cycles_str} minutes"
    )

    # --- Trim the CSV to keep only the last LINES_TO_KEEP entries ---
    try:
        with open(csv_address, "w", newline="") as f_output:
            writer = csv.writer(f_output)
            if header:
                writer.writerow(header)
            writer.writerows(main_lines[-WENJU_SETTINGS["lines_to_keep"] :])
    except Exception as e:
        logger.error(f"[WJ] csv_handler: Failed to write trimmed CSV — {e}")
        summary += "\n*Warning: Failed to trim log file.*"
        return summary

    logger.debug(
        f"[WJ] csv_handler: Trimmed activity CSV to last "
        f"{WENJU_SETTINGS['lines_to_keep']} entries. "
        f"Averages — API: {average_api_calls}, "
        f"Memory: {average_memory}, Cycle: {average_cycle}"
    )

    return summary


def error_log_count() -> str:
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

    # Try to access and parse the error log file.
    try:
        with open(Paths.LOGS["ERROR"], "r", encoding="utf-8") as f:
            error_logs: list[dict] | None = yaml.safe_load(f) or []
    except FileNotFoundError:
        logger.warning("[WJ] error_log_count: Error log file not found.")
        return f"{header}\n* **Error log entries**: 0 (file missing)"
    except yaml.YAMLError as e:
        logger.error(f"[WJ] error_log_count: Failed to parse YAML — {e}")
        return f"{header}\n* **Error log entries**: Unknown (YAML parse error)"

    # Handle empty or malformed logs.
    if not isinstance(error_logs, list) or not error_logs:
        return f"{header}\n* **Error log entries**: 0"

    num_entries: int = len(error_logs)

    # Safely get the last entry's timestamp and resolved status.
    last_entry: dict = error_logs[-1]
    last_timestamp: str = last_entry.get("timestamp", "Unknown time")
    last_resolved: bool = last_entry.get("resolved", False)
    last_entry_resolved_status: str = " (resolved)" if last_resolved else ""

    # Convert timestamp to readable local format if possible.
    # This is an exception to the formal that's usually saved, since
    # this is display-only.
    try:
        last_entry_time: str = datetime.fromisoformat(
            last_timestamp.replace("Z", "+00:00")
        ).strftime("%Y-%m-%d %H:%M:%S UTC")
    except (ValueError, TypeError, AttributeError):
        last_entry_time = last_timestamp  # Fallback to raw value

    # Format for Markdown output.
    formatted_template: str = (
        f"{header}\n"
        f"* **Error log entries**: {num_entries}\n"
        f"* **Last entry from**: {last_entry_time}{last_entry_resolved_status}"
    )

    logger.debug(f"[WJ] error_log_count: Found {num_entries} entries in the error log.")

    return formatted_template


def filter_log_tabulator(start_date=None, end_date=None, include_detailed_stats=False):
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
    today = datetime.now(timezone.utc).date()

    # Read the filter log file
    try:
        with open(Paths.LOGS["FILTER"], "r", encoding="utf-8") as f:
            filter_logs = f.read().strip()
    except FileNotFoundError:
        logger.warning("[WJ] filter_log_tabulator: Filter log file not found.")
        return "* **Filter rate**: Unknown (file missing)"

    # Remove header and get entries
    all_entries = filter_logs.splitlines()[2:]

    if len(all_entries) < 2:
        logger.info("[WJ] filter_log_tabulator: Not enough data in filter log.")
        return "* **Filter rate**: Insufficient data"

    # Determine which entries to analyze
    if start_date is not None:
        # Custom date range mode
        entries, period_start, period_end = _filter_entries_by_date_range(
            all_entries, start_date, end_date or today
        )
        if not entries:
            logger.warning(
                "[WJ] filter_log_tabulator: No entries found in specified date range."
            )
            return "* **Filter rate**: No data in specified range"

        days_elapsed = (period_end - period_start).days or 1
        entry_count = len(entries)
        period_label = f"{period_start} to {period_end}"
    else:
        # Default: use last N entries
        entries = all_entries[-WENJU_SETTINGS["lines_to_keep"] :]
        entry_count = len(entries)

        try:
            first_date_str = entries[0].split("|")[0].strip()
            period_start = datetime.strptime(first_date_str, "%Y-%m-%d").date()
        except Exception as e:
            logger.error(f"[WJ] filter_log_tabulator: Failed to parse first date — {e}")
            return "* **Filter rate**: Unknown (date parse error)"

        period_end = today
        days_elapsed = (period_end - period_start).days or 1
        period_label = f"recent {days_elapsed} days"

    # Calculate rate for the period
    rate_per_day = round(entry_count / days_elapsed, 2)

    # Build basic output
    filter_string = f"* **Filter rate**: {rate_per_day}/day ({period_label})"

    logger.debug(
        f"[WJ] filter_log_tabulator: Average filtered posts: {rate_per_day}/day "
        f"over {days_elapsed} days ({entry_count} entries)."
    )

    # Optionally include detailed stats comparing period vs. total
    if include_detailed_stats:
        try:
            # Parse oldest entry in entire log
            oldest_date_str = all_entries[0].split("|")[0].strip()
            oldest_date = datetime.strptime(oldest_date_str, "%Y-%m-%d").date()

            total_days = (today - oldest_date).days or 1
            total_count = len(all_entries)
            total_rate = round(total_count / total_days, 2)

            # Calculate percentage difference
            if total_rate > 0:
                rate_diff = round(((rate_per_day - total_rate) / total_rate) * 100, 1)
                trend = "↑" if rate_diff > 0 else "↓" if rate_diff < 0 else "→"

                filter_string += (
                    f"\n* **Overall rate**: {total_rate}/day (all-time: {total_count} entries, {total_days} days)"
                    f"\n* **Trend**: {trend} {abs(rate_diff)}% vs. all-time average"
                )

                logger.debug(
                    f"[WJ] filter_log_tabulator: All-time average: {total_rate}/day. "
                    f"Period comparison: {rate_diff:+.1f}%"
                )
            else:
                filter_string += f"\n* **Overall rate**: {total_rate}/day (all-time: {total_count} entries)"

                logger.debug(
                    f"[WJ] filter_log_tabulator: All-time average: {total_rate}/day. "
                    f"Period comparison: N/A"
                )

        except Exception as e:
            logger.error(
                f"[WJ] filter_log_tabulator: Failed to calculate detailed stats — {e}"
            )

    return filter_string


def _filter_entries_by_date_range(entries, start_date, end_date):
    """
    Filter log entries to those within the specified date range.

    Args:
        entries: List of log entry strings
        start_date: datetime.date or Unix timestamp
        end_date: datetime.date or Unix timestamp

    Returns:
        tuple: (filtered_entries, start_date_obj, end_date_obj)
    """
    # Convert Unix timestamps to date objects if needed
    if isinstance(start_date, (int, float)):
        start_date = datetime.fromtimestamp(start_date, tz=timezone.utc).date()
    if isinstance(end_date, (int, float)):
        end_date = datetime.fromtimestamp(end_date, tz=timezone.utc).date()

    filtered = []
    for line_num, entry in enumerate(entries, start=1):
        try:
            # Split by pipe and filter out empty strings
            parts = [p.strip() for p in entry.split("|") if p.strip()]

            if not parts:
                raise ValueError("No valid parts found in entry")

            # First non-empty part should be the date
            entry_date_str = parts[0]

            # Parse the date string to a date object
            entry_date = datetime.strptime(entry_date_str, "%Y-%m-%d").date()

        except Exception as e:
            # Skip entries with malformed dates
            logger.error(f"Encountered entry error at line {line_num}: {e}")
            logger.error(f"ENTRY: {entry}")
            continue

        # Only do comparison if we successfully parsed a date
        if entry_date is not None and start_date <= entry_date <= end_date:
            filtered.append(entry)

    return filtered, start_date, end_date


def note_language_tags():
    """
    Identify recent posts that have temporary or missing language tags.

    Temporary tags include "[?]" and "[--]". Posts with these or blank tags
    should be reviewed and assigned proper language flair.

    This function scans the latest 1000 posts, filters those with malformed
    or missing tags, and returns a Markdown-formatted table summarizing them.
    """

    header = "\n# Entries with Tags to Note\n"

    malformed_tags = {"[?]", "[--]", "[]"}
    flagged_submissions = []

    # Get the last 1000 submissions and check their flair tags.
    for submission in REDDIT_HELPER.subreddit(SETTINGS["subreddit"]).new(limit=1000):
        flair = submission.link_flair_text
        if flair is None or any(tag in flair for tag in malformed_tags):
            flagged_submissions.append(submission)

    # Sort by creation time (oldest first).
    flagged_submissions.sort(key=lambda s: s.created_utc)

    logger.debug(
        f"[WJ] note_language_tags: Found {len(flagged_submissions)} posts with temporary or missing tags."
    )

    # Return early if there are no results.
    if not flagged_submissions:
        return header

    rows = []
    for post in flagged_submissions:
        # Convert timestamp to readable date.
        submission_date = convert_to_day(post.created_utc)

        # Shorten the title if too long.
        title = post.title.strip()
        if len(title) > 30:
            title = title[:30].rstrip() + "..."

        flair_display = post.link_flair_text or "(none)"
        post_url = f"https://redd.it/{post.id}"

        # Add a Markdown bullet instead of a table row.
        rows.append(
            f"* [{title}]({post_url}) ({submission_date}) • "
            f"`{flair_display}` • {post.num_comments} comments"
        )

    formatted_output = header + "\n".join(rows)

    return formatted_output


@task(schedule="daily")
def collate_moderator_digest():
    """
    Sends out an overall digest of the subreddit's state and things for
    moderators to note. Uses Discord. The daily information is also
    saved to a local Markdown file for archival purposes.
    :return: None
    """
    logger.info("Collating moderator digest...")
    today_date_str = get_current_utc_date()
    today_date = datetime.strptime(today_date_str, "%Y-%m-%d").date()
    days_ago = WENJU_SETTINGS["report_command_average"]
    time_delta = 86400 * days_ago
    current_time = int(time.time())
    back_start_date = current_time - time_delta

    # Collect the data.
    error_log_data = error_log_count()
    filter_log_data = filter_log_tabulator(
        start_date=back_start_date, end_date=today_date
    )
    activity_data = activity_csv_handler()
    command_data = generate_command_usage_report(
        back_start_date, current_time, days_ago
    )
    command_data = format_markdown_table_with_padding(command_data)
    noted_entries_data = note_language_tags()

    # Compile the full Markdown summary.
    total_data = "\n".join(
        [
            error_log_data,
            filter_log_data,
            activity_data,
            command_data,
            noted_entries_data,
        ]
    )
    subject_line = f"Moderator Digest for {today_date}"
    digest_summary = f"# {subject_line}\n{total_data}"

    # Resolve the output file path.
    folder_to_save = get_reports_directory()
    output_path = Path(folder_to_save) / f"{today_date}.md"

    # Write to a file safely.
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        f.write(digest_summary)

    logger.info(
        f"[WJ] Daily administrative routine completed and saved to {output_path}"
    )

    # Send as a Discord message.
    send_discord_alert(subject_line, total_data, "alert")
    logger.info("Daily moderator digest completed.")

    return


if __name__ == "__main__":
    print(
        filter_log_tabulator(
            start_date=1759302000, end_date=1761030000, include_detailed_stats=True
        )
    )
    print(filter_log_tabulator())
