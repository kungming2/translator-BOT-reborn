#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""Generate operational and rule-violation reports for moderators."""

import csv
import logging
import re
import time
from collections import Counter
from datetime import datetime
from typing import Any

import yaml

from config import SETTINGS, Paths
from config import logger as _base_logger
from integrations.discord_utils import send_discord_alert
from reddit.connection import REDDIT
from time_handling import get_current_utc_date
from utility import format_markdown_table_with_padding
from wenju import task

logger = logging.LoggerAdapter(_base_logger, {"tag": "WJ:MODREPORT"})

ModRemovalReport = dict[str, Any]


def _activity_csv_summary() -> tuple[str, dict[str, object]]:
    """Read the activity log and summarize recent runtime performance."""
    csv_address = Paths.LOGS["ACTIVITY"]

    try:
        with open(csv_address, newline="") as f_input:
            reader = csv.reader(f_input)
            next(reader, None)
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
    longest_cycles = [
        round(value, 2) for value in sorted(cycle_times, reverse=True)[:3]
    ]
    longest_cycles_str = ", ".join(f"{value:.2f}" for value in longest_cycles)

    summary = (
        f"* **Average API Calls**: {average_api_calls}/cycle"
        f"\n* **Average Memory Used**: {average_memory} MB"
        f"\n* **Average Cycle Length**: {average_cycle} minutes"
        f"\n* **Longest Cycles**: {longest_cycles_str} minutes"
    )
    data = {
        "avgApiCalls": average_api_calls,
        "avgMemoryMB": average_memory,
        "avgCycleMin": average_cycle,
        "longestCycles": longest_cycles,
    }
    return summary, data


def _error_log_summary() -> tuple[str, dict[str, object]]:
    """Summarize the error-log count and most recent entry."""
    header = "# Error Log"

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

    last_entry = error_logs[-1]
    last_timestamp = last_entry.get("timestamp", "Unknown time")
    last_resolved = last_entry.get("resolved", False)
    resolved_suffix = " (resolved)" if last_resolved else ""

    try:
        last_entry_time = datetime.fromisoformat(
            last_timestamp.replace("Z", "+00:00")
        ).strftime("%Y-%m-%d %H:%M:%S UTC")
    except (ValueError, TypeError, AttributeError):
        last_entry_time = last_timestamp

    count = len(error_logs)
    summary = (
        f"{header}\n"
        f"* **Error log entries**: {count}\n"
        f"* **Last entry from**: {last_entry_time}{resolved_suffix}"
    )
    logger.debug(f"Found {count} entries in the error log.")

    return summary, {
        "count": count,
        "lastEntry": last_entry_time + resolved_suffix,
        "resolved": last_resolved,
    }


@task(schedule="daily")
def send_moderator_update() -> None:
    """Send error-log and runtime-performance information to moderators."""
    logger.info("Preparing moderator operational update...")
    today_date = get_current_utc_date()
    error_log_summary, _ = _error_log_summary()
    activity_summary, _ = _activity_csv_summary()
    notification_body = f"{error_log_summary}\n\n# Performance\n{activity_summary}"

    send_discord_alert(f"Moderator Update for {today_date}", notification_body, "alert")
    logger.info("Daily moderator operational update sent.")


def _analyze_mod_removals(start_time: int, end_time: int) -> ModRemovalReport:
    """Analyze moderator removal comments to count rule violations."""
    subreddit = REDDIT.subreddit(SETTINGS["subreddit"])
    mod_team_account = REDDIT.redditor(f"{subreddit}-ModTeam")

    rule_pattern = re.compile(r"\[Rule #([A-Z]\d+)]", re.IGNORECASE)

    rule_violations: list[str] = []
    total_comments_checked: int = 0

    logger.info(f"Fetching comments from u/{subreddit}-ModTeam...")
    try:
        for comment in mod_team_account.comments.new(limit=None):
            total_comments_checked += 1

            if not (start_time <= comment.created_utc <= end_time):
                if comment.created_utc < start_time:
                    break
                continue

            rules_found = rule_pattern.findall(comment.body)
            for rule in rules_found:
                rule_upper = rule.upper()
                rule_violations.append(rule_upper)
                logger.info(
                    f"Found Rule #{rule_upper} in ModTeam comment: "
                    f"https://www.reddit.com/{comment.permalink}"
                )

    except Exception as e:
        logger.error(f"Error fetching comments from u/translator-ModTeam: {e}")

    logger.info("Fetching distinguished mod comments from r/translator...")
    try:
        moderators: list[str] = [mod.name for mod in subreddit.moderator()]

        for comment in subreddit.comments(limit=None):
            total_comments_checked += 1

            if not (start_time <= comment.created_utc <= end_time):
                if comment.created_utc < start_time:
                    break
                continue

            if (
                comment.author
                and comment.author.name in moderators
                and comment.distinguished
            ):
                rules_found = rule_pattern.findall(comment.body)
                for rule in rules_found:
                    rule_upper = rule.upper()
                    rule_violations.append(rule_upper)
                    logger.info(
                        f"Found Rule #{rule_upper} in distinguished comment: "
                        f"https://www.reddit.com/{comment.permalink}"
                    )

    except Exception as e:
        logger.error(f"Error fetching distinguished comments: {e}")

    violation_counts = Counter(rule_violations)

    results = {
        "start_time": start_time,
        "end_time": end_time,
        "start_date": datetime.fromtimestamp(start_time).strftime(
            "%Y-%m-%d %H:%M:%S UTC"
        ),
        "end_date": datetime.fromtimestamp(end_time).strftime("%Y-%m-%d %H:%M:%S UTC"),
        "total_comments_checked": total_comments_checked,
        "total_violations": len(rule_violations),
        "unique_rules_violated": len(violation_counts),
        "violation_counts": dict(violation_counts.most_common()),
    }

    logger.info("Rule violation analysis complete:")
    logger.info(f"  Period: {results['start_date']} to {results['end_date']}")
    logger.info(f"  Total mod comments checked: {total_comments_checked}")
    logger.info(f"  Total violations found: {results['total_violations']}")
    logger.info(f"  Unique rules violated: {results['unique_rules_violated']}")
    logger.info(f"  Top 5 violations: {violation_counts.most_common(5)}")

    return results


@task(schedule="monthly")
def monthly_rule_violation_report() -> ModRemovalReport:
    """Generate a monthly rule-violation report and send it to Discord."""
    end_time = int(time.time())
    start_time = end_time - (30 * 24 * 60 * 60)

    results: ModRemovalReport = _analyze_mod_removals(start_time, end_time)

    subject_line = (
        f"Monthly r/translator Rule Violation Report - {results['end_date'][:10]}"
    )

    report_sections: list[str] = []

    summary = f"""## Summary
- **Analysis Period**: {results["start_date"]} to {results["end_date"]}
- **Total Comments Checked**: {results["total_comments_checked"]:,}
- **Total Violations Found**: {results["total_violations"]}
- **Unique Rules Violated**: {results["unique_rules_violated"]}
"""
    report_sections.append(summary)

    if results["violation_counts"]:
        breakdown_table = [
            "| Rule | Count | Percentage |",
            "|------|-------|------------|",
        ]
        for rule, count in results["violation_counts"].items():
            percentage = (
                (count / results["total_violations"] * 100)
                if results["total_violations"] > 0
                else 0
            )
            breakdown_table.append(f"| Rule #{rule} | {count} | {percentage:.1f}% |")
        report_sections.append(
            "## Rule Violation Breakdown\n"
            + format_markdown_table_with_padding("\n".join(breakdown_table))
        )
    else:
        report_sections.append(
            "## Rule Violation Breakdown\nNo violations found in this period."
        )

    total_data = "\n\n".join(report_sections)

    send_discord_alert(subject_line, total_data, "notification")
    logger.info("Monthly rule violation report sent via Discord.")

    return results
