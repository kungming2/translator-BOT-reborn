#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""Image description command"""

import asyncio

from discord.ext import commands

from integrations.ai import fetch_image_description

from . import command

# ─── Command handler ──────────────────────────────────────────────────────────


# noinspection HttpUrlsUsage
@command(
    name="describe",
    help_text="Generates an AI description of an image from a URL.",
    roles=["Moderator", "Helper"],
)
async def describe_image(ctx: commands.Context, image_url: str) -> None:
    """
    Describe an image using AI for accessibility purposes. Shows the
    caller how the bot would describe an image in a notification.

    Usage: /describe <image_url>
    Example: /describe https://example.com/image.jpg
    """
    try:
        # Validate URL format (http links are supported, just in case)
        if not image_url.startswith(("http://", "https://")):
            await ctx.send(
                "⚠️ Error: Please provide a valid image URL starting with http:// or https://"
            )
            return

        async with ctx.typing():
            description = await asyncio.get_event_loop().run_in_executor(
                None,
                fetch_image_description,
                image_url,
                False,  # nsfw_flag always False
            )

        response = f"**Image Description:**\n{description}"

        if len(response) > 2000:
            response = response[:1997] + "..."

        await ctx.send(response)

    except Exception as e:
        await ctx.send(f"⚠️ An error occurred while describing the image: {str(e)}")
