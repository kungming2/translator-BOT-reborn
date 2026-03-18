#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
Test suite for ziwen_lookup/wp_utils.py and ziwen_lookup/osm.py.

Covers:
  - wikipedia_lookup(): happy path, disambiguation fallback, page error
    fallback, type error on bad input, term limit, string input coercion
  - get_page_location_data(): with coordinates, without coordinates,
    coordinate error handling
  - search_nominatim(): results found, no results (with/without coords),
    HTTP error handling
"""

import unittest
from collections.abc import Callable
from typing import Any
from unittest.mock import MagicMock, patch

import wikipedia

from ziwen_lookup.osm import search_nominatim
from ziwen_lookup.wp_utils import get_page_location_data, wikipedia_lookup

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _skip_if_no_data(fn: Callable[..., Any]) -> Callable[..., Any]:
    """Decorator: skip a test if any data-loading exception is raised."""

    def wrapper(self: unittest.TestCase, *args: Any, **kwargs: Any) -> Any:
        try:
            return fn(self, *args, **kwargs)
        except (FileNotFoundError, ImportError, KeyError, ValueError) as exc:
            self.skipTest(f"Data not available: {exc}")

    wrapper.__name__ = fn.__name__
    return wrapper


def _make_wikipage(
    title: str = "Python",
    url: str = "https://en.wikipedia.org/wiki/Python",
    coordinates: tuple[float, float] | None = None,
) -> MagicMock:
    """Return a minimal mock WikipediaPage."""
    page = MagicMock(spec=wikipedia.WikipediaPage)
    page.title = title
    page.url = url
    page.coordinates = coordinates
    return page


# ---------------------------------------------------------------------------
# wikipedia_lookup()
# ---------------------------------------------------------------------------


class TestWikipediaLookupHappyPath(unittest.TestCase):
    """wikipedia_lookup() returns formatted markdown on success."""

    @patch("ziwen_lookup.wp_utils.get_page_location_data", return_value=None)
    @patch("ziwen_lookup.wp_utils.wikipedia.page")
    @patch("ziwen_lookup.wp_utils.wikipedia.summary")
    def test_returns_string(
        self,
        mock_summary: MagicMock,
        mock_page: MagicMock,
        _mock_location: MagicMock,
    ) -> None:
        mock_summary.return_value = "Python is a programming language."
        mock_page.return_value = _make_wikipage()
        result = wikipedia_lookup(["Python"])
        self.assertIsInstance(result, str)

    @patch("ziwen_lookup.wp_utils.get_page_location_data", return_value=None)
    @patch("ziwen_lookup.wp_utils.wikipedia.page")
    @patch("ziwen_lookup.wp_utils.wikipedia.summary")
    def test_output_contains_term_as_link(
        self,
        mock_summary: MagicMock,
        mock_page: MagicMock,
        _mock_location: MagicMock,
    ) -> None:
        mock_summary.return_value = "Python is a programming language."
        mock_page.return_value = _make_wikipage()
        result = wikipedia_lookup(["Python"])
        self.assertIsNotNone(result)
        assert result is not None
        self.assertIn("**[Python]", result)

    @patch("ziwen_lookup.wp_utils.get_page_location_data", return_value=None)
    @patch("ziwen_lookup.wp_utils.wikipedia.page")
    @patch("ziwen_lookup.wp_utils.wikipedia.summary")
    def test_output_contains_summary_text(
        self,
        mock_summary: MagicMock,
        mock_page: MagicMock,
        _mock_location: MagicMock,
    ) -> None:
        mock_summary.return_value = "Python is a programming language."
        mock_page.return_value = _make_wikipage()
        result = wikipedia_lookup(["Python"])
        self.assertIsNotNone(result)
        assert result is not None
        self.assertIn("Python is a programming language.", result)

    @patch("ziwen_lookup.wp_utils.get_page_location_data", return_value=None)
    @patch("ziwen_lookup.wp_utils.wikipedia.page")
    @patch("ziwen_lookup.wp_utils.wikipedia.summary")
    def test_output_contains_blockquote(
        self,
        mock_summary: MagicMock,
        mock_page: MagicMock,
        _mock_location: MagicMock,
    ) -> None:
        mock_summary.return_value = "Python is a programming language."
        mock_page.return_value = _make_wikipage()
        result = wikipedia_lookup(["Python"])
        self.assertIsNotNone(result)
        assert result is not None
        self.assertIn("> ", result)

    @patch("ziwen_lookup.wp_utils.get_page_location_data", return_value=None)
    @patch("ziwen_lookup.wp_utils.wikipedia.page")
    @patch("ziwen_lookup.wp_utils.wikipedia.summary")
    def test_string_input_coerced_to_list(
        self,
        mock_summary: MagicMock,
        mock_page: MagicMock,
        _mock_location: MagicMock,
    ) -> None:
        mock_summary.return_value = "Python is a programming language."
        mock_page.return_value = _make_wikipage()
        result = wikipedia_lookup("Python")  # string, not list
        self.assertIsNotNone(result)

    @patch("ziwen_lookup.wp_utils.get_page_location_data", return_value=None)
    @patch("ziwen_lookup.wp_utils.wikipedia.page")
    @patch("ziwen_lookup.wp_utils.wikipedia.summary")
    def test_multiple_terms_all_included(
        self,
        mock_summary: MagicMock,
        mock_page: MagicMock,
        _mock_location: MagicMock,
    ) -> None:
        mock_summary.return_value = "A summary."
        mock_page.side_effect = [
            _make_wikipage("Python", "https://en.wikipedia.org/wiki/Python"),
            _make_wikipage("Java", "https://en.wikipedia.org/wiki/Java"),
        ]
        result = wikipedia_lookup(["Python", "Java"])
        self.assertIsNotNone(result)
        assert result is not None
        self.assertIn("Python", result)
        self.assertIn("Java", result)

    @patch("ziwen_lookup.wp_utils.get_page_location_data", return_value=None)
    @patch("ziwen_lookup.wp_utils.wikipedia.page")
    @patch("ziwen_lookup.wp_utils.wikipedia.summary")
    def test_term_limit_of_five(
        self,
        mock_summary: MagicMock,
        mock_page: MagicMock,
        _mock_location: MagicMock,
    ) -> None:
        mock_summary.return_value = "A summary."
        mock_page.return_value = _make_wikipage()
        wikipedia_lookup(["A", "B", "C", "D", "E", "F", "G"])
        # summary should only be called 5 times despite 7 terms
        self.assertEqual(mock_summary.call_count, 5)

    @patch("ziwen_lookup.wp_utils.get_page_location_data", return_value="*Location*:\n")
    @patch("ziwen_lookup.wp_utils.wikipedia.page")
    @patch("ziwen_lookup.wp_utils.wikipedia.summary")
    def test_location_data_appended_when_present(
        self,
        mock_summary: MagicMock,
        mock_page: MagicMock,
        _mock_location: MagicMock,
    ) -> None:
        mock_summary.return_value = "A summary."
        mock_page.return_value = _make_wikipage()
        result = wikipedia_lookup(["Python"])
        self.assertIsNotNone(result)
        assert result is not None
        self.assertIn("*Location*:", result)


class TestWikipediaLookupFallback(unittest.TestCase):
    """wikipedia_lookup() handles disambiguation and page errors gracefully."""

    @patch("ziwen_lookup.wp_utils.get_page_location_data", return_value=None)
    @patch("ziwen_lookup.wp_utils.wikipedia.page")
    @patch("ziwen_lookup.wp_utils.wikipedia.summary")
    def test_disambiguation_on_first_try_falls_back(
        self,
        mock_summary: MagicMock,
        mock_page: MagicMock,
        _mock_location: MagicMock,
    ) -> None:
        # summary raises on the first (outer) call; the inner except block
        # calls summary again (succeeds) then page once (no outer page call
        # was made since summary raised before it was reached).
        mock_summary.side_effect = [
            wikipedia.exceptions.DisambiguationError(
                "Python", ["Python (lang)", "Python (snake)"]
            ),
            "Python is a snake.",
        ]
        mock_page.side_effect = [
            _make_wikipage("Python", "https://en.wikipedia.org/wiki/Python_(snake)"),
        ]
        result = wikipedia_lookup(["Python"])
        self.assertIsNotNone(result)

    @patch("ziwen_lookup.wp_utils.wikipedia.page")
    @patch("ziwen_lookup.wp_utils.wikipedia.summary")
    def test_disambiguation_on_both_tries_returns_none(
        self,
        mock_summary: MagicMock,
        _mock_page: MagicMock,
    ) -> None:
        mock_summary.side_effect = wikipedia.exceptions.DisambiguationError(
            "XYZ", ["XYZ (a)", "XYZ (b)"]
        )
        result = wikipedia_lookup(["XYZ"])
        self.assertIsNone(result)

    @patch("ziwen_lookup.wp_utils.wikipedia.page")
    @patch("ziwen_lookup.wp_utils.wikipedia.summary")
    def test_page_error_on_both_tries_returns_none(
        self,
        mock_summary: MagicMock,
        _mock_page: MagicMock,
    ) -> None:
        mock_summary.side_effect = wikipedia.exceptions.PageError("nonexistent_xyzzy")
        result = wikipedia_lookup(["nonexistent_xyzzy"])
        self.assertIsNone(result)

    @patch("ziwen_lookup.wp_utils.get_page_location_data", return_value=None)
    @patch("ziwen_lookup.wp_utils.wikipedia.page")
    @patch("ziwen_lookup.wp_utils.wikipedia.summary")
    def test_one_bad_term_does_not_block_others(
        self,
        mock_summary: MagicMock,
        mock_page: MagicMock,
        _mock_location: MagicMock,
    ) -> None:
        # BadTerm: outer summary raises, inner except summary also raises →
        # term skipped via continue. No page call is made for BadTerm.
        # Python: outer summary succeeds, outer page succeeds.
        mock_summary.side_effect = [
            wikipedia.exceptions.PageError("bad"),  # BadTerm outer
            wikipedia.exceptions.PageError("bad"),  # BadTerm inner fallback
            "Python is a language.",  # Python outer
        ]
        mock_page.side_effect = [
            _make_wikipage(),  # Python outer
        ]
        result = wikipedia_lookup(["BadTerm", "Python"])
        self.assertIsNotNone(result)
        assert result is not None
        self.assertIn("Python", result)


class TestWikipediaLookupTypeError(unittest.TestCase):
    """wikipedia_lookup() raises TypeError for invalid input types."""

    def test_integer_input_raises_type_error(self) -> None:
        with self.assertRaises(TypeError):
            wikipedia_lookup(42)  # type: ignore[arg-type]

    def test_none_input_raises_type_error(self) -> None:
        with self.assertRaises(TypeError):
            wikipedia_lookup(None)  # type: ignore[arg-type]

    def test_dict_input_raises_type_error(self) -> None:
        with self.assertRaises(TypeError):
            wikipedia_lookup({"term": "Python"})  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# get_page_location_data()
# ---------------------------------------------------------------------------


class TestGetPageLocationDataWithCoords(unittest.TestCase):
    """get_page_location_data() returns markdown when coordinates are present."""

    @patch("ziwen_lookup.wp_utils.search_nominatim")
    def test_returns_string_when_coords_present(self, mock_osm: MagicMock) -> None:
        mock_osm.return_value = ["[Some Place](https://nominatim.example.com) (city)"]
        page = _make_wikipage(coordinates=(51.5074, -0.1278))
        result = get_page_location_data(page)
        self.assertIsInstance(result, str)

    @patch("ziwen_lookup.wp_utils.search_nominatim")
    def test_output_contains_location_header(self, mock_osm: MagicMock) -> None:
        mock_osm.return_value = ["[London](https://nominatim.example.com) (city)"]
        page = _make_wikipage(coordinates=(51.5074, -0.1278))
        result = get_page_location_data(page)
        self.assertIsNotNone(result)
        assert result is not None
        self.assertIn("*Location results*", result)

    @patch("ziwen_lookup.wp_utils.search_nominatim")
    def test_osm_called_with_title_and_coords(self, mock_osm: MagicMock) -> None:
        mock_osm.return_value = []
        page = _make_wikipage(title="London", coordinates=(51.5074, -0.1278))
        get_page_location_data(page)
        mock_osm.assert_called_once()
        call_args = mock_osm.call_args
        self.assertIn("London", call_args[0][0])

    @patch("ziwen_lookup.wp_utils.search_nominatim")
    def test_only_first_osm_result_used(self, mock_osm: MagicMock) -> None:
        mock_osm.return_value = [
            "[First](https://example.com) (city)",
            "[Second](https://example.com) (town)",
        ]
        page = _make_wikipage(coordinates=(51.5074, -0.1278))
        result = get_page_location_data(page)
        self.assertIsNotNone(result)
        assert result is not None
        self.assertIn("First", result)
        self.assertNotIn("Second", result)


class TestGetPageLocationDataNoCoords(unittest.TestCase):
    """get_page_location_data() returns None when coordinates are absent."""

    def test_none_coordinates_returns_none(self) -> None:
        page = _make_wikipage(coordinates=None)
        result = get_page_location_data(page)
        self.assertIsNone(result)

    def test_key_error_on_coordinates_returns_none(self) -> None:
        from unittest.mock import PropertyMock

        page = MagicMock(spec=wikipedia.WikipediaPage)
        page.title = "Test"
        page.url = "https://en.wikipedia.org/wiki/Test"
        type(page).coordinates = PropertyMock(side_effect=KeyError("coordinates"))
        result = get_page_location_data(page)
        self.assertIsNone(result)


# ---------------------------------------------------------------------------
# search_nominatim()
# ---------------------------------------------------------------------------


class TestSearchNominatimResults(unittest.TestCase):
    """search_nominatim() parses and formats API results correctly."""

    @patch("ziwen_lookup.osm.requests.get")
    def test_returns_list_of_strings(self, mock_get: MagicMock) -> None:
        mock_get.return_value.raise_for_status = MagicMock()
        mock_get.return_value.json.return_value = [
            {
                "display_name": "London, England",
                "osm_type": "relation",
                "osm_id": "123456",
                "category": "boundary",
                "type": "administrative",
                "lat": "51.5074",
                "lon": "-0.1278",
            }
        ]
        result = search_nominatim("London")
        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 1)
        self.assertIsInstance(result[0], str)

    @patch("ziwen_lookup.osm.requests.get")
    def test_result_contains_display_name(self, mock_get: MagicMock) -> None:
        mock_get.return_value.raise_for_status = MagicMock()
        mock_get.return_value.json.return_value = [
            {
                "display_name": "London, England",
                "osm_type": "relation",
                "osm_id": "123456",
                "category": "boundary",
                "type": "administrative",
                "lat": "51.5074",
                "lon": "-0.1278",
            }
        ]
        result = search_nominatim("London")
        self.assertIn("London, England", result[0])

    @patch("ziwen_lookup.osm.requests.get")
    def test_result_contains_osm_and_google_links(self, mock_get: MagicMock) -> None:
        mock_get.return_value.raise_for_status = MagicMock()
        mock_get.return_value.json.return_value = [
            {
                "display_name": "London, England",
                "osm_type": "relation",
                "osm_id": "123456",
                "category": "boundary",
                "type": "administrative",
                "lat": "51.5074",
                "lon": "-0.1278",
            }
        ]
        result = search_nominatim("London")
        self.assertIn("OSM", result[0])
        self.assertIn("Google", result[0])

    @patch("ziwen_lookup.osm.requests.get")
    def test_osm_type_letter_uppercased(self, mock_get: MagicMock) -> None:
        mock_get.return_value.raise_for_status = MagicMock()
        mock_get.return_value.json.return_value = [
            {
                "display_name": "Test",
                "osm_type": "node",
                "osm_id": "999",
                "category": "place",
                "type": "city",
                "lat": "10.0",
                "lon": "20.0",
            }
        ]
        result = search_nominatim("Test")
        # node → N in the permalink
        self.assertIn("osmtype=N", result[0])


class TestSearchNominatimNoResults(unittest.TestCase):
    """search_nominatim() handles empty results correctly."""

    @patch("ziwen_lookup.osm.requests.get")
    def test_empty_results_returns_empty_list(self, mock_get: MagicMock) -> None:
        mock_get.return_value.raise_for_status = MagicMock()
        mock_get.return_value.json.return_value = []
        result = search_nominatim("xyzzy_nonexistent")
        self.assertEqual(result, [])

    @patch("ziwen_lookup.osm.requests.get")
    def test_empty_results_with_coords_returns_map_links(
        self, mock_get: MagicMock
    ) -> None:
        mock_get.return_value.raise_for_status = MagicMock()
        mock_get.return_value.json.return_value = []
        result = search_nominatim("xyzzy", coords=[51.5074, -0.1278])
        self.assertEqual(len(result), 1)
        self.assertIn("OSM", result[0])
        self.assertIn("Google", result[0])

    @patch("ziwen_lookup.osm.requests.get")
    def test_empty_results_without_coords_returns_empty_list(
        self, mock_get: MagicMock
    ) -> None:
        mock_get.return_value.raise_for_status = MagicMock()
        mock_get.return_value.json.return_value = []
        result = search_nominatim("xyzzy", coords=None)
        self.assertEqual(result, [])


class TestSearchNominatimHTTPError(unittest.TestCase):
    """search_nominatim() returns empty list on request failure."""

    @patch("ziwen_lookup.osm.requests.get")
    def test_request_exception_returns_empty_list(self, mock_get: MagicMock) -> None:
        import requests

        mock_get.side_effect = requests.RequestException("timeout")
        result = search_nominatim("London")
        self.assertEqual(result, [])

    @patch("ziwen_lookup.osm.requests.get")
    def test_http_error_returns_empty_list(self, mock_get: MagicMock) -> None:
        import requests

        mock_get.return_value.raise_for_status.side_effect = requests.HTTPError("404")
        result = search_nominatim("London")
        self.assertEqual(result, [])


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


def run_all_tests() -> unittest.TestResult:
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    for cls in (
        TestWikipediaLookupHappyPath,
        TestWikipediaLookupFallback,
        TestWikipediaLookupTypeError,
        TestGetPageLocationDataWithCoords,
        TestGetPageLocationDataNoCoords,
        TestSearchNominatimResults,
        TestSearchNominatimNoResults,
        TestSearchNominatimHTTPError,
    ):
        suite.addTests(loader.loadTestsFromTestCase(cls))
    runner = unittest.TextTestRunner(verbosity=2)
    return runner.run(suite)


if __name__ == "__main__":
    print("=" * 70)
    print("Wikipedia / OSM Test Suite")
    print("=" * 70)
    run_all_tests()
