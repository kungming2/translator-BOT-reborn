#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
Test suite for models/komando.py.

Covers:
  - Komando class: initialization, __repr__, to_dict
  - remap_language(): happy path, wrong name raises, empty data
  - _check_specific_mode(): trailing !, valid/invalid lengths, punctuation
  - _deduplicate_args(): strings, tuples, mixed; order preservation
"""

import unittest
from collections.abc import Callable
from typing import Any

# noinspection PyProtectedMember
from models.komando import Komando, _check_specific_mode, _deduplicate_args

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


# ---------------------------------------------------------------------------
# Komando.__init__
# ---------------------------------------------------------------------------


class TestKomandoInit(unittest.TestCase):
    """Komando initialises with correct defaults and stored values."""

    def test_name_only_defaults(self) -> None:
        komando = Komando("translated")
        self.assertEqual(komando.name, "translated")
        self.assertIsNone(komando.data)
        self.assertFalse(komando.specific_mode)
        self.assertFalse(komando.disable_tokenization)

    def test_name_and_data_stored(self) -> None:
        komando = Komando("identify", data=["es"])
        self.assertEqual(komando.name, "identify")
        self.assertEqual(komando.data, ["es"])

    def test_specific_mode_flag_stored(self) -> None:
        komando = Komando("identify", specific_mode=True)
        self.assertTrue(komando.specific_mode)

    def test_disable_tokenization_flag_stored(self) -> None:
        komando = Komando("lookup_cjk", disable_tokenization=True)
        self.assertTrue(komando.disable_tokenization)

    def test_empty_data_list_stored(self) -> None:
        komando = Komando("translated", data=[])
        self.assertEqual(komando.data, [])

    def test_cjk_tuple_data_stored(self) -> None:
        data = [("zh", "中文", False)]
        komando = Komando("lookup_cjk", data=data)
        self.assertEqual(komando.data, data)


# ---------------------------------------------------------------------------
# Komando.__repr__
# ---------------------------------------------------------------------------


class TestKomandoRepr(unittest.TestCase):
    """__repr__ includes all four fields."""

    def test_repr_name_only(self) -> None:
        komando = Komando("translated")
        result = repr(komando)
        self.assertIn("name='translated'", result)
        self.assertIn("data=None", result)
        self.assertIn("specific_mode=False", result)
        self.assertIn("disable_tokenization=False", result)

    def test_repr_with_data(self) -> None:
        komando = Komando("identify", data=["es"])
        result = repr(komando)
        self.assertIn("data=['es']", result)

    def test_repr_with_flags(self) -> None:
        komando = Komando("lookup_cjk", specific_mode=True, disable_tokenization=True)
        result = repr(komando)
        self.assertIn("specific_mode=True", result)
        self.assertIn("disable_tokenization=True", result)


# ---------------------------------------------------------------------------
# Komando.to_dict
# ---------------------------------------------------------------------------


class TestKomandoToDict(unittest.TestCase):
    """to_dict() serialises all four fields correctly."""

    def test_to_dict_keys_present(self) -> None:
        komando = Komando("translated")
        result = komando.to_dict()
        for key in ("name", "data", "specific_mode", "disable_tokenization"):
            self.assertIn(key, result)

    def test_to_dict_name_only(self) -> None:
        result = Komando("translated").to_dict()
        self.assertEqual(result["name"], "translated")
        self.assertIsNone(result["data"])
        self.assertFalse(result["specific_mode"])
        self.assertFalse(result["disable_tokenization"])

    def test_to_dict_with_string_data(self) -> None:
        result = Komando("lookup_wp", data=["Volapuk"]).to_dict()
        self.assertEqual(result["data"], ["Volapuk"])

    def test_to_dict_with_cjk_tuple_data(self) -> None:
        data = [("zh", "中文", False)]
        result = Komando("lookup_cjk", data=data).to_dict()
        self.assertEqual(result["data"], data)

    def test_to_dict_with_flags(self) -> None:
        result = Komando(
            "lookup_cjk",
            data=[("zh", "中文", False)],
            specific_mode=True,
            disable_tokenization=True,
        ).to_dict()
        self.assertTrue(result["specific_mode"])
        self.assertTrue(result["disable_tokenization"])

    def test_to_dict_is_json_serialisable(self) -> None:
        import json

        komando = Komando("lookup_wp", data=["Volapuk"])
        json.dumps(komando.to_dict())  # should not raise


# ---------------------------------------------------------------------------
# Komando.remap_language
# ---------------------------------------------------------------------------


class TestKomandoRemapLanguage(unittest.TestCase):
    """remap_language() remaps language codes in lookup_cjk data."""

    def test_remap_three_tuple_format(self) -> None:
        komando = Komando(
            "lookup_cjk", data=[("zh", "中文", False), ("zh", "麻将", True)]
        )
        remapped = komando.remap_language("ja")
        self.assertIsInstance(remapped, Komando)
        for entry in remapped.data:
            self.assertEqual(entry[0], "ja")

    def test_remap_two_tuple_format(self) -> None:
        komando = Komando("lookup_cjk", data=[("zh", "中文")])
        remapped = komando.remap_language("ko")
        self.assertEqual(remapped.data[0][0], "ko")
        self.assertEqual(remapped.data[0][1], "中文")

    def test_remap_preserves_term(self) -> None:
        komando = Komando("lookup_cjk", data=[("zh", "時間", False)])
        remapped = komando.remap_language("ja")
        self.assertEqual(remapped.data[0][1], "時間")

    def test_remap_preserves_flags(self) -> None:
        komando = Komando(
            "lookup_cjk",
            data=[("zh", "中文", False)],
            specific_mode=True,
            disable_tokenization=True,
        )
        remapped = komando.remap_language("ja")
        self.assertTrue(remapped.specific_mode)
        self.assertTrue(remapped.disable_tokenization)

    def test_remap_wrong_name_raises(self) -> None:
        komando = Komando("identify", data=[("zh", "中文", False)])
        with self.assertRaises(ValueError):
            komando.remap_language("ja")

    def test_remap_empty_data_returns_copy(self) -> None:
        komando = Komando("lookup_cjk", data=None)
        remapped = komando.remap_language("ja")
        self.assertIsNone(remapped.data)
        self.assertEqual(remapped.name, "lookup_cjk")

    def test_remap_returns_new_object(self) -> None:
        komando = Komando("lookup_cjk", data=[("zh", "中文", False)])
        remapped = komando.remap_language("ja")
        self.assertIsNot(remapped, komando)


# ---------------------------------------------------------------------------
# _check_specific_mode()
# ---------------------------------------------------------------------------


class TestCheckSpecificMode(unittest.TestCase):
    """_check_specific_mode() detects trailing ! on 2–4 char codes."""

    def test_two_char_code_with_bang(self) -> None:
        cleaned, is_specific = _check_specific_mode("la!")
        self.assertEqual(cleaned, "la")
        self.assertTrue(is_specific)

    def test_three_char_code_with_bang(self) -> None:
        cleaned, is_specific = _check_specific_mode("grc!")
        self.assertEqual(cleaned, "grc")
        self.assertTrue(is_specific)

    def test_four_char_code_with_bang(self) -> None:
        cleaned, is_specific = _check_specific_mode("Latn!")
        self.assertEqual(cleaned, "Latn")
        self.assertTrue(is_specific)

    def test_no_bang_returns_unchanged(self) -> None:
        cleaned, is_specific = _check_specific_mode("english")
        self.assertEqual(cleaned, "english")
        self.assertFalse(is_specific)

    def test_bang_on_too_long_code_returns_none(self) -> None:
        cleaned, is_specific = _check_specific_mode("toolong!")
        self.assertIsNone(cleaned)
        self.assertFalse(is_specific)

    def test_bang_on_one_char_returns_none(self) -> None:
        cleaned, is_specific = _check_specific_mode("a!")
        self.assertIsNone(cleaned)
        self.assertFalse(is_specific)

    def test_trailing_punctuation_stripped_before_check(self) -> None:
        # Trailing comma stripped, then no bang → not specific
        cleaned, is_specific = _check_specific_mode("la,")
        self.assertEqual(cleaned, "la")
        self.assertFalse(is_specific)

    def test_empty_string_no_bang(self) -> None:
        cleaned, is_specific = _check_specific_mode("")
        self.assertEqual(cleaned, "")
        self.assertFalse(is_specific)


# ---------------------------------------------------------------------------
# _deduplicate_args()
# ---------------------------------------------------------------------------


class TestDeduplicateArgs(unittest.TestCase):
    """_deduplicate_args() removes duplicates while preserving insertion order."""

    def test_empty_list_returns_empty(self) -> None:
        self.assertEqual(_deduplicate_args([]), [])

    def test_strings_deduplicated(self) -> None:
        result = _deduplicate_args(["en", "fr", "en", "de", "fr"])
        self.assertEqual(result, ["en", "fr", "de"])

    def test_strings_order_preserved(self) -> None:
        result = _deduplicate_args(["de", "en", "fr"])
        self.assertEqual(result, ["de", "en", "fr"])

    def test_tuples_deduplicated(self) -> None:
        data = [("zh", "中文", False), ("zh", "麻将", False), ("zh", "中文", False)]
        result = _deduplicate_args(data)
        self.assertEqual(len(result), 2)
        self.assertIn(("zh", "中文", False), result)
        self.assertIn(("zh", "麻将", False), result)

    def test_tuples_order_preserved(self) -> None:
        data = [("zh", "中文", False), ("ko", "시계", True)]
        result = _deduplicate_args(data)
        self.assertEqual(result[0], ("zh", "中文", False))
        self.assertEqual(result[1], ("ko", "시계", True))

    def test_single_item_unchanged(self) -> None:
        self.assertEqual(_deduplicate_args(["en"]), ["en"])

    def test_no_duplicates_unchanged(self) -> None:
        data = ["en", "fr", "de"]
        self.assertEqual(_deduplicate_args(data), data)


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


def run_all_tests() -> unittest.TestResult:
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    for cls in (
        TestKomandoInit,
        TestKomandoRepr,
        TestKomandoToDict,
        TestKomandoRemapLanguage,
        TestCheckSpecificMode,
        TestDeduplicateArgs,
    ):
        suite.addTests(loader.loadTestsFromTestCase(cls))
    runner = unittest.TextTestRunner(verbosity=2)
    return runner.run(suite)


if __name__ == "__main__":
    print("=" * 70)
    print("Komando Test Suite")
    print("=" * 70)
    run_all_tests()
