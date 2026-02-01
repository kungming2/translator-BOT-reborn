#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
Handler for the !transform command, which rotates or flips images from posts.
"""

from config import SETTINGS, logger
from connection import REDDIT_HELPER
from image_handling import TRANSFORM_MAP, rotate_or_flip_image, upload_to_imgbb
from models.instruo import Instruo
from reddit_sender import message_reply
from responses import RESPONSE
from utility import check_url_extension

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
        message_reply(
            comment, RESPONSE.COMMENT_TRANSFORM_NO_DATA + RESPONSE.BOT_DISCLAIMER
        )
        return

    transformation = komando.data[0]

    # Validate transformation
    if transformation not in VALID_TRANSFORMS:
        message_reply(
            comment,
            RESPONSE.COMMENT_TRANSFORM_INVALID.format(transformation)
            + RESPONSE.BOT_DISCLAIMER,
        )
        return

    # Get the submission
    submission = comment.submission

    # Check if submission has an image URL
    if submission.is_self:
        message_reply(
            comment, RESPONSE.COMMENT_TRANSFORM_NOT_IMAGE_POST + RESPONSE.BOT_DISCLAIMER
        )
        return

    image_url = submission.url

    # Verify the URL points to an image
    if not check_url_extension(image_url):
        message_reply(
            comment,
            RESPONSE.COMMENT_TRANSFORM_NO_DIRECT_IMAGE + RESPONSE.BOT_DISCLAIMER,
        )
        return

    logger.info(
        f"[ZW] Transform: Processing image from {image_url} with transformation: {transformation}"
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

    try:
        # Transform the image
        transformed_image = rotate_or_flip_image(image_url, transformation)
        logger.info("[ZW] Transform: Image transformed successfully")

        # Upload to ImgBB with submission title as the name
        uploaded_url = upload_to_imgbb(
            transformed_image,
            title=submission.title[:200],  # Limit to 200 chars for API
        )
        logger.info(f"[ZW] Transform: Image uploaded to {uploaded_url}")

    except Exception as e:
        logger.error(f"[ZW] Transform: Error processing image: {e}")
        message_reply(
            comment,
            RESPONSE.COMMENT_TRANSFORM_ERROR.format(str(e)) + RESPONSE.BOT_DISCLAIMER,
        )
        return

    # Reply with the transformed image URL
    message_reply(
        comment,
        RESPONSE.COMMENT_TRANSFORM_SUCCESS_REPLY.format(
            transform_desc, uploaded_url, expiration_days
        )
        + RESPONSE.BOT_DISCLAIMER,
    )


if "__main__" == __name__:
    while True:
        # Get comment URL from user
        comment_url: str = input(
            "Enter Reddit comment URL (or 'quit' to exit): "
        ).strip()

        # Check for exit
        if comment_url.lower() in ["quit", "exit", "q"]:
            break

        # Get comment from URL and process
        test_comment = REDDIT_HELPER.comment(url=comment_url)
        test_instruo: Instruo = Instruo.from_comment(test_comment)
        print(f"Instruo created: {test_instruo}\n")

        # Find the transform command in the instruo
        transform_komando = None
        for test_komando in test_instruo.commands:
            if test_komando.name == "transform":
                transform_komando = test_komando
                break

        if transform_komando:
            print(handle(test_comment, test_instruo, transform_komando, None))
        else:
            print("No !transform command found in comment")
