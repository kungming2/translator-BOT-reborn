#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""Language conversion command"""

import importlib
import shlex

import languages
from languages import select_random_language, converter, add_alt_language_name
from lookup.reference import get_language_reference

from . import command


@command(
    name="lang",
    help_text="Converts language input using the converter function",
    roles=["Moderator", "Helper"],
)
async def lang_convert(ctx, *, language_input: str):
    try:
        # Safely split input (handles quoted text)
        tokens = shlex.split(language_input.strip())
        add_alt_flag = False
        alt_value = None
        main_lang_input = None

        # Parse arguments in any order
        i = 0
        while i < len(tokens):
            token = tokens[i]
            if token in ("--add_alt", "-add_alt"):
                add_alt_flag = True
                alt_tokens = []
                j = i + 1
                while j < len(tokens) and not tokens[j].startswith("-"):
                    alt_tokens.append(tokens[j])
                    j += 1
                alt_value = " ".join(alt_tokens)
                i = j - 1  # skip processed tokens
            elif main_lang_input is None:
                main_lang_input = token
            i += 1

        if not main_lang_input:
            await ctx.send("You must specify a language code or 'random'.")
            return

        language_input = main_lang_input

        # Handle 'random' argument
        if language_input.lower() == "random":
            random_lang_obj = select_random_language()
            lang_ref = get_language_reference(random_lang_obj)
            language_input = lang_ref["language_code_3"]
            importlib.reload(languages)

        # Run conversion
        result = languages.converter(language_input)
        result_vars = vars(result)

        # Handle --add_alt flag if present
        added_alt = False
        if add_alt_flag and alt_value is not None:
            added_alt = add_alt_language_name(
                converter(language_input).preferred_code, alt_value
            )

        # Format output
        formatted_output = "**Language Conversion Results:**\n\n"
        for key, value in result_vars.items():
            formatted_output += f"**{key}:** {value}\n"

        if add_alt_flag and alt_value:
            if added_alt:
                formatted_output = f"\n✅ Added alternate name: `{alt_value}`"
            else:
                formatted_output = f"\nℹ️ Alternate name `{alt_value}` already exists or could not be added."

        await ctx.send(formatted_output)

    except Exception as e:
        await ctx.send(f"An error occurred: {str(e)}")
