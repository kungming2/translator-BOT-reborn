#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""Tests for language reference lookup failure handling."""

from unittest.mock import MagicMock

from ziwen_lookup import reference


def test_language_reference_treats_wikipedia_json_decode_as_missing_link(
    monkeypatch, tmp_path
):
    """Malformed Wikipedia API responses should not abort reference lookup."""

    language_data_path = tmp_path / "language_data.yaml"
    language_data_path.write_text("abc: {}\n", encoding="utf-8")

    ethnologue_response = MagicMock()
    ethnologue_response.content = b"""
        <div class="view-display-id-page"><div>exists</div></div>
        <div class="alternate-names"><div></div><div><div>Example Alt</div></div></div>
        <div class="field-population"><div></div><div><p>1,234</p></div></div>
        <div class="a-language-of"><div><div><h2><a>Exampleland</a></h2></div></div></div>
        <div class="field-name-language-classification-link"><a>Example family</a></div>
    """
    ethnologue_response.raise_for_status = MagicMock()

    lingvo = MagicMock()
    lingvo.name = "Example"

    monkeypatch.setattr(
        reference.Paths, "STATES", {"LANGUAGE_DATA": language_data_path}
    )
    monkeypatch.setattr(reference, "get_lingvos", MagicMock(return_value={"abc": lingvo}))
    monkeypatch.setattr(reference, "get_random_useragent", MagicMock(return_value={}))
    monkeypatch.setattr(reference.requests, "get", MagicMock(return_value=ethnologue_response))
    monkeypatch.setattr(reference, "converter", MagicMock(return_value=lingvo))
    page_url_mock = MagicMock(return_value=None)
    monkeypatch.setattr(reference, "wikipedia_page_url", page_url_mock)

    result = reference._fetch_language_reference_data(
        "https://web.archive.org/web/20190606120000/https://www.ethnologue.com/language/abc",
        "abc",
    )

    assert result is not None
    assert result["language_code_3"] == "abc"
    assert result["link_wikipedia"] == ""
    page_url_mock.assert_called_once_with("ISO 639:abc")
