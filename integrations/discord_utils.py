#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
Handles simple functions to send one-way notifications for Discord via
webhooks.
...

Logger tag: [DISCORD]
"""

import json
import logging
from pathlib import Path

import requests

from config import Paths, load_settings
from config import logger as _base_logger

logger = logging.LoggerAdapter(_base_logger, {"tag": "DISCORD"})

webhook_settings: dict = load_settings(Paths.SETTINGS["DISCORD_SETTINGS"])


"""WEBHOOK NOTIFICATIONS (ONE-WAY ALERTS)"""


def select_webhook(selection: str) -> tuple[str, str, str] | None:
    """Returns the webhook URL, image URL, and color if found, otherwise None."""
    return webhook_settings.get(selection)


def send_discord_alert(
    subject: str,
    message: str,
    webhook_name: str,
    roles: list[str] | None = None,
    image_path=None,
) -> None:
    """Sends an alert message to the specified Discord webhook
    using an embed with an optional icon and color.
    It can accept an optional roles payload, given as a list.
    If image_path is provided and the file exists, it will be attached
    to the message as a file upload."""

    webhook_data: tuple[str, str, str] | None = select_webhook(webhook_name)
    if not webhook_data:
        logger.error(f"Webhook not found: '{webhook_name}'. Alert not sent.")
        return  # Exit function early if webhook is invalid

    webhook_url, image_url, color_hex = webhook_data  # Extract URL, image, and color

    # Convert hex color to decimal (Discord API requires decimal)
    color_decimal: int = int(color_hex.lstrip("#"), 16)

    # Format the roles section. This must be included outside the
    # embed in order to work properly. Roles are sent as a list.
    roles_content: str | None
    if roles:
        roles_content = " ".join(f"<@&{role}>" for role in roles)
        logger.debug(f"Roles: {roles_content}")
    else:
        roles_content = None

    embed: dict = {
        "title": subject,
        "description": message,
        "color": color_decimal,  # Set the embed color
        "thumbnail": {"url": image_url},  # Set the image as the thumbnail
    }

    # Include a roles section before the embed, if present.
    payload: dict
    if roles_content:
        payload = {"content": roles_content, "embeds": [embed]}
    else:
        payload = {"embeds": [embed]}

    try:
        attach = Path(image_path) if image_path else None
        if attach and attach.exists():
            # Multipart request: embed payload + file attachment
            with attach.open("rb") as img_file:
                response = requests.post(
                    webhook_url,
                    data={"payload_json": json.dumps(payload)},
                    files={"file": (attach.name, img_file, "image/png")},
                )
        else:
            if image_path:
                logger.warning(
                    f"Screenshot file not found, sending without image: {image_path}"
                )
            response = requests.post(webhook_url, json=payload)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to send Discord alert: {e}")
    else:
        logger.info(f"Discord alert sent to webhook {webhook_name!r}: {subject!r}")
