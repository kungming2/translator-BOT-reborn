#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
Wrapper for Reddit functions to allow for testing without sending
messages. This wraps functions for comment replies, message replies,
and message sending. Testing mode is set in settings.yaml.

This module provides a safe abstraction layer for Reddit interactions:
- In production mode, it sends actual Reddit comments/messages
- In testing mode, it logs the content instead of sending to Reddit
- All functions handle common exceptions (APIException, NotFound) gracefully

Functions:
    comment_reply: Reply to a Reddit comment
    message_reply: Reply to a Comment, Message, or Submission
    message_send: Send a private message to a Redditor
"""

from praw.exceptions import APIException
from praw.models import Comment, Message, Redditor, Submission
from prawcore import NotFound

from config import SETTINGS, logger
from testing import log_testing_mode

testing_mode = SETTINGS["testing_mode"]


def comment_reply(comment: Comment, reply_text: str) -> None:
    """
    Send a reply to a PRAW comment object, or logs it in testing mode.

    Args:
        comment: PRAW Comment object.
        reply_text: Text to reply with.
    """
    if testing_mode:
        logger.info(
            f"[TESTING MODE] Would reply to comment ID "
            f"{comment.id} by {comment.author}:"
        )
        logger.info(reply_text)

        log_testing_mode(
            output_text=reply_text,
            title="Comment Reply",
            metadata={
                "Comment ID": comment.id,
                "Author": str(comment.author),
                "Permalink": comment.permalink,
            },
        )
    else:
        try:
            comment.reply(reply_text)
            logger.info(f"Replied to comment ID `{comment.id}` successfully.")
        except (APIException, NotFound):  # Comment has been deleted.
            logger.info(f"Comment ID `{comment.id}` has been deleted.")
            pass


def message_reply(msg_obj: Comment | Message | Submission, reply_text: str) -> None:
    """
    Reply to a Reddit object (Comment, Message, or Submission).
    In testing mode, logs the reply instead of sending it.

    Args:
        msg_obj: A PRAW Comment, Message, or Submission object.
        reply_text: The reply text to send.
    """
    target_id = getattr(msg_obj, "id", "unknown")
    target_author = getattr(msg_obj, "author", "unknown")

    if testing_mode:
        logger.info(f"[TESTING MODE] Would reply to {target_id} by {target_author}:")
        logger.info(reply_text)

        log_testing_mode(
            output_text=reply_text,
            title="Reply",
            metadata={"Reply Target": target_id, "Author": str(target_author)},
        )
        return

    # Actual reply
    if isinstance(msg_obj, (Comment, Message, Submission)):
        try:
            msg_obj.reply(reply_text)
            logger.info(f"Replied to {target_id} successfully.")
        except (APIException, NotFound):
            logger.exception(f"Unexpected error replying to {target_id}.")
    else:
        logger.warning(
            f"Unsupported object type {type(msg_obj).__name__}; no reply attempted."
        )


def message_send(redditor_obj: Redditor, subject: str, body: str) -> None:
    """
    Send a private message to a Reddit user.
    In testing mode, logs the message instead of sending it.

    Args:
        redditor_obj: A PRAW Redditor object representing the recipient.
        subject: The subject line of the message.
        body: The body text of the message.
    """
    username = getattr(redditor_obj, "name", "unknown")

    if testing_mode:
        logger.info(f"[TESTING MODE] Would send a message to u/{username}")
        logger.info(f"Subject: {subject}")
        logger.info(f"Body: {body}")

        log_testing_mode(
            output_text=body,
            title=f"PM to u/{username}",
            metadata={
                "Recipient": username,
                "Subject": subject,
            },
        )
    else:
        try:
            redditor_obj.message(subject=subject, message=body)
            logger.info(f"Sent a private message to u/{username} successfully.")
        except APIException as ex:
            if ex.error_type == "NOT_WHITELISTED_BY_USER_MESSAGE":
                # Specific Reddit PM restriction
                logger.warning(
                    f"Cannot send message to u/{username}: user has disabled PMs or has not whitelisted the bot."
                )
            else:
                logger.error(
                    f"Unable to send a private message to u/{username}: {ex.error_type} - {ex.message}"
                )
