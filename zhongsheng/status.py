#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
Status command that helps check on the state of the bot.
...

Logger tag: [ZS:STATUS]
"""

import logging

import aiohttp
from discord.ext import commands

from config import logger as _base_logger
from database import get_recent_event_log_lines
from reddit.connection import get_random_useragent

from . import command, send_long_message

logger = logging.LoggerAdapter(_base_logger, {"tag": "ZS:STATUS"})


# ─── Command handler ──────────────────────────────────────────────────────────


@command(
    name="status",
    help_text="Shows internet connectivity and the last 5 events from the log for Ziwen.",
    roles=["Moderator", "Helper"],
)
async def status(ctx: commands.Context) -> None:
    """Checks internet connectivity and shows when the last action in the events log was taken."""
    # Check internet connectivity
    try:
        async with (
            aiohttp.ClientSession() as session,
            session.get(
                "https://httpbin.org/get",
                headers=get_random_useragent(),
            ) as resp,
        ):
            if resp.status == 200:
                connectivity_response = "✅ Internet connectivity: OK\n\n"
            else:
                connectivity_response = f"⚠️ Unexpected status code {resp.status} from connectivity check.\n\n"
    except Exception as err:
        logger.error(f"Encountered {err} when checking connectivity.", exc_info=True)
        connectivity_response = "⚠️ Internet connectivity check failed.\n\n"

    # Fetch recent events log entries
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

    await send_long_message(ctx, connectivity_response + status_response)
