#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""Comment search command"""

import logging

from discord.ext import commands

from models.instruo import Instruo
from reddit.connection import REDDIT_HELPER

from . import command

# No need to worry about the PRAW async warning
logging.getLogger("praw").setLevel(logging.CRITICAL)


# ─── Internal helpers ─────────────────────────────────────────────────────────


def _format_commands(list_commands: list) -> str:
    """Format commands section for the response."""
    if not list_commands:
        return ""

    response = "\n**Commands:**\n"
    for cmd in list_commands:
        data_str = f": {cmd.data}" if cmd.data else ""
        response += f"- {cmd.name}{data_str}\n"
    return response


# ─── Command handler ──────────────────────────────────────────────────────────


@command(
    name="comment",
    help_text="Searches for a Reddit comment ID and returns the Instruo data. "
    "Use --text flag to parse raw text.",
    roles=["Moderator"],
)
async def comment_search(ctx: commands.Context, *, comment_input: str) -> None:
    """Discord wrapper for the Instruo parsing."""
    # Check if --text flag is present
    if comment_input.strip().endswith("--text"):
        # Remove the --text flag and get the text content
        text_content = comment_input.rsplit("--text", 1)[0].strip()

        if not text_content:
            await ctx.send(
                "⚠️ No text provided. Please provide text before the --text flag."
            )
            return

        try:
            instruo = Instruo.from_text(text_content)

            response = f"**Commands Found:** {len(instruo.commands)}\n"
            response += _format_commands(instruo.commands)

            await ctx.send(response)

        except Exception as e:
            await ctx.send(f"⚠️ Error processing text: {str(e)}")
            return
    else:
        # Extract comment ID from various URL formats or bare ID
        if "reddit.com/" in comment_input:
            # Format: https://www.reddit.com/r/subreddit/comments/POST_ID/_/COMMENT_ID/
            parts = comment_input.split("/")
            try:
                underscore_idx = parts.index("_")
                comment_id = parts[underscore_idx + 1]
            except (ValueError, IndexError):
                comment_id = [p for p in parts if p][-1]
        elif "redd.it/" in comment_input:
            # Format: redd.it/COMMENT_ID
            comment_id = comment_input.rstrip("/").split("/")[-1]
        else:
            comment_id = comment_input

        if not comment_id or len(comment_id) < 6:  # Reddit IDs are typically 6+ chars
            await ctx.send("⚠️ Could not extract comment ID from the provided input.")
            return

        try:
            comment = REDDIT_HELPER.comment(comment_id)
            instruo = Instruo.from_comment(comment)

            response = f"**Comment ID:** {instruo.id_comment}\n"
            response += f"**Post ID:** {instruo.id_post}\n"
            response += (
                f"**Author (Comment):** [u/{instruo.author_comment}]"
                f"(https://www.reddit.com/user/{instruo.author_comment})\n"
            )
            response += (
                f"**Author (Post):** [u/{instruo.author_post}]"
                f"(https://www.reddit.com/user/{instruo.author_post})\n"
            )
            response += f"**Comment Posted:** <t:{instruo.created_utc}:F>\n"
            response += f"**Commands Found:** {len(instruo.commands)}\n"

            if instruo.body:
                body_preview = (
                    instruo.body[:200] + "..."
                    if len(instruo.body) > 200
                    else instruo.body
                )
                response += f"**Body Preview:** {body_preview}\n"

            response += _format_commands(instruo.commands)

            await ctx.send(response)

        except Exception as e:
            await ctx.send(f"⚠️ Error retrieving comment: {str(e)}")
            return
