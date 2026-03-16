#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
Image handling functions, primarily for the transform command.
...

Logger tag: [IMAGE]
"""

import base64
import logging
from io import BytesIO

import requests
from PIL import Image

from config import SETTINGS, Paths, load_settings
from config import logger as _base_logger

logger = logging.LoggerAdapter(_base_logger, {"tag": "IMAGE"})


# ─── Module-level constants ───────────────────────────────────────────────────

access_credentials = load_settings(Paths.AUTH["CREDENTIALS"])

# Normalisation map for shorthand codes and counterclockwise degree values.
TRANSFORM_MAP: dict[str, str] = {
    "h": "flip_h",
    "v": "flip_v",
    "horizontal": "flip_h",
    "vertical": "flip_v",
    "-90": "270",
    "-180": "180",
    "-270": "90",
}


# ─── Image transformation ─────────────────────────────────────────────────────


def rotate_or_flip_image(image_url: str, transformation: str) -> Image.Image:
    """
    Download an image from a URL and apply a rotation or flip transformation.

    :param image_url: URL of the image to process.
    :param transformation: One of ``'90'``, ``'180'``, ``'270'``,
                           ``'flip_h'``, ``'flip_v'`` (or a shorthand
                           alias defined in ``TRANSFORM_MAP``).
    :return: Transformed PIL Image object.
    :raises ValueError: If the transformation string is not recognised.
    """
    transformation = TRANSFORM_MAP.get(transformation, transformation)
    logger.debug(f"Downloading image from {image_url}")

    response = requests.get(image_url, timeout=45)
    response.raise_for_status()

    img: Image.Image = Image.open(BytesIO(response.content))
    logger.debug(
        f"Image downloaded: {img.size[0]}x{img.size[1]} pixels, mode: {img.mode}"
    )

    if transformation == "90":
        img = img.rotate(-90, expand=True)
    elif transformation == "180":
        img = img.rotate(180, expand=True)
    elif transformation == "270":
        img = img.rotate(90, expand=True)
    elif transformation == "flip_h":
        img = img.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
    elif transformation == "flip_v":
        img = img.transpose(Image.Transpose.FLIP_TOP_BOTTOM)
    else:
        raise ValueError(
            f"Invalid transformation: {transformation!r}. "
            "Use '90', '180', '270', 'flip_h', or 'flip_v'."
        )

    logger.debug(f"Applied transformation: {transformation}")
    return img


# ─── Image upload ─────────────────────────────────────────────────────────────


def _to_jpeg(image: Image.Image) -> bytes:
    """
    Convert a PIL Image to JPEG bytes, compositing transparency onto white
    when necessary (JPEG does not support an alpha channel).
    """
    if image.mode in ("RGBA", "LA", "P"):
        logger.debug(f"Converting image from {image.mode} to RGB for JPEG compression")
        if image.mode == "P":
            image = image.convert("RGBA")
        rgb_image = Image.new("RGB", image.size, (255, 255, 255))
        mask = image.split()[-1] if image.mode in ("RGBA", "LA") else None
        rgb_image.paste(image, mask=mask)
        image = rgb_image
    elif image.mode != "RGB":
        image = image.convert("RGB")

    buffered = BytesIO()
    jpeg_quality: int = SETTINGS["image_jpeg_quality"]
    image.save(buffered, format="JPEG", quality=jpeg_quality)
    logger.debug(f"Image encoded to base64 (JPEG quality: {jpeg_quality}%)")
    return buffered.getvalue()


def upload_to_imgbb(image: Image.Image, title: str | None = None) -> str:
    """
    Upload a PIL Image to ImgBB and return the hosted URL.

    :param image: PIL Image object to upload.
    :param title: Optional filename/title for the upload.
    :return: URL of the uploaded image.
    :raises requests.HTTPError: If the HTTP request fails.
    :raises Exception: If ImgBB reports an unsuccessful upload.
    """
    # Expiration is stored in settings as days; the API expects seconds.
    expiration_seconds: int = SETTINGS["image_retention_age"] * 86400
    img_base64: str = base64.b64encode(_to_jpeg(image)).decode("utf-8")

    payload: dict = {
        "key": access_credentials["IMGBB_API_KEY"],
        "image": img_base64,
        "expiration": expiration_seconds,
    }
    if title:
        payload["name"] = title

    logger.debug(f"Uploading to ImgBB (expiration: {expiration_seconds}s)")
    response = requests.post("https://api.imgbb.com/1/upload", data=payload, timeout=45)
    response.raise_for_status()

    result = response.json()
    if result.get("success"):
        url: str = result["data"]["url"]
        logger.info(f"Image uploaded successfully at {result['data']['display_url']}")
        return url

    logger.error(f"Upload failed: {result}")
    raise Exception(f"Upload failed: {result}")


# ─── Entry point ──────────────────────────────────────────────────────────────


def _show_menu() -> None:
    print("\nSelect an operation:")
    print("1. Rotate/Flip image from URL (without uploading)")
    print("2. Rotate/Flip image and upload to ImgBB")
    print("x. Exit")


def _prompt_transformation() -> str:
    print("\nTransformation options:")
    print("  90     - Rotate 90° clockwise")
    print("  180    - Rotate 180° (upside-down)")
    print("  270    - Rotate 270° clockwise")
    print("  flip_h - Flip horizontally")
    print("  flip_v - Flip vertically")
    return input("Enter transformation: ")


if __name__ == "__main__":
    while True:
        _show_menu()
        choice = input("Enter your choice (1-2 or x): ")

        if choice == "x":
            print("Exiting...")
            break

        if choice not in ("1", "2"):
            print("Invalid choice, please try again.")
            continue

        image_test_url = input("Enter the image URL: ")
        transformation_type = _prompt_transformation()

        try:
            img_test = rotate_or_flip_image(image_test_url, transformation_type)

            if choice == "1":
                logger.info(
                    f"Image transformed successfully: "
                    f"{img_test.size} pixels, format: {img_test.format}"
                )
                if input("Save locally? (y/n): ").lower() == "y":
                    filename = input("Enter filename (e.g., output.png): ")
                    img_test.save(filename)
                    logger.info(f"Saved to {filename}")

            elif choice == "2":
                logger.info("Image transformed, uploading to ImgBB...")
                uploaded_url = upload_to_imgbb(img_test)
                print("\nUploaded successfully!")
                logger.info(f"Image URL: {uploaded_url}")

        except Exception as e:
            logger.error(f"Error: {e}")
