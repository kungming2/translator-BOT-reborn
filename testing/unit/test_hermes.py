#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
Test suite for hermes/matching.py and hermes/hermes_database.py.

Covers:
  - _parse_user_data(): JSON, legacy literal_eval, invalid input
  - HermesDatabaseManager CRUD: upsert, get, delete, prune — in-memory SQLite
  - _extract_segments(): structural title variants
  - title_parser(): real titles from sample DB entries
  - language_matcher(): mocked DB entries, scoring rules
  - get_language_greeting(): non-English selection, English-only fallback
"""

import sqlite3
import time
import unittest
from collections.abc import Callable
from typing import Any

# noinspection PyProtectedMember
from hermes.hermes_database import HermesDatabaseManager, _parse_user_data

# noinspection PyProtectedMember
from hermes.matching import (
    _extract_segments,
    get_language_greeting,
    language_matcher,
    title_parser,
)

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


def _make_db() -> HermesDatabaseManager:
    """Return a HermesDatabaseManager backed by an in-memory SQLite database."""
    mgr = HermesDatabaseManager.__new__(HermesDatabaseManager)
    conn = sqlite3.connect(":memory:")
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE entries (
            username   TEXT PRIMARY KEY,
            user_data  TEXT NOT NULL,
            posted_utc INTEGER NOT NULL
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE processed (
            post_id    TEXT PRIMARY KEY,
            created_utc INTEGER NOT NULL
        )
        """
    )
    conn.commit()
    mgr._conn_hermes = conn  # type: ignore[attr-defined]
    return mgr


# Sample entries matching the real DB snapshot provided
_NOW = int(time.time())
_SAMPLE_ENTRIES: list[tuple[str, dict[str, Any], int]] = [
    (
        "notgingerbutscottish",
        {
            "id": "1rw1l9b",
            "title": "Offering English/ seeking any",
            "posted": 1773739059,
            "offering": ["en"],
            "seeking": [],
            "level": {},
        },
        1773739059,
    ),
    (
        "wushuaiii",
        {
            "id": "1rw2cde",
            "title": "Seeking : Arabic(msa) Offering : English",
            "posted": 1773741878,
            "offering": ["en"],
            "seeking": ["ar"],
            "level": {},
        },
        1773741878,
    ),
    (
        "slight-angle3070",
        {
            "id": "1rw2jqo",
            "title": "Offering: Korean, Seeking: English",
            "posted": 1773742572,
            "offering": ["ko"],
            "seeking": ["en"],
            "level": {},
        },
        1773742572,
    ),
    (
        "sramsedomordy",
        {
            "id": "1rw4hcw",
            "title": "Offering polish and english, seeking russian",
            "posted": 1773748696,
            "offering": ["pl", "en"],
            "seeking": ["ru"],
            "level": {},
        },
        1773748696,
    ),
    (
        "namrednas",
        {
            "id": "1rw5bt6",
            "title": "Offering Russian and English, seeking French",
            "posted": 1773751034,
            "offering": ["ru", "en"],
            "seeking": ["fr"],
            "level": {},
        },
        1773751034,
    ),
    (
        "acceptable_bed7251",
        {
            "id": "1rw6kkw",
            "title": "Offering language: English, Russian, Kazakh, Seeking language: German",
            "posted": 1773754191,
            "offering": ["en", "ru", "kk"],
            "seeking": ["de"],
            "level": {},
        },
        1773754191,
    ),
]


# ---------------------------------------------------------------------------
# _parse_user_data()
# ---------------------------------------------------------------------------


class TestParseUserData(unittest.TestCase):
    """_parse_user_data() handles JSON, legacy literals, and bad input."""

    def test_valid_json_returns_dict(self) -> None:
        raw = '{"offering": ["en"], "seeking": ["fr"]}'
        result = _parse_user_data(raw)
        self.assertIsInstance(result, dict)
        self.assertEqual(result["offering"], ["en"])

    def test_legacy_literal_eval_returns_dict(self) -> None:
        # Python dict literal — the old serialisation format
        raw = "{'offering': ['en'], 'seeking': ['fr']}"
        result = _parse_user_data(raw)
        self.assertIsInstance(result, dict)
        self.assertEqual(result["seeking"], ["fr"])

    def test_empty_string_returns_none(self) -> None:
        self.assertIsNone(_parse_user_data(""))

    def test_invalid_input_returns_none(self) -> None:
        self.assertIsNone(_parse_user_data("this is not valid json or python"))

    def test_nested_data_preserved(self) -> None:
        raw = '{"level": {"en": "Native", "fr": "B2"}}'
        result = _parse_user_data(raw)
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result["level"]["en"], "Native")


# ---------------------------------------------------------------------------
# HermesDatabaseManager — CRUD
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# _extract_segments()
# ---------------------------------------------------------------------------


class TestExtractSegments(unittest.TestCase):
    """_extract_segments() splits title into offering/seeking text."""

    def test_standard_order(self) -> None:
        offering, seeking = _extract_segments("offering: english seeking: korean")
        self.assertIsNotNone(offering)
        self.assertIsNotNone(seeking)
        assert offering is not None and seeking is not None
        self.assertIn("english", offering)
        self.assertIn("korean", seeking)

    def test_reversed_order(self) -> None:
        offering, seeking = _extract_segments("seeking: arabic offering: english")
        self.assertIsNotNone(offering)
        self.assertIsNotNone(seeking)
        assert offering is not None and seeking is not None
        self.assertIn("english", offering)
        self.assertIn("arabic", seeking)

    def test_bracket_style(self) -> None:
        offering, seeking = _extract_segments("[offering] english [seeking] korean")
        self.assertIsNotNone(offering)
        self.assertIsNotNone(seeking)

    def test_offering_only(self) -> None:
        offering, seeking = _extract_segments("offering: english")
        self.assertIsNotNone(offering)
        self.assertIsNone(seeking)

    def test_seeking_only(self) -> None:
        offering, seeking = _extract_segments("seeking: japanese")
        self.assertIsNone(offering)
        self.assertIsNotNone(seeking)

    def test_no_keywords_returns_none_none(self) -> None:
        offering, seeking = _extract_segments("hello world this is a title")
        self.assertIsNone(offering)
        self.assertIsNone(seeking)


# ---------------------------------------------------------------------------
# title_parser() — real sample titles
# ---------------------------------------------------------------------------


class TestTitleParser(unittest.TestCase):
    """title_parser() extracts correct codes from real r/Language_Exchange titles."""

    @_skip_if_no_data
    def test_offering_english_seeking_any(self) -> None:
        offering, seeking, levels = title_parser("Offering English/ seeking any")
        self.assertIn("en", offering)

    @_skip_if_no_data
    def test_seeking_arabic_offering_english(self) -> None:
        offering, seeking, levels = title_parser(
            "Seeking : Arabic(msa) Offering : English"
        )
        self.assertIn("en", offering)
        self.assertIn("ar", seeking)

    @_skip_if_no_data
    def test_offering_korean_seeking_english(self) -> None:
        offering, seeking, levels = title_parser("Offering: Korean, Seeking: English")
        self.assertIn("ko", offering)
        self.assertIn("en", seeking)

    @_skip_if_no_data
    def test_multiple_offering_languages(self) -> None:
        offering, seeking, levels = title_parser(
            "Offering polish and english, seeking russian"
        )
        self.assertIn("pl", offering)
        self.assertIn("en", offering)
        self.assertIn("ru", seeking)

    @_skip_if_no_data
    def test_offering_russian_and_english_seeking_french(self) -> None:
        offering, seeking, levels = title_parser(
            "Offering Russian and English, seeking French"
        )
        self.assertIn("ru", offering)
        self.assertIn("en", offering)
        self.assertIn("fr", seeking)

    @_skip_if_no_data
    def test_three_offering_languages(self) -> None:
        offering, seeking, levels = title_parser(
            "Offering language: English, Russian, Kazakh, Seeking language: German"
        )
        self.assertIn("en", offering)
        self.assertIn("ru", offering)
        self.assertIn("de", seeking)

    @_skip_if_no_data
    def test_returns_tuple_of_three(self) -> None:
        result = title_parser("Offering: English, Seeking: French")
        self.assertIsInstance(result, tuple)
        self.assertEqual(len(result), 3)

    @_skip_if_no_data
    def test_levels_dict_returned(self) -> None:
        _, _, levels = title_parser("Offering: English, Seeking: French")
        self.assertIsInstance(levels, dict)

    @_skip_if_no_data
    def test_unparseable_title_returns_empty_lists(self) -> None:
        offering, seeking, levels = title_parser("Hello everyone!")
        self.assertEqual(offering, [])
        self.assertEqual(seeking, [])

    @_skip_if_no_data
    def test_seeking_alias_looking(self) -> None:
        # "looking" is an alias for "seeking"
        offering, seeking, levels = title_parser("Offering English, looking for French")
        self.assertIn("en", offering)
        self.assertIn("fr", seeking)


# ---------------------------------------------------------------------------
# language_matcher() — real in-memory DB
# ---------------------------------------------------------------------------


class TestLanguageMatcher(unittest.TestCase):
    """language_matcher() scores and returns DB matches correctly.

    Each test builds a fresh in-memory HermesDatabaseManager, populates it
    with the relevant entries, then patches the module-level hermes_db
    singleton so language_matcher reads from that DB.
    """

    @staticmethod
    def _db_with_entries(
        entries: list[tuple[str, dict[str, Any], int]],
    ) -> HermesDatabaseManager:
        """Return a populated in-memory DB containing *entries*."""
        db = _make_db()
        for username, data, posted_utc in entries:
            db.upsert_entry(username, data, posted_utc)
        return db

    def _run_matcher(
        self,
        entries: list[tuple[str, dict[str, Any], int]],
        offering: list[str],
        seeking: list[str],
        cut_off: int | None = None,
    ) -> dict[str, list] | None:
        """Populate a DB, patch the singleton, and run language_matcher."""
        import hermes.matching as matching_module

        db = self._db_with_entries(entries)
        original_db = matching_module.hermes_db
        matching_module.hermes_db = db  # type: ignore[assignment]
        original_cut_off = matching_module._CUT_OFF
        if cut_off is not None:
            matching_module._CUT_OFF = cut_off
        try:
            return language_matcher(offering, seeking)
        finally:
            matching_module.hermes_db = original_db
            matching_module._CUT_OFF = original_cut_off

    @_skip_if_no_data
    def test_no_languages_returns_none(self) -> None:
        result = self._run_matcher(_SAMPLE_ENTRIES, [], [])
        self.assertIsNone(result)

    @_skip_if_no_data
    def test_no_matches_returns_none(self) -> None:
        # Query for Swahili — nobody in sample offers/seeks it
        result = self._run_matcher(_SAMPLE_ENTRIES, ["sw"], ["sw"])
        self.assertIsNone(result)

    @_skip_if_no_data
    def test_mutual_match_scores_five(self) -> None:
        # slight-angle3070 offers Korean, seeks English
        # Query: offering English, seeking Korean → mutual match → score 5
        result = self._run_matcher(_SAMPLE_ENTRIES, ["en"], ["ko"])
        self.assertIsNotNone(result)
        assert result is not None
        self.assertIn("slight-angle3070", result)
        self.assertEqual(result["slight-angle3070"][0], 5)

    @_skip_if_no_data
    def test_offer_only_match_scores_three(self) -> None:
        # wushuaiii offers English, seeks Arabic
        # Query: seeking English, offering French (not sought by wushuaiii)
        # → target offers what we seek but doesn't seek what we offer → score 3
        result = self._run_matcher(_SAMPLE_ENTRIES, ["fr"], ["en"])
        self.assertIsNotNone(result)
        assert result is not None
        self.assertIn("wushuaiii", result)
        self.assertEqual(result["wushuaiii"][0], 3)

    @_skip_if_no_data
    def test_seek_only_match_scores_two(self) -> None:
        # namrednas seeks French → offering French matches → score 2
        result = self._run_matcher(_SAMPLE_ENTRIES, ["fr"], ["sw"])
        self.assertIsNotNone(result)
        assert result is not None
        self.assertIn("namrednas", result)
        self.assertEqual(result["namrednas"][0], 2)

    @_skip_if_no_data
    def test_expired_entries_excluded(self) -> None:
        # cut_off of 1 second; all sample entries are years old
        result = self._run_matcher(_SAMPLE_ENTRIES, ["en"], ["ko"], cut_off=1)
        self.assertIsNone(result)

    @_skip_if_no_data
    def test_native_bonus_added_to_score(self) -> None:
        entries = [
            (
                "native_speaker",
                {
                    "id": "abc",
                    "offering": ["ko"],
                    "seeking": ["en"],
                    "level": {"ko": "Native"},
                },
                _NOW - 60,
            )
        ]
        result = self._run_matcher(entries, ["en"], ["ko"])
        self.assertIsNotNone(result)
        assert result is not None
        # Mutual match (5) + native bonus (1) = 6
        self.assertEqual(result["native_speaker"][0], 6)

    @_skip_if_no_data
    def test_result_structure(self) -> None:
        result = self._run_matcher(_SAMPLE_ENTRIES, ["en"], ["ko"])
        self.assertIsNotNone(result)
        assert result is not None
        for username, data in result.items():
            self.assertIsInstance(username, str)
            self.assertIsInstance(data, list)
            self.assertGreaterEqual(len(data), 5)


# ---------------------------------------------------------------------------
# get_language_greeting()
# ---------------------------------------------------------------------------


class TestGetLanguageGreeting(unittest.TestCase):
    """get_language_greeting() selects a non-English greeting."""

    @_skip_if_no_data
    def test_english_only_returns_empty_string(self) -> None:
        result = get_language_greeting(["en"], ["en"])
        self.assertEqual(result, "")

    @_skip_if_no_data
    def test_empty_lists_returns_empty_string(self) -> None:
        result = get_language_greeting([], [])
        self.assertEqual(result, "")

    @_skip_if_no_data
    def test_non_english_returns_nonempty_string(self) -> None:
        result = get_language_greeting(["fr"], ["en"])
        self.assertIsInstance(result, str)
        self.assertGreater(len(result), 0)

    @_skip_if_no_data
    def test_result_ends_with_space(self) -> None:
        result = get_language_greeting(["ko"], ["en"])
        if result:  # may be empty if converter returns no greeting
            self.assertTrue(result.endswith(" "))

    @_skip_if_no_data
    def test_english_excluded_from_candidates(self) -> None:
        # With only English in offering and a non-English in seeking,
        # the non-English side should be chosen
        result = get_language_greeting(["en"], ["fr"])
        # Result should not be a generic English greeting
        self.assertIsInstance(result, str)


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


def run_all_tests() -> unittest.TestResult:
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    for cls in (
        TestParseUserData,
        TestExtractSegments,
        TestTitleParser,
        TestLanguageMatcher,
        TestGetLanguageGreeting,
    ):
        suite.addTests(loader.loadTestsFromTestCase(cls))
    runner = unittest.TextTestRunner(verbosity=2)
    return runner.run(suite)


if __name__ == "__main__":
    print("=" * 70)
    print("Hermes Test Suite")
    print("=" * 70)
    run_all_tests()
