#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
Command registry for the Zhongsheng Discord bot.
Allows commands to be defined in separate modules and registered via decorator.
"""

import importlib
import logging
import time
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any

from discord.ext import commands

from config import Paths, load_settings

if TYPE_CHECKING:
    from discord.ext.commands import Context


# ─── Command registry ─────────────────────────────────────────────────────────

_commands: list[dict[str, Any]] = []
GUILD_ID_SETTING = "ZHONGSHENG_GUILD_ID"

# Guide descriptions and role requirements. Add one entry for each command.
COMMAND_GUIDE = {
    "cjk": {
        "description": "Look up Chinese, Japanese, or Korean words. Use c/j/k as shortcuts (e.g. `/cjk c 翻译`)",
        "roles": ["Moderator", "Helper"],
    },
    "comment": {
        "description": "Fetch Instruo data and parsed bot commands for a Reddit comment "
        "(accepts comment IDs and Reddit comment URLs). Use the `--text` flag to parse text directly",
        "roles": ["Moderator"],
    },
    "describe": {
        "description": "Generate an AI image description from a URL",
        "roles": ["Moderator", "Helper"],
    },
    "error": {
        "description": "Display the 3 most recent error log entries and event-log errors from the last 3 days",
        "roles": ["Moderator"],
    },
    "filter": {
        "description": "Check whether a Reddit post title would pass r/translator formatting filters",
        "roles": ["Moderator", "Helper"],
    },
    "guide": {
        "description": "Display this informational guide about Zhongsheng commands",
        "roles": ["Moderator", "Helper"],
    },
    "lang": {
        "description": 'Convert language codes/names. Use "random" for a random language (e.g. `/lang random`). '
        "Alternate names can be added as `/lang [code] --add_alt [new_name]`",
        "roles": ["Moderator", "Helper"],
    },
    "notif": {
        "description": "Manage user notification subscriptions for r/translator. "
        "Use `/notif add [username] [languages]` to add language subscriptions, "
        "`/notif status [username]` to view current subscriptions and usage statistics, "
        "or `/notif remove [username]` to purge all subscriptions for that user from the database",
        "roles": ["Moderator"],
    },
    "post": {
        "description": "Search log files and database for a Reddit post ID (accepts IDs and Reddit post URLs). "
        "Also shows available points data",
        "roles": ["Moderator"],
    },
    "recruit": {
        "description": "Generate copyable recruitment-post notification links and request-frequency rows. "
        "Separate multiple language names or codes with commas",
        "roles": ["Moderator"],
    },
    "search": {
        "description": "Search for Reddit translation posts related to a term and return matching results",
        "roles": ["Moderator", "Helper"],
    },
    "status": {
        "description": "Get a random quote from *The Office (US)* and see the last 5 Ziwen event-log entries",
        "roles": ["Moderator", "Helper"],
    },
    "title": {
        "description": "Process a Reddit post title. Use the `--ai` flag for AI parsing",
        "roles": ["Moderator"],
    },
    "user": {
        "description": "Search log files and database for a Reddit username "
        "(accepts usernames and Reddit user URLs). Also shows available user statistics",
        "roles": ["Moderator"],
    },
}


def command(name: str, help_text: str, roles: list | None = None) -> Callable:
    """
    Decorator to register a Discord bot command.

    Args:
        name: Command name (used after /)
        help_text: Help description for the command
        roles: List of required role names, or None for no restrictions
    """

    def decorator(func: Callable) -> Callable:
        _commands.append(
            {"name": name, "help": help_text, "roles": roles or [], "func": func}
        )
        return func

    return decorator


def get_commands() -> list:
    """Get all registered commands."""
    return _commands


def load_expected_guild_id(logger: logging.LoggerAdapter | None = None) -> int | None:
    """Load the only Discord guild authorized for Zhongsheng commands."""
    credentials = load_settings(Paths.AUTH["CREDENTIALS"])
    guild_id = credentials.get(GUILD_ID_SETTING)

    if not guild_id:
        if logger is not None:
            logger.error(
                "Missing required setting %r in credentials file.", GUILD_ID_SETTING
            )
        return None

    try:
        return int(guild_id)
    except (TypeError, ValueError):
        if logger is not None:
            logger.error("%s must be a numeric Discord guild ID.", GUILD_ID_SETTING)
        return None


# ─── Bot registration ─────────────────────────────────────────────────────────


def register_commands(bot: commands.Bot) -> None:
    """Register all commands with the Discord bot as hybrid commands."""

    # Dynamically import all command modules in the zhongsheng/ directory
    # to trigger registration. This automatically includes any .py files
    # without needing to manually list them.
    current_dir = Path(__file__).parent

    for file_path in current_dir.glob("*.py"):
        if file_path.name != "__init__.py":
            module_name = file_path.stem  # filename without .py extension
            importlib.import_module(f".{module_name}", package=__package__)

    for cmd in _commands:
        func = cmd["func"]
        description = cmd["help"][:100]

        # Apply role restrictions if specified
        if cmd["roles"]:
            if len(cmd["roles"]) == 1:
                func = commands.has_role(cmd["roles"][0])(func)
            else:
                func = commands.has_any_role(*cmd["roles"])(func)

        bot.hybrid_command(
            name=cmd["name"],
            description=description,
            help=cmd["help"],
        )(func)


# ─── Shared utilities ─────────────────────────────────────────────────────────


async def send_long_message(
    ctx: commands.Context, content: str, max_length: int = 2000
) -> None:
    """
    Splits long messages into chunks and sends them separately.
    Attempts to split on paragraph boundaries first for readability.
    """
    if len(content) <= max_length:
        await ctx.send(content)
        return

    chunks = []
    current_chunk = ""

    # Split by double newlines (paragraphs) first
    paragraphs = content.split("\n\n")

    for paragraph in paragraphs:
        # If a single paragraph exceeds max length, split it further
        if len(paragraph) > max_length:
            if current_chunk:
                chunks.append(current_chunk)
                current_chunk = ""

            # Split long paragraph by single newlines
            lines = paragraph.split("\n")
            for line in lines:
                if len(line) > max_length:
                    if current_chunk:
                        chunks.append(current_chunk)
                        current_chunk = ""
                    for index in range(0, len(line), max_length):
                        chunks.append(line[index : index + max_length])
                    continue
                if len(current_chunk) + len(line) + 1 > max_length:
                    if current_chunk:
                        chunks.append(current_chunk)
                    current_chunk = line
                else:
                    current_chunk += ("\n" if current_chunk else "") + line
        else:
            # Try to add paragraph to current chunk
            test_chunk = current_chunk + ("\n\n" if current_chunk else "") + paragraph
            if len(test_chunk) <= max_length:
                current_chunk = test_chunk
            else:
                if current_chunk:
                    chunks.append(current_chunk)
                current_chunk = paragraph

    if current_chunk:
        chunks.append(current_chunk)

    for chunk in chunks:
        await ctx.send(chunk)


async def search_logs(ctx: "Context", search_term: str, term_type: str) -> bool:
    """
    Search through log files and the Ajo database for a given term,
    which can be a username or a post ID.

    Args:
        ctx: Discord context
        search_term: The term to search for (username or post_id)
        term_type: Type of search ('user' or 'post') for display purposes
    """
    from config import SETTINGS, Paths
    from config import logger as _base_logger
    from database import search_database

    logger = logging.LoggerAdapter(_base_logger, {"tag": "ZS:SEARCH"})
    days_back = SETTINGS["log_search_days"]
    log_files = {
        "FILTER": Paths.LOGS["FILTER"],
        "EVENTS": Paths.LOGS["EVENTS"],
        "ERROR": Paths.LOGS["ERROR"],
    }

    cutoff_utc = int(time.time()) - (days_back * 86400)

    try:
        log_lines = []

        for log_name, log_path in log_files.items():
            try:
                with open(log_path, encoding="utf-8", errors="replace") as log_file:
                    for line in log_file:
                        if search_term in line:
                            log_lines.append(f"[{log_name}] {line.strip()}")
            except FileNotFoundError:
                await ctx.send(
                    f"Warning: {log_name} log file not found at `{log_path}`"
                )
                continue

        db_results = search_database(search_term, term_type, start_utc=cutoff_utc)

        if not log_lines and not db_results:
            await ctx.send(
                f"No entries found for {term_type} `{search_term}` in logs or "
                f"database records from the last {days_back} days."
            )
            return False

        response = (
            f"Search results for {term_type} `{search_term}` "
            f"(all scanned logs; database records from the last {days_back} days):\n```\n"
        )

        if log_lines:
            response += f"=== LOG FILES ({len(log_lines)} matches) ===\n"
            for line in log_lines:
                if len(response) + len(line) + 10 > 1900:
                    response += "```"
                    await ctx.send(response)
                    response = "```\n"
                response += line + "\n"
            response += "\n"

        if db_results:
            response += f"=== DATABASE ({len(db_results)} records) ===\n"
            for ajo in db_results:
                ajo_str = (
                    f"Post ID: {ajo.id}\n"
                    f"  Author: u/{ajo.author}\n"
                    f"  Status: {ajo.status}\n"
                    f"  Language: {ajo.language_name} ({ajo.preferred_code})\n"
                    f"  Title: {ajo.title}\n"
                    f"  Direction: {ajo.direction}\n"
                    f"---"
                )
                if len(response) + len(ajo_str) + 10 > 1900:
                    response += "```"
                    await ctx.send(response)
                    response = "```\n"
                response += ajo_str + "\n"

        response += "```"
        await ctx.send(response)
        return True

    except Exception as e:
        logger.error(
            f"Error searching logs for {term_type} `{search_term}`: {e}", exc_info=True
        )
        await ctx.send("An error occurred while searching logs and database records.")
        return False
