#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
Contains functions related to statistics tabulation. Many of these
functions are used by Wenyuan, the statistics calculator routine.
"""

from datetime import datetime, timezone
from typing import Optional

import orjson

from config import Paths, logger
from database import db
from tasks import WENJU_SETTINGS
from time_handling import get_current_utc_date


def action_counter(messages_number, action_type):
    """
    Records the number of actions performed by type and date in a JSON file.

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
        return

    # Normalize the action type
    if action_type == "id":
        action_type = "identify"

    current_day = get_current_utc_date()

    # Load existing data
    try:
        with open(Paths.LOGS["COUNTER"], "rb") as f:
            current_actions = orjson.loads(f.read())
    except (FileNotFoundError, orjson.JSONDecodeError):
        current_actions = {}

    # Update the count
    current_actions.setdefault(current_day, {})
    current_actions[current_day][action_type] = (
        current_actions[current_day].get(action_type, 0) + count
    )

    # Save the updated data
    with open(Paths.LOGS["COUNTER"], "wb") as f:
        f.write(orjson.dumps(current_actions))


def load_statistics_data(language_code):
    """
    Loads language statistics from a saved JSON file. This will primarily
    be used by Wenyuan, but is currently unused.

    :param language_code: Language code as a string.
    :return: The corresponding language dictionary if found, otherwise None.
    """
    try:
        with open(Paths.DATASETS["STATISTICS"], "rb") as f:
            stats_data = orjson.loads(f.read())
        return stats_data.get(language_code)
    except (FileNotFoundError, orjson.JSONDecodeError):
        return None


def months_since_redesign(start_year=2016, start_month=5) -> int:
    """
    Calculate the number of months elapsed since the redesign start date.
    The redesign started in May 2016, and no archive data exists before that.
    This is used to help calculate statistics more accurately.
    This will primarily be used by Wenyuan, but is currently unused.

    :param start_year: The starting year of the redesign (default 2016)
    :param start_month: The starting month of the redesign (default May, 5)
    :return: Number of months elapsed since the redesign start date as an integer
    """
    # Convert start date to a total month count
    start_total_months = (start_year * 12) + start_month

    # Get current year and month
    now = datetime.now(timezone.utc)  # datetime object
    current_total_months = (now.year * 12) + now.month

    # Calculate elapsed months
    elapsed_months = current_total_months - start_total_months

    return elapsed_months


def generate_language_frequency_markdown(language_list):
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

        # Load values from the object itself
        daily = lingvo.rate_daily
        monthly = lingvo.rate_monthly
        yearly = lingvo.rate_yearly
        permalink = lingvo.link_statistics

        if all(v is not None for v in (daily, monthly, yearly, permalink)):
            # Determine appropriate frequency bucket
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


def generate_command_usage_report(start_time, end_time, days):
    """
    Generate a Markdown report summarizing average command usage within a time range.

    This function reads data from the counter log file and aggregates command usage
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
        # If file is missing or malformed, return just the header.
        return formatted_content

    # Aggregate command counts within the specified time range.
    command_totals = {}
    for date_text, command_counts in counter_data.items():
        try:
            dt = datetime.strptime(date_text, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            unix_timestamp = int(dt.timestamp())
        except ValueError:
            continue  # Skip invalid date entries.

        if start_time <= unix_timestamp <= end_time:
            for command, count in command_counts.items():
                command_totals[command] = command_totals.get(command, 0) + int(count)

    # Format the results into a Markdown table.
    rows = []
    for command, total in sorted(command_totals.items()):
        daily_average = round(total / days, 2)
        rows.append(f"| {command} | {daily_average} |")

    return formatted_content + "\n".join(rows)


"""NOTIFICATIONS/POINTS STATISTICS"""


def count_notifications(start_time, end_time):
    """
    Gather notification count within a given time period.

    :param start_time: Period start time (Unix timestamp in UTC)
    :param end_time: Period end time (Unix timestamp in UTC)
    :return: Formatted string with notification statistics
    """
    from datetime import datetime
    import json

    # Load counter log
    with open(Paths.LOGS["COUNTER"], "r", encoding="utf-8") as f:
        counter_dict = json.load(f)

    total_notifications = 0
    days_with_data = 0

    # Aggregate notifications within the time range
    for date_str, actions in counter_dict.items():
        # Convert date string to UTC Unix timestamp
        date_obj = datetime.strptime(date_str, "%Y-%m-%d")
        unix_timestamp = int(date_obj.replace(tzinfo=timezone.utc).timestamp())

        if start_time <= unix_timestamp <= end_time:
            days_with_data += 1
            total_notifications += actions.get("Notifications", 0)

    # Calculate average (avoid division by zero)
    avg_notifications = (
        total_notifications / days_with_data if days_with_data > 0 else 0
    )

    return (
        f"\n* Total notifications sent during this period:           {total_notifications:,} messages"
        f"\n* Average notifications sent per day during this period: {avg_notifications:,.2f} messages"
    )


def get_month_points_summary(year_month):
    """
    Generate a formatted table of user points for a given month.
    Settings for this function are in wenju_settings, as this is a
    statistics retrieval function.

    :param year_month: Month identifier in YYYY-MM format (e.g., '2018-09')
    :return: Markdown-formatted table with points breakdown
    """
    # Minimum points required for inclusion in summary
    point_threshold = WENJU_SETTINGS["minimum_points_display_threshold"]

    # Build table header
    header = (
        f"\n| Username | Points in {year_month} | Total Cumulative Points | "
        f"Participated Posts in {year_month} | Total Participated Posts |\n"
        "|-----------|--------|-------|------|-----------|"
    )

    # Get all usernames for the month (sorted alphabetically)
    query = """
            SELECT DISTINCT username
            FROM total_points
            WHERE year_month = ?
            ORDER BY LOWER(username) \
            """
    results = db.fetchall_main(query, (year_month,))
    usernames = [row["username"] for row in results]

    # Exclude translator-ModTeam and bot itself
    usernames_excluded = WENJU_SETTINGS["points_exclude_usernames"]
    usernames = [x for x in usernames if x not in usernames_excluded]

    # Collect user statistics
    user_stats = []
    for username in usernames:
        month_points, month_posts = _get_month_stats(username, year_month)

        # Skip users below threshold
        if month_points < point_threshold:
            continue

        total_points, total_posts = _get_total_stats(username)

        # Escape underscores for markdown formatting
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

    # Sort by month points (descending)
    user_stats.sort(key=lambda user: user["month_points"], reverse=True)

    # Build table rows
    rows = [
        f"\n| u\\/{user['username']} | {user['month_points']} | {user['total_points']} | "
        f"{user['month_posts']} posts | {user['total_posts']} posts |"
        for user in user_stats
    ]

    return header + "".join(rows)


def _get_month_stats(username, year_month):
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


def _get_total_stats(username):
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


"""USER STATISTICS"""


def user_statistics_loader(username: str) -> Optional[str]:
    """
    Function that pairs with messaging_user_statistics_writer.
    Takes a username and looks up what commands they have
    been recorded as using.

    If they have data, it will return a nicely formatted table. Since
    the notifications data is also recorded in the
    same database, this function will also format the data in that
    dictionary and integrate it into the table.

    :param username: The username of a Reddit user.
    :return: None if the user has no data (no commands that they
             called), a sorted Markdown table otherwise.
    """
    header = "| Command | Times |\n|--------|------|\n"
    cursor = db.cursor_main  # Use the DatabaseManager cursor

    def fetch_data(query: str) -> Optional[dict]:
        cursor.execute(query, (username,))
        row = cursor.fetchone()
        return eval(row[1]) if row else None  # Use eval only if trusted input

    def normalize_command(cmd: str) -> str:
        """Normalize command names for display."""
        # Remove leading ! and trailing colons
        cmd = cmd.lstrip("!").rstrip(":")

        # Specific replacements
        if cmd == "`":
            return "lookup_cjk"
        elif cmd == "wikipedia_lookup":
            return "lookup_wp"

        return cmd

    def format_commands(commands: dict) -> list[str]:
        # Aggregate commands by normalized name
        normalized_commands = {}
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
        return [
            f"| Notifications (`{lang}`) | {count} |"
            for lang, count in sorted(notifications.items())
        ]

    # Fetch and process both command and notification data
    commands_dict = fetch_data("SELECT * FROM total_commands WHERE username = ?")
    notifications_dict = fetch_data(
        "SELECT * FROM notify_cumulative WHERE username = ?"
    )

    if not commands_dict and not notifications_dict:
        return None

    command_lines = format_commands(commands_dict) if commands_dict else []
    notification_lines = (
        format_notifications(notifications_dict) if notifications_dict else []
    )

    return header + "\n".join(command_lines + notification_lines)


def user_statistics_writer(instruo):
    """
    Records which commands were used by a Reddit user and stores
    them in the main database.

    :param instruo: An Instruo object that contains the commands
                    and author information.
    :return: Nothing.
    """
    username = instruo.author_comment
    commands_list = instruo.commands  # List of Komando(name=..., data=[...])

    cursor = db.cursor_main
    conn = db.conn_main

    # Load existing record for the user
    cursor.execute(
        "SELECT commands FROM total_commands WHERE username = ?", (username,)
    )
    row = cursor.fetchone()

    if row is None:
        commands_dictionary = {}
        already_saved = False
    else:
        commands_dictionary = eval(row["commands"])
        already_saved = True

    # Count occurrences of each command name
    for komando in commands_list:
        command_name = komando.name
        if command_name in commands_dictionary:
            commands_dictionary[command_name] += 1
        else:
            commands_dictionary[command_name] = 1

    # Skip saving if nothing to store
    if not commands_dictionary:
        logger.debug("[ZW] messaging_user_statistics_writer: No commands to write.")
        return

    # Store or update the command usage in the database
    if already_saved:
        cursor.execute(
            "UPDATE total_commands SET commands = ? WHERE username = ?",
            (str(commands_dictionary), username),
        )
    else:
        cursor.execute(
            "INSERT INTO total_commands (username, commands) VALUES (?, ?)",
            (username, str(commands_dictionary)),
        )

    conn.commit()
    logger.debug(
        f"[ZW] messaging_user_statistics_writer: Stats written for u/{username}."
    )


if "__main__" == __name__:
    while True:
        my_input = input("Check on the user statistics for this username: ")
        print(user_statistics_loader(my_input))
