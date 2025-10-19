#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
Handles error logging and retrieval.
"""

import os

import yaml

from config import SETTINGS, Paths, logger
from connection import REDDIT
from time_handling import get_current_utc_time, time_convert_to_string


class CustomDumper(yaml.SafeDumper):
    pass


def _str_representer(dumper, data):
    if "\n" in data:
        return dumper.represent_scalar("tag:yaml.org,2002:str", data, style="|")
    return dumper.represent_scalar("tag:yaml.org,2002:str", data)


CustomDumper.add_representer(str, _str_representer)


def error_log_basic(entry, bot_routine):
    """
    Logs an error in YAML format by appending a new entry.

    :param entry: The error text (e.g., a traceback).
    :param bot_routine: The routine of the bot writing this error
                        (e.g., 'Ziwen', 'Wenyuan').
    """
    log_entry = {
        "timestamp": get_current_utc_time(),
        "bot_version": bot_routine,
        "error": entry.strip(),
    }

    # Load existing entries (if any)
    if os.path.exists(Paths.LOGS["ERROR"]):
        with open(Paths.LOGS["ERROR"], "r", encoding="utf-8") as f:
            try:
                existing_entries = yaml.safe_load(f) or []
            except yaml.YAMLError:
                existing_entries = []
    else:
        existing_entries = []

    # Append the new error log unconditionally
    existing_entries.append(log_entry)

    # Save all entries back to the file
    with open(Paths.LOGS["ERROR"], "w", encoding="utf-8") as f:
        yaml.dump(
            existing_entries,
            f,
            Dumper=CustomDumper,
            allow_unicode=True,
            sort_keys=False,
            default_flow_style=False,
        )


def _record_last_post_and_comment():
    """
    Retrieves the latest post and comment from r/translator for
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

    # Get latest submission
    for submission in REDDIT.subreddit(SETTINGS["subreddit"]).new(limit=1):
        post_time = time_convert_to_string(submission.created_utc)
        post_info["timestamp"] = post_time
        post_info["link"] = f"https://www.reddit.com{submission.permalink}"
        break

    # Get latest comment
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

    last_post = f"Last post     |   {post_info['timestamp']}:    {post_info['link']}"
    last_comment = (
        f"Last comment  |   {comment_info['timestamp']}:    {comment_info['link']}\n"
        f"              {comment_info['body']}"
    )

    return {
        "last_post": last_post,
        "last_comment": last_comment,
    }


def error_log_extended(error_save_entry, bot_version):
    """
    Logs an error in YAML format. This will include the last post
    and comment that happened when the error happened.

    :param error_save_entry: The traceback text to log.
    :param bot_version: Bot version string (e.g., 'Ziwen', 'Wenyuan').
    :return: None
    """
    error_log_path = Paths.LOGS["ERROR"]

    try:
        # Load existing YAML log (if file exists and is non-empty)
        try:
            with open(error_log_path, "r", encoding="utf-8") as f:
                existing_log = yaml.safe_load(f) or []
        except FileNotFoundError:
            existing_log = []

        # Get contextual info
        last_post_text = _record_last_post_and_comment()

        # Append new entry
        new_entry = {
            "timestamp": get_current_utc_time(),
            "bot_version": bot_version,
            "context": last_post_text,
            "error": error_save_entry,
        }

        existing_log.append(new_entry)

        # Write back to file
        with open(error_log_path, "w", encoding="utf-8") as f:
            yaml.dump(
                existing_log,
                f,
                Dumper=CustomDumper,
                allow_unicode=True,
                sort_keys=False,
                default_flow_style=False,
            )

    except Exception as e:
        logger.error(f"[{bot_version}] Error_Log: Failed to write error log: {e}")


def retrieve_error_log():
    """
    Retrieves the error log from the error log file and formats it
    in a human-readable format (Markdown).
    :return: Formatted Markdown string.
    """
    paragraphs = []

    with open(Paths.LOGS["ERROR"], "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    for entry in data:
        lines = []
        for key, value in entry.items():
            if isinstance(value, dict):
                lines.append(f"**{key.capitalize()}:**")
                # For nested dict, print each subkey with indent
                for subkey, subvalue in value.items():
                    # Replace newlines inside values with indented lines
                    formatted_value = str(subvalue).replace("\n", "\n    ")
                    lines.append(f"  - **{subkey}:** {formatted_value}")
            else:
                # Replace newlines inside values with indented lines
                formatted_value = str(value).replace("\n", "\n  ")
                lines.append(f"**{key.capitalize()}:** {formatted_value}")

        paragraph = "\n".join(lines)
        paragraphs.append(paragraph)
    final_text = "\n---\n".join(paragraphs)

    return final_text


if __name__ == "__main__":
    print(retrieve_error_log())
