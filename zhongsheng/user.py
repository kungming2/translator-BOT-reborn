#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""User search command"""

from database import search_logs
from usage_statistics import user_statistics_loader
from utility import format_markdown_table_for_discord

from . import command


@command(
    name="user",
    help_text="Searches for a username in log files and returns matching lines",
    roles=["Moderator"],
)
async def user_search(ctx, *, user_input: str):
    """Searches through the database and log files for a matching user
    ID for debugging or analysis."""

    # Extract username from URL if provided, otherwise use as-is
    if "reddit.com/user/" in user_input or "reddit.com/u/" in user_input:
        # Extract username from URL
        username = user_input.rstrip("/").split("/")[-1]
    else:
        # Use the input directly as username
        username = user_input

    # Search logs first
    await ctx.send(f"🔎 Searching logs and database for `{username}`...")
    await search_logs(ctx, username, "user")

    # Get and append user statistics
    stats = user_statistics_loader(username)
    if stats:
        stats_table = format_markdown_table_for_discord(stats)
        await ctx.send(f"**User Statistics for {username}:**\n{stats_table}")
    else:
        await ctx.send(f"🈚 No results for {username}.")
