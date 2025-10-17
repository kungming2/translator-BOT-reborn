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
    """
    List all .py files under commands/ (excluding __init__.py)
    """
    files = [
        f
        for f in os.listdir(os.path.dirname(__file__))
        if f.endswith(".py") and f != "__init__.py"
    ]
    for f in files:
        cmd_name = f[:-3]  # Strip .py
        mod = importlib.import_module(f"commands.{cmd_name}")
        if hasattr(mod, "handle"):
            HANDLERS[cmd_name] = mod.handle


def update_status(ajo, komando, status_type, specific_languages=None):
    """
    Shared function to handle status updates for different post types.
    This function is used by: !translated, !doublecheck, !missing,
                              and !claim

    Args:
        ajo: The Ajo object representing the post
        komando: Command object containing data
        status_type: Type of status to set
        specific_languages: Optional list of language objects to update.
                          If provided, these will be used instead of komando.data
    """
    current_time = time.time()

    if ajo.type == "single":
        # Skip if status is already set to the requested value
        if hasattr(ajo, "status") and ajo.status == status_type:
            logger.debug(f"Status is already '{status_type}'. Skipping update.")
            return

        ajo.set_status(status_type)
        ajo.set_time(status_type, current_time)
    else:
        if ajo.is_defined_multiple:
            # Use specific_languages if provided, otherwise fall back to komando.data
            defined_languages = (
                specific_languages if specific_languages is not None else komando.data
            )

            for language in defined_languages:
                ajo.set_defined_multiple_status(language.preferred_code, status_type)
                logger.info(
                    f"Defined multiple post. Marking "
                    f"{language.preferred_code} as {status_type}."
                )
            ajo.set_time(status_type, current_time)
        else:
            logger.debug("Regular multiple post. Skipping...")
            pass


def update_language(ajo, komando):
    """
    Shared function used to set a language. This will automatically
    handle single and defined multiple posts. The data package will
    generally be a list of Lingvos.

    This is used by !set and !identify.
    """
    # Convert a list of single language items to a single object.
    if len(komando.data) == 1:
        languages_to_set = komando.data[0]
    else:
        languages_to_set = komando.data

    # Update the Ajo's language.
    ajo.set_language(languages_to_set)

    return


discover_handlers()  # surface which commands are available


if __name__ == "__main__":
    print(HANDLERS)
