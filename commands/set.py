#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
!set is a mod-accessible means of setting the post flair. The mod's
comment is removed by AutoModerator so it looks like nothing happened.
"""
from config import logger
from connection import is_mod
from reddit_sender import message_send


def handle(comment, _instruo, komando, ajo):
    print("Set handler initiated.")

    # Check to see if the person calling this command is a moderator
    if not is_mod(comment.author):
        logger.debug(f"u/{comment.author} is not a mod. Skipping...")
        return

    logger.info(f"[ZW] Bot: COMMAND: !set, from moderator u/{comment.author} on `{ajo.id}`.")

    # Update the Ajo's language for a single-language post.
    if ajo.type == 'single':
        new_language = komando.data[0]  # Lingvo
        ajo.set_language(new_language)

        # Message the mod who called this command.
        set_msg = f"The [post](https://redd.it/{ajo.id}) has been set to the language `{new_language.preferred_code}` (`{new_language.name}`)."
        message_send(comment.author, subject='[Notification] !set command successful', body=set_msg)
        logger.info("Informed moderator of command success.")
    else:  # Defined multiple post.
        # TODO logic here
        pass

    ajo.update_reddit()
