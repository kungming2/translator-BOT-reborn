#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""Error log display command"""

from io import BytesIO

import discord
import yaml

from config import Paths

from . import command


@command(
    name="error",
    help_text="Displays the 3 most recent error log entries",
    roles=["Moderator"],
)
async def error_logs(ctx):
    """Returns the last few error log entries for analysis."""
    try:
        # Read the YAML file
        with open(Paths.LOGS["ERROR"], "r", encoding="utf-8") as f:
            error_data = yaml.safe_load(f)

        # Handle empty or None error log
        if not error_data:
            await ctx.send("✅ No error logs found.")
            return

        # Get the last 3 entries
        recent_errors = error_data[-3:] if len(error_data) >= 3 else error_data

        # Format the output
        response = "**Most Recent Error Logs:**\n\n"

        for i, entry in enumerate(reversed(recent_errors), 1):
            response += f"**Error #{i}:**\n```\n"
            response += f"**Status:** {entry.get('resolved', 'N/A')}\n"
            response += f"Timestamp: {entry.get('timestamp', 'N/A')}\n"
            response += f"Bot Version: {entry.get('bot_version', 'N/A')}\n"

            if "context" in entry:
                response += "\nContext:\n"
                for key, value in entry["context"].items():
                    response += f"  {key}: {value}\n"

            response += f"\nError:\n{entry.get('error', 'N/A')}\n"
            response += "```\n\n"

        # Discord has a 2000-character limit, so split if needed
        if len(response) > 2000:
            # Send as a text file instead
            file_content = response.replace("**", "").replace("```", "")
            file = discord.File(
                BytesIO(file_content.encode("utf-8")), filename="recent_errors.txt"
            )
            await ctx.send("Error logs are too long, sending as file:", file=file)
        else:
            await ctx.send(response)

    except Exception as e:
        await ctx.send(f"An error occurred while reading error logs: {str(e)}")
