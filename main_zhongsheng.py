#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
Actual bot that can listen and respond to Discord server commands.
TODO INCOMPLETE
"""
import random

import discord
from discord.ext import commands

from config import Paths, load_settings

# Initialize the interactive interface.
intents = discord.Intents.default()
intents.message_content = True  # Enable this if you want to read message content
bot = commands.Bot(command_prefix='!', intents=intents)
DISCORD_TOKEN = load_settings(Paths.AUTH['CREDENTIALS'])['ZHONGSHENG_DISCORD_TOKEN']

"""EVENTS"""


@bot.event
async def on_ready():
    guild = discord.utils.get(bot.guilds, name="r/Translator Oversight")
    print(
        f'{bot.user} is connected to the following guild:\n'
        f'{guild.name} (id: {guild.id})'
    )


@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.errors.CheckFailure):
        await ctx.send('You do not have the correct role for this command.')


"""COMMANDS"""


@bot.command(name='99', help='Responds with a random quote from Brooklyn 99')
@commands.has_role('Moderator')
async def nine_nine(ctx):
    brooklyn_99_quotes = [
        'I\'m the human form of the 💯 emoji.',
        'Bingpot!',
        (
            'Cool. Cool cool cool cool cool cool cool, '
            'no doubt no doubt no doubt no doubt.'
        ),
    ]

    response = random.choice(brooklyn_99_quotes)
    await ctx.send(response)


@bot.command(name='roll_dice', help='Simulates rolling dice.')
@commands.has_role('Moderator')
async def roll(ctx, number_of_dice: int, number_of_sides: int):
    dice = [
        str(random.choice(range(1, number_of_sides + 1)))
        for _ in range(number_of_dice)
    ]
    await ctx.send(', '.join(dice))


bot.run(DISCORD_TOKEN)
