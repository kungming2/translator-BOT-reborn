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

import discord
from discord.ext import commands
from discord.ext.commands import Context

from config import Paths, load_settings
from config import logger as _base_logger
from error import error_log_extended
from zhongsheng import register_commands

logger = logging.LoggerAdapter(_base_logger, {"tag": "ZS"})


# ─── Bot setup ────────────────────────────────────────────────────────────────

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="/", intents=intents)
DISCORD_TOKEN = load_settings(Paths.AUTH["CREDENTIALS"])["ZHONGSHENG_DISCORD_TOKEN"]


# ─── Bot events ───────────────────────────────────────────────────────────────


@bot.event
async def on_ready() -> None:
    """Log the connected guild (server) name and ID when the bot comes online."""
    guild = discord.utils.get(bot.guilds, name="r/Translator Oversight")
    if guild:
        print(
            f"{bot.user} is connected to the following guild:\n"
            f"{guild.name} (id: {guild.id})"
        )
    else:
        print(f"{bot.user} is connected but could not find the expected guild.")


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
    """Strip and log command arguments before the command runs."""
    if ctx.kwargs:
        for key, value in ctx.kwargs.items():
            if isinstance(value, str):
                ctx.kwargs[key] = value.strip().strip("`").strip()

    command_name = ctx.command.name if ctx.command else "<unknown>"
    logger.info(
        f"Invoking command `/{command_name}` by user {ctx.author} "
        f"with args: {ctx.args[2:]} kwargs: {ctx.kwargs}"
    )


# ─── Command registration & entry point ───────────────────────────────────────

register_commands(bot)

if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)
