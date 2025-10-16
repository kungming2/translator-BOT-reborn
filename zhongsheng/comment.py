#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""Comment search command"""
import logging

from connection import REDDIT_HELPER
from models.instruo import Instruo

from . import command

# No need to worry about the PRAW async warning
logging.getLogger("praw").setLevel(logging.CRITICAL)


@command(name='comment',
         help_text='Searches for a Reddit comment ID and returns the Instruo data',
         roles=['Moderator'])
async def comment_search(ctx, comment_input: str):
    # Extract comment ID from various formats

    if 'reddit.com/' in comment_input:
        # Extract from full Reddit URL
        # Format: https://www.reddit.com/r/subreddit/comments/POST_ID/_/COMMENT_ID/
        parts = comment_input.split('/')
        # Comment ID is typically the last meaningful part of the URL
        for i, part in enumerate(parts):
            if part and part not in ['https:', '', 'www.reddit.com', 'r', 'comments', '_']:
                pass
        # Get the last non-empty part
        comment_id = [p for p in parts if p][-1]
    elif 'redd.it/' in comment_input:
        # Extract from short URL
        # Format: redd.it/COMMENT_ID
        comment_id = comment_input.rstrip('/').split('/')[-1]
    else:
        # Assume it's already a comment ID
        comment_id = comment_input

    if not comment_id or len(comment_id) < 6:  # Reddit IDs are typically 6+ characters
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
        response += (f"**Author (Comment):** [u/{instruo.author_comment}]"
                     f"(https://www.reddit.com/user/{instruo.author_comment})\n")
        response += (f"**Author (Post):** [u/{instruo.author_post}]"
                     f"(https://www.reddit.com/user/{instruo.author_post})\n")
        response += f"**Comment Posted:** <t:{instruo.created_utc}:F>\n"
        response += f"**Commands Found:** {len(instruo.commands)}\n"

        if instruo.body:
            body_preview = instruo.body[:200] + "..." if len(instruo.body) > 200 else instruo.body
            response += f"**Body Preview:** {body_preview}\n"

        if instruo.commands:
            response += "\n**Commands:**\n"
            for cmd in instruo.commands:
                data_str = f": {cmd.data}" if cmd.data else ""
                response += f"- {cmd.name}{data_str}\n"

        await ctx.send(response)

    except Exception as e:
        await ctx.send(f"Error retrieving comment: {str(e)}")
        return
