#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
Handles simple functions to send one-way notifications for Discord via
webhooks.
...

Logger tag: [I:DISCORD]
"""

# ─── Imports ──────────────────────────────────────────────────────────────────

import json
import logging
from pathlib import Path

import requests

from config import Paths, load_settings
from config import logger as _base_logger

# ─── Module-level constants ───────────────────────────────────────────────────

logger = logging.LoggerAdapter(_base_logger, {"tag": "I:DISCORD"})

webhook_settings: dict = load_settings(Paths.SETTINGS["DISCORD_SETTINGS"])


# ─── Webhook lookup ───────────────────────────────────────────────────────────


def select_webhook(selection: str) -> tuple[str, str, str] | None:
    """Return the webhook URL, thumbnail image URL, and hex color for
    *selection*, or None if the key is not present in settings."""
    result = webhook_settings.get(selection)
    if result is not None:
        assert len(result) == 3, (
            f"Webhook '{selection}' must have exactly 3 elements "
            f"(url, image_url, color_hex), got {len(result)}"
        )
    return result


# ─── Webhook notifications ────────────────────────────────────────────────────


def send_discord_alert(
    subject: str,
    message: str,
    webhook_name: str,
    roles: list[str] | None = None,
    image_path: str | Path | None = None,
) -> None:
    """
    Send an alert message to the specified Discord webhook using an embed
    with an optional thumbnail icon and color.

    Roles are formatted as Discord mentions and prepended to the embed as
    plain content (required for mentions to fire). If *image_path* is
    provided and the file exists on disk, it is attached to the request as
    a file upload alongside the embed.

    :param subject:      Embed title.
    :param message:      Embed body text.
    :param webhook_name: Key used to look up the webhook in settings.
    :param roles:        Optional list of Discord role IDs to mention.
    :param image_path:   Optional path to a local image file to attach.
    """
    webhook_data: tuple[str, str, str] | None = select_webhook(webhook_name)
    if not webhook_data:
        logger.error(f"Webhook not found: '{webhook_name}'. Alert not sent.")
        return

    webhook_url, image_url, color_hex = webhook_data

    # Discord API requires embed colors as decimal integers.
    color_decimal: int = int(color_hex.lstrip("#"), 16)

    # Role mentions must live outside the embed to actually ping members.
    roles_content: str | None
    if roles:
        roles_content = " ".join(f"<@&{role}>" for role in roles)
        logger.debug(f"Roles: {roles_content}")
    else:
        roles_content = None

    embed: dict = {
        "title": subject,
        "description": message,
        "color": color_decimal,
        "thumbnail": {"url": image_url},
    }

    payload: dict
    if roles_content:
        payload = {"content": roles_content, "embeds": [embed]}
    else:
        payload = {"embeds": [embed]}

    try:
        attach = Path(image_path) if image_path else None
        if attach and attach.exists():
            # Multipart request: embed payload + file attachment.
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
        logger.debug(f"Discord alert sent to webhook {webhook_name!r}: {subject!r}")
