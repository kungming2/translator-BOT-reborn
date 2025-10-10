#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
Handler for the !reset command, to revert a post back to as if it
were freshly processed. This command can only be called by a mod or the
original author of a post.
"""
from config import logger
from connection import is_mod
from reddit_sender import message_send


def handle(comment, _instruo, _komando, ajo):
    logger.info("Reset handler initiated.")
    original_poster = comment.submission.author

    if is_mod(comment.author) or original_poster == comment.author:
        logger.info(f"[ZW] Bot: COMMAND: !reset, from user u/{comment.author} on `{ajo.id}`.")
        ajo.reset()

        # Message the person who called it.
        reset_msg = (f"The [post](https://redd.it/{ajo.id})'s state has been reset to its original state. "
                     f"This command was called by you [here](https://www.reddit.com{comment.permalink}).")
        message_send(comment.author, subject='[Notification] !reset command successful',
                     body=reset_msg)

        logger.info(f"[ZW] Bot: > Reset everything for the designated post `{ajo.id}`.")

    return
