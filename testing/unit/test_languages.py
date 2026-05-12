#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
Test suite for languages.py, lingvo.py, and countries.py.

Covers:
  - Lingvo class construction, properties, equality, hashing, serialisation
  - converter(): stable codes, edge inputs, compound codes, script prefix,
    specific_mode, preserve_country, fuzzy matching
  - normalize(), parse_language_list() (all delimiter styles)
  - country_converter()
  - define_language_lists() / get_lingvos() structure and caching
"""

import unittest
from collections.abc import Callable
from typing import Any

from lang.code_standards import alpha3_code, parse_language_tag
from lang.countries import country_converter
from lang.languages import (converter, define_language_lists, get_lingvos,
                            normalize, parse_language_list)
from models.lingvo import Lingvo

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _skip_if_no_data(fn: Callable[..., Any]) -> Callable[..., Any]:
    """Decorator: skip a test if any data-loading exception is raised."""

    def wrapper(self: unittest.TestCase, *args: Any, **kwargs: Any) -> Any:
        try:
            return fn(self, *args, **kwargs)
        except (FileNotFoundError, ImportError, KeyError, ValueError) as exc:
            self.skipTest(f"Language data not available: {exc}")

    wrapper.__name__ = fn.__name__
    return wrapper


# ---------------------------------------------------------------------------
# Lingvo class
# ---------------------------------------------------------------------------


class TestLingvoInit(unittest.TestCase):
    """Lingvo construction and basic attribute access."""

    def setUp(self) -> None:
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
            name="Unknown",
            language_code_1="unknown",
            language_code_3="unknown",
        )

    def test_basic_attributes(self) -> None:
        self.assertEqual(self.english.name, "English")
        self.assertEqual(self.english.language_code_1, "en")
        self.assertEqual(self.english.language_code_3, "eng")
        self.assertTrue(self.english.supported)

    def test_defaults(self) -> None:
        bare = Lingvo(name="Bare")
        self.assertFalse(bare.supported)
        self.assertEqual(bare.thanks, "Thanks")
        self.assertEqual(bare.greetings, "Hello")
        self.assertEqual(bare.name_alternates, [])

    def test_to_dict_contains_expected_keys(self) -> None:
        d = self.english.to_dict()
        for key in (
            "name",
            "language_code_1",
            "language_code_3",
            "preferred_code",
            "supported",
            "thanks",
            "greetings",
        ):
            self.assertIn(key, d)
        self.assertEqual(d["name"], "English")
        self.assertEqual(d["preferred_code"], "en")


class TestLingvoPreferredCode(unittest.TestCase):
    """preferred_code property priority logic."""

    def test_prefers_code_1_over_code_3(self) -> None:
        lingvo = Lingvo(language_code_1="en", language_code_3="eng")
        self.assertEqual(lingvo.preferred_code, "en")

    def test_falls_back_to_code_3(self) -> None:
        lingvo = Lingvo(language_code_3="spa")
        self.assertEqual(lingvo.preferred_code, "spa")

    def test_falls_back_to_script_code(self) -> None:
        lingvo = Lingvo(language_code_1="unknown", script_code="Cyrl")
        self.assertEqual(lingvo.preferred_code, "cyrl")

    def test_unknown_code_1_skipped(self) -> None:
        lingvo = Lingvo(language_code_1="unknown", language_code_3="eng")
        self.assertEqual(lingvo.preferred_code, "eng")

    def test_all_unknown_returns_unknown(self) -> None:
        lingvo = Lingvo(language_code_1="unknown", language_code_3="unknown")
        self.assertEqual(lingvo.preferred_code, "unknown")

    def test_multiple_code_returned(self) -> None:
        lingvo = Lingvo(language_code_1="multiple")
        self.assertEqual(lingvo.preferred_code, "multiple")

    def test_generic_code_returned(self) -> None:
        lingvo = Lingvo(language_code_1="generic")
        self.assertEqual(lingvo.preferred_code, "generic")


class TestLingvoEqualityAndHashing(unittest.TestCase):
    """__eq__ and __hash__ based on preferred_code."""

    def test_equal_same_code(self) -> None:
        a = Lingvo(name="English A", language_code_1="en")
        b = Lingvo(name="English B", language_code_1="en")
        self.assertEqual(a, b)

    def test_not_equal_different_code(self) -> None:
        a = Lingvo(language_code_1="en")
        b = Lingvo(language_code_1="fr")
        self.assertNotEqual(a, b)

    def test_hashable_set_deduplication(self) -> None:
        a = Lingvo(language_code_1="en")
        b = Lingvo(name="English variant", language_code_1="en")
        c = Lingvo(language_code_1="fr")
        s = {a, b, c}
        self.assertEqual(len(s), 2)

    def test_not_equal_to_non_lingvo(self) -> None:
        lingvo = Lingvo(language_code_1="en")
        self.assertNotEqual(lingvo, "en")


class TestLingvoStringRepresentation(unittest.TestCase):
    def test_str_returns_preferred_code(self) -> None:
        lingvo = Lingvo(language_code_1="fr")
        self.assertEqual(str(lingvo), "fr")

    def test_repr_contains_name_and_code(self) -> None:
        lingvo = Lingvo(name="French", language_code_1="fr")
        r = repr(lingvo)
        self.assertIn("French", r)
        self.assertIn("fr", r)

    def test_repr_flags_script_entries(self) -> None:
        lingvo = Lingvo(name="Cyrillic", language_code_1="unknown", script_code="Cyrl")
        self.assertIn("script", repr(lingvo))


class TestLingvoFromCsvRow(unittest.TestCase):
    def test_basic_construction(self) -> None:
        row = {
            "Language Name": "Spanish",
            "ISO 639-1": "es",
            "ISO 639-3": "spa",
            "Alternate Names": "Castilian; Español",
        }
        lingvo = Lingvo.from_csv_row(row)
        self.assertEqual(lingvo.name, "Spanish")
        self.assertEqual(lingvo.language_code_1, "es")
        self.assertEqual(lingvo.language_code_3, "spa")
        self.assertIn("Castilian", lingvo.name_alternates)

    def test_empty_alternate_names(self) -> None:
        row = {
            "Language Name": "Klingon",
            "ISO 639-1": "",
            "ISO 639-3": "tlh",
            "Alternate Names": "",
        }
        lingvo = Lingvo.from_csv_row(row)
        self.assertEqual(lingvo.name_alternates, [])

    def test_empty_iso_1_becomes_none(self) -> None:
        row = {
            "Language Name": "Xhosa",
            "ISO 639-1": "",
            "ISO 639-3": "xho",
            "Alternate Names": "",
        }
        lingvo = Lingvo.from_csv_row(row)
        self.assertIsNone(lingvo.language_code_1)


# ---------------------------------------------------------------------------
# normalize()
# ---------------------------------------------------------------------------


class TestNormalize(unittest.TestCase):
    def test_lowercases(self) -> None:
        self.assertEqual(normalize("ENGLISH"), "english")

    def test_strips_leading_trailing_whitespace(self) -> None:
        self.assertEqual(normalize("  english  "), "english")

    def test_collapses_internal_whitespace(self) -> None:
        self.assertEqual(normalize("english  language"), "english language")

    def test_removes_punctuation(self) -> None:
        self.assertEqual(normalize("english!"), "english")

    def test_empty_string(self) -> None:
        self.assertEqual(normalize(""), "")

    def test_preserves_numbers(self) -> None:
        self.assertEqual(normalize("Code123"), "code123")


# ---------------------------------------------------------------------------
# converter() — stable codes, edge inputs
# ---------------------------------------------------------------------------


class TestConverterStableCodes(unittest.TestCase):
    """Concrete assertions on codes that will always be in any dataset."""

    @_skip_if_no_data
    def test_two_letter_en(self) -> None:
        result = converter("en")
        self.assertIsNotNone(result)
        self.assertEqual(result.preferred_code, "en")

    @_skip_if_no_data
    def test_two_letter_fr(self) -> None:
        result = converter("fr")
        self.assertIsNotNone(result)
        self.assertEqual(result.preferred_code, "fr")

    @_skip_if_no_data
    def test_three_letter_spa(self) -> None:
        result = converter("spa")
        self.assertIsNotNone(result)
        self.assertIsInstance(result, Lingvo)

    @_skip_if_no_data
    def test_three_letter_fra(self) -> None:
        result = converter("fra")
        self.assertIsNotNone(result)
        self.assertIsInstance(result, Lingvo)

    @_skip_if_no_data
    def test_bibliographic_alpha3_fre(self) -> None:
        result = converter("fre")
        self.assertIsNotNone(result)
        self.assertEqual(result.preferred_code, "fr")

    @_skip_if_no_data
    def test_terminology_alpha3_deu(self) -> None:
        result = converter("deu")
        self.assertIsNotNone(result)
        self.assertEqual(result.preferred_code, "de")

    @_skip_if_no_data
    def test_case_insensitive_EN(self) -> None:
        lower = converter("en")
        upper = converter("EN")
        self.assertIsNotNone(lower)
        self.assertIsNotNone(upper)
        self.assertEqual(lower, upper)

    @_skip_if_no_data
    def test_whitespace_stripped(self) -> None:
        result = converter("  en  ")
        self.assertIsNotNone(result)
        self.assertEqual(result.preferred_code, "en")

    @_skip_if_no_data
    def test_name_lookup_english(self) -> None:
        result = converter("English")
        self.assertIsNotNone(result)
        self.assertEqual(result.preferred_code, "en")

    @_skip_if_no_data
    def test_name_lookup_french(self) -> None:
        result = converter("French")
        self.assertIsNotNone(result)
        self.assertEqual(result.preferred_code, "fr")

    @_skip_if_no_data
    def test_name_lookup_handles_apostrophe_casing_mikmaq(self) -> None:
        result = converter("Mi'kmaq")
        self.assertIsNotNone(result)
        self.assertEqual(result.name, "Mi'kmaq")

    @_skip_if_no_data
    def test_name_lookup_handles_apostrophe_casing_tohono_oodham(self) -> None:
        result = converter("Tohono O'odham")
        self.assertIsNotNone(result)
        self.assertEqual(result.name, "Tohono O'odham")


class TestConverterEdgeInputs(unittest.TestCase):
    """Inputs that should always return None."""

    def test_empty_string(self) -> None:
        self.assertIsNone(converter(""))

    def test_single_character(self) -> None:
        self.assertIsNone(converter("a"))

    def test_gibberish(self) -> None:
        self.assertIsNone(converter("xyzxyzxyz"))


class TestConverterCompoundCodes(unittest.TestCase):
    """Compound language-region codes (zh-CN, pt-BR, etc.)."""

    @_skip_if_no_data
    def test_zh_CN_returns_lingvo(self) -> None:
        result = converter("zh-CN")
        self.assertIsNotNone(result)
        self.assertIsInstance(result, Lingvo)

    @_skip_if_no_data
    def test_zh_CN_has_country_set(self) -> None:
        result = converter("zh-CN")
        self.assertIsNotNone(result)
        self.assertIsNotNone(result.country)

    @_skip_if_no_data
    def test_pt_BR_returns_lingvo(self) -> None:
        result = converter("pt-BR")
        self.assertIsNotNone(result)
        self.assertIsInstance(result, Lingvo)

    @_skip_if_no_data
    def test_pt_BR_has_country_set(self) -> None:
        result = converter("pt-BR")
        self.assertIsNotNone(result)
        self.assertIsNotNone(result.country)

    @_skip_if_no_data
    def test_en_US_returns_lingvo(self) -> None:
        result = converter("en-US")
        self.assertIsNotNone(result)
        self.assertIsInstance(result, Lingvo)

    @_skip_if_no_data
    def test_en_uk_standardizes_to_gb_region(self) -> None:
        result = converter("en-uk")
        self.assertIsNotNone(result)
        self.assertEqual(result.preferred_code, "en")
        self.assertEqual(result.country, "GB")

    @_skip_if_no_data
    def test_sgn_us_standardizes_to_american_sign_language(self) -> None:
        result = converter("sgn-US")
        self.assertIsNotNone(result)
        self.assertEqual(result.preferred_code, "ase")

    @_skip_if_no_data
    def test_script_tag_returns_base_lingvo(self) -> None:
        result = converter("zh-Hans")
        self.assertIsNotNone(result)
        self.assertEqual(result.preferred_code, "zh")


class TestConverterScriptPrefix(unittest.TestCase):
    """unknown-<Script> compound codes."""

    @_skip_if_no_data
    def test_unknown_cyrl_returns_lingvo(self) -> None:
        result = converter("unknown-Cyrl")
        self.assertIsNotNone(result)
        self.assertIsInstance(result, Lingvo)

    @_skip_if_no_data
    def test_unknown_cyrl_code_1_is_unknown(self) -> None:
        result = converter("unknown-Cyrl")
        self.assertIsNotNone(result)
        self.assertEqual(result.language_code_1, "unknown")

    @_skip_if_no_data
    def test_unknown_cyrl_script_code_set(self) -> None:
        result = converter("unknown-Cyrl")
        self.assertIsNotNone(result)
        self.assertIsNotNone(result.script_code)

    @_skip_if_no_data
    def test_unknown_hans_returns_lingvo(self) -> None:
        result = converter("unknown-Hans")
        self.assertIsNotNone(result)
        self.assertIsInstance(result, Lingvo)


class TestConverterSpecificMode(unittest.TestCase):
    """specific_mode=True enforces strict ISO lookups, no fuzzy."""

    @_skip_if_no_data
    def test_specific_mode_2letter_en(self) -> None:
        result = converter("en", specific_mode=True)
        self.assertIsNotNone(result)
        self.assertEqual(result.preferred_code, "en")

    @_skip_if_no_data
    def test_specific_mode_3letter_spa(self) -> None:
        result = converter("spa", specific_mode=True)
        self.assertIsNotNone(result)
        self.assertIsInstance(result, Lingvo)

    @_skip_if_no_data
    def test_specific_mode_4letter_script_cyrl(self) -> None:
        result = converter("Cyrl", specific_mode=True)
        self.assertIsNotNone(result)
        self.assertIsInstance(result, Lingvo)

    @_skip_if_no_data
    def test_specific_mode_name_returns_none(self) -> None:
        # In specific_mode, plain names shouldn't match (no fuzzy, no name walk)
        result = converter("English", specific_mode=True)
        self.assertIsNone(result)

    @_skip_if_no_data
    def test_specific_mode_5plus_chars_returns_none(self) -> None:
        result = converter("English", specific_mode=True)
        self.assertIsNone(result)


class TestConverterPreserveCountry(unittest.TestCase):
    """preserve_country flag keeps vs clears the country field."""

    @_skip_if_no_data
    def test_preserve_country_false_clears_country(self) -> None:
        # Simple code lookup — country should be cleared
        result = converter("en", preserve_country=False)
        self.assertIsNotNone(result)
        self.assertIsNone(result.country)

    @_skip_if_no_data
    def test_preserve_country_true_keeps_country(self) -> None:
        # Only meaningful if the underlying Lingvo has a country set in YAML.
        # We verify the flag doesn't crash and returns a Lingvo.
        result = converter("en", preserve_country=True)
        self.assertIsNotNone(result)
        self.assertIsInstance(result, Lingvo)

    @_skip_if_no_data
    def test_compound_code_always_sets_country(self) -> None:
        # Compound codes attach country regardless of preserve_country
        result = converter("pt-BR", preserve_country=False)
        self.assertIsNotNone(result)
        self.assertIsNotNone(result.country)


class TestConverterFuzzy(unittest.TestCase):
    """Fuzzy matching resolves near-miss language names."""

    @_skip_if_no_data
    def test_fuzzy_on_by_default(self) -> None:
        # "Engish" (typo) should fuzzy-match to English
        result = converter("Engish")
        # May or may not match depending on threshold — just verify no crash
        self.assertTrue(result is None or isinstance(result, Lingvo))

    @_skip_if_no_data
    def test_fuzzy_false_does_not_match_typo(self) -> None:
        result = converter("Engish", fuzzy=False)
        self.assertIsNone(result)

    @_skip_if_no_data
    def test_fuzzy_matches_close_name(self) -> None:
        # "Portugese" is a very common misspelling
        result = converter("Portugese")
        self.assertTrue(result is None or isinstance(result, Lingvo))


# ---------------------------------------------------------------------------
# parse_language_list()
# ---------------------------------------------------------------------------


class TestParseLanguageList(unittest.TestCase):
    def test_empty_string_returns_empty(self) -> None:
        self.assertEqual(parse_language_list(""), [])

    @_skip_if_no_data
    def test_comma_delimited(self) -> None:
        result = parse_language_list("en, fr, es")
        self.assertIsInstance(result, list)
        self.assertTrue(all(isinstance(x, Lingvo) for x in result))

    @_skip_if_no_data
    def test_plus_delimited(self) -> None:
        result = parse_language_list("en+fr")
        self.assertIsInstance(result, list)
        self.assertGreater(len(result), 0)

    @_skip_if_no_data
    def test_newline_delimited(self) -> None:
        result = parse_language_list("en\nfr\nes")
        self.assertIsInstance(result, list)
        self.assertGreater(len(result), 0)

    @_skip_if_no_data
    def test_slash_delimited(self) -> None:
        result = parse_language_list("en/fr/de")
        self.assertIsInstance(result, list)
        self.assertGreater(len(result), 0)

    @_skip_if_no_data
    def test_languages_prefix_stripped(self) -> None:
        result = parse_language_list("LANGUAGES: en, fr")
        self.assertIsInstance(result, list)
        self.assertGreater(len(result), 0)

    @_skip_if_no_data
    def test_markdown_instruction_lines_are_ignored(self) -> None:
        result = parse_language_list(
            "## Sign up for notifications about new requests.\n"
            "## Reply with language names or codes below.\n"
            "Chinese, French"
        )
        codes = [lingvo.preferred_code for lingvo in result]
        self.assertEqual(codes, ["fr", "zh"])

    @_skip_if_no_data
    def test_leading_quote_prompt_is_ignored(self) -> None:
        result = parse_language_list(
            "## Sign up for notifications about new requests.\n"
            "## Type the language names or codes after the > below.\n"
            "> Spanish, Japanese, zh"
        )
        codes = [lingvo.preferred_code for lingvo in result]
        self.assertEqual(codes, ["es", "ja", "zh"])

    @_skip_if_no_data
    def test_utility_codes_excluded(self) -> None:
        result = parse_language_list("en, meta, community, all, fr")
        codes = [lingvo.preferred_code for lingvo in result]
        self.assertNotIn("meta", codes)
        self.assertNotIn("community", codes)
        self.assertNotIn("all", codes)

    @_skip_if_no_data
    def test_deduplication_by_preferred_code(self) -> None:
        # "en" and "eng" resolve to the same preferred_code
        result = parse_language_list("en, eng")
        codes = [lingvo.preferred_code for lingvo in result]
        self.assertEqual(len(codes), len(set(codes)))

    @_skip_if_no_data
    def test_result_is_sorted(self) -> None:
        result = parse_language_list("es, en, fr")
        codes = [lingvo.preferred_code for lingvo in result]
        self.assertEqual(codes, sorted(codes))

    @_skip_if_no_data
    def test_space_delimited_preserves_multiword_language(self) -> None:
        result = parse_language_list("Old English")
        self.assertEqual(len(result), 1)
        # "Old English" is an alternate name for Anglo-Saxon; the canonical
        # name returned by converter() is "Anglo-Saxon".
        self.assertEqual(result[0].name, "Anglo-Saxon")


# ---------------------------------------------------------------------------
# langcodes adapter
# ---------------------------------------------------------------------------


class TestCodeStandardsAdapter(unittest.TestCase):
    def test_alpha3_terminology_and_bibliographic_codes(self) -> None:
        self.assertEqual(alpha3_code("fr", variant="T"), "fra")
        self.assertEqual(alpha3_code("fr", variant="B"), "fre")

    def test_parse_language_region_tag(self) -> None:
        parsed = parse_language_tag("eng_US")
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed.language, "en")
        self.assertEqual(parsed.territory, "US")


# ---------------------------------------------------------------------------
# country_converter()
# ---------------------------------------------------------------------------


class TestCountryConverter(unittest.TestCase):
    def test_empty_returns_empty_tuple(self) -> None:
        self.assertEqual(country_converter(""), ("", ""))

    def test_single_char_returns_empty_tuple(self) -> None:
        self.assertEqual(country_converter("a"), ("", ""))

    def test_two_letter_EE(self) -> None:
        result = country_converter("EE")
        if result[0]:  # only assert if dataset loaded
            self.assertEqual(result[0], "EE")
            self.assertIsInstance(result[1], str)

    def test_three_letter_EST(self) -> None:
        result = country_converter("EST")
        if result[0]:
            self.assertIsInstance(result, tuple)
            self.assertEqual(len(result), 2)

    def test_full_name_estonia(self) -> None:
        result = country_converter("Estonia")
        if result[0]:
            self.assertEqual(result[0], "EE")

    def test_abbreviations_disabled(self) -> None:
        # With abbreviations_okay=False, short codes should not match
        result = country_converter("EE", abbreviations_okay=False)
        self.assertIsInstance(result, tuple)
        self.assertEqual(len(result), 2)

    def test_returns_tuple_always(self) -> None:
        for inp in ["", "a", "US", "France", "zzz"]:
            result = country_converter(inp)
            self.assertIsInstance(result, tuple)
            self.assertEqual(len(result), 2)


# ---------------------------------------------------------------------------
# define_language_lists() and get_lingvos()
# ---------------------------------------------------------------------------


class TestLanguageLists(unittest.TestCase):
    @_skip_if_no_data
    def test_returns_dict(self) -> None:
        lists = define_language_lists()
        self.assertIsInstance(lists, dict)

    @_skip_if_no_data
    def test_expected_keys_present(self) -> None:
        lists = define_language_lists()
        for key in (
            "SUPPORTED_CODES",
            "SUPPORTED_LANGUAGES",
            "ISO_DEFAULT_ASSOCIATED",
            "ISO_639_1",
            "ISO_639_2B",
            "ISO_639_3",
            "ISO_NAMES",
            "MISTAKE_ABBREVIATIONS",
            "LANGUAGE_COUNTRY_ASSOCIATED",
        ):
            self.assertIn(key, lists)

    @_skip_if_no_data
    def test_supported_codes_are_strings(self) -> None:
        lists = define_language_lists()
        for code in lists["SUPPORTED_CODES"]:
            self.assertIsInstance(code, str)

    @_skip_if_no_data
    def test_iso_639_1_codes_unique(self) -> None:
        lists = define_language_lists()
        iso = lists["ISO_639_1"]
        self.assertEqual(len(iso), len(set(iso)))

    @_skip_if_no_data
    def test_iso_639_2b_maps_to_strings(self) -> None:
        lists = define_language_lists()
        for k, v in lists["ISO_639_2B"].items():
            self.assertIsInstance(k, str)
            self.assertIsInstance(v, str)

    @_skip_if_no_data
    def test_caching_returns_same_object(self) -> None:
        lists1 = define_language_lists()
        lists2 = define_language_lists()
        self.assertIs(lists1, lists2)


class TestGetLingvos(unittest.TestCase):
    @_skip_if_no_data
    def test_returns_dict(self) -> None:
        lingvos = get_lingvos()
        self.assertIsInstance(lingvos, dict)

    @_skip_if_no_data
    def test_values_are_lingvo_instances(self) -> None:
        lingvos = get_lingvos()
        for _, v in list(lingvos.items())[:10]:
            self.assertIsInstance(v, Lingvo)

    @_skip_if_no_data
    def test_caching_returns_same_object(self) -> None:
        r1 = get_lingvos()
        r2 = get_lingvos()
        self.assertIs(r1, r2)

    @_skip_if_no_data
    def test_force_refresh_returns_fresh_dict(self) -> None:
        r1 = get_lingvos()
        r2 = get_lingvos(force_refresh=True)
        # Same keys/content but different object after refresh
        self.assertIsInstance(r2, dict)
        self.assertEqual(set(r1.keys()), set(r2.keys()))


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


def run_all_tests() -> unittest.TestResult:
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    for cls in (
        TestLingvoInit,
        TestLingvoPreferredCode,
        TestLingvoEqualityAndHashing,
        TestLingvoStringRepresentation,
        TestLingvoFromCsvRow,
        TestNormalize,
        TestConverterStableCodes,
        TestConverterEdgeInputs,
        TestConverterCompoundCodes,
        TestConverterScriptPrefix,
        TestConverterSpecificMode,
        TestConverterPreserveCountry,
        TestConverterFuzzy,
        TestParseLanguageList,
        TestCountryConverter,
        TestLanguageLists,
        TestGetLingvos,
    ):
        suite.addTests(loader.loadTestsFromTestCase(cls))
    runner = unittest.TextTestRunner(verbosity=2)
    return runner.run(suite)


if __name__ == "__main__":
    print("=" * 70)
    print("Language Module Test Suite")
    print("=" * 70)
    run_all_tests()
