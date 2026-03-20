#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
Integration tests for utility.py.

These tests hit live external services (Reddit CDN, YouTube) and are
intentionally separated from unit tests.  Run with::

    pytest test_utility_integration.py -v

Markers
-------
- ``integration``   – requires network access
- ``slow``          – may take a few seconds (image download, yt-dlp)

To skip slow tests::

    pytest test_utility_integration.py -v -m "not slow"
"""

import re

import pytest

from utility import (
    check_url_extension,
    clean_reddit_image_url,
    fetch_youtube_length,
    format_markdown_table_with_padding,
    generate_image_hash,
    is_valid_image_url,
)

# ---------------------------------------------------------------------------
# Constants used across tests
# ---------------------------------------------------------------------------

YOUTUBE_URL = "https://www.youtube.com/watch?v=Bbp9ZaJD_eA"

IMAGE_URL_PNG = "https://i.redd.it/5jwg3hv3jfq61.png"
IMAGE_URL_JPG = "https://i.redd.it/yi32txfcaisc1.jpg"

PREVIEW_URL_PNG = (
    "https://preview.redd.it/5jwg3hv3jfq61.png"
    "?width=2253&format=pjpg&auto=webp&s=abc123"
)
PREVIEW_URL_JPG = (
    "https://preview.redd.it/yi32txfcaisc1.jpg"
    "?width=1080&format=pjpg&auto=webp&s=def456"
)

# ---------------------------------------------------------------------------
# check_url_extension
# ---------------------------------------------------------------------------


class TestCheckUrlExtension:
    """Unit-style tests – no network needed."""

    @pytest.mark.parametrize(
        "url",
        [
            "https://i.redd.it/abc.jpg",
            "https://i.redd.it/abc.jpeg",
            "https://i.redd.it/abc.png",
            "https://i.redd.it/abc.webp",
            "https://i.redd.it/abc.JPG",  # case-insensitive
            "https://i.redd.it/abc.PNG",
        ],
    )
    def test_valid_extensions(self, url: str) -> None:
        assert check_url_extension(url) is True

    @pytest.mark.parametrize(
        "url",
        [
            "",
            "   ",
            None,  # type: ignore[arg-type]
            "https://i.redd.it/abc.gif",
            "https://i.redd.it/abc.bmp",
            "https://i.redd.it/abc.jpg?width=800",  # query params break the \Z anchor
            "https://example.com/page",
        ],
    )
    def test_invalid_extensions(self, url: str) -> None:
        assert check_url_extension(url) is False

    def test_whitespace_only_url(self) -> None:
        assert check_url_extension("   \n\t  ") is False


# ---------------------------------------------------------------------------
# clean_reddit_image_url
# ---------------------------------------------------------------------------


class TestCleanRedditImageUrl:
    def test_preview_to_direct(self) -> None:
        cleaned = clean_reddit_image_url(PREVIEW_URL_PNG)
        assert cleaned.startswith("https://i.redd.it/")
        assert "?" not in cleaned

    def test_strips_query_params(self) -> None:
        url = "https://i.redd.it/abc.jpg?width=100&s=xyz"
        assert clean_reddit_image_url(url) == "https://i.redd.it/abc.jpg"

    def test_already_clean_url_unchanged(self) -> None:
        assert clean_reddit_image_url(IMAGE_URL_PNG) == IMAGE_URL_PNG

    def test_non_reddit_url_unchanged(self) -> None:
        url = "https://example.com/image.jpg"
        assert clean_reddit_image_url(url) == url


# ---------------------------------------------------------------------------
# is_valid_image_url
# ---------------------------------------------------------------------------


class TestIsValidImageUrl:
    def test_direct_png_url(self) -> None:
        assert is_valid_image_url(IMAGE_URL_PNG) is True

    def test_direct_jpg_url(self) -> None:
        assert is_valid_image_url(IMAGE_URL_JPG) is True

    def test_preview_url_with_format_pjpg(self) -> None:
        assert is_valid_image_url(PREVIEW_URL_PNG) is True

    def test_preview_url_jpg(self) -> None:
        assert is_valid_image_url(PREVIEW_URL_JPG) is True

    def test_empty_string(self) -> None:
        assert is_valid_image_url("") is False

    def test_none_value(self) -> None:
        assert is_valid_image_url(None) is False  # type: ignore[arg-type]

    def test_non_image_url(self) -> None:
        assert is_valid_image_url("https://www.reddit.com/r/translator/") is False

    def test_url_with_image_ext_and_query_params(self) -> None:
        url = "https://example.com/photo.png?v=1"
        assert is_valid_image_url(url) is True


# ---------------------------------------------------------------------------
# generate_image_hash  (integration – downloads images)
# ---------------------------------------------------------------------------


class TestGenerateImageHash:
    def test_png_returns_hash_string(self) -> None:
        result = generate_image_hash(IMAGE_URL_PNG)
        assert result is not None
        assert isinstance(result, str)
        assert len(result) > 0

    def test_jpg_returns_hash_string(self) -> None:
        result = generate_image_hash(IMAGE_URL_JPG)
        assert result is not None
        assert isinstance(result, str)
        assert len(result) > 0

    def test_same_url_produces_same_hash(self) -> None:
        hash1 = generate_image_hash(IMAGE_URL_PNG)
        hash2 = generate_image_hash(IMAGE_URL_PNG)
        assert hash1 is not None
        assert hash1 == hash2

    def test_different_images_produce_different_hashes(self) -> None:
        hash_png = generate_image_hash(IMAGE_URL_PNG)
        hash_jpg = generate_image_hash(IMAGE_URL_JPG)
        assert hash_png is not None
        assert hash_jpg is not None
        assert hash_png != hash_jpg

    def test_invalid_url_returns_none(self) -> None:
        result = generate_image_hash("https://i.redd.it/this_does_not_exist_xyz.png")
        assert result is None

    def test_empty_url_returns_none(self) -> None:
        assert generate_image_hash("") is None

    def test_non_image_url_returns_none(self) -> None:
        # A URL that returns HTML, not an image
        result = generate_image_hash("https://www.reddit.com")
        assert result is None


# ---------------------------------------------------------------------------
# fetch_youtube_length  (integration – calls yt-dlp)
# ---------------------------------------------------------------------------


class TestFetchYoutubeLength:
    def test_returns_positive_integer(self) -> None:
        duration = fetch_youtube_length(YOUTUBE_URL)
        assert duration is not None
        assert isinstance(duration, int)
        assert duration > 0

    def test_empty_url_returns_none(self) -> None:
        assert fetch_youtube_length("") is None

    def test_none_url_returns_none(self) -> None:
        assert fetch_youtube_length(None) is None  # type: ignore[arg-type]

    def test_invalid_url_returns_none(self) -> None:
        result = fetch_youtube_length("https://www.youtube.com/watch?v=INVALID_ID_XYZ")
        assert result is None

    def test_non_youtube_url_returns_none(self) -> None:
        result = fetch_youtube_length("https://www.example.com/not-a-video")
        assert result is None


# ---------------------------------------------------------------------------
# format_markdown_table_with_padding
# ---------------------------------------------------------------------------


class TestFormatMarkdownTableWithPadding:
    SIMPLE_TABLE = """\
| Name  | Score |
|-------|-------|
| Alice | 100   |
| Bob   | 85    |
"""

    def test_empty_input_returns_placeholder(self) -> None:
        result = format_markdown_table_with_padding("")
        assert "No table provided" in result
        assert result.startswith("```")

    def test_returns_code_block(self) -> None:
        result = format_markdown_table_with_padding(self.SIMPLE_TABLE)
        assert "```" in result

    def test_table_rows_present_in_output(self) -> None:
        result = format_markdown_table_with_padding(self.SIMPLE_TABLE)
        assert "Alice" in result
        assert "Bob" in result

    def test_columns_are_padded(self) -> None:
        result = format_markdown_table_with_padding(self.SIMPLE_TABLE)
        # Each data row should be pipe-delimited with spaces around cells
        lines = [
            line for line in result.splitlines() if "|" in line and "---" not in line
        ]
        # All content rows should have the same length (uniform padding)
        widths = [len(line) for line in lines]
        assert len(set(widths)) == 1, f"Rows have inconsistent widths: {widths}"

    def test_header_outside_code_block(self) -> None:
        text_with_header = "Top scores\n\n" + self.SIMPLE_TABLE
        result = format_markdown_table_with_padding(text_with_header)
        # Header appears before the opening backtick fence
        header_pos = result.index("Top scores")
        fence_pos = result.index("```")
        assert header_pos < fence_pos

    def test_separator_row_uses_dashes(self) -> None:
        result = format_markdown_table_with_padding(self.SIMPLE_TABLE)
        # Separator row should contain only dashes and pipes/spaces
        lines = [line for line in result.splitlines() if "---" in line]
        assert len(lines) == 1
        assert re.match(r"^\|[-| ]+\|$", lines[0]), f"Unexpected separator: {lines[0]}"

    def test_no_pipe_table_returns_placeholder(self) -> None:
        result = format_markdown_table_with_padding("just some text, no pipes")
        assert "No valid table found" in result

    def test_single_column_table(self) -> None:
        table = "| Item |\n|------|\n| A |\n| BB |\n"
        result = format_markdown_table_with_padding(table)
        assert "A" in result
        assert "BB" in result
