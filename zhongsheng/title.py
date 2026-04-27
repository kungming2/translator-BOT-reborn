#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""Title processing command"""

import asyncio
import logging
from typing import Any

from discord.ext import commands

from config import logger as _base_logger
from title.title_ai import title_ai_parser
from title.title_handling import process_title

from . import command, send_long_message

logger = logging.LoggerAdapter(_base_logger, {"tag": "ZS:TITLE"})

# ─── Command handler ──────────────────────────────────────────────────────────


@command(
    name="title",
    help_text="Processes a title and returns detailed information. Use --ai flag for AI parsing.",
    roles=["Moderator"],
)
async def title_search(ctx: commands.Context, *, title: str) -> None:
    """Discord wrapper for Titolo creation."""
    use_ai = title.endswith((" --ai", " –ai", " -ai"))

    if use_ai:
        title = title[:-5].strip()  # Remove ' --ai' from the end

    try:
        result: Any
        if use_ai:
            async with ctx.typing():
                loop = asyncio.get_running_loop()
                result = await loop.run_in_executor(None, title_ai_parser, title, None)
        else:
            result = process_title(title)

        # Check if result is an error tuple
        if isinstance(result, tuple) and len(result) == 2 and result[0] == "error":
            await send_long_message(ctx, f"**AI Parsing Error:** {result[1]}")
            return

        if result:
            formatted_output = "**Title Processing Results:**\n\n"

            if isinstance(result, dict):
                for key, value in result.items():
                    formatted_output += f"**{key}:** {value}\n"
            else:
                for key, value in vars(result).items():
                    formatted_output += f"**{key}:** {value}\n"
        else:
            formatted_output = f"🈚 No valid title processing results for `{title}`"

        await send_long_message(ctx, formatted_output)

    except Exception as e:
        logger.error(f"Error processing title `{title}`: {e}", exc_info=True)
        await ctx.send("⚠️ An error occurred while processing the title.")
