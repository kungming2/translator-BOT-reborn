#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
import time

from config import logger


def handle(comment, instruo, komando, ajo):
    print("Doublecheck handler initiated.")
    logger.info(f"[ZW] Bot: COMMAND: !doublecheck, from u/{comment.author}.")
    current_time = time.time()

    if ajo.type == 'single':
        if ajo.status != "translated" and ajo.status != "doublecheck":
            ajo.set_status('doublecheck')
            ajo.set_time('doublecheck', current_time)
    else:  # TODO Defined multiple logic here
        pass

    # TODO Delete any claimed comment.

    logger.info("[ZW] Bot: > Marked post as 'Needs Review.'")
    ajo.update_reddit()
