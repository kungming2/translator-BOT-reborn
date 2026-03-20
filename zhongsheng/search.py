#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""Search command wrapper, searches DDG or Reddit for a term."""

from discord.ext import commands

from integrations.search_handling import build_search_results, fetch_search_reddit_posts

from . import command, send_long_message


@command(
    name="search",
    help_text="Searches for Reddit translation posts related to a term.",
    roles=["Moderator", "Helper"],
)
async def search_posts(ctx: commands.Context, *, search_term: str) -> None:
    """Discord wrapper for the search command."""
    try:
        await ctx.send(f"🔍 **Searching for:** `{search_term}` …")

        # Fetch Reddit post IDs using the chosen search engine
        post_ids = fetch_search_reddit_posts(search_term)

        if not post_ids:
            await ctx.send(
                "🈚 No results found. Try another term or adjust your query."
            )
            return

        # Build and format the search results
        formatted_results = build_search_results(post_ids, search_term)

        if not formatted_results.strip():
            await ctx.send("🈚 No relevant comments found in matching posts.")
            return

        # Use the helper to handle Discord message length limits
        await send_long_message(ctx, formatted_results)

    except Exception as e:
        await ctx.send(f"⚠️ An error occurred during search: `{type(e).__name__}: {e}`")
