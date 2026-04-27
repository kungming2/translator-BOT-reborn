#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""User search command"""

from discord.ext import commands

from monitoring.usage_statistics import user_statistics_loader
from utility import format_markdown_table_with_padding

from . import command, search_logs, send_long_message

# ─── Command handler ──────────────────────────────────────────────────────────


@command(
    name="user",
    help_text="Searches for a username in log files and returns matching lines.",
    roles=["Moderator"],
)
async def user_search(ctx: commands.Context, *, user_input: str) -> None:
    """Searches through the database and log files for a matching user
    ID for debugging or analysis."""

    # Extract username from URL if provided, otherwise use as-is.
    if "reddit.com/user/" in user_input or "reddit.com/u/" in user_input:
        username = user_input.rstrip("/").split("/")[-1]
    else:
        username = user_input

    await ctx.send(f"🔎 Searching logs and database for `{username}`...")
    found_results = await search_logs(ctx, username, "user")

    stats = user_statistics_loader(username)
    if stats:
        stats_table = format_markdown_table_with_padding(stats)
        await send_long_message(
            ctx, f"**User Statistics for {username}:**\n{stats_table}"
        )
    elif not found_results:
        await ctx.send(f"🈚 No results for {username}.")
