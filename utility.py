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
    """
    # Strip whitespace/newlines first
    submission_url = submission_url.strip()

    # Use \Z instead of $ to match absolute end of string
    pattern = r"\.(jpg|jpeg|gif|webp|png)\Z"

    # Check if the URL ends with one of the specified extensions
    has_image_extension = bool(re.search(pattern, submission_url, re.IGNORECASE))

    if not has_image_extension:
        logger.warning("URL does not have a valid image extension.")
        return False
    else:
        logger.debug("URL does have a valid image extension.")
        return True


def extract_text_within_curly_braces(text: str) -> list[str]:
    """Extracts all content inside {{...}} blocks, with whitespace stripped."""
    pattern = r"\{\{(.*?)\}\}"  # Non-greedy match inside double curly braces
    return [match.strip() for match in re.findall(pattern, text)]


def generate_image_hash(image_url: str) -> str | None:
    """
    Generates an image hash from a linked URL for later comparison.
    :param image_url: A direct link to a URL containing an image.
    :return: The hash of the image, or None if unable to hash.
    """

    # Download the image from the URL
    try:
        response = requests.get(image_url)
        img = Image.open(io.BytesIO(response.content))
    except (PIL.UnidentifiedImageError, requests.exceptions.ConnectionError):
        # Imgur redirects break this.
        logger.debug(f"[ZW] generate_image_hash: Unable to hash {image_url}.")
        return None
    else:
        # Generate the hash using `dhash` algorithm.
        hash_value = str(imagehash.dhash(img))
        logger.debug(f"[ZW] generate_image_hash: Assessed {image_url}: {hash_value}")

    return hash_value


def fetch_youtube_length(youtube_url: str) -> int | None:
    """
    Returns the length of a YouTube video in seconds using the
    yt-dlp library. Returns None if unable to fetch.
    """
    ydl_opts = {
        "quiet": True,
        "skip_download": True,  # we only want metadata
    }

    with YoutubeDL(ydl_opts) as ydl:
        try:
            info = ydl.extract_info(youtube_url, download=False)
            if info is None:
                return None
            return info.get("duration")  # duration in seconds
        except Exception as e:
            logger.error(f"Error fetching video info: {e}")
            return None


"""MARKDOWN FUNCTIONS"""


def format_markdown_table_with_padding(table_text: str) -> str:
    """
    Formats a Markdown table (with optional header above it)
    into a neatly aligned triple-backtick code block for Discord.
    Basically, this pads out the rows to look more even.
    """
    lines = [line.rstrip() for line in table_text.strip().splitlines() if line.strip()]

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

    return f"{header_block}\n\n{table_block}"


if __name__ == "__main__":
    test_url = input("Enter a YouTube URL: ").strip()
    length_seconds = fetch_youtube_length(test_url)

    if length_seconds is not None:
        print(f"Video length: {length_seconds}")
    else:
        print("Failed to fetch video length.")
