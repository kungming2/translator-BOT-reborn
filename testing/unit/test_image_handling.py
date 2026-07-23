#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""Tests for transform image download hardening."""

from io import BytesIO
from unittest.mock import MagicMock

import pytest
import requests
from PIL import Image

from integrations import image_handling


class FakeResponse:
    def __init__(
        self,
        *,
        body: bytes = b"image",
        headers: dict[str, str] | None = None,
        redirect: bool = False,
    ) -> None:
        self.body = body
        self.headers = headers or {"Content-Type": "image/png"}
        self.is_redirect = redirect
        self.is_permanent_redirect = False

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    @staticmethod
    def raise_for_status() -> None:
        return None

    def iter_content(self, chunk_size: int = 8192):
        for index in range(0, len(self.body), chunk_size):
            yield self.body[index : index + chunk_size]


def _public_dns(_hostname: str, _port: object) -> list[tuple]:
    return [(None, None, None, None, ("93.184.216.34", 0))]


def _private_dns(_hostname: str, _port: object) -> list[tuple]:
    return [(None, None, None, None, ("127.0.0.1", 0))]


def _png_bytes(width: int = 2, height: int = 2) -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (width, height), "white").save(buffer, format="PNG")
    return buffer.getvalue()


def test_transform_settings_load_validated_values(monkeypatch) -> None:
    monkeypatch.setitem(
        image_handling.SETTINGS,
        "transform_allowed_image_hosts",
        ["I.REDD.IT.", "i.imgur.com"],
    )
    monkeypatch.setitem(
        image_handling.SETTINGS,
        "transform_download_timeout_seconds",
        {"connect": 4, "read": 12},
    )

    assert image_handling._transform_hosts_setting() == frozenset(
        {"i.redd.it", "i.imgur.com"}
    )
    assert image_handling._transform_download_timeout_setting() == (4, 12)


@pytest.mark.parametrize("value", [None, True, 0, -1, 1.5, "5"])
def test_transform_positive_integer_setting_rejects_invalid_values(
    monkeypatch, value: object
) -> None:
    monkeypatch.setitem(image_handling.SETTINGS, "test_transform_limit", value)

    with pytest.raises(RuntimeError, match="must be a positive integer"):
        image_handling._int_setting("test_transform_limit", minimum=1)


def test_transform_integer_setting_allows_zero_at_zero_minimum(monkeypatch) -> None:
    monkeypatch.setitem(image_handling.SETTINGS, "test_transform_limit", 0)

    assert image_handling._int_setting("test_transform_limit", minimum=0) == 0


def test_transform_fetch_rejects_untrusted_host(monkeypatch) -> None:
    get_mock = MagicMock()
    monkeypatch.setattr(image_handling.socket, "getaddrinfo", _public_dns)
    monkeypatch.setattr(image_handling.requests, "get", get_mock)

    with pytest.raises(image_handling.TransformImageError, match="not allowed"):
        image_handling._fetch_transform_image_bytes("https://example.com/image.jpg")

    get_mock.assert_not_called()


def test_transform_fetch_rejects_allowed_host_private_dns(monkeypatch) -> None:
    get_mock = MagicMock()
    monkeypatch.setattr(image_handling.socket, "getaddrinfo", _private_dns)
    monkeypatch.setattr(image_handling.requests, "get", get_mock)

    with pytest.raises(image_handling.TransformImageError, match="blocked IP"):
        image_handling._fetch_transform_image_bytes("https://i.redd.it/image.jpg")

    get_mock.assert_not_called()


def test_transform_fetch_rejects_redirect_to_untrusted_host(monkeypatch) -> None:
    monkeypatch.setattr(image_handling.socket, "getaddrinfo", _public_dns)
    monkeypatch.setattr(
        image_handling.requests,
        "get",
        MagicMock(
            return_value=FakeResponse(
                headers={"Location": "https://example.com/image.jpg"},
                redirect=True,
            )
        ),
    )

    with pytest.raises(image_handling.TransformImageError, match="not allowed"):
        image_handling._fetch_transform_image_bytes("https://i.redd.it/image.jpg")


def test_transform_fetch_rejects_oversized_content_length(monkeypatch) -> None:
    monkeypatch.setattr(image_handling.socket, "getaddrinfo", _public_dns)
    monkeypatch.setattr(
        image_handling.requests,
        "get",
        MagicMock(
            return_value=FakeResponse(
                headers={
                    "Content-Type": "image/png",
                    "Content-Length": str(image_handling.MAX_TRANSFORM_IMAGE_BYTES + 1),
                }
            )
        ),
    )

    with pytest.raises(image_handling.TransformImageError, match="too large"):
        image_handling._fetch_transform_image_bytes("https://i.redd.it/image.jpg")


def test_transform_fetch_rejects_stream_over_byte_limit(monkeypatch) -> None:
    monkeypatch.setattr(image_handling.socket, "getaddrinfo", _public_dns)
    monkeypatch.setattr(image_handling, "MAX_TRANSFORM_IMAGE_BYTES", 3)
    monkeypatch.setattr(
        image_handling.requests,
        "get",
        MagicMock(
            return_value=FakeResponse(
                body=b"1234",
                headers={"Content-Type": "image/png"},
            )
        ),
    )

    with pytest.raises(image_handling.TransformImageError, match="exceeded size"):
        image_handling._fetch_transform_image_bytes("https://i.redd.it/image.jpg")


def test_transform_fetch_rejects_wrong_content_type(monkeypatch) -> None:
    monkeypatch.setattr(image_handling.socket, "getaddrinfo", _public_dns)
    monkeypatch.setattr(
        image_handling.requests,
        "get",
        MagicMock(
            return_value=FakeResponse(headers={"Content-Type": "text/html"})
        ),
    )

    with pytest.raises(image_handling.TransformImageError, match="Content-Type"):
        image_handling._fetch_transform_image_bytes("https://i.redd.it/image.jpg")


def test_open_transform_image_rejects_oversized_dimensions(monkeypatch) -> None:
    monkeypatch.setattr(image_handling, "MAX_TRANSFORM_IMAGE_DIMENSION", 1)

    with pytest.raises(image_handling.TransformImageError, match="dimensions"):
        image_handling._open_transform_image(_png_bytes(width=2, height=2))


def test_rotate_or_flip_image_accepts_safe_png(monkeypatch) -> None:
    monkeypatch.setattr(image_handling.socket, "getaddrinfo", _public_dns)
    monkeypatch.setattr(
        image_handling.requests,
        "get",
        MagicMock(
            return_value=FakeResponse(
                body=_png_bytes(width=2, height=1),
                headers={"Content-Type": "image/png"},
            )
        ),
    )

    result = image_handling.rotate_or_flip_image("https://i.redd.it/image.png", "90")

    assert result.size == (1, 2)


def test_imgbb_rejection_logs_response_and_raises_safe_error(monkeypatch) -> None:
    api_key = image_handling.access_credentials["IMGBB_API_KEY"]
    response = MagicMock(
        ok=False,
        status_code=400,
        reason="Bad Request",
        text=(
            '{"error":{"message":"Invalid API v1 key.","code":100},'
            f'"echoed_key":"{api_key}","status_code":400}}'
        ),
    )
    post_mock = MagicMock(return_value=response)
    error_mock = MagicMock()
    monkeypatch.setattr(image_handling.requests, "post", post_mock)
    monkeypatch.setattr(image_handling.logger, "error", error_mock)

    with pytest.raises(
        image_handling.ImgBBUploadError,
        match=r"image-hosting service rejected the upload \(HTTP 400\)",
    ):
        image_handling.upload_to_imgbb(Image.new("RGB", (1, 1), "white"))

    logged_message = error_mock.call_args.args[0]
    assert "HTTP 400 Bad Request" in logged_message
    assert "Invalid API v1 key" in logged_message
    assert "<redacted API key>" in logged_message
    assert api_key not in logged_message


def test_imgbb_connection_failure_raises_host_specific_error(monkeypatch) -> None:
    monkeypatch.setattr(
        image_handling.requests,
        "post",
        MagicMock(side_effect=requests.ConnectionError("network unavailable")),
    )

    with pytest.raises(
        image_handling.ImgBBUploadError,
        match="image-hosting service could not be reached",
    ):
        image_handling.upload_to_imgbb(Image.new("RGB", (1, 1), "white"))


def test_upload_image_url_to_imgbb_reuses_transform_pipeline(monkeypatch) -> None:
    image_bytes = _png_bytes(width=2, height=1)
    image = Image.new("RGB", (2, 1), "white")
    fetch_mock = MagicMock(return_value=image_bytes)
    open_mock = MagicMock(return_value=image)
    upload_mock = MagicMock(return_value="https://imgbb.example/upload.jpg")
    monkeypatch.setattr(image_handling, "_fetch_transform_image_bytes", fetch_mock)
    monkeypatch.setattr(image_handling, "_open_transform_image", open_mock)
    monkeypatch.setattr(image_handling, "upload_to_imgbb", upload_mock)

    result = image_handling.upload_image_url_to_imgbb(
        "https://i.redd.it/image.png", title="Devtools upload"
    )

    assert result == "https://imgbb.example/upload.jpg"
    fetch_mock.assert_called_once_with("https://i.redd.it/image.png")
    open_mock.assert_called_once_with(image_bytes)
    upload_mock.assert_called_once_with(image, title="Devtools upload")
