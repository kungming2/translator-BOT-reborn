#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
Handles directing of paths as well as the logger.
"""

import logging
import os
import time
from pathlib import Path

import yaml
from prawcore.exceptions import RequestException, ResponseException, ServerError

from time_handling import get_current_month

# Base directory configuration
BASE_DIR: str = os.path.dirname(os.path.realpath(__file__))
# Note that since this is a storage folder and not a module,
# it is capitalized in my logic.
DATA_DIR: str = os.path.join(BASE_DIR, "Data")


# Group related paths into dictionaries for better organization
class Paths:
    """Centralized path configuration for all application files
    Use like:
        Paths.CAT_NAME["KEY_NAME"]
        Paths.SETTINGS["TITLE_MODULE_SETTINGS"]
    """

    # Core database files
    DATABASE: dict[str, str] = {
        "AJO": os.path.join(DATA_DIR, "Databases", "ajo.db"),
        "MAIN": os.path.join(DATA_DIR, "Databases", "main.db"),
        "CACHE": os.path.join(DATA_DIR, "Databases", "cache.db"),
    }

    # Authentication and configuration files
    AUTH: dict[str, str] = {
        "CREDENTIALS": os.path.join(DATA_DIR, "auth.yaml"),
    }

    # Written responses and templates by the bot.
    # Included here for completion; for regular use, utilize
    # responses.py's RESPONSE object instead.
    RESPONSES: dict[str, str] = {
        "TEXT": os.path.join(DATA_DIR, "responses.yaml"),
    }

    # Language reference datasets (infrequently changed)
    DATASETS: dict[str, str] = {
        "COUNTRIES": os.path.join(DATA_DIR, "Datasets", "countries.csv"),
        "LANGUAGE_DATA": os.path.join(DATA_DIR, "Datasets", "language_data.yaml"),
        "UTILITY_LINGVO_DATA": os.path.join(
            DATA_DIR, "Datasets", "utility_lingvo_data.yaml"
        ),
        "ISO_CODES": os.path.join(DATA_DIR, "Datasets", "iso_codes.csv"),
        "ISO_SCRIPT_CODES": os.path.join(DATA_DIR, "Datasets", "iso_script_codes.csv"),
        "ISO_CODES_UPDATES": os.path.join(
            DATA_DIR, "Datasets", "iso_codes_updates.yaml"
        ),
        "OLD_CHINESE": os.path.join(DATA_DIR, "Datasets", "old_chinese.csv"),
        "STATISTICS": os.path.join(DATA_DIR, "Datasets", "_statistics.json"),
        "ZH_ROMANIZATION": os.path.join(
            DATA_DIR, "Datasets", "romanization_chinese.csv"
        ),
        "ZH_BUDDHIST": os.path.join(DATA_DIR, "Datasets", "buddhist_chinese.md"),
        "ZH_CCANTO": os.path.join(DATA_DIR, "Datasets", "ccanto.md"),
    }

    # Log files that are frequently written to
    LOGS: dict[str, str] = {
        "ERROR": os.path.join(DATA_DIR, "Logs", "_log_error.yaml"),
        "COUNTER": os.path.join(DATA_DIR, "Logs", "_log_counter.json"),
        "FILTER": os.path.join(DATA_DIR, "Logs", "_log_filter.md"),
        "EVENTS": os.path.join(DATA_DIR, "Logs", "_log_events.md"),
        "ACTIVITY": os.path.join(DATA_DIR, "Logs", "_log_activity.csv"),
        "TESTING": os.path.join(DATA_DIR, "Logs", "_log_testing.md"),
    }

    # Settings files. No private information should be in these.
    SETTINGS: dict[str, str] = {
        "SETTINGS": os.path.join(DATA_DIR, "Settings", "settings.yaml"),
        "WENJU_SETTINGS": os.path.join(DATA_DIR, "Settings", "wenju_settings.yaml"),
        "DISCORD_SETTINGS": os.path.join(DATA_DIR, "Settings", "discord_settings.yaml"),
        "LANGUAGES_MODULE_SETTINGS": os.path.join(
            DATA_DIR, "Settings", "languages_settings.yaml"
        ),
        "TITLE_MODULE_SETTINGS": os.path.join(
            DATA_DIR, "Settings", "title_settings.yaml"
        ),
    }

    # Wenyuan output files
    WENYUAN: dict[str, str] = {
        "MONTHLY_STATISTICS": os.path.join(
            DATA_DIR, "Wenyuan", "monthly_statistics_output.md"
        ),
        "TRANSLATION_CHALLENGE": os.path.join(DATA_DIR, "translation_challenge.md"),
    }

    # Archival output files
    ARCHIVAL: dict[str, str] = {
        "ALL_IDENTIFIED": os.path.join(DATA_DIR, "Archival", "all_identified.md"),
        "ALL_SAVED": os.path.join(DATA_DIR, "Archival", "all_saved.md"),
    }


def get_reports_directory(base_dir: Path | None = None) -> Path:
    """
    Return the Path object for the current month's reports directory.
    This used for digest reports by tasks in the tasks folder.

    :param base_dir: Optional base path for data storage.
                     Defaults to the "Data" folder next to this file.
    :return: A Path object for the monthly log directory, e.g.:
             /path/to/Data/Reports/2025-10
    """
    if base_dir is None:
        base_dir = Path(__file__).resolve().parent / "Data"

    current_month: str = get_current_month()
    log_dir: Path = base_dir / "Reports" / current_month

    return log_dir


def set_up_logger() -> logging.Logger:
    """
    Set up the unified logger for all routines.

    :return: A logger object.
    """
    # Logging code, defining the basic logger.
    logformatter: str = "%(levelname)s: %(asctime)s - %(message)s"
    logging.basicConfig(
        format=logformatter, level=logging.INFO
    )  # By default, only show INFO or higher levels.
    logger_object: logging.Logger = logging.getLogger(__name__)

    # Define the logging handler (the file to write to with formatting.)
    handler: logging.FileHandler = logging.FileHandler(Paths.LOGS["EVENTS"])
    handler.setLevel(
        logging.INFO
    )  # Change this level for debugging or to display more information.

    # Use UTC time in the formatter
    handler_format: logging.Formatter = logging.Formatter(
        logformatter, datefmt="%Y-%m-%dT%H:%M:%SZ"
    )
    handler_format.converter = time.gmtime  # Use UTC time
    handler.setFormatter(handler_format)
    logger_object.addHandler(handler)

    return logger_object


def load_settings(path: str | Path) -> dict:
    """
    General function for loading settings from a YAML file.
    :param path: Path to YAML file.
    :return: Settings dictionary.
    """
    with open(path, "r", encoding="utf-8") as f:
        settings: dict = yaml.safe_load(f)  # Parse the file's content

    return settings


logger: logging.Logger = set_up_logger()
TRANSIENT_ERRORS = (
    ServerError,
    RequestException,
    ResponseException,
    ConnectionError,
    TimeoutError,
)

# To use, SETTINGS['variable_name']
SETTINGS: dict = load_settings(Paths.SETTINGS["SETTINGS"])
