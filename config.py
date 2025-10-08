#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
Handles directing of paths as well as the logger.
"""

import logging
import os

import yaml

# Base directory configuration
BASE_DIR = os.path.dirname(os.path.realpath(__file__))
# Note that since this is a storage folder and not a module,
# it is capitalized in my logic.
DATA_DIR = os.path.join(BASE_DIR, "Data")


# Group related paths into dictionaries for better organization
class Paths:
    """Centralized path configuration for all application files"""

    # Core database files
    DATABASE = {
        "AJO": os.path.join(DATA_DIR, "Databases", "ajo.db"),
        "MAIN": os.path.join(DATA_DIR, "Databases", "main.db"),
        "CACHE": os.path.join(DATA_DIR, "Databases", "cache.db"),
    }

    # Authentication and configuration files
    AUTH = {
        "CREDENTIALS": os.path.join(DATA_DIR, "auth.yaml"),
    }

    # Written responses by the bot
    RESPONSES = {
        "TEXT": os.path.join(DATA_DIR, "responses.yaml"),
    }

    # Language reference datasets (infrequently changed)
    DATASETS = {
        "COUNTRIES": os.path.join(DATA_DIR, "Datasets", "countries.csv"),
        "LANGUAGE_DATA": os.path.join(DATA_DIR, "Datasets", "language_data.yaml"),
        "UTILITY_LINGVO_DATA": os.path.join(DATA_DIR, "Datasets", "utility_lingvo_data.yaml"),
        "ISO_CODES": os.path.join(DATA_DIR, "Datasets", "iso_codes.csv"),
        "ISO_SCRIPT_CODES": os.path.join(DATA_DIR, "Datasets", "iso_script_codes.csv"),
        "OLD_CHINESE": os.path.join(DATA_DIR, "Datasets", "old_chinese.csv"),
        "ZH_ROMANIZATION": os.path.join(DATA_DIR, "Datasets", "romanization_chinese.csv"),
        "ZH_BUDDHIST": os.path.join(DATA_DIR, "Datasets", "buddhist_chinese.md"),
        "ZH_CCANTO": os.path.join(DATA_DIR, "Datasets", "ccanto.md"),
    }

    # Log files that are frequently written to
    LOGS = {
        "ERROR": os.path.join(DATA_DIR, "_log_error.yaml"),
        "COUNTER": os.path.join(DATA_DIR, "_log_counter.json"),
        "FILTER": os.path.join(DATA_DIR, "_log_filter.md"),
        "EVENTS": os.path.join(DATA_DIR, "_log_events.md"),
        "ACTIVITY": os.path.join(DATA_DIR, "_log_activity.csv"),
        "HASHES": os.path.join(DATA_DIR, "_log_hashes.json"),
        "STATISTICS": os.path.join(DATA_DIR, "_statistics.json"),
        "TESTING": os.path.join(DATA_DIR, "_log_testing.md"),
    }

    # Settings files. No private information should be in these.
    SETTINGS = {
        "SETTINGS": os.path.join(DATA_DIR, "Settings", "settings.yaml"),
        "DISCORD_SETTINGS": os.path.join(DATA_DIR, "Settings", "discord_settings.yaml"),
        "LANGUAGES_MODULE_SETTINGS": os.path.join(DATA_DIR, "Settings", "languages_settings.yaml"),
        "TITLE_MODULE_SETTINGS": os.path.join(DATA_DIR, "Settings", "title_settings.yaml")
    }

    # Wenyuan output files
    WENYUAN = {
        "STATISTICS": os.path.join(DATA_DIR, "wy_statistics_output.md"),
        "TITLE_LOG": os.path.join(DATA_DIR, "wy_title_test_output.md"),
        "WEEKLY_CHALLENGE": os.path.join(DATA_DIR, "wy_weekly_challenge.md"),
        "ALL_IDENTIFIED": os.path.join(DATA_DIR, "Archival", "all_identified.md"),
        "ALL_SAVED": os.path.join(DATA_DIR, "Archival", "all_saved.md"),
    }


def set_up_logger():
    # Logging code, defining the basic logger.
    logformatter = '%(levelname)s: %(asctime)s - %(message)s'
    logging.basicConfig(format=logformatter, level=logging.INFO)  # By default, only show INFO or higher levels.
    logger_object = logging.getLogger(__name__)

    # Define the logging handler (the file to write to with formatting.)
    handler = logging.FileHandler(Paths.LOGS['EVENTS'])
    handler.setLevel(logging.INFO)  # Change this level for debugging or to display more information.
    handler_format = logging.Formatter(logformatter, datefmt="%Y-%m-%d [%I:%M:%S %p]")
    handler.setFormatter(handler_format)
    logger_object.addHandler(handler)

    return logger_object


def load_settings(path):
    """General function for loading settings from a YAML file."""
    with open(path, 'r', encoding='utf-8') as f:
        settings = yaml.safe_load(f)  # Parse the file's content

    return settings


logger = set_up_logger()
# To use, SETTINGS['variable_name']
SETTINGS = load_settings(Paths.SETTINGS['SETTINGS'])
