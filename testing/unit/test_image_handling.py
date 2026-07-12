#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""Tests for transform image download hardening."""

from io import BytesIO
from unittest.mock import MagicMock

import pytest
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
