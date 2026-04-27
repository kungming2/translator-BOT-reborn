#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
Handles interfacing for AI queries.
...

Logger tag: [I:AI]
"""

# ─── Imports ──────────────────────────────────────────────────────────────────

import logging

from openai import (
    APIError,  # Used for both DeepSeek and OpenAI
    BadRequestError,
    OpenAI,
    Stream,
)

from config import Paths, load_settings
from config import logger as _base_logger
from responses import RESPONSE

# ─── Module-level constants ───────────────────────────────────────────────────

logger = logging.LoggerAdapter(_base_logger, {"tag": "I:AI"})

access_credentials = load_settings(Paths.AUTH["API"])


# ─── Authentication ───────────────────────────────────────────────────────────


def deepseek_access() -> OpenAI:
    """Return an authenticated DeepSeek client."""
    return OpenAI(
        api_key=access_credentials["DEEPSEEK_KEY"],
        base_url="https://api.deepseek.com",
    )


def openai_access() -> OpenAI:
    """Return an authenticated OpenAI client."""
    return OpenAI(api_key=access_credentials["OPENAI_KEY"])


# ─── Core query interface ─────────────────────────────────────────────────────


def ai_query(
    service: str = "openai",  # can switch between default services here
    behavior: str = "",
    query: str = "",
    image_url: str | None = None,
) -> str | None:
    """
    Pass a query to an AI service, optionally with image support.
    Image support requires the service to be ``"openai"``.

    :param service: `'deepseek'` or `'openai'` (latter is default)
    :param behavior: System-role instructions for the service.
    :param query: Text prompt to pass to the AI.
    :param image_url: Optional public image URL (OpenAI Vision only).
    :return: The AI-generated response content, or None if an error occurred.
    """

    user_content: list[dict] | str
    messages: list[dict]

    if service == "deepseek":
        client = deepseek_access()
        model = access_credentials["DEEPSEEK_MODEL"]
        supports_images = False

    elif service == "openai":
        client = openai_access()
        model = access_credentials["OPENAI_MODEL"]
        supports_images = True

    else:
        raise ValueError("Service must be either 'deepseek' or 'openai'.")

    # ─── Build message payload ────────────────────────────────────────
    if image_url and supports_images:
        image_url = image_url.strip().rstrip(".")
        user_content = [
            {"type": "text", "text": query},
            {"type": "image_url", "image_url": {"url": image_url}},
        ]
        logger.debug(f"Image attached to input: {image_url}")
    else:
        user_content = query

    messages = [
        {"role": "system", "content": behavior},
        {"role": "user", "content": user_content},
    ]

    # ─── Execute request ──────────────────────────────────────────────
    try:
        # noinspection PyTypeChecker
        response = client.chat.completions.create(
            model=model,
            messages=messages,  # type: ignore[arg-type]
            stream=False,
        )
        assert not isinstance(response, Stream)
        return response.choices[0].message.content

    except BadRequestError as e:
        # Invalid requests: bad image URL, invalid parameters, etc.
        logger.error(f"{service.upper()} BadRequestError: {e}")
        if image_url:
            logger.warning(f"Problematic image URL: {image_url}")
        return None

    except APIError as e:
        # Other API errors: rate limits, server errors, etc.
        logger.warning(f"{service.upper()} APIError: {e}")
        return None

    except Exception as e:
        logger.error(f"Unexpected error in ai_query for ({service}): {e}")
        return None


# ─── Image description ────────────────────────────────────────────────────────

_NSFW_SKIP_MESSAGE: str = (
    "Out of an abundance of caution, a description will "
    "not be provided for this NSFW image."
)

_IMAGE_DESCRIPTION_BEHAVIOR: str = (
    "You are an assistant that provides concise, accurate image descriptions "
    "for accessibility purposes."
)


def fetch_image_description(image_url: str, nsfw_flag: bool = False) -> str:
    """
    Fetch a brief description of an image suitable for alt text.

    :param image_url: Public URL of the image to describe.
    :param nsfw_flag: When True, skips querying the AI and returns a
                      placeholder message — recipients don't need an
                      explicit description of NSFW content in their inbox.
    :return: AI-generated short description, or an empty string on failure.
    """
    if nsfw_flag:
        logger.debug("Skipping image description due to NSFW flag.")
        return _NSFW_SKIP_MESSAGE

    logger.debug("Fetching image description...")
    description = ai_query(
        behavior=_IMAGE_DESCRIPTION_BEHAVIOR,
        query=RESPONSE.IMAGE_DESCRIPTION_QUERY,
        image_url=image_url,
    )
    return description or ""
