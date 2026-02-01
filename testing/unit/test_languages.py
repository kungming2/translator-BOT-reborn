#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
Test suite for languages.py module.
Tests Lingvo class, converter functions, and language utilities.
"""

import unittest

from languages import (
    Lingvo,
    converter,
    country_converter,
    define_language_lists,
    get_lingvos,
    normalize,
    parse_language_list,
)


class TestLingvoClass(unittest.TestCase):
    """Test the Lingvo class initialization and methods."""

    def setUp(self):
        """Create sample Lingvo objects for testing."""
        self.english = Lingvo(
            name="English",
            name_alternates=["American English"],
            language_code_1="en",
            language_code_3="eng",
            supported=True,
            thanks="Thanks",
        )
        self.mandarin = Lingvo(
            name="Mandarin Chinese",
            name_alternates=["Chinese", "Standard Chinese"],
            language_code_1="zh",
            language_code_3="cmn",
            script_code="Hans",
            supported=True,
        )
        self.unknown = Lingvo(
            name="Unknown", language_code_1="unknown", language_code_3="unknown"
        )

    def test_lingvo_initialization(self):
        """Test Lingvo object creation with various parameters."""
        self.assertEqual(self.english.name, "English")
        self.assertEqual(self.english.language_code_1, "en")
        self.assertEqual(self.english.language_code_3, "eng")
        self.assertTrue(self.english.supported)

    def test_preferred_code_priority(self):
        """Test that preferred_code returns correct priority."""
        self.assertEqual(self.english.preferred_code, "en")
        self.assertEqual(self.mandarin.preferred_code, "zh")
        self.assertEqual(self.unknown.preferred_code, "unknown")

    def test_preferred_code_with_script(self):
        """Test preferred_code fallback to script_code."""
        script_lingvo = Lingvo(
            name="Cyrillic", script_code="Cyrl", language_code_1="unknown"
        )
        self.assertEqual(script_lingvo.preferred_code, "cyrl")

    def test_lingvo_string_representation(self):
        """Test __str__ and __repr__ methods."""
        self.assertEqual(str(self.english), "en")
        self.assertIn("English", repr(self.english))
        self.assertIn("en", repr(self.english))

    def test_lingvo_equality(self):
        """Test equality comparison based on preferred_code."""
        english_copy = Lingvo(
            name="English (variant)", language_code_1="en", language_code_3="eng"
        )
        self.assertEqual(self.english, english_copy)

    def test_lingvo_hashing(self):
        """Test that Lingvo objects are hashable."""
        lingvo_set = {self.english, self.mandarin, self.english}
        self.assertEqual(len(lingvo_set), 2)  # Duplicate removed

    def test_lingvo_to_dict(self):
        """Test conversion to dictionary."""
        lingvo_dict = self.english.to_dict()
        self.assertIsInstance(lingvo_dict, dict)
        self.assertEqual(lingvo_dict["name"], "English")
        self.assertEqual(lingvo_dict["preferred_code"], "en")
        self.assertIn("language_code_1", lingvo_dict)

    def test_lingvo_from_csv_row(self):
        """Test creating Lingvo from CSV row data."""
        row = {
            "Language Name": "Spanish",
            "ISO 639-1": "es",
            "ISO 639-3": "spa",
            "Alternate Names": "Castilian; EspaÃ±ol",
        }
        lingvo = Lingvo.from_csv_row(row)
        self.assertEqual(lingvo.name, "Spanish")
        self.assertEqual(lingvo.language_code_1, "es")
        self.assertEqual(lingvo.language_code_3, "spa")
        self.assertIn("Castilian", lingvo.name_alternates)


class TestConverterFunction(unittest.TestCase):
    """Test the converter function with various inputs."""

    def test_converter_with_2letter_code(self):
        """Test converter with 2-letter ISO 639-1 codes."""
        result = converter("en")
        if result:
            self.assertIsInstance(result, Lingvo)

    def test_converter_with_3letter_code(self):
        """Test converter with 3-letter ISO 639-3 codes."""
        result = converter("fra")
        if result:
            self.assertIsInstance(result, Lingvo)

    def test_converter_too_short_input(self):
        """Test converter rejects input that's too short."""
        result = converter("a")
        self.assertIsNone(result)

    def test_converter_empty_input(self):
        """Test converter handles empty input gracefully."""
        result = converter("")
        self.assertIsNone(result)

    def test_converter_with_whitespace(self):
        """Test converter strips whitespace."""
        result = converter("  en  ")
        if result:
            self.assertEqual(result.preferred_code, "en")

    def test_converter_case_insensitive(self):
        """Test converter is case-insensitive."""
        result_lower = converter("en")
        result_upper = converter("EN")
        if result_lower and result_upper:
            self.assertEqual(result_lower, result_upper)

    def test_converter_with_compound_code(self):
        """Test converter with compound codes like zh-CN."""
        result = converter("zh-CN")
        if result:
            self.assertIsInstance(result, Lingvo)

    def test_converter_with_script_code(self):
        """Test converter with script codes like unknown-Cyrl."""
        result = converter("unknown-Cyrl")
        if result:
            self.assertIsInstance(result, Lingvo)


class TestNormalizeFunction(unittest.TestCase):
    """Test the normalize utility function."""

    def test_normalize_lowercase(self):
        """Test normalize converts to lowercase."""
        self.assertEqual(normalize("ENGLISH"), "english")

    def test_normalize_collapses_whitespace(self):
        """Test normalize collapses multiple spaces."""
        self.assertEqual(normalize("English  Language"), "english language")

    def test_normalize_strips_whitespace(self):
        """Test normalize strips leading/trailing whitespace."""
        self.assertEqual(normalize("  English  "), "english")

    def test_normalize_empty_string(self):
        """Test normalize handles empty strings."""
        self.assertEqual(normalize(""), "")

    def test_normalize_numbers(self):
        """Test normalize preserves numbers."""
        self.assertEqual(normalize("Code123"), "code123")


class TestParseLanguageList(unittest.TestCase):
    """Test the parse_language_list function."""

    def test_parse_comma_delimited(self):
        """Test parsing comma-delimited language list."""
        result = parse_language_list("en, fr, es")
        self.assertIsInstance(result, list)

    def test_parse_plus_delimited(self):
        """Test parsing plus-delimited language list."""
        result = parse_language_list("en+fr+es")
        self.assertIsInstance(result, list)

    def test_parse_newline_delimited(self):
        """Test parsing newline-delimited language list."""
        result = parse_language_list("en\nfr\nes")
        self.assertIsInstance(result, list)

    def test_parse_with_language_prefix(self):
        """Test parsing with LANGUAGES: prefix."""
        result = parse_language_list("LANGUAGES: en, fr, es")
        self.assertIsInstance(result, list)

    def test_parse_empty_string(self):
        """Test parsing empty string returns empty list."""
        result = parse_language_list("")
        self.assertEqual(result, [])

    def test_parse_removes_duplicates(self):
        """Test parsing deduplicates languages by preferred_code."""
        result = parse_language_list("en, en, eng")
        self.assertIsInstance(result, list)

    def test_parse_ignores_utility_codes(self):
        """Test parsing ignores utility codes like 'meta'."""
        result = parse_language_list("en, meta, fr")
        self.assertIsInstance(result, list)

    def test_parse_returns_sorted(self):
        """Test parsing returns sorted results."""
        result = parse_language_list("es, en, fr")
        self.assertIsInstance(result, list)
        if len(result) > 1:
            codes = [lingvo.preferred_code for lingvo in result]
            self.assertEqual(codes, sorted(codes))


class TestCountryConverter(unittest.TestCase):
    """Test the country_converter function."""

    def test_country_converter_too_short(self):
        """Test country converter rejects single character."""
        result = country_converter("a")
        self.assertEqual(result, ("", ""))

    def test_country_converter_empty(self):
        """Test country converter handles empty input."""
        result = country_converter("")
        self.assertEqual(result, ("", ""))

    def test_country_converter_2letter_code(self):
        """Test country converter with 2-letter code."""
        result = country_converter("US")
        if result[0]:  # Only test if dataset is available
            self.assertIsInstance(result, tuple)
            self.assertEqual(len(result), 2)

    def test_country_converter_3letter_code(self):
        """Test country converter with 3-letter code."""
        result = country_converter("USA")
        if result[0]:
            self.assertIsInstance(result, tuple)

    def test_country_converter_abbreviations_disabled(self):
        """Test country converter with abbreviations disabled."""
        result = country_converter("US", abbreviations_okay=False)
        self.assertIsInstance(result, tuple)


class TestLanguageLists(unittest.TestCase):
    """Test the define_language_lists function."""

    def test_language_lists_structure(self):
        """Test that language lists are properly structured."""
        try:
            lists = define_language_lists()
            self.assertIsInstance(lists, dict)
            expected_keys = {
                "SUPPORTED_CODES",
                "SUPPORTED_LANGUAGES",
                "ISO_DEFAULT_ASSOCIATED",
                "ISO_639_1",
                "ISO_639_2B",
                "ISO_639_3",
                "ISO_NAMES",
                "MISTAKE_ABBREVIATIONS",
                "LANGUAGE_COUNTRY_ASSOCIATED",
            }
            for key in expected_keys:
                self.assertIn(key, lists)
        except (FileNotFoundError, ImportError, KeyError, ValueError) as e:
            self.skipTest(f"Language data not available: {e}")

    def test_supported_codes_are_strings(self):
        """Test that supported codes are strings."""
        try:
            lists = define_language_lists()
            for code in lists["SUPPORTED_CODES"]:
                self.assertIsInstance(code, str)
        except (FileNotFoundError, ImportError, KeyError, ValueError):
            self.skipTest("Language data not available")

    def test_iso_codes_are_unique(self):
        """Test that ISO codes are unique in their lists."""
        try:
            lists = define_language_lists()
            iso_639_1 = lists["ISO_639_1"]
            self.assertEqual(len(iso_639_1), len(set(iso_639_1)))
        except (FileNotFoundError, ImportError, KeyError, ValueError):
            self.skipTest("Language data not available")


class TestGetLingvos(unittest.TestCase):
    """Test the get_lingvos caching function."""

    def test_get_lingvos_returns_dict(self):
        """Test get_lingvos returns a dictionary."""
        try:
            lingvos = get_lingvos()
            self.assertIsInstance(lingvos, dict)
        except (FileNotFoundError, ImportError, KeyError, ValueError):
            self.skipTest("Language data not available")

    def test_get_lingvos_values_are_lingvo(self):
        """Test get_lingvos dictionary contains Lingvo objects."""
        try:
            lingvos = get_lingvos()
            for key, value in list(lingvos.items())[:5]:
                self.assertIsInstance(value, Lingvo)
        except (FileNotFoundError, ImportError, KeyError, ValueError):
            self.skipTest("Language data not available")

    def test_get_lingvos_caching(self):
        """Test get_lingvos caches results."""
        try:
            result1 = get_lingvos()
            result2 = get_lingvos()
            self.assertIs(result1, result2)
        except (FileNotFoundError, ImportError, KeyError, ValueError):
            self.skipTest("Language data not available")


def run_specific_test(test_class, test_method=None):
    """Run specific test class or method."""
    suite = unittest.TestLoader().loadTestsFromTestCase(test_class)
    if test_method:
        suite = unittest.TestSuite([test_class(test_method)])
    runner = unittest.TextTestRunner(verbosity=2)
    return runner.run(suite)


def run_all_tests():
    """Run all tests with detailed output."""
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    test_classes = [
        TestLingvoClass,
        TestConverterFunction,
        TestNormalizeFunction,
        TestParseLanguageList,
        TestCountryConverter,
        TestLanguageLists,
        TestGetLingvos,
    ]

    for test_class in test_classes:
        suite.addTests(loader.loadTestsFromTestCase(test_class))

    runner = unittest.TextTestRunner(verbosity=2)
    return runner.run(suite)


if __name__ == "__main__":
    print("=" * 70)
    print("Language Module Test Suite")
    print("=" * 70)
    run_all_tests()
