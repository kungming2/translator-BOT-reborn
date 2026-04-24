#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
Main script to fetch and handle messages. Much of the logic for this
module is in messaging.py; this function primarily reads the messages
and then passes it on to that module.
...

Logger tag: [ZW:M]
"""

import logging

from praw.models import Message, Redditor

from config import TRANSIENT_ERRORS
from config import logger as _base_logger
from reddit.connection import REDDIT, is_mod, is_valid_user
from reddit.messaging import (
    handle_add,
    handle_points,
    handle_remove,
    handle_status,
    handle_subscribe,
    handle_unsubscribe,
)

logger = logging.LoggerAdapter(_base_logger, {"tag": "ZW:M"})


# ─── Main message processing loop ────────────────────────────────────────────


def ziwen_messages() -> None:
    """Main function to process commands via Reddit messaging system.

    Processes unread inbox messages and routes them to appropriate handlers
    based on message subject. Supports subscription management, status checks,
    points queries, and moderator commands (add/remove).

    Valid commands (case-insensitive subjects):
    - subscribe: Subscribe to notifications
    - unsubscribe: Unsubscribe from notifications
    - status: Check subscription status
    - points: Check points balance
    - add: Add user (moderators only)
    - remove: Remove user (moderators only)
    """
    try:
        messages = list(REDDIT.inbox.unread(limit=10))
    except TRANSIENT_ERRORS as ex:
        logger.warning(f"Encountered a transient error while fetching messages: {ex}")
        return
    except Exception:
        logger.exception("Encountered an unexpected error while fetching messages.")
        return

    if messages:
        logger.info(f"Processing {len(messages)} unread message(s)")

    for message in messages:
        message_id = getattr(message, "id", "<unknown>")

        try:
            if not isinstance(message, Message):
                logger.info(
                    "Skipping unread inbox item `%s` of unsupported type `%s`.",
                    message_id,
                    type(message).__name__,
                )
                continue

            message_subject = message.subject.strip().lower()

            # Now-deleted author.
            if message.author is None:
                logger.info("Skipping message `%s` with deleted author.", message_id)
                continue

            message_author: Redditor = message.author

            # Invalid user (e.g. shadow-banned)
            if not is_valid_user(message_author.name):
                logger.warning(f"Messages: Invalid author u/{message_author}.")
                continue

            # ── Subject routing ────────────────────────────────────────────────

            if "unsubscribe" in message_subject:
                handle_unsubscribe(message, message_author)
            elif "subscribe" in message_subject:
                handle_subscribe(message, message_author)
            elif "status" in message_subject:
                handle_status(message, message_author)
            elif "points" in message_subject:
                handle_points(message, message_author)
            elif message_subject == "add":
                if is_mod(message_author):
                    handle_add(message, message_author)
                else:
                    logger.warning(
                        "Ignoring unauthorized `add` message from u/%s.",
                        message_author,
                    )
            elif message_subject == "remove":
                if is_mod(message_author):
                    handle_remove(message, message_author)
                else:
                    logger.warning(
                        "Ignoring unauthorized `remove` message from u/%s.",
                        message_author,
                    )
            else:
                logger.info(
                    f"Unrecognised message subject {message_subject!r} from u/{message_author}. Ignoring."
                )
        except TRANSIENT_ERRORS as ex:
            logger.warning(
                "Transient error while processing message `%s`: %s",
                message_id,
                ex,
            )
        except Exception:
            logger.exception("Failed while processing message `%s`.", message_id)
        finally:
            try:
                message.mark_read()
            except Exception:
                logger.exception("Failed to mark message `%s` as read.", message_id)

    return
