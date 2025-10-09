#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
Handles processing commands by users.
"""
import importlib
import os
import time

from connection import logger

HANDLERS = {}


def discover_handlers():
    # List all .py files under commands/ (excluding __init__.py)
    files = [f for f in os.listdir(os.path.dirname(__file__))
             if f.endswith('.py') and f != '__init__.py']
    for f in files:
        cmd_name = f[:-3]  # Strip .py
        mod = importlib.import_module(f'commands.{cmd_name}')
        if hasattr(mod, 'handle'):
            HANDLERS[cmd_name] = mod.handle


def update_status(ajo, komando, status_type):
    """
    Shared function to handle status updates for different post types.

    Args:
        ajo: The Ajo object representing the post
        komando: Command object containing data
        status_type: Type of status to set
    """
    current_time = time.time()

    if ajo.type == 'single':
        ajo.set_status(status_type)
        ajo.set_time(status_type, current_time)
    else:
        if ajo.is_defined_multiple:
            defined_languages = komando.data  # Lingvo object list
            for language in defined_languages:
                ajo.set_defined_multiple_status(language.preferred_code,
                                                status_type)
                logger.info(f"Defined multiple post. Marking "
                            f"{language.preferred_code} as {status_type}.")
            ajo.set_time(status_type, current_time)
        else:
            logger.debug("Regular multiple post. Skipping...")
            pass


discover_handlers()


if __name__ == "__main__":
    print(HANDLERS)
