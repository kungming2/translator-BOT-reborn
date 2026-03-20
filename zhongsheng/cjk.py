#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""CJK lookup command"""

from discord.ext import commands

from lang.languages import converter
from ziwen_commands.lookup_cjk import perform_cjk_lookups

from . import command, send_long_message


@command(
    name="cjk",
    help_text="Performs CJK lookups for a given language and search terms",
    roles=["Moderator", "Helper"],
)
async def cjk_lookup(
    ctx: commands.Context, language: str, *, search_terms: str
) -> None:
    """Discord wrapper for the CJK lookup command."""
    try:
        # Map initials to full language names
        initial_map = {"c": "Chinese", "j": "Japanese", "k": "Korean"}

        # Check if input is an initial
        if language.lower() in initial_map:
            language_name = initial_map[language.lower()]
        else:
            # Use converter for full language names/codes
            _lingvo = converter(language)
            language_name = (
                _lingvo.name
                if _lingvo is not None and _lingvo.name is not None
                else language
            )

        # Validate language is CJK
        if language_name not in ["Chinese", "Japanese", "Korean"]:
            await ctx.send(
                f"Error: '{language_name}' is not a supported CJK "
                f"language. Please use Chinese, Japanese, or "
                f"Korean-associated codes or names."
            )
            return

        # Show typing indicator while processing
        async with ctx.typing():
            result = await perform_cjk_lookups(language_name, [search_terms.strip()])
            formatted_result = "\n\n".join(result)

        # Split and send if result exceeds Discord's 2000 char limit
        await send_long_message(ctx, formatted_result)

    except Exception as e:
        await ctx.send(f"An error occurred: {str(e)}")
