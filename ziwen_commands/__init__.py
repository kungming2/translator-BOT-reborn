#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
Handles processing commands by users.
...

Logger tag: [ZW:CMD]
"""

import importlib
import logging
import time
from pathlib import Path
from typing import Callable, Union

from config import logger as _base_logger
from models.ajo import Ajo
from models.komando import Komando
from models.lingvo import Lingvo

logger = logging.LoggerAdapter(_base_logger, {"tag": "ZW:CMD"})


# ─── Handler registry ─────────────────────────────────────────────────────────

HANDLERS: dict[str, Callable] = {}


def discover_handlers() -> None:
    """
    List all .py files under commands/ (excluding __init__.py)
    """
    for file_path in Path(__file__).parent.glob("*.py"):
        if file_path.name == "__init__.py":
            continue
        cmd_name = file_path.stem
        mod = importlib.import_module(f".{cmd_name}", package=__package__)
        if hasattr(mod, "handle"):
            HANDLERS[cmd_name] = mod.handle


# ─── Shared status helpers ────────────────────────────────────────────────────


def update_status(
    ajo: "Ajo",
    komando: "Komando",
    status_type: str,
    specific_languages: list | None = None,
) -> None:
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
    current_time = int(time.time())

    if ajo.type == "single":
        if hasattr(ajo, "status") and ajo.status == status_type:
            logger.debug(f"Status is already '{status_type}'. Skipping update.")
            return

        ajo.set_status(status_type)
        ajo.set_time(status_type, current_time)
    else:
        if ajo.is_defined_multiple:
            defined_languages = (
                specific_languages if specific_languages is not None else komando.data
            )

            if not defined_languages:
                logger.debug("No languages to update status for. Skipping.")
                return

            for language in defined_languages:
                ajo.set_defined_multiple_status(language.preferred_code, status_type)
                logger.info(
                    f"Defined multiple post. Marking "
                    f"{language.preferred_code} as {status_type}."
                )
            ajo.set_time(status_type, current_time)
        else:
            logger.debug("Regular multiple post. Skipping...")


# ─── Shared language helpers ──────────────────────────────────────────────────


def update_language(ajo: "Ajo", komando: "Komando") -> None:
    """
    Shared function used to set a language. This will automatically
    handle single and defined multiple posts. The data package will
    generally be a list of Lingvos.

    This is used by !set and !identify.

    Args:
        ajo: An Ajo object whose language will be updated.
        komando: A command object containing a `data` attribute with a sequence
                 of Lingvo objects.

    Raises:
        ValueError: If komando.data contains None values instead of Lingvo objects.

    Note:
        If komando.data contains a single Lingvo, it will be set directly.
        If it contains multiple Lingvos, the entire sequence will be set.
    """
    if komando.data is None:
        raise ValueError("Cannot set language: komando.data is None")
    if None in komando.data:
        raise ValueError(
            "Cannot set language: komando.data contains "
            "None value(s) instead of Lingvo objects"
        )

    languages_to_set: Union[Lingvo, list[Lingvo]]
    if len(komando.data) == 1:
        languages_to_set = komando.data[0]
    else:
        languages_to_set = komando.data

    ajo.set_language(languages_to_set)


# ─── Module-level initialization ─────────────────────────────────────────────

discover_handlers()
