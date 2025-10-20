#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
A bot that can listen and respond to Discord server commands, primarily
to look up data and reference information.

Zhongsheng is a Discord bot for the r/Translator
moderation team. It provides various utility commands for:
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
"""

import discord
from discord.ext import commands
from discord.ext.commands import Context

from config import Paths, load_settings
from connection import logger
from zhongsheng import register_commands

# Initialize the bot
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="/", intents=intents)
DISCORD_TOKEN = load_settings(Paths.AUTH["CREDENTIALS"])["ZHONGSHENG_DISCORD_TOKEN"]


@bot.event
async def on_ready() -> None:
    guild = discord.utils.get(bot.guilds, name="r/Translator Oversight")
    print(
        f"{bot.user} is connected to the following guild:\n"
        f"{guild.name} (id: {guild.id})"
    )


@bot.event
async def on_command_error(ctx: Context, error: commands.CommandError) -> None:
    if isinstance(error, commands.errors.CheckFailure):
        await ctx.send("You do not have the correct role for this command.")


@bot.event
async def on_command_completion(ctx: Context) -> None:
    """Log command usage when a command completes successfully."""
    logger.info(
        f"Command `/{ctx.command.name}` called by user {ctx.author} "
        f"(ID: {ctx.author.id}) in {ctx.guild.name}"
    )


@bot.before_invoke
async def before_command(ctx: Context) -> None:
    """Log command invocation before it runs."""
    logger.info(
        f"Invoking command `/{ctx.command.name}` by user {ctx.author} "
        f"with args: {ctx.args[2:]} kwargs: {ctx.kwargs}"
    )


# Register all commands from the zhongsheng module
register_commands(bot)

if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)
