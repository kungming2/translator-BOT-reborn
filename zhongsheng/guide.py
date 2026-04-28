#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""Command that shows the information about Zhongsheng.
This should be updated after addition of new features or commands."""

from discord.ext import commands

from . import COMMAND_GUIDE, command

# ─── Command handler ──────────────────────────────────────────────────────────


@command(
    name="guide",
    help_text="Display this informative message",
    roles=["Moderator", "Helper"],
)
async def guide_command(ctx: commands.Context, command_name: str | None = None) -> None:
    """
    Display help information for all commands or a specific command.

    Usage: /guide [command_name]
    """
    if command_name:
        # Show help for a specific command
        command_info = COMMAND_GUIDE.get(command_name)
        if command_info:
            description = command_info["description"]
            roles = command_info["roles"]
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
        # Show all commands, grouped by role requirements
        response = "**Zhongsheng Bot Commands:**\n\n"

        moderator_only = []
        helper_commands = []

        for cmd, command_info in sorted(COMMAND_GUIDE.items()):
            desc = command_info["description"]
            roles = command_info["roles"]

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

        # Split if too long for Discord's character limit
        if len(response) > 2000:
            chunks = [response[i : i + 1900] for i in range(0, len(response), 1900)]
            for chunk in chunks:
                await ctx.send(chunk)
        else:
            await ctx.send(response)
