#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
!set is a mod-accessible means of setting the post flair. The mod's
comment is removed by AutoModerator so it looks like nothing happened.
"""
from config import logger
from connection import is_mod
from models.kunulo import Kunulo
from reddit_sender import message_send

from . import update_language


def handle(comment, _instruo, komando, ajo):
    logger.info("Set handler initiated.")

    # Check to see if the person calling this command is a moderator
    if not is_mod(comment.author):
        logger.debug(f"u/{comment.author} is not a mod. Skipping...")
        return

    logger.info(f"[ZW] Bot: COMMAND: !set, from moderator u/{comment.author} on `{ajo.id}`.")

    # Update the Ajo's language(s) post.
    update_language(ajo, komando)

    # Delete any pre-existing defined multiple or "Unknown" comment.
    delete_tags = ['comment_defined_multiple', 'comment_unknown']
    for tag in delete_tags:
        kunulo_object = Kunulo.from_submission(ajo.submission)
        kunulo_object.delete(tag)

    # Message the mod who called this command.
    new_language = komando.data[0]  # Lingvo
    set_msg = (f"The [post](https://www.reddit.com{ajo.permalink}) has been set to the language "
               f"`{new_language.preferred_code}` (`{new_language.name}`).")
    message_send(comment.author, subject='[Notification] !set command successful', body=set_msg)
    logger.info("Informed moderator of command success.")

    return
