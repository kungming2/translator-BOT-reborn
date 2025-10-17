#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""Search command wrapper."""

from search_handling import build_search_results, fetch_search_reddit_posts

from . import command


@command(
    name="search",
    help_text="Searches for Reddit translation posts related to a term.",
    roles=["Moderator", "Helper"],
)
async def search_posts(ctx, *, search_term: str):
    try:
        await ctx.send(f"🔍 **Searching for:** `{search_term}` …")

        # Fetch Reddit post IDs using the chosen search engine
        post_ids = fetch_search_reddit_posts(search_term)

        if not post_ids:
            await ctx.send("No results found. Try another term or adjust your query.")
            return

        # Build and format the search results
        formatted_results = build_search_results(post_ids, search_term)

        if not formatted_results.strip():
            await ctx.send("No relevant comments found in matching posts.")
            return

        # Discord message length limit is 2000 characters, so chunk if necessary
        for chunk in _split_message(formatted_results):
            await ctx.send(chunk)

    except Exception as e:
        await ctx.send(f"⚠️ An error occurred during search: `{type(e).__name__}: {e}`")


def _split_message(text, limit=2000):
    """Splits long messages into chunks to stay within Discord's 2000-char limit."""
    lines = text.split("\n")
    chunks, current_chunk = [], ""

    for line in lines:
        if len(current_chunk) + len(line) + 1 > limit:
            chunks.append(current_chunk)
            current_chunk = line
        else:
            current_chunk += "\n" + line

    if current_chunk:
        chunks.append(current_chunk)

    return chunks
