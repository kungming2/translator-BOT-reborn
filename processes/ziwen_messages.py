#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
Main script to fetch and handle messages. Much of the logic for this
module is in messaging.py.
"""
import traceback

from wasabi import msg

from config import logger
from connection import REDDIT, is_mod, is_valid_user
from error import error_log_extended
from messaging import handle_subscribe, handle_unsubscribe, handle_status, handle_points, handle_add, handle_remove


def ziwen_messages():
    """Main function to process commands via Reddit messaging system."""

    messages = list(REDDIT.inbox.unread(limit=10))

    # Iterate over the messages in the inbox.
    for message in messages:
        if message.author is None:
            continue

        # Invalid user (e.g. shadow-banned)
        if not is_valid_user(message.author):
            logger.error('[ZW] Messages: Invalid author.')
            continue

        message_author = message.author  # Redditor object
        message_subject = message.subject.lower()
        message.mark_read()  # Mark the message as read.

        if "subscribe" in message_subject and "un" not in message_subject:
            handle_subscribe(message, message_author)
        elif "unsubscribe" in message_subject:
            handle_unsubscribe(message, message_author)
        elif "status" in message_subject:
            handle_status(message, message_author)
        elif "points" in message_subject:
            handle_points(message, message_author)
        elif "add" in message_subject and is_mod(message_author):
            handle_add(message, message_author)
        elif "remove" in message_subject and is_mod(message_author):
            handle_remove(message, message_author)

    return


# Primary runtime.
if __name__ == "__main__":
    msg.good("Launching Ziwen messages...")
    try:
        ziwen_messages()
    except Exception:  # intentionally broad: catch all exceptions for logging
        error_entry = traceback.format_exc()
        error_log_extended(error_entry, "Ziwen Messages")
    msg.info("Ziwen messages routine completed.")
