#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""Tests for Wikipedia lookup helper failure handling."""

from unittest.mock import MagicMock

import requests

from ziwen_lookup import wp_utils


def test_wikipedia_lookup_treats_json_decode_as_lookup_miss(monkeypatch):
    """Malformed Wikipedia API responses should not escape the helper."""

    set_lang_mock = MagicMock()
    page_mock = MagicMock()

    monkeypatch.setattr(wp_utils.wikipedia, "set_lang", set_lang_mock)
    monkeypatch.setattr(
        wp_utils.wikipedia,
        "summary",
        MagicMock(side_effect=requests.exceptions.JSONDecodeError("bad json", "", 0)),
    )
    monkeypatch.setattr(wp_utils.wikipedia, "page", page_mock)

    assert wp_utils.wikipedia_lookup("ISO_639:abc") is None
    page_mock.assert_not_called()
    assert set_lang_mock.call_count == 2
    set_lang_mock.assert_called_with("en")


def test_wikipedia_page_url_treats_json_decode_as_lookup_miss(monkeypatch):
    """URL-only Wikipedia lookups should fail soft on malformed API responses."""

    monkeypatch.setattr(
        wp_utils.wikipedia,
        "page",
        MagicMock(side_effect=requests.exceptions.JSONDecodeError("bad json", "", 0)),
    )

    assert wp_utils.wikipedia_page_url("ISO 639:abc") is None


def test_wikipedia_lookup_treats_fallback_request_error_as_lookup_miss(monkeypatch):
    """Fallback lookup request failures should be skipped like a missing page."""

    set_lang_mock = MagicMock()
    page_mock = MagicMock()
    summary_mock = MagicMock(
        side_effect=[
            wp_utils.wikipedia.exceptions.PageError("ISO_639:abc"),
            requests.exceptions.ConnectionError("temporary network failure"),
        ]
    )

    monkeypatch.setattr(wp_utils.wikipedia, "set_lang", set_lang_mock)
    monkeypatch.setattr(wp_utils.wikipedia, "summary", summary_mock)
    monkeypatch.setattr(wp_utils.wikipedia, "page", page_mock)

    assert wp_utils.wikipedia_lookup("ISO_639:abc") is None
    page_mock.assert_not_called()
    assert set_lang_mock.call_count == 2
    set_lang_mock.assert_called_with("en")


def test_wikipedia_language_setup_uses_https_api():
    """The wikipedia package resets API_URL to HTTP; the helper restores HTTPS."""

    wp_utils._set_wikipedia_language("en")

    assert wp_utils.wikipedia_client.API_URL == "https://en.wikipedia.org/w/api.php"
    assert "translator-BOT-reborn" in wp_utils.wikipedia_client.USER_AGENT
