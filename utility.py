#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
A grab-bag of various simple utility functions.
"""

import io
import re
from typing import List, Optional

import imagehash
import PIL
import requests
from PIL import Image
from yt_dlp import YoutubeDL

from config import logger


def check_url_extension(submission_url: str) -> bool:
    """Checks to see if a URL extension matches an image file.
    Returns True if it is, False otherwise."""

    # Regular expression to match file extensions
    pattern = r"\.(jpg|jpeg|gif|webp|png)$"

    # Check if the URL ends with one of the specified extensions
    if re.search(pattern, submission_url, re.IGNORECASE):
        return True
    else:
        return False


def extract_text_within_curly_braces(text: str) -> List[str]:
    """Extracts all content inside {{...}} blocks, with whitespace stripped."""
    pattern = r"\{\{(.*?)\}\}"  # Non-greedy match inside double curly braces
    return [match.strip() for match in re.findall(pattern, text)]


def generate_image_hash(image_url: str) -> Optional[str]:
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


def fetch_youtube_length(youtube_url: str) -> Optional[int]:
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
            return info.get("duration")  # duration in seconds
        except Exception as e:
            logger.error(f"Error fetching video info: {e}")
            return None


if __name__ == "__main__":
    test_url = input("Enter a YouTube URL: ").strip()
    length_seconds = fetch_youtube_length(test_url)

    if length_seconds is not None:
        print(f"Video length: {length_seconds}")
    else:
        print("Failed to fetch video length.")
