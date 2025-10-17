#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""Command that shows the information about Zhongsheng"""

from . import command

# Custom command descriptions - edit these as needed
COMMAND_DESCRIPTIONS = {
    "lang": 'Convert language codes/names. Use "random" for a random language (e.g. `/lang random`). '
    "Alternate names can be added as `/lang [code] --add_alt [new_name]`",
    "user": "Search log files and database for a Reddit username (accepts strings and URLs). Data limited to the last month",
    "post": "Search log files and database for a Reddit post ID (accepts strings and URLs)",
    "comment": "See relevant data for a Reddit comment with bot commands (accepts strings and URLs). "
    "Use the ``--text`` flag to check text directly",
    "title": "Process a Reddit post title. Use the ``--ai`` flag for AI parsing",
    "filter": "Check if a Reddit post title would be approved or rejected by the title filtration routine",
    "cjk": "Look up Chinese, Japanese, or Korean words. Use c/j/k as shortcuts (e.g. `/cjk c 翻译`)",
    "error": "Display the 3 most recent error log entries",
    "describe": "Generate an AI alt-text description of an image from a URL",
    "office": "Get a random quote from *The Office (US)*",
    "guide": "Display this informational guide about Zhongsheng commands",
}

# Role requirements for each command
COMMAND_ROLES = {
    "lang": ["Moderator", "Helper"],
    "user": ["Moderator"],
    "post": ["Moderator"],
    "title": ["Moderator"],
    "cjk": ["Moderator", "Helper"],
    "error": ["Moderator"],
    "describe": ["Moderator", "Helper"],
    "filter": ["Moderator", "Helper"],
    "guide": ["Moderator", "Helper"],
    "office": ["Moderator", "Helper"],
}


@command(
    name="guide",
    help_text="Display this informative message",
    roles=["Moderator", "Helper"],
)
async def guide_command(ctx, command_name: str = None):
    """
    Display help information for all commands or a specific command.

    Usage: /guide [command_name]
    """
    if command_name:
        # Show help for a specific command
        if command_name in COMMAND_DESCRIPTIONS:
            description = COMMAND_DESCRIPTIONS[command_name]
            roles = COMMAND_ROLES.get(command_name, [])
            role_text = (
                f"**Required roles:** {', '.join(roles)}"
                if roles
                else "**No role restrictions**"
            )

            response = f"**/{command_name}**\n{description}\n{role_text}"
            await ctx.send(response)
        else:
            await ctx.send(f"Command `{command_name}` not found.")
    else:
        # Show all commands
        response = "**Zhongsheng Bot Commands:**\n\n"

        # Group by role requirements
        moderator_only = []
        helper_commands = []

        for cmd, desc in sorted(COMMAND_DESCRIPTIONS.items()):
            roles = COMMAND_ROLES.get(cmd, [])

            if roles == ["Moderator"]:
                moderator_only.append(f"**/{cmd}** - {desc}")
            else:
                helper_commands.append(f"**/{cmd}** - {desc}")

        if helper_commands:
            response += "**Available to Moderators & Helpers:**\n"
            response += "\n".join(helper_commands)
            response += "\n\n"

        if moderator_only:
            response += "**Moderator Only:**\n"
            response += "\n".join(moderator_only)

        response += "\n\nUse `/guide <command>` for detailed information about a specific command."

        # Split if too long
        if len(response) > 2000:
            chunks = [response[i : i + 1900] for i in range(0, len(response), 1900)]
            for chunk in chunks:
                await ctx.send(chunk)
        else:
            await ctx.send(response)
