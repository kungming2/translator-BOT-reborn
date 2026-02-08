#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
A grab-bag of various simple utility functions.


This module contains general-purpose utility functions for:
- URL validation and extension checking
- Text parsing and extraction
- Image processing and hashing
- YouTube video metadata retrieval
"""

import io
import re
import time
from typing import Any

import imagehash
import PIL
import requests
from PIL import Image
from yt_dlp import YoutubeDL

from config import logger

"""MEDIA FUNCTIONS"""


def check_url_extension(submission_url: str) -> bool:
    """
    Checks if a URL has an image file extension.

    :param submission_url: The URL to check.
    :return: True if URL has valid image extension, False otherwise.
    """
    if not submission_url:
        logger.debug("check_url_extension: Received empty or None URL.")
        return False

    # Strip whitespace/newlines first
    submission_url = submission_url.strip()

    if not submission_url:
        logger.debug("check_url_extension: URL is empty after stripping whitespace.")
        return False

    # Use \Z instead of $ to match absolute end of string
    pattern = r"\.(jpg|jpeg|webp|png)\Z"

    # Check if the URL ends with one of the specified extensions
    has_image_extension = bool(re.search(pattern, submission_url, re.IGNORECASE))

    if not has_image_extension:
        logger.debug(
            f"check_url_extension: URL does not have a valid image extension: {submission_url}"
        )
        return False
    else:
        extension = submission_url.split(".")[-1].lower()
        logger.debug(f"check_url_extension: URL has valid .{extension} extension.")
        return True


def clean_reddit_image_url(url: str) -> str:
    """
    Clean up Reddit preview URLs to get the direct image URL.

    Converts URLs like:
    https://preview.redd.it/abc123.jpg?width=2253&format=pjpg&auto=webp&s=...

    To:
    https://i.redd.it/abc123.jpg

    :param url: The URL to clean.
    :return: Cleaned URL.
    """
    if "preview.redd.it" in url:
        # Replace preview.redd.it with i.redd.it
        url = url.replace("preview.redd.it", "i.redd.it")

    # Remove query parameters
    if "?" in url:
        url = url.split("?")[0]

    return url


def is_valid_image_url(url: str) -> bool:
    """
    Check if a URL is a valid image URL, including URLs with query parameters.

    This is more lenient than check_url_extension() as it handles:
    - Direct image URLs (e.g., image.jpg)
    - Reddit preview URLs with query params (e.g., preview.redd.it/...?format=pjpg)
    - Image URLs with tracking parameters

    :param url: The URL to check.
    :return: True if URL appears to be an image, False otherwise.
    """
    if not url:
        return False

    url = url.strip()

    # First try the standard check for direct image URLs
    if check_url_extension(url):
        return True

    # Handle Reddit preview/image URLs with query parameters
    if "redd.it" in url:
        # Check if format parameter indicates an image
        if "format=pjpg" in url or "format=png" in url or "format=jpg" in url:
            return True
        # Check if the URL path (before query params) ends with an image extension
        url_without_params = url.split("?")[0]
        if check_url_extension(url_without_params):
            return True

    # Check if URL path (before query params) has an image extension
    # This handles cases like: example.com/image.jpg?param=value
    if "?" in url:
        url_without_params = url.split("?")[0]
        if check_url_extension(url_without_params):
            return True

    return False


def generate_image_hash(image_url: str) -> str | None:
    """
    Generates an image hash from a linked URL for later comparison.

    :param image_url: A direct link to a URL containing an image.
    :return: The hash of the image, or None if unable to hash.
    """
    if not image_url:
        logger.warning("generate_image_hash: Received empty or None URL.")
        return None

    logger.debug(f"generate_image_hash: Attempting to hash image from: {image_url}")
    start_time = time.time()

    # Download the image from the URL
    try:
        response = requests.get(image_url, timeout=10)
        response.raise_for_status()
        img = Image.open(io.BytesIO(response.content))
    except PIL.UnidentifiedImageError as e:
        logger.warning(
            f"generate_image_hash: Unable to identify image format for {image_url}: {e}"
        )
        return None
    except requests.exceptions.ConnectionError as e:
        logger.warning(f"generate_image_hash: Connection error for {image_url}: {e}")
        return None
    except requests.exceptions.Timeout as e:
        logger.warning(f"generate_image_hash: Request timeout for {image_url}: {e}")
        return None
    except requests.exceptions.HTTPError as e:
        logger.warning(f"generate_image_hash: HTTP error for {image_url}: {e}")
        return None
    except Exception as e:
        logger.error(f"generate_image_hash: Unexpected error for {image_url}: {e}")
        return None
    else:
        # Generate the hash using `dhash` algorithm.
        hash_value = str(imagehash.dhash(img))
        elapsed = time.time() - start_time
        logger.debug(
            f"generate_image_hash: Successfully hashed {image_url} -> {hash_value} "
            f"(took {elapsed:.2f}s)"
        )

    return hash_value


"""OTHER FUNCTIONS"""


def extract_text_within_curly_braces(text: str) -> list[str]:
    """
    Extracts all content inside {{...}} blocks, with whitespace stripped.

    :param text: Text to search for curly brace patterns.
    :return: List of extracted strings.
    """
    if not text:
        logger.debug("extract_text_within_curly_braces: Received empty or None text.")
        return []

    pattern = r"\{\{(.*?)\}\}"  # Non-greedy match inside double curly braces
    matches = [match.strip() for match in re.findall(pattern, text)]

    if matches:
        logger.debug(
            f"extract_text_within_curly_braces: Found {len(matches)} match(es)."
        )

    return matches


def fetch_youtube_length(youtube_url: str) -> int | None:
    """
    Returns the length of a YouTube video in seconds using the
    yt-dlp library. Returns None if unable to fetch.

    :param youtube_url: URL of the YouTube video.
    :return: Video duration in seconds, or None if fetch failed.
    """
    if not youtube_url:
        logger.warning("fetch_youtube_length: Received empty or None URL.")
        return None

    logger.debug(f"fetch_youtube_length: Fetching video length for: {youtube_url}")
    start_time = time.time()

    ydl_opts: dict[str, Any] = {
        "quiet": True,
        "skip_download": True,
        "no_warnings": True,
    }

    try:
        with YoutubeDL(ydl_opts) as ydl:  # type: ignore
            info = ydl.extract_info(youtube_url, download=False)
            if info is None:
                logger.warning(
                    f"fetch_youtube_length: No video info returned for {youtube_url}"
                )
                return None

            duration = info.get("duration")
            elapsed = time.time() - start_time

            if duration:
                logger.debug(
                    f"fetch_youtube_length: Video is {duration}s long "
                    f"(fetched in {elapsed:.2f}s)"
                )
            else:
                logger.warning(
                    f"fetch_youtube_length: Duration not available for {youtube_url}"
                )

            return duration
    except Exception as e:
        elapsed = time.time() - start_time
        logger.error(
            f"fetch_youtube_length: Error fetching video info for {youtube_url} "
            f"after {elapsed:.2f}s: {type(e).__name__}: {e}"
        )
        return None


"""MARKDOWN FUNCTIONS"""


def format_markdown_table_with_padding(table_text: str) -> str:
    """
    Formats a Markdown table (with optional header above it)
    into a neatly aligned triple-backtick code block for Discord.
    Basically, this pads out the rows to look more even.

    :param table_text: Raw Markdown table text to format.
    :return: Formatted table as Discord code block.
    """
    if not table_text:
        logger.debug("format_markdown_table_with_padding: Received empty table text.")
        return "```\n(No table provided)\n```"

    lines = [line.rstrip() for line in table_text.strip().splitlines() if line.strip()]

    if not lines:
        logger.debug(
            "format_markdown_table_with_padding: No valid lines found in table."
        )
        return "```\n(No valid content)\n```"

    # Split header and table parts
    header_lines = []
    table_lines = []
    found_table = False

    for line in lines:
        if "|" in line:
            found_table = True
        if found_table:
            table_lines.append(line)
        else:
            header_lines.append(line)

    if not table_lines:
        logger.debug(
            "format_markdown_table_with_padding: No table rows with '|' found."
        )
        return "```\n(No valid table found)\n```"

    # Parse table rows
    rows = []
    for line in table_lines:
        parts = [cell.strip() for cell in line.split("|")]
        if parts and parts[0] == "":
            parts = parts[1:]
        if parts and parts[-1] == "":
            parts = parts[:-1]
        rows.append(parts)

    if not rows:
        logger.debug("format_markdown_table_with_padding: No valid rows after parsing.")
        return "```\n(No valid table found)\n```"

    # Compute column widths
    num_cols = max(len(row) for row in rows)
    col_widths = [0] * num_cols
    for row in rows:
        for i, cell in enumerate(row):
            col_widths[i] = max(col_widths[i], len(cell))

    # Rebuild table with alignment
    formatted_table = []
    for row in rows:
        padded = [
            cell.ljust(col_widths[i]) if "---" not in cell else "-" * col_widths[i]
            for i, cell in enumerate(row)
        ]
        formatted_table.append("| " + " | ".join(padded) + " |")

    # Header outside the code block
    header_block = "\n".join(header_lines)
    table_block = "```\n" + "\n".join(formatted_table) + "\n```"

    result = f"{header_block}\n\n{table_block}" if header_block else table_block
    logger.debug(
        f"format_markdown_table_with_padding: Formatted table with {len(rows)} rows, "
        f"{num_cols} columns."
    )

    return result


if __name__ == "__main__":
    test_url = input("Enter a YouTube URL: ").strip()
    length_seconds = fetch_youtube_length(test_url)

    if length_seconds is not None:
        print(f"Video length: {length_seconds} seconds")
    else:
        print("Failed to fetch video length.")
