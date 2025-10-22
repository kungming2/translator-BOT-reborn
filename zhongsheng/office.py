#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""Office quote command"""

import aiohttp

from connection import get_random_useragent

from . import command


@command(
    name="office",
    help_text="Responds with a random quote from The Office",
    roles=["Moderator", "Helper"],
)
async def office_quote(ctx):
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
                    response = f'**{character}**: "{quote}"'
                    await ctx.send(response)
                else:
                    await ctx.send(
                        f"⚠️ Failed to fetch quote. API returned status code {resp.status}"
                    )
    except Exception as e:
        await ctx.send(f"⚠️ An error occurred: {str(e)}")
