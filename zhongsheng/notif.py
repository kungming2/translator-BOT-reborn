#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
Notification management command for moderators.
...

Logger tag: [ZS:NOTIF]
"""

import logging
from typing import Optional

from discord.ext import commands

from config import logger as _base_logger
from reddit.messaging import parse_language_list, user_statistics_loader
from reddit.notifications import (
    notifier_language_list_editor,
    notifier_language_list_retriever,
)
from utility import format_markdown_table_with_padding

from . import command

logger = logging.LoggerAdapter(_base_logger, {"tag": "ZS:NOTIF"})


# ─── Command dispatcher ───────────────────────────────────────────────────────


@command(
    name="notif",
    help_text="Manage user notification subscriptions for r/translator.",
    roles=["Moderator"],
)
async def notif(
    ctx: commands.Context, action: str, username: str, language: Optional[str] = None
) -> None:
    """
    Discord wrapper for notification management.

    Usage:
        /notif add username language_codes
        /notif remove username
        /notif status username

    Examples:
        /notif add JohnDoe es, fr, de
        /notif remove JohnDoe
        /notif status JohnDoe
    """
    username = username.strip().lstrip("u/").lstrip("/u/")
    action = action.lower()

    try:
        if action == "add":
            await handle_notif_add(ctx, username, language)
        elif action == "remove":
            await handle_notif_remove(ctx, username)
        elif action == "status":
            await handle_notif_status(ctx, username)
        else:
            await ctx.send(
                f"⚠️ Invalid action: `{action}`\n"
                f"Valid actions are: `add`, `remove`, `status`"
            )
    except Exception as e:
        logger.error(f"Error in notif command: {e}", exc_info=True)
        await ctx.send(f"⚠️ An error occurred: `{type(e).__name__}: {e}`")


# ─── Action handlers ──────────────────────────────────────────────────────────


async def handle_notif_add(
    ctx: commands.Context, username: str, language: Optional[str]
) -> None:
    """Handle adding notification subscriptions using the database editor directly."""
    if not language:
        await ctx.send("⚠️ Language codes are required for the `add` action.")
        return

    logger.info(f"Notification add request for u/{username} from {ctx.author.name}")

    language_matches = parse_language_list(language)

    if not language_matches:
        await ctx.send(
            f"⚠️ No valid language codes found in: `{language}`\n"
            f"Please use ISO 639 codes (e.g., `es`, `fr`, `zh`) or language names."
        )
        return

    try:
        notifier_language_list_editor(language_matches, username, "insert")

        match_codes_print = ", ".join(
            lang.name for lang in language_matches if lang.name is not None
        )

        await ctx.send(
            f"✅ **Added notifications for u/{username}**\n"
            f"Languages: `{match_codes_print}`"
        )
    except Exception as e:
        logger.error(f"Error adding notifications: {e}", exc_info=True)
        await ctx.send(f"⚠️ Failed to add notifications: `{e}`")


async def handle_notif_remove(ctx: commands.Context, username: str) -> None:
    """Handle removing ALL notification subscriptions using the database editor directly."""
    logger.info(f"Notification remove request for u/{username} from {ctx.author.name}")

    subscribed_codes = notifier_language_list_retriever(username)

    if not subscribed_codes:
        await ctx.send(f"🈚 u/{username} has no active subscriptions.")
        return

    try:
        notifier_language_list_editor([], username, "purge")

        subscribed_codes_list = [x.preferred_code for x in subscribed_codes]
        final_match_codes_print = ", ".join(subscribed_codes_list)

        await ctx.send(
            f"✅ **Removed all notifications for u/{username}**\n"
            f"Previous subscriptions: `{final_match_codes_print}`"
        )
    except Exception as e:
        logger.error(f"Error removing notifications: {e}", exc_info=True)
        await ctx.send(f"⚠️ Failed to remove notifications: `{e}`")


async def handle_notif_status(ctx: commands.Context, username: str) -> None:
    """Handle status request for user subscriptions."""
    logger.info(f"Notification status request for u/{username} from {ctx.author.name}")

    final_match_entries = notifier_language_list_retriever(username)
    internal_entries = notifier_language_list_retriever(username, internal=True)

    if not final_match_entries and not internal_entries:
        await ctx.send(f"🈚 **u/{username}** has no active notification subscriptions.")
        return

    subscriptions_list = []

    if final_match_entries:
        final_match_names_set = set()
        for entry in final_match_entries:
            script_label = (
                " (Script)"
                if entry.script_code is not None or "unknown-" in str(entry)
                else ""
            )
            final_match_names_set.add(
                f"{entry.name} (`{entry.preferred_code}`){script_label}"
            )
        subscriptions_list.extend(
            sorted(list(final_match_names_set), key=lambda x: x.lower())
        )

    if internal_entries:
        internal_names = [
            f"{post_type.capitalize()} (Internal)" for post_type in internal_entries
        ]
        subscriptions_list.extend(internal_names)

    subscriptions_list.sort(key=lambda x: x.lower())

    subscriptions_formatted = "\n• ".join(subscriptions_list)
    status_message = (
        f"📬 **Notification subscriptions for u/{username}:**\n\n"
        f"• {subscriptions_formatted}"
    )

    # Append notification statistics if available
    user_commands_statistics_data = user_statistics_loader(username)
    if user_commands_statistics_data:
        lines = user_commands_statistics_data.strip().split("\n")
        notification_lines = [
            line
            for line in lines
            if "Notifications" in line
            or line.startswith("|")
            and line.count("|") >= 2 > lines.index(line)
        ]

        if (
            len(notification_lines) > 2
        ):  # Has header + separator + at least one data row
            filtered_stats = "\n".join(notification_lines)
            formatted_table = format_markdown_table_with_padding(filtered_stats)
            status_message += (
                f"\n\n**Notification Usage Statistics:**\n{formatted_table}"
            )

    await ctx.send(status_message)
