#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
Image handling functions, primarily for the transform command.
...

Logger tag: [I:IMAGE]
"""

# ─── Imports ──────────────────────────────────────────────────────────────────

import base64
import ipaddress
import logging
import socket
from io import BytesIO
from urllib.parse import urljoin, urlparse

import requests
from PIL import Image, UnidentifiedImageError

from config import SETTINGS, Paths, load_settings
from config import logger as _base_logger

# ─── Module-level constants ───────────────────────────────────────────────────

logger = logging.LoggerAdapter(_base_logger, {"tag": "I:IMAGE"})

access_credentials = load_settings(Paths.AUTH["API"])


def _int_setting(setting_name: str, *, minimum: int) -> int:
    """Return an integer setting at or above the required minimum."""
    value = SETTINGS.get(setting_name)
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        requirement = (
            "a positive integer"
            if minimum == 1
            else f"an integer of at least {minimum}"
        )
        raise RuntimeError(f"Setting '{setting_name}' must be {requirement}")
    return value


def _transform_hosts_setting() -> frozenset[str]:
    """Load and validate the transform image host allowlist."""
    value = SETTINGS.get("transform_allowed_image_hosts")
    if not isinstance(value, list) or not value:
        raise RuntimeError(
            "Setting 'transform_allowed_image_hosts' must be a non-empty list"
        )

    hosts: set[str] = set()
    for item in value:
        if not isinstance(item, str):
            raise RuntimeError(
                "Setting 'transform_allowed_image_hosts' must contain only strings"
            )
        host = item.strip().lower().rstrip(".")
        if not host or "://" in host or any(char in host for char in "/:@"):
            raise RuntimeError(
                "Setting 'transform_allowed_image_hosts' contains an invalid hostname"
            )
        hosts.add(host)

    return frozenset(hosts)


def _transform_download_timeout_setting() -> tuple[int, int]:
    """Load the validated requests connect/read timeout pair."""
    value = SETTINGS.get("transform_download_timeout_seconds")
    if not isinstance(value, dict):
        raise RuntimeError(
            "Setting 'transform_download_timeout_seconds' must be a mapping"
        )

    timeouts: list[int] = []
    for key in ("connect", "read"):
        timeout = value.get(key)
        if isinstance(timeout, bool) or not isinstance(timeout, int) or timeout <= 0:
            raise RuntimeError(
                f"Setting 'transform_download_timeout_seconds.{key}' "
                "must be a positive integer"
            )
        timeouts.append(timeout)

    return timeouts[0], timeouts[1]


ALLOWED_TRANSFORM_IMAGE_HOSTS = _transform_hosts_setting()
ALLOWED_TRANSFORM_CONTENT_TYPES = frozenset({"image/jpeg", "image/png", "image/webp"})
MAX_TRANSFORM_IMAGE_BYTES = _int_setting("transform_max_image_bytes", minimum=1)
MAX_TRANSFORM_IMAGE_PIXELS = _int_setting("transform_max_image_pixels", minimum=1)
MAX_TRANSFORM_IMAGE_DIMENSION = _int_setting("transform_max_image_dimension", minimum=1)
MAX_TRANSFORM_REDIRECTS = _int_setting("transform_max_redirects", minimum=0)
TRANSFORM_DOWNLOAD_TIMEOUT = _transform_download_timeout_setting()
TRANSFORM_UPLOAD_TIMEOUT = _int_setting("transform_upload_timeout_seconds", minimum=1)

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


class TransformImageError(ValueError):
    """Raised when a transform source image is unsafe or unsupported."""


class ImgBBUploadError(RuntimeError):
    """Raised when a transformed image cannot be uploaded to ImgBB."""


def _validate_transform_url(url: str) -> str:
    parsed = urlparse(url.strip())
    if parsed.scheme not in {"http", "https"}:
        raise TransformImageError("Image URL must use http or https.")
    if not parsed.hostname:
        raise TransformImageError("Image URL must include a hostname.")
    if parsed.username or parsed.password:
        raise TransformImageError("Image URL must not include credentials.")

    hostname = parsed.hostname.lower()
    if hostname not in ALLOWED_TRANSFORM_IMAGE_HOSTS:
        raise TransformImageError(f"Image host is not allowed: {hostname}")

    _validate_public_hostname(hostname)
    return parsed.geturl()


def _validate_public_hostname(hostname: str) -> None:
    try:
        addr_infos = socket.getaddrinfo(hostname, None)
    except socket.gaierror as e:
        raise TransformImageError(f"Unable to resolve image host: {hostname}") from e

    addresses = {info[4][0] for info in addr_infos}
    if not addresses:
        raise TransformImageError(f"Unable to resolve image host: {hostname}")

    for address in addresses:
        ip = ipaddress.ip_address(address)
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or ip.is_unspecified
        ):
            raise TransformImageError(f"Image host resolves to blocked IP: {address}")


def _is_allowed_content_type(content_type: str) -> bool:
    media_type = content_type.split(";", 1)[0].strip().lower()
    return media_type in ALLOWED_TRANSFORM_CONTENT_TYPES


def _fetch_transform_image_bytes(image_url: str) -> bytes:
    current_url = _validate_transform_url(image_url)

    for _redirect_count in range(MAX_TRANSFORM_REDIRECTS + 1):
        with requests.get(
            current_url,
            allow_redirects=False,
            stream=True,
            timeout=TRANSFORM_DOWNLOAD_TIMEOUT,
        ) as response:
            if response.is_redirect or response.is_permanent_redirect:
                location = response.headers.get("Location")
                if not location:
                    raise TransformImageError(
                        "Image redirect did not include Location."
                    )
                current_url = _validate_transform_url(urljoin(current_url, location))
                continue

            response.raise_for_status()

            content_type = response.headers.get("Content-Type", "")
            if not _is_allowed_content_type(content_type):
                raise TransformImageError(
                    f"Image response has unsupported Content-Type: {content_type}"
                )

            content_length = response.headers.get("Content-Length")
            if (
                content_length
                and content_length.isdigit()
                and int(content_length) > MAX_TRANSFORM_IMAGE_BYTES
            ):
                raise TransformImageError("Image response is too large.")

            buffer = BytesIO()
            downloaded = 0
            for chunk in response.iter_content(chunk_size=8192):
                if not chunk:
                    continue
                downloaded += len(chunk)
                if downloaded > MAX_TRANSFORM_IMAGE_BYTES:
                    raise TransformImageError("Image response exceeded size limit.")
                buffer.write(chunk)

            return buffer.getvalue()

    raise TransformImageError("Image URL redirected too many times.")


def _open_transform_image(image_bytes: bytes) -> Image.Image:
    previous_max_pixels = Image.MAX_IMAGE_PIXELS
    Image.MAX_IMAGE_PIXELS = MAX_TRANSFORM_IMAGE_PIXELS

    try:
        with Image.open(BytesIO(image_bytes)) as image:
            image.verify()

        img = Image.open(BytesIO(image_bytes))
        width, height = img.size
        if (
            width > MAX_TRANSFORM_IMAGE_DIMENSION
            or height > MAX_TRANSFORM_IMAGE_DIMENSION
            or width * height > MAX_TRANSFORM_IMAGE_PIXELS
        ):
            raise TransformImageError("Image dimensions are too large.")

        img.load()
        return img
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as e:
        raise TransformImageError("Image response could not be decoded.") from e
    finally:
        Image.MAX_IMAGE_PIXELS = previous_max_pixels


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

    try:
        img = _open_transform_image(_fetch_transform_image_bytes(image_url))
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to download image from {image_url}: {e}")
        raise
    except TransformImageError as e:
        logger.error(f"Failed to open image from {image_url}: {e}")
        raise
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


# ─── Image encoding ───────────────────────────────────────────────────────────


def _to_jpeg(image: Image.Image) -> bytes:
    """
    Convert a PIL Image to JPEG bytes, compositing transparency onto white
    when necessary (JPEG does not support an alpha channel).
    """
    if image.mode in ("RGBA", "LA", "P"):
        logger.debug(f"Converting image from {image.mode} to RGB for JPEG compression")
        # Normalise to RGBA so paste() always receives a consistent source mode.
        image = image.convert("RGBA")
        rgb_image = Image.new("RGB", image.size, (255, 255, 255))
        mask = image.split()[-1]  # Alpha channel from RGBA
        rgb_image.paste(image, mask=mask)
        image = rgb_image
    elif image.mode != "RGB":
        image = image.convert("RGB")

    buffered = BytesIO()
    jpeg_quality: int = SETTINGS["image_jpeg_quality"]
    image.save(buffered, format="JPEG", quality=jpeg_quality)
    logger.debug(f"Image encoded to base64 (JPEG quality: {jpeg_quality}%)")
    return buffered.getvalue()


# ─── Image upload ─────────────────────────────────────────────────────────────


def upload_to_imgbb(image: Image.Image, title: str | None = None) -> str:
    """
    Upload a PIL Image to ImgBB and return the hosted URL.

    :param image: PIL Image object to upload.
    :param title: Optional filename/title for the upload.
    :return: URL of the uploaded image.
    :raises ImgBBUploadError: If the request fails or ImgBB rejects the upload.
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
    try:
        response = requests.post(
            "https://api.imgbb.com/1/upload",
            data=payload,
            timeout=TRANSFORM_UPLOAD_TIMEOUT,
        )
    except requests.RequestException as e:
        logger.error(f"ImgBB upload request failed: {type(e).__name__}: {e}")
        raise ImgBBUploadError("The image-hosting service could not be reached.") from e

    if not response.ok:
        # ImgBB normally returns a small JSON error object. Record it before
        # raising, since requests' default HTTPError text omits the response
        # body that explains why the upload was rejected. Redact the API key
        # defensively in case an upstream response ever echoes request data.
        response_body = response.text.strip() or "<empty response body>"
        response_body = response_body.replace(
            access_credentials["IMGBB_API_KEY"], "<redacted API key>"
        )[:2000]
        logger.error(
            f"ImgBB upload rejected: HTTP {response.status_code} "
            f"{response.reason}; response: {response_body}"
        )
        raise ImgBBUploadError(
            f"The image-hosting service rejected the upload "
            f"(HTTP {response.status_code})."
        )

    result = response.json()
    if result.get("success"):
        url: str = result["data"]["url"]
        logger.info(f"Image uploaded successfully at {result['data']['display_url']}")
        return url

    logger.error(f"ImgBB reported an unsuccessful upload: {result}")
    raise ImgBBUploadError("The image-hosting service reported an unsuccessful upload.")
