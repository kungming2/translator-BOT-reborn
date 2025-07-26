#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
This handles the !long command, which toggles a post as being
quite long for translators.
"""
from config import logger
from connection import is_mod


def handle(comment, instruo, komando, ajo):
    print("Long handler initiated.")

    if is_mod(comment.author):
        logger.info(f"[ZW] Bot: COMMAND: !long, from mod u/{comment.author} on `{ajo.id}`.")

        # This command works as a flip switch. It changes the state to the opposite.
        current_status = ajo.is_long
        new_status = not current_status

        # TODO take a Kunulo and delete any long informational comment.

        ajo.set_long(new_status)
        logger.info(f"[ZW] Bot: Changed post `{ajo.id}`'s long state to '{new_status}.'")
        ajo.update_reddit()
