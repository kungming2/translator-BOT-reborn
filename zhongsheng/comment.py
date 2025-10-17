#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""Comment search command"""

import logging

from connection import REDDIT_HELPER
from models.instruo import Instruo

from . import command

# No need to worry about the PRAW async warning
logging.getLogger("praw").setLevel(logging.CRITICAL)


def _format_commands(commands):
    """Format commands section for the response."""
    if not commands:
        return ""

    response = "\n**Commands:**\n"
    for cmd in commands:
        data_str = f": {cmd.data}" if cmd.data else ""
        response += f"- {cmd.name}{data_str}\n"
    return response


@command(
    name="comment",
    help_text="Searches for a Reddit comment ID and returns the Instruo data. "
    "Use --text flag to parse raw text instead.",
    roles=["Moderator"],
)
async def comment_search(ctx, *, comment_input: str):
    """Discord wrapper for the Instruo parsing."""
    # Check if --text flag is present
    if comment_input.strip().endswith("--text"):
        # Remove the --text flag and get the text content
        text_content = comment_input.rsplit("--text", 1)[0].strip()

        if not text_content:
            await ctx.send(
                "No text provided. Please provide text before the --text flag."
            )
            return

        try:
            # Create Instruo object from the text
            instruo = Instruo.from_text(text_content)

            # Format the response (testing mode shows only commands found)
            response = f"**Commands Found:** {len(instruo.commands)}\n"
            response += _format_commands(instruo.commands)

            await ctx.send(response)

        except Exception as e:
            await ctx.send(f"Error processing text: {str(e)}")
            return
    else:
        # Original behavior: extract comment ID from various formats
        if "reddit.com/" in comment_input:
            # Extract from full Reddit URL
            # Format: https://www.reddit.com/r/subreddit/comments/POST_ID/_/COMMENT_ID/
            parts = comment_input.split("/")
            # Find the index of the underscore and get the part after it
            try:
                underscore_idx = parts.index("_")
                comment_id = parts[underscore_idx + 1]
            except (ValueError, IndexError):
                # Fallback: get the last non-empty part
                comment_id = [p for p in parts if p][-1]
        elif "redd.it/" in comment_input:
            # Extract from short URL
            # Format: redd.it/COMMENT_ID
            comment_id = comment_input.rstrip("/").split("/")[-1]
        else:
            # Assume it's already a comment ID
            comment_id = comment_input

        if (
            not comment_id or len(comment_id) < 6
        ):  # Reddit IDs are typically 6+ characters
            await ctx.send("Could not extract comment ID from the provided input.")
            return

        try:
            # Fetch the comment using the existing REDDIT_HELPER instance
            comment = REDDIT_HELPER.comment(comment_id)

            # Create Instruo object from the comment
            instruo = Instruo.from_comment(comment)

            # Format the response
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
            await ctx.send(f"Error retrieving comment: {str(e)}")
            return
