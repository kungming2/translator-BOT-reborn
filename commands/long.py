#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
This handles the !long command, which toggles a post as being marked
quite long for translators.
"""
from config import logger
from connection import is_mod
from models.kunulo import Kunulo


def handle(comment, _instruo, _komando, ajo):
    print("Long handler initiated.")

    if is_mod(comment.author):
        logger.info(f"[ZW] Bot: COMMAND: !long, from mod u/{comment.author} on `{ajo.id}`.")

        # This command works as a flip switch.
        # It changes the state to the opposite.
        current_status = ajo.is_long
        new_status = not current_status

        # Take a Kunulo and delete any long informational comment, if the
        # toggle for long status is now False (it's not actually long).
        if not new_status:
            kunulo_object = Kunulo.from_submission(ajo.submission)
            kunulo_object.delete('comment_long')

        ajo.set_long(new_status)
        logger.info(f"[ZW] Bot: Changed post `{ajo.id}`'s long state to '{new_status}.'")

    return
