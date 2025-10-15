#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""Title processing command"""
import asyncio
from . import command
from title_handling import process_title, title_ai_parser


@command(name='title',
         help_text='Processes a title and returns detailed information. Use --ai flag for AI parsing.',
         roles=['Moderator'])
async def title_search(ctx, *, title: str):
    # Check if --ai flag is present
    use_ai = title.endswith(' --ai')

    # Remove the flag from the title if present
    if use_ai:
        title = title[:-5].strip()  # Remove ' --ai' from the end

    try:
        # Show typing indicator for AI processing
        if use_ai:
            async with ctx.typing():
                # Run synchronous AI parser in thread pool
                loop = asyncio.get_running_loop()
                result = await loop.run_in_executor(None, title_ai_parser, title, None)
        else:
            # Process the title normally
            result = process_title(title)

        # Check if result is an error tuple
        if isinstance(result, tuple) and len(result) == 2 and result[0] == "error":
            await ctx.send(f"**AI Parsing Error:** {result[1]}")
            return

        # Pretty print the result
        if result:
            formatted_output = "**Title Processing Results:**\n\n"

            # Handle dictionary results (from AI parser)
            if isinstance(result, dict):
                for key, value in result.items():
                    formatted_output += f"**{key}:** {value}\n"
            else:
                # Handle object results (from process_title)
                for key, value in vars(result).items():
                    formatted_output += f"**{key}:** {value}\n"
        else:
            formatted_output = f"No valid title processing results for `{title}`"

        await ctx.send(formatted_output)

    except Exception as e:
        await ctx.send(f"An error occurred: {str(e)}")
        import traceback
        traceback.print_exc()
