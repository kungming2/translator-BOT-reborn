#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
Handles error logging and retrieval.

This module provides a comprehensive error logging system that stores errors
in YAML format with contextual information. It supports two logging modes:

1. Basic logging (error_log_basic):
   - Simple error logging with timestamp and bot version
   - Quick error capture without additional context

2. Extended logging (error_log_extended):
   - Full error logging with Reddit context
   - Captures the last post and comment from r/translator
   - Provides rich context for debugging

Error logs are stored in YAML format with custom formatting for multi-line
strings (using pipe notation) for better readability. The retrieve_error_log
function can format these logs as Markdown for easy review.

Typical usage:
    from error import error_log_extended
    try:
        # risky operation
    except Exception:
        error_log_extended(traceback.format_exc(), "Ziwen")
...

Logger tag: [ERROR]
"""

# ─── Imports ──────────────────────────────────────────────────────────────────

import logging
import os
import tempfile
from datetime import UTC, datetime, timedelta
from typing import Any

import yaml

from config import SETTINGS, Paths
from config import logger as _base_logger
from database import get_recent_event_log_lines
from reddit.connection import REDDIT
from time_handling import get_current_utc_time, time_convert_to_string

# ─── Module-level constants ───────────────────────────────────────────────────

logger = logging.LoggerAdapter(_base_logger, {"tag": "ERROR"})


# ─── YAML serialization ───────────────────────────────────────────────────────


class CustomDumper(yaml.SafeDumper):
    """Custom YAML dumper that uses pipe notation for multi-line strings."""

    pass


def _str_representer(dumper: yaml.Dumper, data: str) -> yaml.ScalarNode:
    """
    Custom string representer for YAML that formats multi-line strings
    with pipe notation (|) for better readability in error logs.
    """
    if "\n" in data:
        return dumper.represent_scalar("tag:yaml.org,2002:str", data, style="|")
    return dumper.represent_scalar("tag:yaml.org,2002:str", data)


# PyCharm incorrectly flags this - SafeDumper is compatible with CustomDumper
# noinspection PyTypeChecker
CustomDumper.add_representer(str, _str_representer)  # type: ignore[arg-type]


def _atomic_yaml_dump(path: str, data: list[dict[str, Any]]) -> None:
    """
    Write *data* as YAML to *path* atomically using a sibling temp file
    and ``os.replace``, so a concurrent write or mid-write crash cannot
    leave the log in a partially-written state.

    :param path: Destination file path.
    :param data: List of log-entry dicts to serialize.
    """
    dir_name = os.path.dirname(path) or "."
    fd, tmp_path = tempfile.mkstemp(dir=dir_name, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            yaml.dump(
                data,
                f,
                Dumper=CustomDumper,
                allow_unicode=True,
                sort_keys=False,
                default_flow_style=False,
            )
        os.replace(tmp_path, path)
    except Exception:
        try:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
        except OSError:
            pass
        raise


def _load_error_entries(path: str) -> list[dict[str, Any]]:
    """
    Load error entries from YAML, returning an empty list if the file is missing
    or unreadable due to invalid YAML.

    :param path: YAML log file path.
    :return: List of error entry dicts.
    """
    try:
        with open(path, encoding="utf-8") as f:
            loaded = yaml.safe_load(f)
    except FileNotFoundError:
        return []
    except yaml.YAMLError as e:
        logger.warning(f"Error_Log: Could not parse YAML at {path}: {e}")
        return []

    if isinstance(loaded, list):
        return loaded

    if loaded is None:
        return []

    logger.warning(
        f"Error_Log: Expected list structure in YAML at {path}; got {type(loaded).__name__}."
    )
    return []


# ─── Context capture ──────────────────────────────────────────────────────────


def _record_last_post_and_comment() -> dict[str, str]:
    """
    Retrieve the latest post and comment from r/translator for
    reference in error logging.

    :return: A dictionary with keys:
             - 'last_post': Formatted string of the last post's timestamp and link.
             - 'last_comment': Formatted string of the last comment's timestamp, link, and body.
    """
    fallback_time = get_current_utc_time()

    post_info = {
        "timestamp": fallback_time,
        "link": "",
    }

    comment_info = {
        "timestamp": fallback_time,
        "link": "",
        "body": "",
    }

    for submission in REDDIT.subreddit(SETTINGS["subreddit"]).new(limit=1):
        post_time = time_convert_to_string(submission.created_utc)
        post_info["timestamp"] = post_time
        post_info["link"] = f"https://www.reddit.com{submission.permalink}"
        break

    for comment in REDDIT.subreddit(SETTINGS["subreddit"]).comments(limit=1):
        comment_time = time_convert_to_string(comment.created_utc)
        replaced_body = comment.body.replace("\n", "\n> ")
        formatted_body = f"> {replaced_body}"
        comment_info.update(
            {
                "timestamp": comment_time,
                "link": f"https://www.reddit.com{comment.permalink}",
                "body": formatted_body,
            }
        )
        break

    last_post = f"{post_info['timestamp']}: {post_info['link']}"
    last_comment = (
        f"{comment_info['timestamp']}: {comment_info['link']}\n{comment_info['body']}"
    )

    return {
        "last_post": last_post,
        "last_comment": last_comment,
    }


# ─── Error log writers ────────────────────────────────────────────────────────


def error_log_basic(entry: str, bot_routine: str) -> None:
    """
    Log an error in YAML format by appending a new entry.

    :param entry: The error text (e.g., a traceback).
    :param bot_routine: The routine of the bot writing this error
                        (e.g., 'Ziwen', 'Wenyuan').
    """
    log_entry = {
        "timestamp": get_current_utc_time(),
        "bot_version": bot_routine,
        "error": entry.strip(),
        "resolved": False,
    }

    existing_entries = _load_error_entries(Paths.LOGS["ERROR"])

    existing_entries.append(log_entry)
    _atomic_yaml_dump(Paths.LOGS["ERROR"], existing_entries)


def error_log_extended(error_save_entry: str, bot_version: str) -> None:
    """
    Log an error in YAML format. This will include the last post
    and comment that happened when the error happened.

    :param error_save_entry: The traceback text to log.
    :param bot_version: Bot version string (e.g., 'Ziwen', 'Wenju').
    :return: None
    """
    error_log_path = Paths.LOGS["ERROR"]

    try:
        existing_log = _load_error_entries(error_log_path)

        try:
            last_post_text = _record_last_post_and_comment()
        except Exception as reddit_err:
            logger.warning(
                f"[{bot_version}] Error_Log: Could not capture Reddit context: {reddit_err}"
            )
            last_post_text = {
                "last_post": "unavailable (Reddit API error)",
                "last_comment": "unavailable (Reddit API error)",
            }

        # Match bot name prefix to its shortform tag (e.g. "Ziwen Main" → "ZW")
        bot_tag = next(
            (
                tag
                for name, tag in SETTINGS["bot_shortform_tags"].items()
                if bot_version.startswith(name)
            ),
            None,
        )
        last_events = get_recent_event_log_lines(10, bot_tag)[0]

        new_entry = {
            "timestamp": get_current_utc_time(),
            "bot_version": bot_version,
            "context": last_post_text,
            "events": last_events,
            "error": error_save_entry.strip(),
            "resolved": False,
        }

        existing_log.append(new_entry)
        _atomic_yaml_dump(error_log_path, existing_log)

    except Exception as e:
        logger.error(f"[{bot_version}] Error_Log: Failed to write error log: {e}")


# ─── Error log readers ────────────────────────────────────────────────────────


def retrieve_error_log() -> str:
    """
    Retrieve the error log and format it as a human-readable Markdown string.

    :return: Formatted Markdown string.
    """
    paragraphs = []

    data = _load_error_entries(Paths.LOGS["ERROR"])
    if not os.path.exists(Paths.LOGS["ERROR"]):
        return "No error log found."

    for entry in data:
        lines = []
        for key, value in entry.items():
            if isinstance(value, dict):
                lines.append(f"**{key.capitalize()}:**")
                for subkey, subvalue in value.items():
                    formatted_value = str(subvalue).replace("\n", "\n    ")
                    lines.append(f"  - **{subkey}:** {formatted_value}")
            else:
                formatted_value = str(value).replace("\n", "\n  ")
                lines.append(f"**{key.capitalize()}:** {formatted_value}")

        paragraph = "\n".join(lines)
        paragraphs.append(paragraph)
    final_text = "\n---\n".join(paragraphs)

    return final_text


def display_event_errors(days: int = 7) -> list[str]:
    """
    Display errors recorded in the events log (as opposed to the error log).

    :param days: How many days back to search (default: 7).
    :return: List of matching log line strings.
    """
    cutoff_date = datetime.now(UTC) - timedelta(days=days)
    results = []

    try:
        with open(Paths.LOGS["EVENTS"], encoding="utf-8") as f:
            for line in f:
                if "ERROR:" in line:
                    try:
                        timestamp_str = line.split(" - ")[0].split(": ")[1]
                        log_date = datetime.fromisoformat(
                            timestamp_str.replace("Z", "+00:00")
                        )
                        if log_date >= cutoff_date:
                            results.append(line.rstrip())
                    except (ValueError, IndexError):
                        results.append(line.rstrip())
    except FileNotFoundError:
        pass
    except Exception as e:
        results.append(f"Error reading log file: {e}")

    return results
