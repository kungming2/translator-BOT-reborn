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
from zhongsheng import load_expected_guild_id, register_commands

logger = logging.LoggerAdapter(_base_logger, {"tag": "ZS"})
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

    Sync only to the configured moderation guild. If the expected guild cannot
    be found, do not fall back to a global sync.
    """
    global _tree_synced

    if _tree_synced:
        return

    expected_guild_id = load_expected_guild_id(logger)
    if expected_guild_id is None:
        logger.error(
            "Skipping application command sync because no valid guild ID is configured."
        )
        return

    guild = bot.get_guild(expected_guild_id)
    if guild is None:
        logger.error(
            "Expected guild id %s was not found during sync; skipping global command sync.",
            expected_guild_id,
        )
        return

    bot.tree.copy_global_to(guild=guild)
    synced_commands = await bot.tree.sync(guild=guild)
    logger.info(
        "Synced %s application commands to guild %s (id: %s).",
        len(synced_commands),
        guild.name,
        guild.id,
    )

    _tree_synced = True


# ─── Bot events ───────────────────────────────────────────────────────────────


@bot.event
async def on_ready() -> None:
    """Log the connected guild (server) name and ID when the bot comes online."""
    expected_guild_id = load_expected_guild_id(logger)
    guild = bot.get_guild(expected_guild_id) if expected_guild_id is not None else None
    if guild:
        logger.info(
            "%s is connected to guild %s (id: %s)",
            bot.user,
            guild.name,
            guild.id,
        )
    else:
        logger.warning(
            "%s is connected but could not find expected guild id %s.",
            bot.user,
            expected_guild_id,
        )

    await sync_application_commands()


@bot.event
async def on_command_error(ctx: Context, error: commands.CommandError) -> None:
    """Handle command errors, rejecting unauthorized roles and logging all others."""
    if isinstance(error, commands.errors.CheckFailure):
        await ctx.send("You do not have the correct role or server for this command.")
    elif isinstance(error, commands.CommandOnCooldown):
        await ctx.send(
            f"Command is on cooldown. Try again in {error.retry_after:.0f}s."
        )
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


@bot.check
async def only_expected_guild(ctx: Context) -> bool:
    """Allow command execution only in the configured moderation guild."""
    return _is_expected_guild_context(ctx)


def _is_expected_guild_context(ctx: Context) -> bool:
    """Return whether a command context belongs to the configured guild."""
    expected_guild_id = load_expected_guild_id(logger)
    actual_guild_id = ctx.guild.id if ctx.guild else None

    if expected_guild_id is not None and actual_guild_id == expected_guild_id:
        return True

    logger.warning(
        "Rejected command `/%s` outside the expected guild. guild_id=%s user=%s user_id=%s",
        ctx.command.name if ctx.command else "<unknown>",
        actual_guild_id,
        ctx.author,
        ctx.author.id,
    )
    return False


@bot.before_invoke
async def before_command(ctx: Context) -> None:
    """Prepare command invocation context for both prefix and slash execution."""
    if ctx.interaction is not None and not ctx.interaction.response.is_done():
        # Hybrid slash commands must acknowledge the interaction quickly or
        # Discord invalidates the response token with "Unknown interaction".
        await ctx.defer()

    if not _is_expected_guild_context(ctx):
        raise commands.CheckFailure("Command invoked outside the configured guild.")

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
        error_message = "You do not have the correct role or server for this command."
        if interaction.response.is_done():
            await interaction.followup.send(error_message, ephemeral=True)
        else:
            await interaction.response.send_message(error_message, ephemeral=True)
        return

    if isinstance(error, (commands.CommandOnCooldown, app_commands.CommandOnCooldown)):
        error_message = (
            f"Command is on cooldown. Try again in {error.retry_after:.0f}s."
        )
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
