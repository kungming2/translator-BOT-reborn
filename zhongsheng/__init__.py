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
        _commands.append({
            'name': name,
            'help': help_text,
            'roles': roles or [],
            'func': func
        })
        return func

    return decorator


def register_commands(bot):
    """Register all commands with the Discord bot"""
    # Import all command modules to trigger registration
    from . import office, lang, user, post, title, cjk, error, describe, info

    for cmd in _commands:
        # Start with the function
        func = cmd['func']

        # Add role requirements if specified
        if cmd['roles']:
            if len(cmd['roles']) == 1:
                func = commands.has_role(cmd['roles'][0])(func)
            else:
                func = commands.has_any_role(*cmd['roles'])(func)

        # Register the command with the bot
        bot.command(name=cmd['name'], help=cmd['help'])(func)


def get_commands():
    """Get all registered commands"""
    return _commands
