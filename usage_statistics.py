#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
Contains functions related to statistics tabulation. Many of these
functions are used by Wenyuan, the statistics calculator routine.
"""

from datetime import datetime, timezone

import orjson

from config import Paths, logger
from database import db
from time_handling import get_current_utc_date


def action_counter(messages_number, action_type):
    """
    Records the number of actions performed by type and date in a JSON file.

    :param messages_number: The number of actions to record (typically 1).
    :param action_type: A string representing the type of action (e.g., "command").
    """
    try:
        count = int(messages_number)
        if count == 0:
            return
    except (ValueError, TypeError):
        return

    # Normalize the action type
    if action_type == "!id:":
        action_type = "!identify:"

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
    formatted_content = "\n##### Commands (Daily Average)"
    formatted_content += "\n| Command | Times Used |\n|----------|------------|\n"

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
        if command == "!translate":
            continue  # Skip excluded command.
        display_name = r"\`lookup\`" if command == "`" else command
        daily_average = round(total / days, 2)
        rows.append(f"| {display_name} | {daily_average} |")

    return formatted_content + "\n".join(rows)


"""USER STATISTICS"""


def user_statistics_loader(username):
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

    def fetch_data(query):
        cursor.execute(query, (username,))
        row = cursor.fetchone()
        return eval(row[1]) if row else None  # Use eval only if trusted input

    def format_commands(commands):
        return [
            f"| {'`lookup`' if cmd == '`' else cmd} | {count} |"
            for cmd, count in sorted(commands.items())
            if cmd != "Notifications"
        ]

    def format_notifications(notifications):
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
