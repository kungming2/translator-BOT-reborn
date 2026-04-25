#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""Language conversion command"""

import shlex

from discord import Member
from discord.ext import commands

from lang.languages import (
    add_alt_language_name,
    converter,
    get_lingvos,
    select_random_language,
)

from . import command

# ─── Command handler ──────────────────────────────────────────────────────────


@command(
    name="lang",
    help_text="Converts language input using the converter function.",
    roles=["Moderator", "Helper"],
)
async def lang_convert(ctx: commands.Context, *, language_input: str) -> None:
    """Discord wrapper for Lingvo creation."""
    try:
        # Safely split input (handles quoted text)
        tokens = shlex.split(language_input.strip())
        add_alt_flag = False
        alt_value = None
        main_lang_tokens = []

        # Parse arguments in any order
        i = 0
        while i < len(tokens):
            token = tokens[i]
            if token in ("--add_alt", "–add_alt", "-add_alt", "—add_alt"):
                add_alt_flag = True
                alt_tokens = []
                j = i + 1
                while j < len(tokens) and not tokens[j].startswith("-"):
                    alt_tokens.append(tokens[j])
                    j += 1
                alt_value = " ".join(alt_tokens)
                i = j - 1  # skip processed tokens
            else:
                main_lang_tokens.append(token)
            i += 1

        if not main_lang_tokens:
            await ctx.send("⚠️ You must specify a language code or 'random'.")
            return

        language_input = " ".join(main_lang_tokens)

        # Handle 'random' argument
        if language_input.lower() == "random":
            random_lang_obj = select_random_language()
            if random_lang_obj is None:
                await ctx.send("⚠️ An error occurred. No valid random results found.")
                return

            # select_random_language already returns a Lingvo, so prefer its
            # known codes directly instead of doing a separate reference lookup.
            language_input = random_lang_obj.preferred_code

        result = converter(language_input, preserve_country=True)
        if not result:
            await ctx.send("🈚 No matching results found by converter.")
            return
        else:
            result_vars = vars(result)

        # Handle --add_alt flag — Moderators only
        added_alt = False
        if add_alt_flag:
            if not isinstance(ctx.author, Member):
                await ctx.send("🚫 This command can only be used in a server.")
                return
            user_role_names = [role.name for role in ctx.author.roles]
            if "Moderator" not in user_role_names:
                await ctx.send("🚫 You do not have permission to use `--add_alt`.")
                add_alt_flag = False  # disable further processing
            elif alt_value is not None:
                added_alt = add_alt_language_name(result.preferred_code, alt_value)
                if added_alt:
                    get_lingvos(
                        force_refresh=True
                    )  # flush stale caches after YAML write

        formatted_output = "**Language Conversion Results:**\n\n"
        for key, value in result_vars.items():
            formatted_output += f"**{key}:** {value}\n"

        if add_alt_flag and alt_value:
            if added_alt:
                formatted_output = (
                    f"\n✅ Added alternate name: `{alt_value}` "
                    f"for language **{result.name}** (`{result.preferred_code}`)."
                )
            else:
                formatted_output = f"\nℹ️ Alternate name `{alt_value}` already exists or could not be added."

        await ctx.send(formatted_output)

    except Exception as e:
        await ctx.send(f"⚠️ An error occurred: {str(e)}")
