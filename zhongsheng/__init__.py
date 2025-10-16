#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
Command registry for Zhongsheng bot.
Allows commands to be defined in separate modules and registered via decorator.
"""

from discord.ext import commands

_commands = []


def command(name, help_text, roles=None):
    """
    Decorator to register a Discord bot command.

    Args:
        name: Command name (used after !)
        help_text: Help description for the command
        roles: List of required role names, or None for no restrictions
    """

    def decorator(func):
        _commands.append(
            {"name": name, "help": help_text, "roles": roles or [], "func": func}
        )
        return func

    return decorator


def register_commands(bot):
    """Register all commands with the Discord bot"""
    # Import all command modules to trigger registration
    from . import cjk, comment, describe, error, guide, lang, office, post, title, user

    for cmd in _commands:
        # Start with the function
        func = cmd["func"]

        # Add role requirements if specified
        if cmd["roles"]:
            if len(cmd["roles"]) == 1:
                func = commands.has_role(cmd["roles"][0])(func)
            else:
                func = commands.has_any_role(*cmd["roles"])(func)

        # Register the command with the bot
        bot.command(name=cmd["name"], help=cmd["help"])(func)


def get_commands():
    """Get all registered commands"""
    return _commands


async def send_long_message(ctx, content: str, max_length: int = 2000):
    """
    Splits long messages into chunks and sends them separately.
    Attempts to split on paragraph boundaries first for readability.
    """
    if len(content) <= max_length:
        await ctx.send(content)
        return

    chunks = []
    current_chunk = ""

    # Split by double newlines (paragraphs) first
    paragraphs = content.split("\n\n")

    for paragraph in paragraphs:
        # If a single paragraph exceeds max length, split it further
        if len(paragraph) > max_length:
            # Add current chunk if it exists
            if current_chunk:
                chunks.append(current_chunk)
                current_chunk = ""

            # Split long paragraph by single newlines
            lines = paragraph.split("\n")
            for line in lines:
                if len(current_chunk) + len(line) + 1 > max_length:
                    if current_chunk:
                        chunks.append(current_chunk)
                    current_chunk = line
                else:
                    current_chunk += ("\n" if current_chunk else "") + line
        else:
            # Try to add paragraph to current chunk
            test_chunk = current_chunk + ("\n\n" if current_chunk else "") + paragraph
            if len(test_chunk) <= max_length:
                current_chunk = test_chunk
            else:
                # Current chunk is full, start a new one
                if current_chunk:
                    chunks.append(current_chunk)
                current_chunk = paragraph

    # Add remaining content
    if current_chunk:
        chunks.append(current_chunk)

    # Send all chunks
    for chunk in chunks:
        await ctx.send(chunk)
