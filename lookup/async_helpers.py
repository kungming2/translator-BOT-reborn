#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""ASYNC FUNCTIONS"""

import asyncio

from config import logger


async def fetch_json(session, url):
    """
    Fetch and parse a JSON response asynchronously.

    Args:
        session (aiohttp.ClientSession): An active aiohttp session used
                                         for making HTTP requests.
        url (str): The URL to fetch JSON data from.

    Returns:
        dict | list | None: The parsed JSON response if successful;
                            otherwise None if an error occurs.

    Notes:
        - Logs an error if the request or JSON parsing fails.
        - Does not raise exceptions; failures are handled internally and
          return None.
    """
    try:
        async with session.get(url) as response:
            return await response.json()
    except Exception as e:
        logger.error(f"[ZW] Fetch failed for {url}: {e}")
        return None


async def call_sync_async(func, *args, **kwargs):
    """
    Execute a function that may be synchronous or asynchronous.

    If the function is a coroutine, it is awaited directly.
    Otherwise, it runs in a thread executor to avoid blocking the event loop.

    Args:
        func (Callable): The function to execute. Can be async or sync.
        *args: Positional arguments to pass to the function.
        **kwargs: Keyword arguments to pass to the function.

    Returns:
        Any: The result of the function call, awaited or executed as appropriate.
    """

    if asyncio.iscoroutinefunction(func):
        return await func(*args, **kwargs)
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, func, *args)
