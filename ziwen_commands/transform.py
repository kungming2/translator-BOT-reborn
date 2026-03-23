#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
Handler for the !transform command, which rotates or flips images from posts.
...

Logger tag: [ZW:TRANSFORM]
"""

import logging
import re

from praw.models import Comment, Submission

from config import SETTINGS
from config import logger as _base_logger
from integrations.image_handling import (
    TRANSFORM_MAP,
    rotate_or_flip_image,
    upload_to_imgbb,
)
from models.ajo import Ajo
from models.instruo import Instruo
from models.komando import Komando
from reddit.reddit_sender import reddit_reply
from responses import RESPONSE
from utility import check_url_extension, clean_reddit_image_url, is_valid_image_url

logger = logging.LoggerAdapter(_base_logger, {"tag": "ZW:TRANSFORM"})

# Valid transformation values
VALID_TRANSFORMS = {
    "90",
    "180",
    "270",
    "-90",
    "-180",
    "-270",
    "h",
    "v",
    "horizontal",
    "vertical",
    "flip_h",
    "flip_v",
}


# ─── Image extraction helpers ─────────────────────────────────────────────────


def _extract_gallery_images(submission: Submission) -> list[str]:
    """
    Extract image URLs from a Reddit gallery post.

    Args:
        submission: A PRAW submission object

    Returns:
        list: List of image URLs from the gallery (videos and non-images excluded),
              limited to the first 5 images.
    """
    image_urls: list[str] = []

    if hasattr(submission, "is_gallery") and submission.is_gallery:
        if hasattr(submission, "gallery_data"):
            media_metadata = submission.media_metadata

            for item in submission.gallery_data["items"]:
                if len(image_urls) >= 5:
                    break

                media_id = item["media_id"]

                if media_id in media_metadata:
                    media_info = media_metadata[media_id]

                    if "s" in media_info:
                        image_url = media_info["s"]["u"]
                        image_url = image_url.replace("&amp;", "&")
                        image_url = clean_reddit_image_url(image_url)

                        if check_url_extension(image_url):
                            image_urls.append(image_url)

    return image_urls


def _extract_images_from_submission(submission: Submission) -> list[str]:
    """
    Extract all image URLs from a Reddit submission.

    Handles three types of posts:
    - Gallery posts: Extracts all images from the gallery
    - Self/text posts: Extracts image URLs from the body text
    - Single image posts: Returns the submission URL

    Args:
        submission: A PRAW submission object

    Returns:
        list: List of image URLs found in the submission
    """
    # Gallery post
    if hasattr(submission, "is_gallery") and submission.is_gallery:
        logger.info(f"Detected gallery post for {submission.id}")
        image_urls = _extract_gallery_images(submission)
        logger.info(f"Found {len(image_urls)} images in gallery")
        return image_urls

    # Self/text post — extract image URLs from body
    if submission.is_self:
        logger.info(f"Detected text post for {submission.id}")
        url_pattern = r'https?://[^\s<>"{}|\\^`\[\]]+'
        found_urls = re.findall(url_pattern, submission.selftext)

        image_urls = []
        for url in found_urls:
            if is_valid_image_url(url):
                image_urls.append(clean_reddit_image_url(url))

        logger.info(f"Found {len(image_urls)} image URLs in text body")
        return image_urls

    # Single image post
    if submission.url and check_url_extension(submission.url):
        logger.info(f"Detected single image post for {submission.id}")
        return [submission.url]

    logger.info(f"No images found in submission {submission.id}")
    return []


# ─── Command handler ──────────────────────────────────────────────────────────


def handle(comment: Comment, _instruo: Instruo, komando: Komando, _ajo: Ajo) -> None:
    """
    Command handler called by ziwen_commands().
    Example data:
        [Komando(name='transform', data=['90'])]
        [Komando(name='transform', data=['h'])]
    """
    logger.info(f"!transform, from u/{comment.author}.")

    if not komando.data or len(komando.data) == 0:
        reddit_reply(
            comment, RESPONSE.COMMENT_TRANSFORM_NO_DATA + RESPONSE.BOT_DISCLAIMER
        )
        return

    # Strip any trailing index suffix the command parser may have included
    # (e.g. "h:1" → "h"). The index is re-parsed from the raw comment body below.
    transformation = komando.data[0].split(":")[0]

    # Re-parse the optional image index from the raw comment body.
    # Kept here rather than in komando.py so that this transform-specific
    # logic doesn't bleed into the general argument parser.
    target_index = None
    index_match = re.search(
        r"!transform\s*:\s*\S+?\s*:\s*(\d+)", comment.body, re.IGNORECASE
    )
    if index_match:
        target_index = int(index_match.group(1))
        logger.info(f"Image index argument detected: target image {target_index}")

    if transformation not in VALID_TRANSFORMS:
        reddit_reply(
            comment,
            RESPONSE.COMMENT_TRANSFORM_INVALID.format(transformation)
            + RESPONSE.BOT_DISCLAIMER,
        )
        return

    submission = comment.submission
    image_urls = _extract_images_from_submission(submission)

    if not image_urls:
        reddit_reply(
            comment, RESPONSE.COMMENT_TRANSFORM_NO_IMAGE + RESPONSE.BOT_DISCLAIMER
        )
        return

    # Validate and apply target_index if provided.
    if target_index is not None:
        if len(image_urls) <= 1:
            reddit_reply(
                comment,
                RESPONSE.COMMENT_TRANSFORM_INDEX_SINGLE + RESPONSE.BOT_DISCLAIMER,
            )
            return
        if target_index < 1 or target_index > len(image_urls):
            reddit_reply(
                comment,
                RESPONSE.COMMENT_TRANSFORM_INDEX_OOB.format(
                    target_index, len(image_urls)
                )
                + RESPONSE.BOT_DISCLAIMER,
            )
            return
        logger.info(f"Filtering to image {target_index} of {len(image_urls)}")
        image_urls = [image_urls[target_index - 1]]

    logger.info(
        f"Processing {len(image_urls)} image(s) with transformation: {transformation}"
    )

    # Resolve a human-readable description of the transformation.
    transform_desc = TRANSFORM_MAP.get(transformation, transformation)
    if transformation in {"90", "180", "270"}:
        transform_desc = f"{transformation}° clockwise rotation"
    elif transformation in {"-90", "-180", "-270"}:
        transform_desc = f"{transformation[1:]}° counterclockwise rotation"
    elif transform_desc == "flip_h":
        transform_desc = "horizontal flip"
    elif transform_desc == "flip_v":
        transform_desc = "vertical flip"

    expiration_days = SETTINGS["image_retention_age"]

    # Transform and upload each image.
    transformed_urls = []
    failed_images = []

    for idx, image_url in enumerate(image_urls, 1):
        try:
            logger.info(f"Processing image {idx}/{len(image_urls)}: {image_url}")

            transformed_image = rotate_or_flip_image(image_url, transformation)
            logger.info(f"Image {idx} transformed successfully")

            title_suffix = f" ({idx}/{len(image_urls)})" if len(image_urls) > 1 else ""
            uploaded_url = upload_to_imgbb(
                transformed_image,
                title=(submission.title[:190] + title_suffix)[:200],
            )
            logger.info(f"Image {idx} uploaded to {uploaded_url}")
            transformed_urls.append(uploaded_url)

        except Exception as e:
            logger.error(f"Error processing image {idx}: {e}")
            failed_images.append((idx, str(e)))

    # Build and send the reply.
    if not transformed_urls:
        error_msg = "Failed to process all images. Errors:\n"
        for idx, error in failed_images:
            error_msg += f"- Image {idx}: {error}\n"
        reddit_reply(
            comment,
            RESPONSE.COMMENT_TRANSFORM_ERROR.format(error_msg)
            + RESPONSE.BOT_DISCLAIMER,
        )
        return

    if len(transformed_urls) == 1:
        image_link = f"**[Image]({transformed_urls[0]})**"
        reply_text = RESPONSE.COMMENT_TRANSFORM_SUCCESS_REPLY.format(
            transform_desc, image_link, expiration_days
        )
    else:
        image_links = ""
        for idx, url in enumerate(transformed_urls, 1):
            image_links += f"* **[Image {idx}]({url})**\n"
        reply_text = RESPONSE.COMMENT_TRANSFORM_SUCCESS_REPLY.format(
            transform_desc, image_links.strip(), expiration_days
        )

    if failed_images:
        reply_text += (
            f"\n\n---\n\n**Note:** {len(failed_images)} image(s) failed to process:\n"
        )
        for idx, error in failed_images:
            reply_text += f"- Image {idx}: {error}\n"

    reddit_reply(comment, reply_text + RESPONSE.BOT_DISCLAIMER)
