#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""Status command"""

from datetime import datetime, timezone
from pathlib import Path

import aiohttp

from config import Paths
from connection import get_random_useragent

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
                headers=get_random_useragent(),
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    character = data.get("character", "Unknown")
                    quote = data.get("quote", "No quote available")
                    office_response = f'**{character}**: "{quote}"\n\n'
                else:
                    office_response = f"⚠️ Failed to fetch quote. API returned status code {resp.status}\n\n"
    except Exception as e:
        office_response = f"⚠️ An error occurred fetching quote: {str(e)}\n\n"

    # Now get the events log status
    try:
        events_path = Path(Paths.LOGS["EVENTS"])

        # Check if the file exists
        if not events_path.exists():
            status_response = "⚠️ Events log file not found."
        else:
            # Read the last 5 lines from the file
            with open(events_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
                last_five = lines[-5:] if len(lines) >= 5 else lines

            if not last_five:
                status_response = "⚠️ Events log is empty."
            else:
                # Find the last line with [ZW] in it
                zw_lines = [line for line in last_five if "[ZW]" in line]

                if not zw_lines:
                    time_ago = "no ZW events found"
                else:
                    last_zw_line = zw_lines[-1].strip()
                    try:
                        # Extract timestamp from format: INFO: 2026-01-07T19:45:59Z - ...
                        timestamp_str = last_zw_line.split(" - ")[0].split(": ")[1]
                        last_event_time = datetime.fromisoformat(
                            timestamp_str.replace("Z", "+00:00")
                        )
                        current_time = datetime.now(timezone.utc)

                        # Calculate time delta
                        delta = current_time - last_event_time
                        delta_seconds = delta.total_seconds()

                        # Format the time difference
                        if delta_seconds < 3600:  # Less than 1 hour
                            minutes = int(delta_seconds / 60)
                            time_ago = (
                                f"{minutes} minute{'s' if minutes != 1 else ''} ago"
                            )
                        else:  # 1 hour or more
                            hours = delta_seconds / 3600
                            if hours < 48:  # Less than 2 days, show in hours
                                hours_int = int(hours)
                                time_ago = f"{hours_int} hour{'s' if hours_int != 1 else ''} ago"
                            else:  # 2 days or more
                                days = int(hours / 24)
                                time_ago = f"{days} day{'s' if days != 1 else ''} ago"
                    except (IndexError, ValueError):
                        time_ago = "unknown"

                # Format the response
                log_content = "```\n" + "".join(last_five) + "```"
                status_response = f"**Last 5 Events:**\n{log_content}\n**Last Ziwen Event:** {time_ago}"

    except Exception as e:
        status_response = f"⚠️ An error occurred reading logs: {str(e)}"

    # Send combined response
    await ctx.send(office_response + status_response)
