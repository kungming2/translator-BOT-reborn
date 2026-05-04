#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
Contains functions related to statistics tabulation. Many of these
functions are used by Wenyuan, the statistics calculator routine.
...

Logger tag: [MN:USAGE]
"""

# ─── Imports ──────────────────────────────────────────────────────────────────

import ast
import logging
from datetime import UTC, datetime

import orjson

from config import Paths
from config import logger as _base_logger
from database import db
from integrations.discord_utils import send_discord_alert
from models.instruo import Instruo
from time_handling import get_current_utc_date
from wenju import WENJU_SETTINGS

# ─── Module-level constants ───────────────────────────────────────────────────

logger = logging.LoggerAdapter(_base_logger, {"tag": "MN:USAGE"})


# ─── Action counter ───────────────────────────────────────────────────────────


def _send_action_counter_alert(action_type: str, count: int) -> None:
    """Send a verbose Discord log entry for a recorded action count."""
    message = f"**Action:** `{action_type}`\n**Recorded:** `{count}`\n"
    send_discord_alert("Ziwen Logging", message, "logs")


def action_counter(messages_number: int, action_type: str) -> None:
    """
    Record the number of actions performed by type and date in a JSON file.

    :param messages_number: The number of actions to record (typically 1).
    :param action_type: A string representing the type of action
                        (e.g., "!translated"). This is usually the Komando
                        name.
    """
    try:
        count = int(messages_number)
        if count == 0:
            return
    except (ValueError, TypeError):
        logger.debug(
            f"action_counter: invalid messages_number {messages_number!r}, skipping."
        )
        return

    if action_type == "id":
        action_type = "identify"

    current_day = get_current_utc_date()

    try:
        with open(Paths.LOGS["COUNTER"], "rb") as f:
            current_actions = orjson.loads(f.read())
    except (FileNotFoundError, orjson.JSONDecodeError):
        current_actions = {}

    current_actions.setdefault(current_day, {})
    current_actions[current_day][action_type] = (
        current_actions[current_day].get(action_type, 0) + count
    )

    with open(Paths.LOGS["COUNTER"], "wb") as f:
        f.write(orjson.dumps(current_actions))

    _send_action_counter_alert(action_type, count)


# ─── Language statistics ──────────────────────────────────────────────────────


def months_since_redesign(start_year: int = 2016, start_month: int = 5) -> int:
    """
    Calculate the number of months elapsed since the redesign start date.
    The redesign started in May 2016, and no archive data exists before that.
    Primarily used by Wenyuan, but currently unused.

    :param start_year: The starting year of the redesign (default 2016)
    :param start_month: The starting month of the redesign (default May, 5)
    :return: Number of months elapsed since the redesign start date as an integer
    """
    start_total_months = (start_year * 12) + start_month

    now = datetime.now(UTC)
    current_total_months = (now.year * 12) + now.month

    return current_total_months - start_total_months


def generate_language_frequency_markdown(language_list: list) -> str:
    """
    Generate a Markdown table of relative frequency statistics for
    given Lingvos. Uses data embedded in Lingvo objects if available,
    falling back on stored statistics otherwise.
    """
    header = (
        "| Language Name        | Average Number of Posts | Per   |\n"
        "|----------------------|--------------------------:|:------|\n"
    )
    line_template = (
        "| [{name}]({url})        | {rate:.2f} posts              | {freq} |"
    )
    no_data_template = "| {name:<21} | No recorded statistics     | ---   |"

    lines = []

    for lingvo in language_list:
        language_name = lingvo.name
        daily = lingvo.rate_daily
        monthly = lingvo.rate_monthly
        yearly = lingvo.rate_yearly
        permalink = lingvo.link_statistics

        if all(v is not None for v in (daily, monthly, yearly, permalink)):
            if daily >= 2:
                freq, rate = "day", daily
            elif daily > 0.05:
                freq, rate = "month", monthly
            else:
                freq, rate = "year", yearly

            line = line_template.format(
                name=language_name, url=permalink, rate=rate, freq=freq
            )
        else:
            line = no_data_template.format(name=language_name)

        lines.append(line)

    return header + "\n".join(lines)


# ─── Command usage reporting ──────────────────────────────────────────────────


def generate_command_usage_report(start_time: int, end_time: int, days: int) -> str:
    """
    Generate a Markdown report summarizing average command usage within a time range.

    Reads data from the counter log file and aggregates command usage
    between the given start and end times, then computes a daily average.

    :param start_time: Start time as a Unix timestamp.
    :param end_time: End time as a Unix timestamp.
    :param days: Number of days to average the usage over.
    :return: A Markdown-formatted string summarizing command usage.
    """
    formatted_content = "\n## Actions (Daily Average)"
    formatted_content += "\n| Action | Recorded Count |\n|----------|------------|\n"

    try:
        with open(Paths.LOGS["COUNTER"], "rb") as file:
            counter_data = orjson.loads(file.read())
    except (FileNotFoundError, orjson.JSONDecodeError):
        return formatted_content

    command_totals: dict[str, int] = {}
    for date_text, command_counts in counter_data.items():
        try:
            dt = datetime.strptime(date_text, "%Y-%m-%d").replace(tzinfo=UTC)
            unix_timestamp = int(dt.timestamp())
        except ValueError:
            logger.debug(f"Skipping malformed date entry: {date_text!r}.")
            continue

        if start_time <= unix_timestamp <= end_time:
            for command, count in command_counts.items():
                command_totals[command] = command_totals.get(command, 0) + int(count)

    rows = []
    for command, total in sorted(command_totals.items()):
        daily_average = round(total / days, 2)
        rows.append(f"| {command} | {daily_average} |")

    return formatted_content + "\n".join(rows)


# ─── Notification & points statistics ────────────────────────────────────────


def count_notifications(start_time: int, end_time: int) -> str:
    """
    Gather notification count within a given time period.

    :param start_time: Period start time (Unix timestamp in UTC)
    :param end_time: Period end time (Unix timestamp in UTC)
    :return: Formatted string with notification statistics
    """
    with open(Paths.LOGS["COUNTER"], "rb") as f:
        counter_dict = orjson.loads(f.read())

    total_notifications = 0
    days_with_data = 0

    for date_str, actions in counter_dict.items():
        date_obj = datetime.strptime(date_str, "%Y-%m-%d")
        unix_timestamp = int(date_obj.replace(tzinfo=UTC).timestamp())

        if start_time <= unix_timestamp <= end_time:
            days_with_data += 1
            total_notifications += actions.get("Notifications", 0)

    avg_notifications = (
        total_notifications / days_with_data if days_with_data > 0 else 0
    )

    return (
        f"\n* Total notifications sent during this period:           {total_notifications:,} messages"
        f"\n* Average notifications sent per day during this period: {avg_notifications:,.2f} messages"
    )


def _get_month_stats(username: str, year_month: str) -> tuple[int, int]:
    """Calculate points and unique posts for a user in a specific month."""
    query = """
            SELECT points, post_id
            FROM total_points
            WHERE username = ? \
              AND year_month = ? \
            """
    results = db.fetchall_main(query, (username, year_month))

    total_points = sum(row["points"] for row in results)
    unique_posts = len(set(row["post_id"] for row in results))

    return total_points, unique_posts


def _get_total_stats(username: str) -> tuple[int, int]:
    """Calculate cumulative points for a user across all time."""
    query = """
            SELECT points, post_id
            FROM total_points
            WHERE username = ? \
            """
    results = db.fetchall_main(query, (username,))

    total_points = sum(row["points"] for row in results)
    unique_posts = len(set(row["post_id"] for row in results))

    return total_points, unique_posts


def get_month_points_summary(year_month: str) -> str:
    """
    Generate a formatted table of user points for a given month.
    Settings for this function are in wenju_settings, as this is a
    statistics retrieval function.

    :param year_month: Month identifier in YYYY-MM format (e.g., '2018-09')
    :return: Markdown-formatted table with points breakdown
    """
    point_threshold = WENJU_SETTINGS["minimum_points_display_threshold"]

    header = (
        f"\n| Username | Points in {year_month} | Total Cumulative Points | "
        f"Participated Posts in {year_month} | Total Participated Posts |\n"
        "|-----------|--------|-------|------|-----------|"
    )

    query = """
            SELECT DISTINCT username
            FROM total_points
            WHERE year_month = ?
            ORDER BY LOWER(username) \
            """
    results = db.fetchall_main(query, (year_month,))
    usernames = [row["username"] for row in results]

    usernames_excluded = WENJU_SETTINGS["points_exclude_usernames"]
    usernames = [x for x in usernames if x not in usernames_excluded]

    user_stats = []
    for username in usernames:
        month_points, month_posts = _get_month_stats(username, year_month)

        if month_points < point_threshold:
            continue

        total_points, total_posts = _get_total_stats(username)
        formatted_username = username.replace("_", r"\_")

        user_stats.append(
            {
                "username": formatted_username,
                "month_points": month_points,
                "month_posts": month_posts,
                "total_points": total_points,
                "total_posts": total_posts,
            }
        )

    user_stats.sort(key=lambda user: user["month_points"], reverse=True)

    rows = [
        f"\n| u\\/{user['username']} | {user['month_points']} | {user['total_points']} | "
        f"{user['month_posts']} posts | {user['total_posts']} posts |"
        for user in user_stats
    ]

    return header + "".join(rows)


# ─── User statistics ──────────────────────────────────────────────────────────


def _canonical_notification_language_code(language_code: str) -> str:
    """Return the canonical display key for stored notification stats."""
    parts = language_code.split("-", 1)
    if len(parts) == 2 and parts[0].lower() == parts[1].lower() and len(parts[0]) == 4:
        return f"unknown-{parts[0].lower()}"
    return language_code


def user_statistics_loader(username: str) -> str | None:
    """
    Look up which commands a user has been recorded as using and return
    a formatted table. Also integrates notification data from the same
    database.

    :param username: The username of a Reddit user.
    :return: None if the user has no data, a sorted Markdown table otherwise.
    """
    header = "| Commands/Notifications | Times |\n|--------|------|\n"
    cursor = db.cursor_main

    def fetch_data(query: str) -> dict | None:
        cursor.execute(query, (username,))
        row = cursor.fetchone()
        if not row:
            return None
        value = row[1]
        if isinstance(value, (bytes, bytearray)):
            value = value.decode("utf-8")
        try:
            return orjson.loads(value)
        except orjson.JSONDecodeError:
            return ast.literal_eval(value)

    def normalize_command(cmd: str) -> str:
        """Normalize command names for display."""
        cmd = cmd.lstrip("!").rstrip(":")
        if cmd == "`":
            return "lookup_cjk"
        elif cmd == "wikipedia_lookup":
            return "lookup_wp"
        return cmd

    def format_commands(commands: dict) -> list[str]:
        normalized_commands: dict[str, int] = {}
        for cmd, count in commands.items():
            if cmd == "Notifications":
                continue
            normalized = normalize_command(cmd)
            normalized_commands[normalized] = (
                normalized_commands.get(normalized, 0) + count
            )
        return [
            f"| {cmd} | {count} |" for cmd, count in sorted(normalized_commands.items())
        ]

    def format_notifications(notifications: dict) -> list[str]:
        normalized_notifications: dict[str, int] = {}
        for lang, count in notifications.items():
            normalized = _canonical_notification_language_code(lang)
            normalized_notifications[normalized] = (
                normalized_notifications.get(normalized, 0) + count
            )
        return [
            f"| Notifications (`{lang}`) | {count} |"
            for lang, count in sorted(normalized_notifications.items())
        ]

    commands_dict = fetch_data("SELECT * FROM total_commands WHERE username = ?")
    notifications_dict = fetch_data(
        "SELECT * FROM total_notifications WHERE username = ?"
    )

    if not commands_dict and not notifications_dict:
        logger.debug(f"No statistics found for u/{username}.")
        return None

    command_lines = format_commands(commands_dict) if commands_dict else []
    notification_lines = (
        format_notifications(notifications_dict) if notifications_dict else []
    )

    return header + "\n".join(command_lines + notification_lines)


def user_statistics_writer(instruo: Instruo) -> None:
    """
    Record which commands were used by a Reddit user and store
    them in the main database.

    :param instruo: An Instruo object that contains the commands
                    and author information.
    :return: Nothing.
    """
    username = instruo.author_comment
    commands_list = instruo.commands

    cursor = db.cursor_main
    conn = db.conn_main

    cursor.execute(
        "SELECT commands FROM total_commands WHERE username = ?", (username,)
    )
    row = cursor.fetchone()

    if row is None:
        commands_dictionary = {}
        already_saved = False
    else:
        commands_dictionary = orjson.loads(row["commands"])
        already_saved = True

    for komando in commands_list:
        command_name = komando.name
        if command_name in commands_dictionary:
            commands_dictionary[command_name] += 1
        else:
            commands_dictionary[command_name] = 1

    if not commands_dictionary:
        logger.debug("No commands to write.")
        return

    if already_saved:
        cursor.execute(
            "UPDATE total_commands SET commands = ? WHERE username = ?",
            (orjson.dumps(commands_dictionary).decode("utf-8"), username),
        )
    else:
        cursor.execute(
            "INSERT INTO total_commands (username, commands) VALUES (?, ?)",
            (username, orjson.dumps(commands_dictionary).decode("utf-8")),
        )

    conn.commit()
    logger.debug(f"Stats written for u/{username}.")
