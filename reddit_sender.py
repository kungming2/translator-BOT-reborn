#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
Wrapper for Reddit functions to allow for testing without sending
messages. This wraps functions for comment replies, message replies,
and message sending.
"""

from praw.exceptions import APIException
from praw.models import Comment, Message, Submission
from prawcore import NotFound

from config import SETTINGS, logger
from testing import log_testing_mode

testing_mode = SETTINGS["testing_mode"]


def comment_reply(comment, reply_text):
    """
    Send a reply to a PRAW comment object, or print it if dry-run.

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
            logger.info(f"Replied to comment ID {comment.id} successfully.")
        except (APIException, NotFound):  # Comment has been deleted.
            logger.info(f"Comment ID {comment.id} has been deleted.")
            pass


def message_reply(msg_obj, reply_text):
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


def message_send(redditor_obj, subject, body):
    """
    Send a private message to a Reddit user.
    In testing mode, logs the message instead of sending it.

    Args:
        redditor_obj: A PRAW Redditor object representing the recipient.
        subject (str): The subject line of the message.
        body (str): The body text of the message.
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
        except APIException:
            logger.error(f"Unable to send a private message to u/{username}.")
