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

_data = Path(DATA_DIR)


class Paths:
    """
    Centralized path configuration for all application files.

    Usage:
        Paths.CAT_NAME["KEY_NAME"]
        Paths.SETTINGS["TITLE_SETTINGS"]
    """

    # Core translator-BOT database files
    _db = _data / "databases"
    DATABASE: dict[str, str] = {
        "AJO": str(_db / "ajo.db"),
        "CACHE": str(_db / "cache.db"),
        "MAIN": str(_db / "main.db"),
    }

    # Authentication and configuration files
    _au = _data / "auth"
    AUTH: dict[str, str] = {
        "API": str(_au / "api.yaml"),
        "CREDENTIALS": str(_au / "reddit.yaml"),
    }

    # Written responses and templates by the bot.
    # Included here for completion; for regular use, utilize
    # responses.py's RESPONSE object instead.
    # Also has a HTML template for the rendered moderator digest.
    _tmpl = _data / "templates"
    TEMPLATES: dict[str, str] = {
        "RESPONSES": str(_tmpl / "responses.yaml"),
        "MODERATOR_DIGEST": str(_tmpl / "moderator_digest.html"),
        "TRANSLATION_CHALLENGE": str(_tmpl / "translation_challenge.md"),
    }

    # Language reference datasets (almost never changed)
    _ds = _data / "datasets"
    DATASETS: dict[str, str] = {
        "COUNTRIES": str(_ds / "dataset_countries.csv"),
        "ISO_CODES": str(_ds / "dataset_iso_codes.csv"),
        "ISO_SCRIPT_CODES": str(_ds / "dataset_iso_script_codes.csv"),
        "ZH_BUDDHIST": str(_ds / "zh_buddhist_dict.md"),
        "ZH_CANTONESE": str(_ds / "zh_cantonese_dict.md"),
        "ZH_OCMC": str(_ds / "zh_ocmc.csv"),
        "ZH_ROMANIZATION": str(_ds / "zh_romanization.csv"),
    }

    # State files are like datasets, but are occasionally changed
    _st = _data / "states"
    STATES: dict[str, str] = {
        "LANGUAGE_DATA": str(_st / "language_data.yaml"),
        "ISO_CODES_UPDATES": str(_st / "iso_codes_updates.yaml"),
        "STATISTICS": str(_st / "statistics.json"),
        "UTILITY_LINGVO_DATA": str(_st / "utility_lingvo_data.yaml"),
    }

    # Log files that are frequently written to and changed
    _lg = _data / "logs"
    LOGS: dict[str, str] = {
        "ACTIVITY": str(_lg / "log_activity.csv"),
        "COUNTER": str(_lg / "log_counter.json"),
        "ERROR": str(_lg / "log_error.yaml"),
        "EVENTS": str(_lg / "log_events.md"),
        "FILTER": str(_lg / "log_filter.md"),
        "MESSAGING": str(_lg / "log_messaging.csv"),
        "TESTING": str(_lg / "log_testing.md"),
    }

    # Settings files. No private information should be in these.
    _cfg = _data / "settings"
    SETTINGS: dict[str, str] = {
        "SETTINGS": str(_cfg / "settings.yaml"),  # Main settings
        "DISCORD_SETTINGS": str(_cfg / "discord_settings.yaml"),
        "LANGUAGES_SETTINGS": str(_cfg / "languages_settings.yaml"),
        "SCHEDULER_SETTINGS": str(_cfg / "scheduler_settings.yaml"),
        "TITLE_SETTINGS": str(_cfg / "title_settings.yaml"),
        "WENJU_SETTINGS": str(_cfg / "wenju_settings.yaml"),
    }

    # Wenyuan output files
    _wy = _data / "wenyuan"
    WENYUAN: dict[str, str] = {
        "MONTHLY_STATISTICS": str(_wy / "monthly_statistics_output.md"),
    }  # currently unused

    # Archival output files
    _ar = _data / "archival"
    ARCHIVAL: dict[str, str] = {
        "ALL_IDENTIFIED": str(_ar / "all_identified.md"),
        "ALL_SAVED": str(_ar / "all_saved.md"),
    }

    # Chinese Reference logger output
    CR: dict[str, str] = {
        "CR_EVENTS": str(_lg / "log_events_cr.md"),
    }

    # Hermes-specific files (spread across databases/, settings/, and
    # logs/) - Hermes is not specifically part of translator-BOT and
    # is thus grouped separately.
    HERMES: dict[str, str] = {
        "HERMES_DATABASE": str(_db / "hermes.db"),
        "HERMES_EVENTS": str(_lg / "log_events_hermes.md"),
        "HERMES_SETTINGS": str(_cfg / "hermes_settings.yaml"),
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
    with open(path, encoding="utf-8") as f:
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


def get_specific_logger(tag: str, log_path: str | None = None) -> logging.LoggerAdapter:
    """
    Return a LoggerAdapter that writes to both the shared console handler
    and a bot-specific log file, without touching the root logger.

    :param tag: Log tag shown in the formatter (e.g. "HM", "CR").
    :param log_path: Path to the bot-specific log file.
    """
    # Use a logger name derived from the tag so each bot gets its own
    # Logger instance with its own handlers, not a shared one.
    bot_logger = logging.getLogger(f"bot.{tag.lower()}")
    bot_logger.propagate = False  # don't bubble up to root/events log

    if not bot_logger.handlers:
        logformatter = "%(levelname)s: %(asctime)s #%(process)d - [%(tag)s] %(message)s"

        # File handler — bot-specific log
        file_handler = logging.FileHandler(log_path)
        file_handler.setLevel(logging.INFO)
        fmt = TagFormatter(logformatter, datefmt="%Y-%m-%dT%H:%M:%SZ")
        fmt.converter = time.gmtime
        file_handler.setFormatter(fmt)
        bot_logger.addHandler(file_handler)

        # Console handler — mirrors what the root logger does
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(fmt)
        bot_logger.addHandler(console_handler)

        bot_logger.setLevel(logging.INFO)

    return logging.LoggerAdapter(bot_logger, {"tag": tag})


def enable_debug_logging() -> None:
    """Enables DEBUG level on all handlers for local test runs."""
    logger.setLevel(logging.DEBUG)
    for handler in logger.handlers:
        handler.setLevel(logging.DEBUG)


# ─── Module-level singletons ──────────────────────────────────────────────────

logger: logging.Logger = set_up_logger()

# Transient/temporary API errors that may succeed on retry next cycle
TRANSIENT_ERRORS = (
    ServerError,
    RequestException,
    ResponseException,
    ConnectionError,
    TimeoutError,
)

SETTINGS: dict = load_settings(Paths.SETTINGS["SETTINGS"])
SCHEDULER_SETTINGS: dict = load_settings(Paths.SETTINGS["SCHEDULER_SETTINGS"])
