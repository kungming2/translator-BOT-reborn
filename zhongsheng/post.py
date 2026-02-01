#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""Post search command. Used for database inquiry."""

import traceback

from database import search_logs
from points import points_post_retriever

from . import command


@command(
    name="post",
    help_text="Searches for a Reddit post ID in log files and returns matching lines",
    roles=["Moderator"],
)
async def post_search(ctx, post_input: str):
    """Searches through the database and log files for a matching Reddit
    post ID for debugging or analysis."""

    # Extract post ID from various formats
    post_id = None

    if "reddit.com/" in post_input:
        # Extract from full Reddit URL
        # Format: https://www.reddit.com/r/subreddit/comments/POST_ID/title/
        parts = post_input.split("/")
        if "comments" in parts:
            comment_index = parts.index("comments")
            if comment_index + 1 < len(parts):
                post_id = parts[comment_index + 1]
    elif "redd.it/" in post_input:
        # Extract from short URL
        # Format: redd.it/POST_ID
        post_id = post_input.rstrip("/").split("/")[-1]
    else:
        # Assume it's already a post ID
        post_id = post_input

    if not post_id:
        await ctx.send("⚠️ Could not extract post ID from the provided input.")
        return

    # First run the standard search_logs function
    await search_logs(ctx, post_id, "post")

    # Then query and display points data
    try:
        points_data = points_post_retriever(post_id)

        if points_data is not None:
            # Build the points data table
            response = f"```\n=== POINTS DATA ({len(points_data)} records) ===\n"
            response += "Comment ID | Username | Points\n"
            response += "-----------|----------|-------\n"

            total_points = 0
            for comment_id, username, points in points_data:
                total_points += points
                response += f"{comment_id} | {username} | {points}\n"

            # Add summary line
            response += "-----------|----------|-------\n"
            response += f"Total: {len(points_data)} award(s) | {total_points} points\n"
            response += "```"

            await ctx.send(response)
    except Exception as e:
        await ctx.send(f"Error retrieving points data: {str(e)}")
        traceback.print_exc()
