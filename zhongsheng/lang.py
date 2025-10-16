#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""Language conversion command"""

import importlib

import languages
from languages import select_random_language
from lookup.reference import get_language_reference

from . import command


@command(
    name="lang",
    help_text="Converts language input using the converter function",
    roles=["Moderator", "Helper"],
)
async def lang_convert(ctx, *, language_input: str):
    try:
        # Handle special 'random' argument
        if language_input.lower() == "random":
            random_lang_obj = select_random_language()
            lang_ref = get_language_reference(random_lang_obj)
            language_input = lang_ref["language_code_3"]

            # Reload the module to get fresh data
            importlib.reload(languages)

        # Always use languages.converter (either reloaded or original)
        result = languages.converter(language_input)
        result_vars = vars(result)

        # Pretty print the result
        formatted_output = "**Language Conversion Results:**\n\n"
        for key, value in result_vars.items():
            formatted_output += f"**{key}:** {value}\n"

        await ctx.send(formatted_output)
    except Exception as e:
        await ctx.send(f"An error occurred: {str(e)}")
