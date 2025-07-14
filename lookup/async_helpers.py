"""ASYNC FUNCTIONS"""
import asyncio

from config import logger


async def fetch_json(session, url):
    try:
        async with session.get(url) as response:
            return await response.json()
    except Exception as e:
        logger.error(f"[ZW] Fetch failed for {url}: {e}")
        return None


async def maybe_async(func, *args, **kwargs):
    """Utility to await if a function is async; otherwise run it in executor."""
    if asyncio.iscoroutinefunction(func):
        return await func(*args, **kwargs)
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, func, *args)
