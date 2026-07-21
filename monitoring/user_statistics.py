#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""Store and render per-user command and notification statistics."""

import ast
import logging

import orjson

from config import logger as _base_logger
from database import db
from models.instruo import Instruo

logger = logging.LoggerAdapter(_base_logger, {"tag": "MN:USERSTATS"})


def _canonical_notification_language_code(language_code: str) -> str:
    """Return the canonical display key for stored notification stats."""
    parts = language_code.split("-", 1)
    if len(parts) == 2 and parts[0].lower() == parts[1].lower() and len(parts[0]) == 4:
        return f"unknown-{parts[0].lower()}"
    return language_code


def user_statistics_loader(username: str) -> str | None:
    """Return a Markdown table of one user's commands and notifications."""
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

    def normalize_command(command: str) -> str:
        command = command.lstrip("!").rstrip(":")
        if command == "`":
            return "lookup_cjk"
        if command == "wikipedia_lookup":
            return "lookup_wp"
        return command

    def format_commands(commands: dict) -> list[str]:
        normalized_commands: dict[str, int] = {}
        for command, count in commands.items():
            if command == "Notifications":
                continue
            normalized = normalize_command(command)
            normalized_commands[normalized] = (
                normalized_commands.get(normalized, 0) + count
            )
        return [
            f"| {command} | {count} |"
            for command, count in sorted(normalized_commands.items())
        ]

    def format_notifications(notifications: dict) -> list[str]:
        normalized_notifications: dict[str, int] = {}
        for language, count in notifications.items():
            normalized = _canonical_notification_language_code(language)
            normalized_notifications[normalized] = (
                normalized_notifications.get(normalized, 0) + count
            )
        return [
            f"| Notifications (`{language}`) | {count} |"
            for language, count in sorted(normalized_notifications.items())
        ]

    command_counts = fetch_data("SELECT * FROM total_commands WHERE username = ?")
    notification_counts = fetch_data(
        "SELECT * FROM total_notifications WHERE username = ?"
    )
    if not command_counts and not notification_counts:
        logger.debug(f"No statistics found for u/{username}.")
        return None

    command_lines = format_commands(command_counts) if command_counts else []
    notification_lines = (
        format_notifications(notification_counts) if notification_counts else []
    )
    return header + "\n".join(command_lines + notification_lines)


def user_statistics_writer(instruo: Instruo) -> None:
    """Record commands used by one Reddit user in the main database."""
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
        commands_dictionary[command_name] = commands_dictionary.get(command_name, 0) + 1

    if not commands_dictionary:
        logger.debug("No commands to write.")
        return

    serialized_commands = orjson.dumps(commands_dictionary).decode("utf-8")
    if already_saved:
        cursor.execute(
            "UPDATE total_commands SET commands = ? WHERE username = ?",
            (serialized_commands, username),
        )
    else:
        cursor.execute(
            "INSERT INTO total_commands (username, commands) VALUES (?, ?)",
            (username, serialized_commands),
        )

    conn.commit()
    logger.debug(f"Stats written for u/{username}.")
