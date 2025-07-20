#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
A grab-bag of various simple utility functions.
"""
import io
import re
import requests

import imagehash
import PIL

from config import logger
from PIL import Image


def check_url_extension(submission_url):
    """Checks to see if a URL extension matches an image file.
    Returns True if it is, False otherwise."""

    # Regular expression to match file extensions
    pattern = r"\.(jpg|jpeg|gif|webp|png)$"

    # Check if the URL ends with one of the specified extensions
    if re.search(pattern, submission_url, re.IGNORECASE):
        return True
    else:
        return False


def extract_text_within_curly_braces(text):
    """Extracts all content inside {{...}} blocks, with whitespace stripped."""
    pattern = r"\{\{(.*?)\}\}"  # Non-greedy match inside double curly braces
    return [match.strip() for match in re.findall(pattern, text)]


def generate_image_hash(image_url):
    """
    Generates an image hash from a linked URL for later comparison.
    :param image_url: A direct link to a URL containing an image.
    :return: The hash of the image.
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
