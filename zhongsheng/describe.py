#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""Image description command"""

import asyncio

from ai import fetch_image_description

from . import command


# noinspection HttpUrlsUsage
@command(
    name="describe",
    help_text="Generates an AI description of an image from a URL",
    roles=["Moderator", "Helper"],
)
async def describe_image(ctx, image_url: str):
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

        # Show typing indicator while processing
        async with ctx.typing():
            # Run the blocking function in a thread pool
            description = await asyncio.get_event_loop().run_in_executor(
                None,
                fetch_image_description,
                image_url,
                False,  # nsfw_flag always False
            )

        # Format and send the response
        response = f"**Image Description:**\n{description}"

        # Check Discord's character limit
        if len(response) > 2000:
            response = response[:1997] + "..."

        await ctx.send(response)

    except Exception as e:
        await ctx.send(f"⚠️ An error occurred while describing the image: {str(e)}")
