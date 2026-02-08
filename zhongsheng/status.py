#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""Status command"""

import aiohttp
import traceback

from config import logger
from connection import get_random_useragent
from database import get_recent_event_log_lines

from . import command


@command(
    name="status",
    help_text="Shows a random Office quote and the last 5 events from the log for Ziwen",
    roles=["Moderator", "Helper"],
)
async def status(ctx):
    # First, get the Office quote
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                "https://officeapi.akashrajpurohit.com/quote/random",
                headers={
                    **get_random_useragent(),
                    "Accept-Encoding": "gzip, deflate",
                },  # Explicitly avoid br
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    character = data.get("character", "Unknown")
                    quote = data.get("quote", "No quote available")
                    office_response = f'**{character}**: "{quote}"\n\n'
                else:
                    office_response = f"⚠️ Failed to fetch quote. API returned status code {resp.status}\n\n"
    except Exception as err:
        tb = traceback.format_exc()
        logger.error(f"[WJ] Encountered {err} when fetching quote.")
        office_response = f"⚠️ An error occurred fetching quote:\n```\n{tb}\n```\n\n"

    # Now get the events log status
    try:
        log_content, time_ago = get_recent_event_log_lines(num_lines=5, tag="ZW")
        status_response = (
            f"**Last 5 Events:**\n{log_content}\n**Last Ziwen Event:** {time_ago}"
        )
    except FileNotFoundError:
        status_response = "⚠️ Events log file not found."
    except ValueError:
        status_response = "⚠️ Events log is empty."
    except Exception as e:
        status_response = f"⚠️ An error occurred reading logs: {str(e)}"

    # Send combined response
    await ctx.send(office_response + status_response)
