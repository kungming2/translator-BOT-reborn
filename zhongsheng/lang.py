#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""Language conversion command"""

import logging
import shlex

from discord import Member
from discord.ext import commands

from config import logger as _base_logger
from lang.languages import (
    add_alt_language_name,
    converter,
    get_lingvos,
    has_editable_language_entry,
    select_random_language,
)

from . import command, send_long_message

logger = logging.LoggerAdapter(_base_logger, {"tag": "ZS:LANG"})

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
        action = None

        if tokens and tokens[0].lower() in ("lookup", "random", "add_alt"):
            action = tokens.pop(0).lower()
            if action == "random":
                main_lang_tokens = ["random"]
            elif action == "add_alt":
                add_alt_flag = True
                if tokens:
                    main_lang_tokens = [tokens.pop(0)]
                    alt_value = " ".join(tokens)
            else:
                main_lang_tokens = tokens

        if action is None:
            # Parse legacy arguments in any order.
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

        if add_alt_flag and not alt_value:
            await ctx.send("⚠️ You must specify an alternate name for `add_alt`.")
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

        # Handle alternate-name edits - Moderators only.
        added_alt = False
        editable_language_entry = True
        if add_alt_flag:
            if not isinstance(ctx.author, Member):
                await ctx.send("🚫 This command can only be used in a server.")
                return
            user_role_names = [role.name for role in ctx.author.roles]
            if "Moderator" not in user_role_names:
                await ctx.send("🚫 You do not have permission to use `add_alt`.")
                add_alt_flag = False  # disable further processing
            elif alt_value is not None:
                editable_language_entry = has_editable_language_entry(
                    result.preferred_code
                )
                if editable_language_entry:
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
            elif not editable_language_entry:
                formatted_output = (
                    f"\nℹ️ `{result.name}` resolved to `{result.preferred_code}`, "
                    "but that language is not in the editable language dataset. "
                    "Add a `language_data.yaml` entry before adding alternate names."
                )
            else:
                formatted_output = (
                    f"\nℹ️ Alternate name `{alt_value}` already exists "
                    f"for `{result.preferred_code}`."
                )

        await send_long_message(ctx, formatted_output)

    except Exception as e:
        logger.error(
            f"Error converting language input `{language_input}`: {e}", exc_info=True
        )
        await ctx.send("⚠️ An error occurred while converting the language input.")
