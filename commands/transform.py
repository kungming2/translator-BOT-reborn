#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
Handler for the !transform command, which rotates or flips images from posts.
"""

import re

from config import SETTINGS, logger
from connection import REDDIT_HELPER
from image_handling import TRANSFORM_MAP, rotate_or_flip_image, upload_to_imgbb
from models.instruo import Instruo
from reddit_sender import reddit_reply
from responses import RESPONSE
from utility import check_url_extension, clean_reddit_image_url, is_valid_image_url

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


def _extract_gallery_images(submission):
    """
    Extract image URLs from a Reddit gallery post.

    Args:
        submission: A PRAW submission object

    Returns:
        list: List of image URLs from the gallery (videos and non-images excluded)
              Limited to first 5 images to avoid processing too many images.
    """
    image_urls = []

    # Check if the submission has a gallery
    if hasattr(submission, "is_gallery") and submission.is_gallery:
        # Get the gallery data
        if hasattr(submission, "gallery_data"):
            # Get media metadata
            media_metadata = submission.media_metadata

            # Iterate through gallery items in order
            for item in submission.gallery_data["items"]:
                # Stop after collecting 5 images
                if len(image_urls) >= 5:
                    break

                media_id = item["media_id"]

                # Get the image info from media_metadata
                if media_id in media_metadata:
                    media_info = media_metadata[media_id]

                    # Get the largest resolution image URL
                    if "s" in media_info:
                        image_url = media_info["s"]["u"]
                        # URLs are HTML encoded, decode them
                        image_url = image_url.replace("&amp;", "&")
                        # Clean up the Reddit URL
                        image_url = clean_reddit_image_url(image_url)

                        # Only add if it's a valid image URL
                        if check_url_extension(image_url):
                            image_urls.append(image_url)

    return image_urls


def _extract_images_from_submission(submission):
    """
    Extract all image URLs from a Reddit submission.

    Handles three types of posts:
    - Self/text posts: Extracts image URLs from the body text
    - Single image posts: Returns the submission URL
    - Gallery posts: Extracts all images from the gallery

    Args:
        submission: A PRAW submission object

    Returns:
        list: List of image URLs found in the submission
    """
    image_urls = []

    # Case 1: Gallery post
    if hasattr(submission, "is_gallery") and submission.is_gallery:
        logger.info(f"[ZW] Transform: Detected gallery post for {submission.id}")
        image_urls = _extract_gallery_images(submission)
        logger.info(f"[ZW] Transform: Found {len(image_urls)} images in gallery")
        return image_urls

    # Case 2: Self/text post
    if submission.is_self:
        logger.info(f"[ZW] Transform: Detected text post for {submission.id}")
        # Extract URLs from the selftext using regex
        # This pattern matches common image hosting URLs
        url_pattern = r'https?://[^\s<>"{}|\\^`\[\]]+'
        test_found_urls = re.findall(url_pattern, submission.selftext)

        for url in test_found_urls:
            # Use the more lenient check for self-text URLs
            if is_valid_image_url(url):
                # Clean up Reddit preview URLs
                cleaned_url = clean_reddit_image_url(url)
                image_urls.append(cleaned_url)

        logger.info(f"[ZW] Transform: Found {len(image_urls)} image URLs in text body")
        return image_urls

    # Case 3: Single image post
    if submission.url and check_url_extension(submission.url):
        logger.info(f"[ZW] Transform: Detected single image post for {submission.id}")
        image_urls.append(submission.url)
        return image_urls

    # No images found
    logger.info(f"[ZW] Transform: No images found in submission {submission.id}")
    return image_urls


def handle(comment, _instruo, komando, _ajo) -> None:
    """
    Command handler called by ziwen_commands().
    Example data:
        [Komando(name='transform', data=['90'])]
        [Komando(name='transform', data=['h'])]
    """

    logger.info("Transform handler initiated.")

    # Get the transformation from komando data
    if not komando.data or len(komando.data) == 0:
        reddit_reply(
            comment, RESPONSE.COMMENT_TRANSFORM_NO_DATA + RESPONSE.BOT_DISCLAIMER
        )
        return

    transformation = komando.data[0]

    # Validate transformation
    if transformation not in VALID_TRANSFORMS:
        reddit_reply(
            comment,
            RESPONSE.COMMENT_TRANSFORM_INVALID.format(transformation)
            + RESPONSE.BOT_DISCLAIMER,
        )
        return

    # Get the submission
    submission = comment.submission

    # Extract all image URLs from the submission
    image_urls = _extract_images_from_submission(submission)

    # Check if we found any images
    if not image_urls:
        reddit_reply(
            comment, RESPONSE.COMMENT_TRANSFORM_NO_IMAGE + RESPONSE.BOT_DISCLAIMER
        )
        return

    logger.info(
        f"[ZW] Transform: Processing {len(image_urls)} image(s) with transformation: {transformation}"
    )

    # Determine transformation description for reply
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

    # Process each image
    transformed_urls = []
    failed_images = []

    for idx, image_url in enumerate(image_urls, 1):
        try:
            logger.info(
                f"[ZW] Transform: Processing image {idx}/{len(image_urls)}: {image_url}"
            )

            # Transform the image
            transformed_image = rotate_or_flip_image(image_url, transformation)
            logger.info(f"[ZW] Transform: Image {idx} transformed successfully")

            # Upload to ImgBB with submission title as the name
            title_suffix = f" ({idx}/{len(image_urls)})" if len(image_urls) > 1 else ""
            uploaded_url = upload_to_imgbb(
                transformed_image,
                title=(submission.title[:190] + title_suffix)[
                    :200
                ],  # Limit to 200 chars for API
            )
            logger.info(f"[ZW] Transform: Image {idx} uploaded to {uploaded_url}")
            transformed_urls.append(uploaded_url)

        except Exception as e:
            logger.error(f"[ZW] Transform: Error processing image {idx}: {e}")
            failed_images.append((idx, str(e)))

    # Prepare response
    if not transformed_urls:
        # All images failed
        error_msg = "Failed to process all images. Errors:\n"
        for idx, error in failed_images:
            error_msg += f"- Image {idx}: {error}\n"
        reddit_reply(
            comment,
            RESPONSE.COMMENT_TRANSFORM_ERROR.format(error_msg)
            + RESPONSE.BOT_DISCLAIMER,
        )
        return

    # Build success message
    if len(transformed_urls) == 1:
        # Single image response
        image_link = f"**[Image]({transformed_urls[0]})**"
        reply_text = RESPONSE.COMMENT_TRANSFORM_SUCCESS_REPLY.format(
            transform_desc, image_link, expiration_days
        )
    else:
        # Multiple images response - build the image links list
        image_links = ""
        for idx, url in enumerate(transformed_urls, 1):
            image_links += f"* **[Image {idx}]({url})**\n"

        reply_text = RESPONSE.COMMENT_TRANSFORM_SUCCESS_REPLY.format(
            transform_desc, image_links.strip(), expiration_days
        )

    # Add failure notice if some images failed
    if failed_images:
        reply_text += (
            f"\n\n---\n\n**Note:** {len(failed_images)} image(s) failed to process:\n"
        )
        for idx, error in failed_images:
            reply_text += f"- Image {idx}: {error}\n"

    reddit_reply(comment, reply_text + RESPONSE.BOT_DISCLAIMER)


if __name__ == "__main__":
    import logging

    # Configure logging to DEBUG level
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    # Also set the module logger to DEBUG explicitly
    logger.setLevel(logging.DEBUG)

    def show_menu():
        print("\nSelect a test to run:")
        print("1. Test _extract_images_from_submission (enter submission ID)")
        print("2. Test full transform handler (enter comment URL)")
        print("x. Exit")

    while True:
        show_menu()
        menu_choice = input("Enter your choice (1-2, or x): ")

        if menu_choice == "x":
            print("Exiting...")
            break

        if menu_choice not in ["1", "2"]:
            print("Invalid choice, please try again.")
            continue

        if menu_choice == "1":
            test_submission_id = input("Enter Reddit submission ID: ").strip()
            try:
                test_submission = REDDIT_HELPER.submission(id=test_submission_id)
                print(f"\nSubmission: {test_submission.title}")
                print(f"Is self post: {test_submission.is_self}")
                print(
                    f"Is gallery: {hasattr(test_submission, 'is_gallery') and test_submission.is_gallery}"
                )
                print(f"URL: {test_submission.url}")

                if test_submission.is_self:
                    print(f"\nSelf-text body:\n{test_submission.selftext}\n")

                    # Debug: show what URLs are found
                    url_pattern_test = r'https?://[^\s<>"{}|\\^`\[\]]+'
                    found_urls = re.findall(url_pattern_test, test_submission.selftext)
                    print(f"URLs found in self-text: {len(found_urls)}")
                    for test_idx, found_url in enumerate(found_urls, 1):
                        is_valid = is_valid_image_url(found_url)
                        print(f"  {test_idx}. {found_url}")
                        print(f"      Valid image URL: {is_valid}")

                extracted_image_urls = _extract_images_from_submission(test_submission)

                print(f"\n{'=' * 60}")
                print(f"Found {len(extracted_image_urls)} image(s):")
                print(f"{'=' * 60}")
                for img_idx, img_url in enumerate(extracted_image_urls, 1):
                    print(f"{img_idx}. {img_url}")
                print(f"{'=' * 60}\n")

            except Exception as err:
                print(f"Error: {err}")

        elif menu_choice == "2":
            test_comment_url = input("Enter Reddit comment URL: ").strip()
            try:
                test_comment = REDDIT_HELPER.comment(url=test_comment_url)
                test_instruo = Instruo.from_comment(test_comment)
                print(f"Instruo created: {test_instruo}\n")

                # Find the transform command in the instruo
                test_transform_komando = None
                for test_komando in test_instruo.commands:
                    if test_komando.name == "transform":
                        test_transform_komando = test_komando
                        break

                if test_transform_komando:
                    print(
                        handle(test_comment, test_instruo, test_transform_komando, None)
                    )
                else:
                    print("No !transform command found in comment")

            except Exception as err:
                print(f"Error: {err}")
