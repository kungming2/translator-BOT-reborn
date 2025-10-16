#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
Handles simple functions to send one-way notifications for Discord.
"""
import requests

from config import Paths, load_settings, logger

webhook_settings = load_settings(Paths.SETTINGS["DISCORD_SETTINGS"])


"""WEBHOOK NOTIFICATIONS (ONE-WAY ALERTS)"""


def select_webhook(selection):
    """Returns the webhook URL, image URL, and color if found, otherwise None."""
    return webhook_settings.get(selection)


def send_discord_alert(subject, message, webhook_name, roles=None):
    """Sends an alert message to the specified Discord webhook
    using an embed with an optional icon and color.
    It can accept an optional roles payload, given as a list."""

    webhook_data = select_webhook(webhook_name)
    if not webhook_data:
        logger.error(f"Webhook not found: '{webhook_name}'. Alert not sent.")
        return  # Exit function early if webhook is invalid

    webhook_url, image_url, color_hex = webhook_data  # Extract URL, image, and color

    # Convert hex color to decimal (Discord API requires decimal)
    color_decimal = int(color_hex.lstrip("#"), 16)

    # Format the roles section. This must be included outside the
    # embed in order to work properly. Roles are sent as a list.
    if roles:
        roles_content = ' '.join(f'<@&{role}>' for role in roles)
        logger.debug(f"Roles: {roles_content}")
    else:
        roles_content = None

    embed = {
        "title": subject,
        "description": message,
        "color": color_decimal,  # Set the embed color
        "thumbnail": {"url": image_url}  # Set the image as the thumbnail
    }

    # Include a roles section before the embed.
    if roles_content:
        payload = {"content": roles_content,
                   "embeds": [embed]}
    else:
        payload = {"embeds": [embed]}

    try:
        response = requests.post(webhook_url, json=payload)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to send Discord alert: {e}")
