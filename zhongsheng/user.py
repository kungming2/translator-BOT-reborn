#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""User search command"""
from . import command
from database import search_logs


@command(name='user',
         help_text='Searches for a username in log files and returns matching lines',
         roles=['Moderator'])
async def user_search(ctx, user_input: str):
    # Extract username from URL if provided, otherwise use as-is
    if 'reddit.com/user/' in user_input or 'reddit.com/u/' in user_input:
        # Extract username from URL
        username = user_input.rstrip('/').split('/')[-1]
    else:
        # Use the input directly as username
        username = user_input

    await search_logs(ctx, username, 'user')
