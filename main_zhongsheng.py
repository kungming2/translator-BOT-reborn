#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
A bot that can listen and respond to Discord server commands, primarily
to look up data and reference information.

Zhongsheng is a Discord bot for the r/Translator moderation team.
It provides various utility commands for:
- Looking up translation statistics and data
- Querying database information
- Accessing reference materials
- Managing subreddit-related tasks

The bot listens to slash commands (/) and provides responses within the
Discord server. All commands are registered via the zhongsheng module,
which contains the actual command implementations.

Bot features:
- Restricted to authorized Discord server
- Role-based permission checking
- Comprehensive logging of all command invocations
- Async command processing via discord.py
...

Logger tag: [ZS]
"""

import logging
import traceback

import discord
from discord import app_commands
from discord.ext import commands
from discord.ext.commands import Context

from config import Paths, load_settings
from config import logger as _base_logger
from error import error_log_extended
from zhongsheng import register_commands

logger = logging.LoggerAdapter(_base_logger, {"tag": "ZS"})
EXPECTED_GUILD_NAME = "r/Translator Oversight"
_tree_synced = False


# ─── Bot setup ────────────────────────────────────────────────────────────────

intents = discord.Intents.default()
if hasattr(intents, "message_content"):
    intents.message_content = True
else:
    logger.warning(
        "discord.Intents.message_content is unavailable in this installed Discord library; "
        "prefix command handling may be limited, but slash commands will still work."
    )
bot = commands.Bot(command_prefix="/", intents=intents)


async def sync_application_commands() -> None:
    """
    Sync the application command tree.

    If the expected guild is available, sync there first so updates appear
    quickly for the moderation server. Otherwise, fall back to a global sync.
    """
    global _tree_synced

    if _tree_synced:
        return

    guild = discord.utils.get(bot.guilds, name=EXPECTED_GUILD_NAME)
    if guild is not None:
        bot.tree.copy_global_to(guild=guild)
        synced_commands = await bot.tree.sync(guild=guild)
        logger.info(
            "Synced %s application commands to guild %s (id: %s).",
            len(synced_commands),
            guild.name,
            guild.id,
        )
    else:
        synced_commands = await bot.tree.sync()
        logger.warning(
            "Expected guild %r was not found during sync; synced %s global application commands instead.",
            EXPECTED_GUILD_NAME,
            len(synced_commands),
        )

    _tree_synced = True


# ─── Bot events ───────────────────────────────────────────────────────────────


@bot.event
async def on_ready() -> None:
    """Log the connected guild (server) name and ID when the bot comes online."""
    guild = discord.utils.get(bot.guilds, name=EXPECTED_GUILD_NAME)
    if guild:
        logger.info(
            "%s is connected to guild %s (id: %s)",
            bot.user,
            guild.name,
            guild.id,
        )
    else:
        logger.warning(
            "%s is connected but could not find the expected guild.",
            bot.user,
        )

    await sync_application_commands()


@bot.event
async def on_command_error(ctx: Context, error: commands.CommandError) -> None:
    """Handle command errors, rejecting unauthorized roles and logging all others."""
    if isinstance(error, commands.errors.CheckFailure):
        await ctx.send("You do not have the correct role for this command.")
    else:
        command_name = ctx.command.name if ctx.command else "<unknown>"
        logger.critical(
            f"Critical error in command `/{command_name}` by user {ctx.author} "
            f"(ID: {ctx.author.id}): {type(error).__name__}: {error}",
            exc_info=error,
        )
        error_log_extended(str(error), "Zhongsheng")


@bot.event
async def on_command_completion(ctx: Context) -> None:
    """Log command usage when a command completes successfully."""
    command_name = ctx.command.name if ctx.command else "<unknown>"
    guild_name = ctx.guild.name if ctx.guild else "<unknown guild>"
    logger.info(
        f"Command `/{command_name}` called by user {ctx.author} "
        f"(ID: {ctx.author.id}) in {guild_name}"
    )


# ─── Bot hooks ────────────────────────────────────────────────────────────────


@bot.before_invoke
async def before_command(ctx: Context) -> None:
    """Prepare command invocation context for both prefix and slash execution."""
    if ctx.interaction is not None and not ctx.interaction.response.is_done():
        # Hybrid slash commands must acknowledge the interaction quickly or
        # Discord invalidates the response token with "Unknown interaction".
        await ctx.defer()

    if ctx.kwargs:
        for key, value in ctx.kwargs.items():
            if isinstance(value, str):
                ctx.kwargs[key] = value.strip().strip("`").strip()

    command_name = ctx.command.name if ctx.command else "<unknown>"
    logger.info(
        f"Invoking command `/{command_name}` by user {ctx.author} "
        f"with args: {ctx.args[2:]} kwargs: {ctx.kwargs}"
    )


@bot.tree.error
async def on_app_command_error(
    interaction: discord.Interaction,
    error: app_commands.AppCommandError,
) -> None:
    """Handle slash-command errors with user feedback and structured logging."""
    command_name = interaction.command.name if interaction.command else "<unknown>"
    user_name = interaction.user if interaction.user else "<unknown user>"
    user_id = interaction.user.id if interaction.user else "<unknown id>"

    if isinstance(error, app_commands.errors.CheckFailure):
        error_message = "You do not have the correct role for this command."
        if interaction.response.is_done():
            await interaction.followup.send(error_message, ephemeral=True)
        else:
            await interaction.response.send_message(error_message, ephemeral=True)
        return

    logger.critical(
        "Critical app-command error in `/%s` by user %s (ID: %s): %s: %s",
        command_name,
        user_name,
        user_id,
        type(error).__name__,
        error,
        exc_info=error,
    )
    error_text = f"{type(error).__name__}: {error}\n\n{traceback.format_exc()}"
    error_log_extended(error_text, "Zhongsheng")

    user_message = "An unexpected error occurred while running this command."
    if interaction.response.is_done():
        await interaction.followup.send(user_message, ephemeral=True)
    else:
        await interaction.response.send_message(user_message, ephemeral=True)


# ─── Command registration & entry point ───────────────────────────────────────

register_commands(bot)


def load_discord_token() -> str:
    """Load and validate the Zhongsheng Discord token from credentials."""
    credentials = load_settings(Paths.AUTH["CREDENTIALS"])
    token = credentials.get("ZHONGSHENG_DISCORD_TOKEN")

    if not token:
        raise KeyError(
            "Missing required setting 'ZHONGSHENG_DISCORD_TOKEN' in credentials file."
        )

    return token


def main() -> None:
    """Start the Zhongsheng Discord bot with structured startup logging."""
    try:
        discord_token = load_discord_token()
        bot.run(discord_token)

    except (KeyboardInterrupt, SystemExit):
        logger.info("Manual user shutdown.")
        raise

    except Exception as e:
        logger.critical("Failed to start Zhongsheng: %s", e)
        error_text = f"{type(e).__name__}: {e}\n\n{traceback.format_exc()}"
        error_log_extended(error_text, "Zhongsheng")


if __name__ == "__main__":
    main()
