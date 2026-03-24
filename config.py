#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
Handles directing of paths as well as the logger.
No prefix for this as this is where the logger is defined.
"""

# ─── Imports ──────────────────────────────────────────────────────────────────

import logging
import os
import time
from pathlib import Path

import yaml
from prawcore.exceptions import RequestException, ResponseException, ServerError

from time_handling import get_current_month

# ─── Path configuration ───────────────────────────────────────────────────────

# Base directory configuration
BASE_DIR: str = os.path.dirname(os.path.realpath(__file__))
# Note that since this is a storage folder and not a module,
# it has a leading underscore to place it towards the top.
DATA_DIR: str = os.path.join(BASE_DIR, "_data")


class Paths:
    """
    Centralized path configuration for all application files.

    Usage:
        Paths.CAT_NAME["KEY_NAME"]
        Paths.SETTINGS["TITLE_MODULE_SETTINGS"]
    """

    # Core translator-BOT database files
    DATABASE: dict[str, str] = {
        "AJO": os.path.join(DATA_DIR, "databases", "ajo.db"),
        "MAIN": os.path.join(DATA_DIR, "databases", "main.db"),
        "CACHE": os.path.join(DATA_DIR, "databases", "cache.db"),
    }

    # Authentication and configuration files
    AUTH: dict[str, str] = {
        "CREDENTIALS": os.path.join(DATA_DIR, "_auth.yaml"),
    }

    # Written responses and templates by the bot.
    # Included here for completion; for regular use, utilize
    # responses.py's RESPONSE object instead.
    # Also has a HTML template for the rendered moderator digest.
    TEMPLATES: dict[str, str] = {
        "RESPONSES": os.path.join(DATA_DIR, "templates", "responses.yaml"),
        "MODERATOR_DIGEST": os.path.join(
            DATA_DIR, "templates", "moderator_digest.html"
        ),
        "TRANSLATION_CHALLENGE": os.path.join(
            DATA_DIR, "templates", "translation_challenge.md"
        ),
    }

    # Language reference datasets (infrequently changed)
    DATASETS: dict[str, str] = {
        "COUNTRIES": os.path.join(DATA_DIR, "datasets", "countries.csv"),
        "LANGUAGE_DATA": os.path.join(DATA_DIR, "datasets", "language_data.yaml"),
        "UTILITY_LINGVO_DATA": os.path.join(
            DATA_DIR, "datasets", "utility_lingvo_data.yaml"
        ),
        "ISO_CODES": os.path.join(DATA_DIR, "datasets", "iso_codes.csv"),
        "ISO_SCRIPT_CODES": os.path.join(DATA_DIR, "datasets", "iso_script_codes.csv"),
        "ISO_CODES_UPDATES": os.path.join(
            DATA_DIR, "datasets", "iso_codes_updates.yaml"
        ),
        "OLD_CHINESE": os.path.join(DATA_DIR, "datasets", "old_chinese.csv"),
        "STATISTICS": os.path.join(DATA_DIR, "datasets", "statistics.json"),
        "ZH_ROMANIZATION": os.path.join(
            DATA_DIR, "datasets", "romanization_chinese.csv"
        ),
        "ZH_BUDDHIST": os.path.join(DATA_DIR, "datasets", "buddhist_chinese.md"),
        "ZH_CCANTO": os.path.join(DATA_DIR, "datasets", "ccanto.md"),
    }

    # Log files that are frequently written to
    LOGS: dict[str, str] = {
        "ERROR": os.path.join(DATA_DIR, "logs", "log_error.yaml"),
        "COUNTER": os.path.join(DATA_DIR, "logs", "log_counter.json"),
        "FILTER": os.path.join(DATA_DIR, "logs", "log_filter.md"),
        "EVENTS": os.path.join(DATA_DIR, "logs", "log_events.md"),
        "ACTIVITY": os.path.join(DATA_DIR, "logs", "log_activity.csv"),
        "MESSAGING": os.path.join(DATA_DIR, "logs", "log_messaging.csv"),
        "TESTING": os.path.join(DATA_DIR, "logs", "log_testing.md"),
    }

    # Settings files. No private information should be in these.
    SETTINGS: dict[str, str] = {
        "SETTINGS": os.path.join(DATA_DIR, "settings", "settings.yaml"),
        "WENJU_SETTINGS": os.path.join(DATA_DIR, "settings", "wenju_settings.yaml"),
        "DISCORD_SETTINGS": os.path.join(DATA_DIR, "settings", "discord_settings.yaml"),
        "LANGUAGES_MODULE_SETTINGS": os.path.join(
            DATA_DIR, "settings", "languages_settings.yaml"
        ),
        "TITLE_MODULE_SETTINGS": os.path.join(
            DATA_DIR, "settings", "title_settings.yaml"
        ),
        "SCHEDULER_SETTINGS": os.path.join(
            DATA_DIR, "settings", "scheduler_settings.yaml"
        ),
    }

    # Wenyuan output files
    WENYUAN: dict[str, str] = {
        "MONTHLY_STATISTICS": os.path.join(
            DATA_DIR, "wenyuan", "monthly_statistics_output.md"
        ),
    }

    # Archival output files
    ARCHIVAL: dict[str, str] = {
        "ALL_IDENTIFIED": os.path.join(DATA_DIR, "archival", "all_identified.md"),
        "ALL_SAVED": os.path.join(DATA_DIR, "archival", "all_saved.md"),
    }

    # Hermes-specific files
    HERMES: dict[str, str] = {
        "HERMES_DATABASE": os.path.join(DATA_DIR, "databases", "hermes.db"),
        "HERMES_SETTINGS": os.path.join(DATA_DIR, "settings", "hermes_settings.yaml"),
        "HERMES_EVENTS": os.path.join(DATA_DIR, "logs", "log_events_hermes.md"),
    }


def get_reports_directory(base_dir: str | None = None) -> Path:
    """
    Return the Path object for the current month's reports directory.
    Used for digest reports by tasks in the tasks folder.

    :param base_dir: Optional base path for data storage.
                     Defaults to DATA_DIR.
    :return: A Path object for the monthly log directory, e.g.:
             /path/to/_data/reports/2025-10
    """
    if base_dir is None:
        base_dir = DATA_DIR

    current_month: str = get_current_month()
    log_dir: Path = Path(base_dir) / "reports" / current_month

    return log_dir


# ─── Settings loader ──────────────────────────────────────────────────────────


def load_settings(path: str | Path) -> dict:
    """
    Load settings from a YAML file.

    :param path: Path to YAML file.
    :return: Settings dictionary.
    """
    with open(path, "r", encoding="utf-8") as f:
        settings: dict = yaml.safe_load(f)
    return settings


# ─── Logging setup ────────────────────────────────────────────────────────────


class TagFormatter(logging.Formatter):
    """
    Custom formatter that injects a default tag value for log records
    that were not emitted through a LoggerAdapter with a 'tag' extra.
    """

    def format(self, record: logging.LogRecord) -> str:
        """Inject a default tag if absent, then delegate to the parent formatter."""
        if not hasattr(record, "tag"):
            record.tag = "-"
        return super().format(record)


def set_up_logger() -> logging.Logger:
    """
    Set up the unified logger for all routines.

    :return: A logger object.
    """
    logformatter: str = (
        "%(levelname)s: %(asctime)s #%(process)d - [%(tag)s] %(message)s"
    )

    # Manually configure the root logger so TagFormatter (which injects a
    # default 'tag' field) applies to ALL handlers globally — including those
    # used by third-party libraries like httpx/openai that bubble up to root.
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    if not root_logger.handlers:
        root_handler = logging.StreamHandler()
        root_handler.setLevel(logging.INFO)
        root_fmt = TagFormatter(logformatter, datefmt="%Y-%m-%dT%H:%M:%SZ")
        root_fmt.converter = time.gmtime
        root_handler.setFormatter(root_fmt)
        root_logger.addHandler(root_handler)

    logger_object: logging.Logger = logging.getLogger(__name__)

    # File handler — writes to the shared events log.
    handler: logging.FileHandler = logging.FileHandler(Paths.LOGS["EVENTS"])
    handler.setLevel(logging.INFO)

    handler_format: TagFormatter = TagFormatter(
        logformatter, datefmt="%Y-%m-%dT%H:%M:%SZ"
    )
    handler_format.converter = time.gmtime  # Use UTC time
    handler.setFormatter(handler_format)
    logger_object.addHandler(handler)

    return logger_object


def get_hermes_logger(tag: str = "HM") -> logging.LoggerAdapter:
    """
    Return a LoggerAdapter that writes to both the shared console handler
    and a Hermes-specific log file, without touching the root logger.
    """
    hermes_logger = logging.getLogger("hermes")
    hermes_logger.propagate = False  # don't bubble up to root/events log

    if not hermes_logger.handlers:
        logformatter = "%(levelname)s: %(asctime)s #%(process)d - [%(tag)s] %(message)s"

        # File handler — Hermes-only log
        file_handler = logging.FileHandler(Paths.HERMES["HERMES_EVENTS"])
        file_handler.setLevel(logging.INFO)
        fmt = TagFormatter(logformatter, datefmt="%Y-%m-%dT%H:%M:%SZ")
        fmt.converter = time.gmtime
        file_handler.setFormatter(fmt)
        hermes_logger.addHandler(file_handler)

        # Console handler — mirrors what the root logger does
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(fmt)
        hermes_logger.addHandler(console_handler)

        hermes_logger.setLevel(logging.INFO)

    return logging.LoggerAdapter(hermes_logger, {"tag": tag})


def enable_debug_logging() -> None:
    """Enable DEBUG level on all handlers for local test runs."""
    logger.setLevel(logging.DEBUG)
    for handler in logger.handlers:
        handler.setLevel(logging.DEBUG)


# ─── Module-level singletons ──────────────────────────────────────────────────

logger: logging.Logger = set_up_logger()

TRANSIENT_ERRORS = (
    ServerError,
    RequestException,
    ResponseException,
    ConnectionError,
    TimeoutError,
)

SETTINGS: dict = load_settings(Paths.SETTINGS["SETTINGS"])
SCHEDULER_SETTINGS: dict = load_settings(Paths.SETTINGS["SCHEDULER_SETTINGS"])
