#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
Wrapper for Reddit functions to allow for testing without sending
messages. This wraps functions for comment replies, message replies,
and message sending.
"""
from config import SETTINGS, logger
from testing import log_testing_mode

testing_mode = SETTINGS['testing_mode']


def comment_reply(comment, reply_text):
    """
    Send a reply to a PRAW comment object, or print it if dry-run.

    Args:
        comment: PRAW Comment object.
        reply_text: Text to reply with.
    """
    if testing_mode:
        logger.info(f"[TESTING MODE] Would reply to comment ID {comment.id} by {comment.author}:")
        logger.info(reply_text)

        log_testing_mode(
            output_text=reply_text,
            title="Comment Reply",
            metadata={
                "Comment ID": comment.id,
                "Author": str(comment.author),
                "Permalink": comment.permalink
            }
        )
    else:
        comment.reply(reply_text)
        logger.info(f"Replied to comment ID {comment.id} successfully.")


def message_reply(message_obj, reply_text):
    """
    Reply to a Reddit comment or private message object.
    In testing mode, logs the reply instead of sending it.

    Args:
        message_obj: A PRAW Comment or Message object.
        reply_text: The reply text to send.
    """
    if testing_mode:
        logger.info(f"[TESTING MODE] Would reply to {getattr(message_obj, 'id', 'unknown')} by {getattr(message_obj, 'author', 'unknown')}:")
        logger.info(reply_text)

        log_testing_mode(
            output_text=reply_text,
            title="Reply",
            metadata={
                "Reply Target": getattr(message_obj, 'id', 'unknown'),
                "Author": str(getattr(message_obj, 'author', 'unknown'))
            },
        )
    else:
        message_obj.reply(reply_text)
        logger.info(f"Replied to {getattr(message_obj, 'id', 'unknown')} successfully.")


def message_send(redditor_obj, subject, body):
    """
    Send a private message to a Reddit user.
    In testing mode, logs the message instead of sending it.

    Args:
        redditor_obj: A PRAW Redditor object representing the recipient.
        subject (str): The subject line of the message.
        body (str): The body text of the message.
    """
    username = getattr(redditor_obj, 'name', 'unknown')

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
        redditor_obj.message(subject=subject, message=body)
        logger.info(f"Sent a private message to u/{username} successfully.")
