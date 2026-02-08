#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
Handles interfacing for AI queries.
"""

from openai import (
    APIError,  # Used for both DeepSeek and OpenAI
    BadRequestError,
    OpenAI,
)

from config import Paths, load_settings, logger
from responses import RESPONSE

access_credentials = load_settings(Paths.AUTH["CREDENTIALS"])


def deepseek_access() -> OpenAI:
    """
    Function to authenticate with Deepseek.
    """

    deepseek_client: OpenAI = OpenAI(
        api_key=access_credentials["DEEPSEEK_KEY"], base_url="https://api.deepseek.com"
    )

    return deepseek_client


def openai_access() -> OpenAI:
    """
    Function to authenticate with OpenAI.
    """

    openai_client: OpenAI = OpenAI(api_key=access_credentials["OPENAI_KEY"])

    return openai_client


def ai_query(
    service: str,
    client_object: OpenAI,
    behavior: str,
    query: str,
    image_url: str | None = None,
) -> str | None:
    """
    Function to pass a query to an AI service, optionally with
    image support. Image support requires the service to be "openai".

    :param service: 'deepseek' or 'openai'
    :param client_object: Client object that's authenticated.
    :param behavior: Instructions for how the service should act.
    :param query: Text prompt to pass to the AI.
    :param image_url: Optional public image URL (for OpenAI Vision).
    :return: The AI-generated response content, or None if an error occurred.
    """

    if service == "deepseek":
        ai_model: str = access_credentials["DEEPSEEK_MODEL"]

        # DeepSeek does not support image input, so ignore image_url
        messages: list[dict] = [
            {"role": "system", "content": behavior},
            {"role": "user", "content": query},
        ]

    elif service == "openai":
        ai_model: str = access_credentials["OPENAI_MODEL"]

        # Clean image URL if present
        if image_url:
            image_url = image_url.strip().rstrip(".")
            user_content: list[dict] | str = [
                {"type": "text", "text": query},
                {"type": "image_url", "image_url": {"url": image_url}},
            ]
            logger.debug(f"[S] AI: API: Image attached to input: {image_url}")
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
        response_data: str = ai_response.choices[0].message.content
        return response_data

    except BadRequestError as e:
        # Handle invalid requests (e.g., bad image URL, invalid parameters)
        logger.error(f"[S] AI: ERROR: {service.upper()} BadRequestError: {e}")
        if image_url:
            logger.warning(f"[S] AI: Warning: Problematic image URL: {image_url}")
        return None

    except APIError as e:
        # Handle other API errors (rate limits, server errors, etc.)
        logger.warning(f"[S] AI: Warning: {service.upper()} APIError: {e}")
        return None

    except Exception as e:
        # Catch any other unexpected errors
        logger.error(
            f"[S] AI: ERROR: Unexpected error in ai_query for ({service}): {e}"
        )
        return None


"""IMAGE DESCRIPTION"""


def fetch_image_description(image_url: str, nsfw_flag: bool = False) -> str:
    """
    Fetches a brief description of an image suitable for alt text.

    :param image_url: Public URL of the image to describe.
    :param nsfw_flag: Flag to determine if the image is NSFW. This will
                      automatically return a skip message. People
                      probably don't need a filthy description in their
                      inboxes.
    :return: The AI-generated short description of the image.
    """
    query: str = RESPONSE.IMAGE_DESCRIPTION_QUERY
    if nsfw_flag:
        reply: str = (
            "Out of an abundance of caution, a description will "
            "not be provided for this NSFW image."
        )
        return reply

    # Define behavior/system instructions
    behavior: str = (
        "You are an assistant that provides concise, accurate image descriptions "
        "for accessibility purposes."
    )

    # Send to AI (needs to use OpenAI for image assessment)
    logger.debug(f"[S] AI: PROCESS: Fetching image description")
    description: str = ai_query(
        service="openai",
        client_object=openai_access(),
        behavior=behavior,
        query=query,
        image_url=image_url,
    )

    return description


if __name__ == "__main__":
    deepseek_access()
    openai_access()
    while True:
        image_test: str = input(
            "Please enter the image URL you'd like a description of: "
        )
        print(fetch_image_description(image_test))
