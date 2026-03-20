#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
Integration tests for Wikipedia and OSM lookup pipeline.

Tests the full stack: wikipedia_lookup → get_page_location_data →
search_nominatim (Nominatim API).

Test subjects
─────────────
  No coordinates : Esperanto         – language article, no coordinates
  With coordinates: Forbidden City   – landmark, has coordinates
                    Chongqing        – city, has coordinates

Run with:
    pytest test_wp.py -v
or:
    python -m pytest test_wp.py -v --tb=short

Requirements (beyond the project's own deps):
    pip install pytest wikipedia
"""

import re

import pytest
import wikipedia

# ── project imports ───────────────────────────────────────────────────────────
from ziwen_lookup.wp_utils import wikipedia_lookup, get_page_location_data
from ziwen_lookup.osm import search_nominatim


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


def _assert_entry_header(output: str, term: str, context: str) -> None:
    """Assert the output contains a bold Markdown link header for the term."""
    assert re.search(
        rf"\*\*\[{re.escape(term.title())}[^]]*]\(http" , output, re.IGNORECASE
    ), f"[{context}] Missing bold link header for '{term}'"


def _assert_blockquote_summary(output: str, context: str) -> None:
    """Assert the output contains a blockquote summary line."""
    assert re.search(r"^> .+", output, re.MULTILINE), (
        f"[{context}] Missing blockquote summary (> ...)"
    )


def _assert_no_location_block(output: str, context: str) -> None:
    """Assert the output does NOT contain a location results block."""
    assert "*Location results*" not in output, (
        f"[{context}] Expected no location block, but found one"
    )


def _assert_location_block(output: str, context: str) -> None:
    """Assert the output contains a location results block."""
    assert "*Location results*" in output, (
        f"[{context}] Expected location block to be present"
    )


# ─────────────────────────────────────────────────────────────────────────────
# 1. wikipedia_lookup – full formatted output
# ─────────────────────────────────────────────────────────────────────────────


class TestWikipediaLookup:
    """Live network tests for wikipedia_lookup."""

    def test_esperanto_returns_result(self):
        """Esperanto – lookup must return a non-None result."""
        result = wikipedia_lookup("Esperanto")
        assert result is not None, "wikipedia_lookup returned None for 'Esperanto'"

    def test_esperanto_header(self):
        """Esperanto – output must contain a bold link header."""
        result = wikipedia_lookup("Esperanto")
        assert result is not None
        _assert_entry_header(result, "Esperanto", "Esperanto")

    def test_esperanto_blockquote_summary(self):
        """Esperanto – output must contain a blockquote summary."""
        result = wikipedia_lookup("Esperanto")
        assert result is not None
        _assert_blockquote_summary(result, "Esperanto")

    def test_esperanto_no_location_block(self):
        """Esperanto – language article has no coordinates, so no location block."""
        result = wikipedia_lookup("Esperanto")
        assert result is not None
        _assert_no_location_block(result, "Esperanto")

    def test_esperanto_wikipedia_link(self):
        """Esperanto – output must link to en.wikipedia.org."""
        result = wikipedia_lookup("Esperanto")
        assert result and "wikipedia.org" in result, (
            "Expected a Wikipedia link in output for Esperanto"
        )

    def test_forbidden_city_returns_result(self):
        """Forbidden City – lookup must return a non-None result."""
        result = wikipedia_lookup("Forbidden City")
        assert result is not None, "wikipedia_lookup returned None for 'Forbidden City'"

    def test_forbidden_city_header(self):
        """Forbidden City – output must contain a bold link header."""
        result = wikipedia_lookup("Forbidden City")
        assert result is not None
        _assert_entry_header(result, "Forbidden City", "Forbidden City")

    def test_forbidden_city_blockquote_summary(self):
        """Forbidden City – output must contain a blockquote summary."""
        result = wikipedia_lookup("Forbidden City")
        assert result is not None
        _assert_blockquote_summary(result, "Forbidden City")

    def test_forbidden_city_has_location_block(self):
        """Forbidden City – landmark has coordinates, so a location block must appear."""
        result = wikipedia_lookup("Forbidden City")
        assert result is not None
        _assert_location_block(result, "Forbidden City")

    def test_forbidden_city_location_has_map_links(self):
        """Forbidden City – location block must contain OSM and Google Maps links."""
        result = wikipedia_lookup("Forbidden City")
        assert result is not None
        assert "openstreetmap.org" in result, (
            "Expected an OpenStreetMap link in Forbidden City output"
        )
        assert "google.com/maps" in result, (
            "Expected a Google Maps link in Forbidden City output"
        )

    def test_chongqing_returns_result(self):
        """Chongqing – lookup must return a non-None result."""
        result = wikipedia_lookup("Chongqing")
        assert result is not None, "wikipedia_lookup returned None for 'Chongqing'"

    def test_chongqing_header(self):
        """Chongqing – output must contain a bold link header."""
        result = wikipedia_lookup("Chongqing")
        assert result is not None
        _assert_entry_header(result, "Chongqing", "Chongqing")

    def test_chongqing_has_location_block(self):
        """Chongqing – city article has coordinates, so a location block must appear."""
        result = wikipedia_lookup("Chongqing")
        assert result is not None
        _assert_location_block(result, "Chongqing")

    def test_chongqing_location_has_map_links(self):
        """Chongqing – location block must contain OSM and Google Maps links."""
        result = wikipedia_lookup("Chongqing")
        assert result is not None
        assert "openstreetmap.org" in result
        assert "google.com/maps" in result

    def test_invalid_term_returns_none(self):
        """A completely nonsense term should return None gracefully."""
        result = wikipedia_lookup("xqzjfkwvbnmplsrtdhyg")
        assert result is None, f"Expected None for nonsense term, got: {repr(result)}"

    def test_accepts_string_input(self):
        """wikipedia_lookup must accept a plain string (not just a list)."""
        result = wikipedia_lookup("Esperanto")
        assert result is not None, "Should accept a plain string input"

    def test_accepts_list_input(self):
        """wikipedia_lookup must accept a list of strings."""
        result = wikipedia_lookup(["Esperanto"])
        assert result is not None, "Should accept a list input"

    def test_invalid_type_raises_type_error(self):
        """Passing an int should raise TypeError."""
        with pytest.raises(TypeError):
            wikipedia_lookup(12345)  # type: ignore[arg-type]

    def test_multi_term_list_returns_multiple_entries(self):
        """A list of two terms must produce entries for both."""
        result = wikipedia_lookup(["Esperanto", "Chongqing"])
        assert result is not None
        assert "Esperanto" in result, "Expected Esperanto entry in multi-term output"
        assert "Chongqing" in result, "Expected Chongqing entry in multi-term output"

    def test_list_capped_at_five_terms(self):
        """A list of more than five terms must only process the first five."""
        terms = ["Esperanto", "Chongqing", "Python", "Wikipedia", "Tokyo", "London"]
        result = wikipedia_lookup(terms)
        assert result is not None
        # London is the 6th term and must be absent
        assert "London" not in result, (
            "Term beyond the five-item cap must not appear in output"
        )


# ─────────────────────────────────────────────────────────────────────────────
# 2. get_page_location_data – coordinate extraction and OSM lookup
# ─────────────────────────────────────────────────────────────────────────────


class TestGetPageLocationData:
    """Tests for get_page_location_data using live Wikipedia page objects."""

    def test_esperanto_returns_none(self):
        """Esperanto page has no coordinates – must return None."""
        page = wikipedia.page("Esperanto", auto_suggest=False)
        result = get_page_location_data(page)
        assert result is None, (
            f"Expected None for Esperanto (no coordinates); got: {repr(result)}"
        )

    def test_forbidden_city_returns_string(self):
        """Forbidden City page has coordinates – must return a non-None string."""
        page = wikipedia.page("Forbidden City", auto_suggest=False)
        result = get_page_location_data(page)
        assert result is not None, "Expected location data for Forbidden City"
        assert isinstance(result, str)

    def test_forbidden_city_contains_location_header(self):
        """Forbidden City location data must include the *Location results* header."""
        page = wikipedia.page("Forbidden City", auto_suggest=False)
        result = get_page_location_data(page)
        assert result and "*Location results*" in result, (
            f"Missing '*Location results*' header:\n{result}"
        )

    def test_forbidden_city_contains_osm_link(self):
        """Forbidden City location data must include an OSM link."""
        page = wikipedia.page("Forbidden City", auto_suggest=False)
        result = get_page_location_data(page)
        assert result and "openstreetmap.org" in result, (
            "Expected OpenStreetMap link in Forbidden City location data"
        )

    def test_forbidden_city_contains_google_maps_link(self):
        """Forbidden City location data must include a Google Maps link."""
        page = wikipedia.page("Forbidden City", auto_suggest=False)
        result = get_page_location_data(page)
        assert result and "google.com/maps" in result, (
            "Expected Google Maps link in Forbidden City location data"
        )

    def test_chongqing_returns_string(self):
        """Chongqing page has coordinates – must return a non-None string."""
        page = wikipedia.page("Chongqing", auto_suggest=False)
        result = get_page_location_data(page)
        assert result is not None, "Expected location data for Chongqing"
        assert isinstance(result, str)

    def test_chongqing_coordinates_in_map_links(self):
        """Chongqing location data map links must embed plausible coordinates."""
        page = wikipedia.page("Chongqing", auto_suggest=False)
        result = get_page_location_data(page)
        assert result is not None
        # Chongqing is roughly 29°N 106°E — check the sign is positive for both
        assert re.search(r"q=2[0-9]\.[0-9]+,10[0-9]\.[0-9]+", result), (
            f"Expected Chongqing-region coordinates in map link:\n{result}"
        )


# ─────────────────────────────────────────────────────────────────────────────
# 3. search_nominatim – OSM API directly
# ─────────────────────────────────────────────────────────────────────────────


class TestSearchNominatim:
    """Live network tests for search_nominatim."""

    def test_forbidden_city_returns_results(self):
        """Forbidden City – Nominatim must return at least one result."""
        results = search_nominatim("Forbidden City", coords=[39.9163, 116.3972])
        assert results and len(results) > 0, (
            "Expected at least one result for 'Forbidden City'"
        )

    def test_forbidden_city_result_is_string(self):
        """Forbidden City – each result must be a formatted string."""
        results = search_nominatim("Forbidden City", coords=[39.9163, 116.3972])
        assert results
        assert all(isinstance(r, str) for r in results), "All results must be strings"

    def test_forbidden_city_result_has_osm_link(self):
        """Forbidden City – result must contain an OSM permalink or map link."""
        results = search_nominatim("Forbidden City", coords=[39.9163, 116.3972])
        assert results
        assert any("openstreetmap.org" in r for r in results), (
            "Expected OpenStreetMap link in at least one result"
        )

    def test_forbidden_city_result_has_google_maps_link(self):
        """Forbidden City – result must contain a Google Maps link."""
        results = search_nominatim("Forbidden City", coords=[39.9163, 116.3972])
        assert results
        assert any("google.com/maps" in r for r in results), (
            "Expected Google Maps link in at least one result"
        )

    def test_chongqing_returns_results(self):
        """Chongqing – Nominatim must return at least one result."""
        results = search_nominatim("Chongqing", coords=[29.5637, 106.5504])
        assert results and len(results) > 0, (
            "Expected at least one result for 'Chongqing'"
        )

    def test_unknown_location_with_coords_returns_map_links(self):
        """An unknown place with coords must fall back to coordinate-based map links."""
        results = search_nominatim("xqzjfkwvbnmplsrtdhyg", coords=[39.9163, 116.3972])
        assert results and len(results) > 0, (
            "Expected fallback map link result when query has no Nominatim match"
        )
        assert any("openstreetmap.org" in r for r in results), (
            "Fallback result must include an OSM map link"
        )
        assert any("google.com/maps" in r for r in results), (
            "Fallback result must include a Google Maps link"
        )

    def test_unknown_location_without_coords_returns_empty(self):
        """An unknown place with no coords must return an empty list."""
        results = search_nominatim("xqzjfkwvbnmplsrtdhyg")
        assert results == [], (
            f"Expected empty list for unknown query without coords; got: {results}"
        )

    def test_result_format_contains_display_name(self):
        """Forbidden City result must contain a display name as a Markdown link."""
        results = search_nominatim("Forbidden City", coords=[39.915833, 116.390833])
        assert results
        # Formatted as [display name](permalink) ...
        assert re.search(r"\[.+]\(https://nominatim", results[0]), (
            f"Expected Markdown link with Nominatim permalink; got: {results[0]}"
        )

    def test_result_format_contains_coordinates(self):
        """Forbidden City result must embed lat/lon coordinates."""
        results = search_nominatim("Forbidden City", coords=[39.915833, 116.390833])
        assert results
        assert re.search(r"\[[\d.]+, [\d.]+]", results[0]), (
            f"Expected [lat, lon] in result; got: {results[0]}"
        )
