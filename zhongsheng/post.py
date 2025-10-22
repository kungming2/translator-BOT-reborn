#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""Post search command. Used for database inquiry."""

from database import search_logs

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

    await search_logs(ctx, post_id, "post")
