#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""Post search command. Used for database inquiry."""

import logging

from discord.ext import commands

from config import logger as _base_logger
from monitoring.points import points_post_retriever

from . import command, search_logs, send_long_message

logger = logging.LoggerAdapter(_base_logger, {"tag": "ZS:POST"})

# ─── Command handler ──────────────────────────────────────────────────────────


@command(
    name="post",
    help_text="Searches for a Reddit post ID in log files and returns matching lines.",
    roles=["Moderator"],
)
async def post_search(ctx: commands.Context, post_input: str) -> None:
    """Searches through the database and log files for a matching Reddit
    post ID for debugging or analysis."""

    # Extract post ID from various URL formats or bare ID.
    post_id = None

    if "reddit.com/" in post_input:
        # Format: https://www.reddit.com/r/subreddit/comments/POST_ID/title/
        parts = post_input.split("/")
        if "comments" in parts:
            comment_index = parts.index("comments")
            if comment_index + 1 < len(parts):
                post_id = parts[comment_index + 1]
    elif "redd.it/" in post_input:
        # Format: redd.it/POST_ID
        post_id = post_input.rstrip("/").split("/")[-1]
    else:
        post_id = post_input

    if not post_id:
        await ctx.send("⚠️ Could not extract post ID from the provided input.")
        return

    await search_logs(ctx, post_id, "post")

    # Append points data if available.
    try:
        points_data = points_post_retriever(post_id)

        if points_data is not None:
            response = f"```\n=== POINTS DATA ({len(points_data)} records) ===\n"
            response += "Comment ID | Username | Points\n"
            response += "-----------|----------|-------\n"

            total_points = 0
            for comment_id, username, points in points_data:
                total_points += points
                response += f"{comment_id} | {username} | {points}\n"

            response += "-----------|----------|-------\n"
            response += f"Total: {len(points_data)} award(s) | {total_points} points\n"
            response += "```"

            await send_long_message(ctx, response)
    except Exception as e:
        logger.error(
            f"Error retrieving points data for post `{post_id}`: {e}", exc_info=True
        )
        await ctx.send("Error retrieving points data.")
