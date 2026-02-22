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
    reddit_reply: Reply to a Comment, Message, or Submission
    message_send: Send a private message to a Redditor
"""

from praw.exceptions import APIException
from praw.models import Comment, Message, Redditor, Submission
from prawcore import NotFound
from prawcore.exceptions import ServerError

from config import SETTINGS, logger
from testing import log_testing_mode

testing_mode = SETTINGS["testing_mode"]


def reddit_reply(
    msg_obj: Comment | Message | Submission,
    reply_text: str,
    distinguish: bool = False,
) -> Comment | Submission | None:
    """
    Reply to a Reddit object (Comment, Message, or Submission).
    In testing mode, logs the reply instead of sending it.

    Args:
        msg_obj: A PRAW Comment, Message, or Submission object.
        reply_text: The reply text to send.
        distinguish: If True, distinguishes the reply as a mod comment.
                     Only applies when the returned object is a Comment;
                     distinguish is not supported on Message replies.
    """
    target_id = getattr(msg_obj, "id", "unknown")
    target_author = getattr(msg_obj, "author", "unknown")

    if testing_mode:
        logger.info(f"[TESTING MODE] Would reply to `{target_id}` by {target_author}:")
        logger.info(reply_text)

        log_testing_mode(
            output_text=reply_text,
            title="Reply",
            metadata={
                "Object Type": type(msg_obj).__name__,
                "Reply Target": target_id,
                "Author": str(target_author),
                "Distinguish": distinguish,
            },
        )
        return None

    # Actual reply
    if isinstance(msg_obj, (Comment, Message, Submission)):
        try:
            returned_object = msg_obj.reply(reply_text)
            logger.info(f"Replied to `{target_id}` successfully.")

            if distinguish and isinstance(returned_object, Comment):
                returned_object.mod.distinguish(sticky=False)
                logger.info(f"Distinguished reply to `{target_id}`.")
        except NotFound:
            logger.info(f"Object `{target_id}` has been deleted; reply not sent.")
        except APIException:
            logger.exception(f"Unexpected error replying to `{target_id}`.")
        else:
            return returned_object
    else:
        logger.warning(
            f"Unsupported object type {type(msg_obj).__name__}; no reply attempted."
        )
        return None


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
            logger.info(f"Successfully sent a private message to u/{username}.")
        except APIException as ex:
            if ex.error_type == "NOT_WHITELISTED_BY_USER_MESSAGE":
                # Specific Reddit PM restriction
                logger.warning(
                    f"Cannot send message to u/{username}: user has disabled PMs or has not whitelisted the bot."
                )
            elif ex.error_type == "RATELIMIT":
                # Rate limited by the API.
                logger.info(
                    f"Reddit API rate limit reached. Cannot send message to u/{username}."
                )
            elif ex.error_type == "USER_DOESNT_EXIST":
                # User no longer exists.
                logger.info(
                    f"User does not exist. Unable to send message to u/{username}."
                )
            else:
                logger.warning(
                    f"Unable to send a private message to u/{username}: {ex.error_type} - {ex.message}"
                )
        except ServerError as ex:  # Server-side issue.
            logger.exception(f"Encountered server error: {ex}.")
