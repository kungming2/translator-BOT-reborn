#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""Shared policy and request helpers for HTTP integrations."""

from random_user_agent.params import OperatingSystem, SoftwareName
from random_user_agent.user_agent import UserAgent

DEFAULT_HTTP_TIMEOUT: tuple[int, int] = (5, 15)
DISCORD_HTTP_TIMEOUT: tuple[int, int] = (5, 20)
WIKIMEDIA_USER_AGENT = (
    "translator-BOT/2.3 "
    "(https://github.com/kungming2/translator-BOT-reborn; u/translator-BOT)"
)


def get_random_useragent() -> dict[str, str]:
    """Return randomized browser-style headers for external HTTP requests."""
    user_agent_rotator = UserAgent(
        software_names=[SoftwareName.CHROME.value],
        operating_systems=[
            OperatingSystem.WINDOWS.value,
            OperatingSystem.LINUX.value,
        ],
        limit=1,
    )
    return {
        "User-Agent": user_agent_rotator.get_random_user_agent(),
        "Accept": (
            "text/html,application/json,application/xhtml+xml,"
            "application/xml;q=0.9,image/webp,*/*;q=0.8"
        ),
    }


def get_wikimedia_useragent() -> dict[str, str]:
    """Return a stable, contactable User-Agent for Wikimedia API requests."""
    return {
        "User-Agent": WIKIMEDIA_USER_AGENT,
        "Accept": "application/json",
    }
