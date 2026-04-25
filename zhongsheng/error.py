#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""Error log display command"""

from io import BytesIO

import discord
import yaml
from discord.ext.commands import Context

from config import Paths
from error import display_event_errors

from . import command

# ─── Command handler ──────────────────────────────────────────────────────────


@command(
    name="error",
    help_text="Displays the 3 most recent error log entries.",
    roles=["Moderator"],
)
async def error_logs(ctx: Context) -> None:
    """Returns the last few error log entries for analysis."""
    try:
        with open(Paths.LOGS["ERROR"], encoding="utf-8") as f:
            error_data = yaml.safe_load(f)

        if not error_data:
            await ctx.send("✅ No error logs found.")
            return

        recent_errors = error_data[-3:] if len(error_data) >= 3 else error_data

        response = "**Most Recent Error Logs:**\n\n"

        for i, entry in enumerate(reversed(recent_errors), 1):
            response += f"**Error #{i}:**\n```\n"
            response += f"**Resolved Status:** {entry.get('resolved', 'N/A')}\n"
            response += f"Timestamp: {entry.get('timestamp', 'N/A')}\n"
            response += f"Bot Version: {entry.get('bot_version', 'N/A')}\n"

            if "context" in entry:
                response += "\nContext:\n"
                for key, value in entry["context"].items():
                    response += f"  {key}: {value}\n"

            response += f"\nError:\n{entry.get('error', 'N/A')}\n"
            response += "```\n\n"

        # Append event log errors from the last 3 days
        event_errors = display_event_errors(days=3)

        if event_errors:
            response += "**Event Log Errors (Last 3 Days):**\n```\n"
            for error_line in event_errors:
                response += f"{error_line}\n"
            response += "```\n"
        else:
            response += "✅ No event log errors in the last 3 days.\n"

        # Send as a text file if the response exceeds Discord's character limit
        if len(response) > 2000:
            file_content = response.replace("**", "").replace("```", "")
            file = discord.File(
                BytesIO(file_content.encode("utf-8")), filename="recent_errors.txt"
            )
            await ctx.send("🗂️ Error logs are too long, sending as file:", file=file)
        else:
            await ctx.send(response)

    except Exception as e:
        await ctx.send(f"⚠️ An error occurred while reading error logs: {str(e)}")
