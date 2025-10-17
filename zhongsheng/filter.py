#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""Post filter command"""

import asyncio

from title_handling import main_posts_filter

from . import command

# Filter reason descriptions
FILTER_REASONS = {
    "1": "Missing required keywords",
    "1A": '"to Language" phrasing not early in the title',
    "1B": "Too short and generic (no valid language detected)",
    "2": "'>' present but poorly placed or not formatted",
}


@command(
    name="filter",
    help_text="Validates a post title against community formatting guidelines",
    roles=["Moderator", "Helper"],
)
async def filter_post(ctx, *, title: str):
    """
    Filter a post title based on r/translator formatting guidelines.
    Tests whether it would pass or fail.

    Usage: /filter <title>
    Example: /filter [English > French] Help translating this phrase
    """
    try:
        # Validate that a title was provided
        if not title or not title.strip():
            await ctx.send("Error: Please provide a post title to filter.")
            return

        # Run the blocking function in a thread pool
        (
            post_okay,
            filtered_title,
            filter_reason,
        ) = await asyncio.get_event_loop().run_in_executor(
            None,
            main_posts_filter,
            title,
        )

        # Format and send the response
        if post_okay:
            response = "✅ **Post Title Valid**\n"
            if filtered_title != title:
                response += f"**Original:** {title}\n**Normalized:** {filtered_title}"
            else:
                response += f"**Title:** {title}"
        else:
            reason_code = filter_reason
            reason_desc = FILTER_REASONS.get(reason_code, "Unknown reason")
            response = f"❌ **Post Title Rejected**\n**Rule #{reason_code}:** {reason_desc}\n**Title:** {title}"

        await ctx.send(response)

    except Exception as e:
        await ctx.send(f"An error occurred while filtering the post: {str(e)}")
