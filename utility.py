#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
A grab-bag of various simple utility functions.

This module contains general-purpose utility functions for:
- URL validation and extension checking
- Text parsing and extraction
- Image processing and hashing
- YouTube video metadata retrieval
...

Logger tag: [UTILITY]
"""

# ─── Imports ──────────────────────────────────────────────────────────────────

import io
import logging
import re
import time
from typing import Any
from urllib.parse import parse_qs, urlparse

import imagehash
import PIL
import requests
from PIL import Image
from yt_dlp import YoutubeDL

from config import logger as _base_logger

# ─── Module-level constants ───────────────────────────────────────────────────

logger = logging.LoggerAdapter(_base_logger, {"tag": "UTILITY"})


# ─── URL validation ───────────────────────────────────────────────────────────


def check_url_extension(submission_url: str) -> bool:
    """
    Check if a URL has an image file extension.

    :param submission_url: The URL to check.
    :return: True if URL has valid image extension, False otherwise.
    """
    if not submission_url:
        logger.debug("Received empty or None URL.")
        return False

    submission_url = submission_url.strip()

    if not submission_url:
        logger.debug("URL is empty after stripping whitespace.")
        return False

    # Use \Z instead of $ to match absolute end of string
    pattern = r"\.(jpg|jpeg|webp|png)\Z"
    has_image_extension = bool(re.search(pattern, submission_url, re.IGNORECASE))

    if not has_image_extension:
        logger.debug(f"URL does not have a valid image extension: {submission_url}")
        return False

    extension = submission_url.split(".")[-1].lower()
    logger.debug(f"URL has valid .{extension} extension.")
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
    if not url:
        logger.debug("Received empty or None URL for cleaning.")
        return ""

    url = url.strip()
    if not url:
        logger.debug("URL is empty after stripping whitespace.")
        return ""

    if "preview.redd.it" in url:
        url = url.replace("preview.redd.it", "i.redd.it")

    if "?" in url:
        url = url.split("?")[0]

    return url


def is_valid_image_url(url: str) -> bool:
    """
    Check if a URL is a valid image URL, including URLs with query parameters.

    More lenient than check_url_extension() — handles:
    - Direct image URLs (e.g., image.jpg)
    - Reddit preview URLs with query params (e.g., preview.redd.it/...?format=pjpg)
    - Image URLs with tracking parameters

    :param url: The URL to check.
    :return: True if URL appears to be an image, False otherwise.
    """
    if not url:
        return False

    url = url.strip()
    if not url:
        return False

    if check_url_extension(url):
        return True

    parsed = urlparse(url)
    hostname = (parsed.hostname or "").lower()
    path_url = parsed._replace(query="", fragment="").geturl()

    if check_url_extension(path_url):
        return True

    # Support Reddit preview links where image type is advertised in query args.
    if hostname.endswith("redd.it"):
        params = parse_qs(parsed.query)
        format_values = [
            v.lower() for value in params.get("format", []) for v in [value]
        ]
        if any(fmt in {"pjpg", "jpg", "jpeg", "png", "webp"} for fmt in format_values):
            return True

    return False


# ─── Image hashing ────────────────────────────────────────────────────────────


def generate_image_hash(image_url: str) -> str | None:
    """
    Generate an image hash from a linked URL for later comparison.

    Note: ``timeout=10`` governs the connection/read timeout for the initial
    request but does not bound the total download time for large images served
    by a slow host. This is acceptable for the expected image sizes on Reddit.

    :param image_url: A direct link to a URL containing an image.
    :return: The hash of the image, or None if unable to hash.
    """
    if not image_url:
        logger.warning("Received empty or None URL.")
        return None

    logger.debug(f"Attempting to hash image from: {image_url}")
    start_time = time.time()

    try:
        with requests.get(image_url, timeout=10, stream=True) as response:
            response.raise_for_status()

            content_length = response.headers.get("Content-Length")
            if (
                content_length
                and content_length.isdigit()
                and int(content_length) > 20 * 1024 * 1024
            ):
                logger.warning(
                    f"Image at {image_url} exceeds max allowed size (20MB): "
                    f"{content_length} bytes"
                )
                return None

            img_bytes = io.BytesIO()
            downloaded = 0
            for chunk in response.iter_content(chunk_size=8192):
                if not chunk:
                    continue
                downloaded += len(chunk)
                if downloaded > 20 * 1024 * 1024:
                    logger.warning(
                        f"Image at {image_url} exceeded max allowed size during download "
                        f"(20MB)."
                    )
                    return None
                img_bytes.write(chunk)

            img_bytes.seek(0)
            img = Image.open(img_bytes)
            img.load()
    except PIL.UnidentifiedImageError as e:
        logger.warning(f"Unable to identify image format for {image_url}: {e}")
        return None
    except requests.exceptions.ConnectionError as e:
        logger.warning(f"Connection error for {image_url}: {e}")
        return None
    except requests.exceptions.Timeout as e:
        logger.warning(f"Request timeout for {image_url}: {e}")
        return None
    except requests.exceptions.HTTPError as e:
        logger.warning(f"HTTP error for {image_url}: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error for {image_url}: {e}")
        return None
    else:
        hash_value = str(imagehash.dhash(img))
        elapsed = time.time() - start_time
        logger.debug(
            f"Successfully hashed {image_url} -> {hash_value} (took {elapsed:.2f}s)"
        )

    return hash_value


# ─── YouTube metadata ─────────────────────────────────────────────────────────


def fetch_youtube_length(youtube_url: str) -> int | None:
    """
    Return the length of a YouTube video in seconds using yt-dlp.
    Returns None if unable to fetch.

    Note: None is returned for both "duration metadata absent" and "fetch
    error" cases. Callers that need to distinguish these should check the
    log output; both paths emit a warning-level log entry.

    :param youtube_url: URL of the YouTube video.
    :return: Video duration in seconds, or None if fetch failed or duration
             is unavailable.
    """
    if not youtube_url:
        logger.warning("Received empty or None URL.")
        return None

    logger.debug(f"Fetching video length for: {youtube_url}")
    start_time = time.time()

    ydl_opts: dict[str, Any] = {
        "quiet": True,
        "skip_download": True,
        "no_warnings": True,
        "socket_timeout": 60,
    }

    try:
        with YoutubeDL(ydl_opts) as ydl:  # type: ignore
            info = ydl.extract_info(youtube_url, download=False)
            if info is None:
                logger.warning(f"No video info returned for {youtube_url}")
                return None

            duration = info.get("duration")
            elapsed = time.time() - start_time

            if duration is not None:
                logger.debug(f"Video is {duration}s long (fetched in {elapsed:.2f}s)")
                return int(duration)
            else:
                logger.warning(
                    f"Duration metadata absent for {youtube_url} "
                    f"(fetched in {elapsed:.2f}s)"
                )
                return None
    except Exception as e:
        elapsed = time.time() - start_time
        logger.error(
            f"Error fetching video info for {youtube_url} "
            f"after {elapsed:.2f}s: {type(e).__name__}: {e}"
        )
        return None


# ─── Markdown formatting ──────────────────────────────────────────────────────


def format_markdown_table_with_padding(table_text: str) -> str:
    """
    Format a Markdown table (with optional header above it) into a
    neatly aligned triple-backtick code block for Discord.
    Pads out rows so columns align visually.

    :param table_text: Raw Markdown table text to format.
    :return: Formatted table as Discord code block.
    """
    if not table_text:
        logger.debug("Received empty table text.")
        return "```\n(No table provided)\n```"

    lines = [line.rstrip() for line in table_text.strip().splitlines() if line.strip()]

    if not lines:
        logger.debug("No valid lines found in table.")
        return "```\n(No valid content)\n```"

    # Split into pre-table header lines and table lines
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
        logger.debug("No table rows with '|' found.")
        return "```\n(No valid table found)\n```"

    separator_pattern = re.compile(r"^\s*:?-{3,}:?\s*$")

    # Parse table rows into cells
    rows = []
    for line in table_lines:
        parts = [cell.strip() for cell in line.split("|")]
        if parts and parts[0] == "":
            parts = parts[1:]
        if parts and parts[-1] == "":
            parts = parts[:-1]
        rows.append(parts)

    if not rows:
        logger.debug("No valid rows after parsing.")
        return "```\n(No valid table found)\n```"

    # Compute per-column widths
    num_cols = max(len(row) for row in rows)
    col_widths = [0] * num_cols
    for row in rows:
        for i, cell in enumerate(row):
            col_widths[i] = max(col_widths[i], len(cell))

    # Rebuild with padding
    formatted_table = []
    for row in rows:
        normalized_row = [row[i] if i < len(row) else "" for i in range(num_cols)]
        padded = [
            cell.ljust(col_widths[i])
            if not separator_pattern.fullmatch(cell)
            else "-" * col_widths[i]
            for i, cell in enumerate(normalized_row)
        ]
        formatted_table.append("| " + " | ".join(padded) + " |")

    header_block = "\n".join(header_lines)
    table_block = "```\n" + "\n".join(formatted_table) + "\n```"

    result = f"{header_block}\n\n{table_block}" if header_block else table_block
    logger.debug(f"Formatted table with {len(rows)} rows, {num_cols} columns.")

    return result
