#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
A bot that can listen and respond to Discord server commands, primarily
to look up data and reference information.
"""
import aiohttp
from io import BytesIO

import discord
from discord.ext import commands
import yaml

from commands.lookup_cjk import perform_cjk_lookups
from config import Paths, load_settings
from languages import converter, select_random_language
from lookup.reference import get_language_reference
from title_handling import process_title

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


@bot.command(name='office', help='Responds with a random quote from The Office')
@commands.has_any_role('Moderator', 'Helper')
async def office_quote(ctx):
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get('https://officeapi.akashrajpurohit.com/quote/random') as resp:
                if resp.status == 200:
                    data = await resp.json()
                    character = data.get('character', 'Unknown')
                    quote = data.get('quote', 'No quote available')
                    response = f"**{character}**: \"{quote}\""
                    await ctx.send(response)
                else:
                    await ctx.send(f"Failed to fetch quote. API returned status code {resp.status}")
    except Exception as e:
        await ctx.send(f"An error occurred: {str(e)}")


@bot.command(name='lang', help='Converts language input using the converter function')
@commands.has_any_role('Moderator', 'Helper')
async def lang_convert(ctx, *, language_input: str):
    try:
        # Handle special 'random' argument
        if language_input.lower() == 'random':
            random_lang_obj = select_random_language()
            lang_ref = get_language_reference(random_lang_obj)
            language_input = lang_ref['language_code_3']

        result = converter(language_input)
        result_vars = vars(result)

        # Pretty print the result
        formatted_output = "**Language Conversion Results:**\n\n"
        for key, value in result_vars.items():
            formatted_output += f"**{key}:** {value}\n"

        await ctx.send(formatted_output)
    except Exception as e:
        await ctx.send(f"An error occurred: {str(e)}")


async def _search_logs(ctx, search_term: str, term_type: str):
    """
    Internal helper function to search through log files for a given term.

    Args:
        ctx: Discord context
        search_term: The term to search for (username or post_id)
        term_type: Type of search ('user' or 'post') for display purposes
    """
    log_files = {
        'FILTER': Paths.LOGS['FILTER'],
        'EVENTS': Paths.LOGS['EVENTS'],
        'ERROR': Paths.LOGS['ERROR'],
    }

    try:
        all_matching_lines = []

        # Search through both log files
        for log_name, log_path in log_files.items():
            try:
                with open(log_path, 'r', encoding='utf-8', errors='replace') as log_file:
                    for line in log_file:
                        if search_term in line:
                            # Prepend log source to each line
                            all_matching_lines.append(f"[{log_name}] {line.strip()}")
            except FileNotFoundError:
                await ctx.send(f"Warning: {log_name} log file not found at `{log_path}`")
                continue

        # Send results back to the user
        if all_matching_lines:
            response = f"Found {len(all_matching_lines)} line(s) for {term_type} `{search_term}`:\n```\n"

            for line in all_matching_lines:
                # Check if adding this line would exceed Discord's limit
                if len(response) + len(line) + 10 > 1900:  # Leave buffer for closing backticks
                    response += "```"
                    await ctx.send(response)
                    response = "```\n"

                response += line + "\n"

            response += "```"
            await ctx.send(response)
        else:
            await ctx.send(f"No entries found for {term_type} `{search_term}` in the log files.")

    except Exception as e:
        await ctx.send(f"An error occurred: {str(e)}")


@bot.command(name='user',
             help='Searches for a username in log files and returns matching lines')
@commands.has_role('Moderator')
async def user_search(ctx, user_input: str):
    # Extract username from URL if provided, otherwise use as-is
    if 'reddit.com/user/' in user_input or 'reddit.com/u/' in user_input:
        # Extract username from URL
        username = user_input.rstrip('/').split('/')[-1]
    else:
        # Use the input directly as username
        username = user_input

    await _search_logs(ctx, username, 'user')


@bot.command(name='post', help='Searches for a Reddit post ID in log files and returns matching lines')
@commands.has_role('Moderator')
async def post_search(ctx, post_input: str):
    # Extract post ID from various formats
    post_id = None

    if 'reddit.com/' in post_input:
        # Extract from full Reddit URL
        # Format: https://www.reddit.com/r/subreddit/comments/POST_ID/title/
        parts = post_input.split('/')
        if 'comments' in parts:
            comment_index = parts.index('comments')
            if comment_index + 1 < len(parts):
                post_id = parts[comment_index + 1]
    elif 'redd.it/' in post_input:
        # Extract from short URL
        # Format: redd.it/POST_ID
        post_id = post_input.rstrip('/').split('/')[-1]
    else:
        # Assume it's already a post ID
        post_id = post_input

    if not post_id:
        await ctx.send("Could not extract post ID from the provided input.")
        return

    await _search_logs(ctx, post_id, 'post')


@bot.command(name='title',
             help='Processes a title and returns detailed information.')
@commands.has_role('Moderator')
async def title_search(ctx, *, title: str):

    # Process the title
    result = process_title(title)

    # Pretty print the result
    if result:
        formatted_output = "**Title Processing Results:**\n\n"
        for key, value in vars(result).items():
            formatted_output += f"**{key}:** {value}\n"
    else:
        formatted_output = f"No valid title processing results for `{title}`"

    await ctx.send(formatted_output)


@bot.command(name='cjk', help='Performs CJK lookups for a given language and search terms')
@commands.has_any_role('Moderator', 'Helper')
async def cjk_lookup(ctx, language: str, *, search_terms: str):
    try:
        language_name = converter(language).name

        # Validate language is CJK
        if language_name not in ['Chinese', 'Japanese', 'Korean']:
            await ctx.send(
                f"Error: '{language_name}' is not a supported CJK "
                f"language. Please use Chinese, Japanese, or Korean.")
            return

        result = await perform_cjk_lookups(language_name, [search_terms.strip()])
        formatted_result = '\n\n'.join(result)

        await ctx.send(formatted_result)
    except Exception as e:
        await ctx.send(f"An error occurred: {str(e)}")


@bot.command(name='error',
             help='Displays the 3 most recent error log entries')
@commands.has_role('Moderator')
async def error_logs(ctx):
    try:
        # Read the YAML file
        with open(Paths.LOGS["ERROR"], 'r', encoding='utf-8') as f:
            error_data = yaml.safe_load(f)

        # Get the last 3 entries
        recent_errors = error_data[-3:] if len(error_data) >= 3 else error_data

        # Format the output
        response = "**Most Recent Error Logs:**\n\n"

        for i, entry in enumerate(reversed(recent_errors), 1):
            response += f"**Error #{i}:**\n```\n"
            response += f"Timestamp: {entry.get('timestamp', 'N/A')}\n"
            response += f"Bot Version: {entry.get('bot_version', 'N/A')}\n"

            if 'context' in entry:
                response += f"\nContext:\n"
                for key, value in entry['context'].items():
                    response += f"  {key}: {value}\n"

            response += f"\nError:\n{entry.get('error', 'N/A')}\n"
            response += "```\n\n"

        # Discord has a 2000-character limit, so split if needed
        if len(response) > 2000:
            # Send as a text file instead
            file_content = response.replace('**', '').replace('```', '')
            file = discord.File(BytesIO(file_content.encode('utf-8')), filename='recent_errors.txt')
            await ctx.send("Error logs are too long, sending as file:", file=file)
        else:
            await ctx.send(response)

    except Exception as e:
        await ctx.send(f"An error occurred while reading error logs: {str(e)}")


bot.run(DISCORD_TOKEN)
