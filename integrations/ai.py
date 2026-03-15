#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
Handles interfacing for AI queries.
...

Logger tag: [AI]
"""

import logging

from openai import APIError  # Used for both DeepSeek and OpenAI
from openai import BadRequestError, OpenAI

from config import Paths, load_settings
from config import logger as _base_logger
from responses import RESPONSE

logger = logging.LoggerAdapter(_base_logger, {"tag": "AI"})


# ─── Module-level constants ───────────────────────────────────────────────────

access_credentials = load_settings(Paths.AUTH["CREDENTIALS"])


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
    service: str,
    client_object: OpenAI,
    behavior: str,
    query: str,
    image_url: str | None = None,
) -> str | None:
    """
    Pass a query to an AI service, optionally with image support.
    Image support requires the service to be ``"openai"``.

    :param service: ``'deepseek'`` or ``'openai'``
    :param client_object: Authenticated client object.
    :param behavior: System-role instructions for the service.
    :param query: Text prompt to pass to the AI.
    :param image_url: Optional public image URL (OpenAI Vision only).
    :return: The AI-generated response content, or None if an error occurred.
    """
    if service == "deepseek":
        ai_model: str = access_credentials["DEEPSEEK_MODEL"]

        # DeepSeek does not support image input, so ignore image_url.
        messages: list[dict] = [
            {"role": "system", "content": behavior},
            {"role": "user", "content": query},
        ]

    elif service == "openai":
        ai_model: str = access_credentials["OPENAI_MODEL"]

        if image_url:
            image_url = image_url.strip().rstrip(".")
            user_content: list[dict] | str = [
                {"type": "text", "text": query},
                {"type": "image_url", "image_url": {"url": image_url}},
            ]
            logger.debug(f"Image attached to input: {image_url}")
        else:
            user_content: list[dict] | str = query

        messages: list[dict] = [
            {"role": "system", "content": behavior},
            {"role": "user", "content": user_content},
        ]

    else:
        raise ValueError("Service must be either 'deepseek' or 'openai'.")

    try:
        # noinspection PyTypeChecker
        ai_response = client_object.chat.completions.create(
            model=ai_model,
            messages=messages,
            stream=False,  # type: ignore
        )
        return ai_response.choices[0].message.content

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
        return _NSFW_SKIP_MESSAGE

    logger.debug("Fetching image description...")
    description = ai_query(
        service="openai",
        client_object=openai_access(),
        behavior=_IMAGE_DESCRIPTION_BEHAVIOR,
        query=RESPONSE.IMAGE_DESCRIPTION_QUERY,
        image_url=image_url,
    )
    return description or ""


# ─── Entry point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    deepseek_access()
    openai_access()
    while True:
        image_test: str = input(
            "Please enter the image URL you'd like a description of: "
        )
        print(fetch_image_description(image_test))
