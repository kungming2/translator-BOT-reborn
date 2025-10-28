#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""Notification management command for moderators."""

import logging
from typing import Optional

from notifications import notifier_language_list_retriever
from messaging import handle_add, handle_remove, user_statistics_loader

from . import command

logger = logging.getLogger("ziwen")


class MockMessage:
    """Mock message object that mimics Reddit's message structure."""

    def __init__(self, body, author):
        self.body = body
        self.author = author


@command(
    name="notif",
    help_text="Manage user notification subscriptions for r/translator.",
    roles=["Moderator"],
)
async def notif(ctx, action: str, username: str, language: Optional[str] = None):
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
        logger.error(f"[ZW] Discord: Error in notif command: {e}", exc_info=True)
        await ctx.send(f"⚠️ An error occurred: `{type(e).__name__}: {e}`")


async def handle_notif_add(ctx, username: str, language: Optional[str]):
    """Handle adding notification subscriptions using existing Reddit handler."""
    if not language:
        await ctx.send("⚠️ Language codes are required for the `add` action.")
        return

    logger.info(
        f"[ZW] Discord: Notification add request for u/{username} "
        f"from {ctx.author.name}"
    )

    # Format the message body to match what handle_add expects
    mock_body = f"USERNAME: {username}\nLANGUAGES: {language}"
    mock_message = MockMessage(mock_body, ctx.author.name)

    # Call the existing handle_add function
    # This will handle parsing, validation, and database operations
    try:
        handle_add(mock_message, ctx.author.name)
        await ctx.send(
            f"✅ **Added notifications for u/{username}**\n"
            f"Languages: `{language}`"
        )
    except Exception as e:
        await ctx.send(f"⚠️ Failed to add notifications: `{e}`")


async def handle_notif_remove(ctx, username: str):
    """Handle removing ALL notification subscriptions using existing Reddit handler."""
    logger.info(
        f"[ZW] Discord: Notification remove request for u/{username} "
        f"from {ctx.author.name}"
    )

    # Get subscriptions before removal for confirmation message
    subscribed_codes = notifier_language_list_retriever(username)

    if not subscribed_codes:
        await ctx.send(f"ℹ️ u/{username} has no active subscriptions.")
        return

    # Format body to match what handle_remove expects
    mock_body = f"USERNAME: {username}"
    mock_message = MockMessage(mock_body, ctx.author.name)

    # Call the existing handle_remove function (purges all subscriptions)
    try:
        handle_remove(mock_message, ctx.author.name)

        # Format response with removed subscriptions
        subscribed_codes_list = [x.preferred_code for x in subscribed_codes]
        final_match_codes_print = ", ".join(subscribed_codes_list)

        await ctx.send(
            f"✅ **Removed all notifications for u/{username}**\n"
            f"Previous subscriptions: `{final_match_codes_print}`"
        )
    except Exception as e:
        await ctx.send(f"⚠️ Failed to remove notifications: `{e}`")


async def handle_notif_status(ctx, username: str):
    """Handle status request for user subscriptions."""
    logger.info(
        f"[ZW] Discord: Notification status request for u/{username} "
        f"from {ctx.author.name}"
    )

    # Get language subscriptions
    final_match_entries = notifier_language_list_retriever(username)

    # Get internal subscriptions (meta, community)
    internal_entries = notifier_language_list_retriever(username, internal=True)

    if not final_match_entries and not internal_entries:
        await ctx.send(
            f"ℹ️ **u/{username}** has no active notification subscriptions."
        )
        return

    # Build subscription list
    subscriptions_list = []

    # Process language subscriptions
    if final_match_entries:
        final_match_names_set = {
            f"{entry.name}{' (Script)' if 'unknown-' in entry else ''}"
            for entry in final_match_entries
        }
        subscriptions_list.extend(
            sorted(list(final_match_names_set), key=lambda x: x.lower())
        )

    # Process internal subscriptions
    if internal_entries:
        internal_names = [
            f"{post_type.capitalize()} (Internal)" for post_type in internal_entries
        ]
        subscriptions_list.extend(internal_names)

    # Sort combined list
    subscriptions_list.sort(key=lambda x: x.lower())

    # Format output
    subscriptions_formatted = "\n• ".join(subscriptions_list)
    status_message = (
        f"📬 **Notification subscriptions for u/{username}:**\n\n"
        f"• {subscriptions_formatted}"
    )

    # Add user statistics if available
    user_commands_statistics_data = user_statistics_loader(username)
    if user_commands_statistics_data:
        status_message += f"\n\n**User Commands Statistics:**\n{user_commands_statistics_data}"

    await ctx.send(status_message)
