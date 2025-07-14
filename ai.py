#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
Handles interfacing for AI queries.
"""
from openai import OpenAI  # Used for both DeepSeek and OpenAI

from config import Paths, load_settings, logger

access_credentials = load_settings(Paths.AUTH['CREDENTIALS'])


def deepseek_access():
    """
    Function to authenticate with Deepseek.
    """

    deepseek_client = OpenAI(api_key=access_credentials['DEEPSEEK_KEY'],
                             base_url="https://api.deepseek.com")

    return deepseek_client


def openai_access():
    """
    Function to authenticate with OpenAI.
    """

    openai_client = OpenAI(api_key=access_credentials['OPENAI_KEY'])

    return openai_client


def ai_query(service, client_object, behavior, query, image_url=None):
    """
    Function to pass a query to an AI service, optionally with image support.

    :param service: 'deepseek' or 'openai'
    :param client_object: Client object that's authenticated.
    :param behavior: Instructions for how the service should act.
    :param query: Text prompt to pass to the AI.
    :param image_url: Optional public image URL (for OpenAI Vision).
    :return: The AI-generated response content.
    """

    if service == "deepseek":
        ai_model = access_credentials['DEEPSEEK_MODEL']

        # DeepSeek does not support image input, so ignore image_url
        messages = [
            {"role": "system", "content": behavior},
            {"role": "user", "content": query},
        ]

    elif service == "openai":
        ai_model = access_credentials['OPENAI_MODEL']

        # Construct multimodal message if image is present
        if image_url:
            user_content = [
                {"type": "text", "text": query},
                {"type": "image_url", "image_url": {"url": image_url}}
            ]
            logger.debug("Image attached to input.")
        else:
            user_content = query

        messages = [
            {"role": "system", "content": behavior},
            {"role": "user", "content": user_content},
        ]

    else:
        raise ValueError("Service must be either 'deepseek' or 'openai'.")

    ai_response = client_object.chat.completions.create(
        model=ai_model,
        messages=messages,
        stream=False
    )
    response_data = ai_response.choices[0].message.content

    return response_data


if __name__ == "__main__":
    deepseek_access()
    openai_access()
