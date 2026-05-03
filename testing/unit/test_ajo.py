#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
Test suite for ajo.py module.
Tests the Ajo class, serialization, state management, and related functions.
"""

import unittest
from unittest.mock import MagicMock

# noinspection PyProtectedMember
from models.ajo import (
    Ajo,
    _convert_to_dict,
    _normalize_lang_field,
    ajo_defined_multiple_flair_former,
    parse_ajo_data,
)
from models.lingvo import Lingvo
from models.titolo import Direction, Titolo

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_lingvo(
    name: str, code1: str | None = None, code3: str | None = None
) -> Lingvo:
    """Construct a minimal Lingvo using the current kwargs-only API."""
    return Lingvo(name=name, language_code_1=code1, language_code_3=code3)


def make_titolo(
    source_codes: list[tuple[str, str | None, str | None]],
    target_codes: list[tuple[str, str | None, str | None]],
    final_code: str = "unknown",
    final_text: str = "Unknown",
    direction: Direction = "english_to",
    title_original: str = "[? > English] test",
    title_actual: str = "test",
) -> Titolo:
    """Build a Titolo without running the full parse pipeline."""
    t = Titolo()
    t.source = [make_lingvo(n, c1, c3) for n, c1, c3 in source_codes]
    t.target = [make_lingvo(n, c1, c3) for n, c1, c3 in target_codes]
    t.final_code = final_code
    t.final_text = final_text
    t.direction = direction
    t.title_original = title_original
    t.title_actual = title_actual
    return t


# ---------------------------------------------------------------------------
# Real Ajo sample data (anonymised from production)
# ---------------------------------------------------------------------------

REAL_AJOS = [
    # 1rw44gg — unknown language, still untranslated
    {
        "author": "test_user_a",
        "author_messaged": False,
        "closed_out": False,
        "created_utc": 1773747620,
        "direction": "english_to",
        "id": "1rw44gg",
        "image_hash": "50d04c4c515551d4",
        "is_defined_multiple": False,
        "is_identified": False,
        "is_long": False,
        "language_history": ["unknown"],
        "notified": ["test_notified_a"],
        "original_source_language_name": ["Unknown"],
        "original_target_language_name": ["English"],
        "output_post_flair_css": None,
        "output_post_flair_text": None,
        "preferred_code": "unknown",
        "recorded_translators": [],
        "status": "untranslated",
        "time_delta": {},
        "title": "",
        "title_original": "[?Tibetian? >English] Plant chart caption translation please",
        "type": "single",
    },
    # 1rvytkz — Chinese (Mandarin), translated
    {
        "author": "test_user_b",
        "author_messaged": False,
        "closed_out": True,
        "created_utc": 1773728507,
        "direction": "english_to",
        "id": "1rvytkz",
        "image_hash": "585a588e161f1f0e",
        "is_defined_multiple": False,
        "is_identified": False,
        "is_long": False,
        "language_history": ["zh"],
        "notified": ["test_notified_b", "test_notified_c"],
        "original_source_language_name": ["Chinese"],
        "original_target_language_name": ["English"],
        "output_post_flair_css": None,
        "output_post_flair_text": None,
        "preferred_code": "zh",
        "recorded_translators": [],
        "status": "translated",
        "time_delta": {"translated": 1773728764},
        "title": "jade pendant",
        "title_original": "[Mandarin? > English] jade pendant",
        "type": "single",
    },
    # 1ru6ced — defined multiple (Chinese + Vietnamese), english_from
    {
        "author": "test_user_c",
        "author_messaged": False,
        "closed_out": False,
        "created_utc": 1773554376,
        "direction": "english_from",
        "id": "1ru6ced",
        "image_hash": None,
        "is_defined_multiple": True,
        "is_identified": True,
        "is_long": False,
        "language_history": [["zh", "vi"]],
        "notified": ["test_notified_d", "test_notified_e"],
        "original_source_language_name": ["English"],
        "original_target_language_name": ["Chinese", "Vietnamese"],
        "output_post_flair_css": None,
        "output_post_flair_text": None,
        "preferred_code": "multiple",
        "recorded_translators": [],
        "status": {"vi": "untranslated", "zh": "untranslated"},
        "time_delta": {},
        "title": "Peanut Allergy Cards",
        "title_original": "[English > Mandarin, Vietnamese] Peanut Allergy Cards",
        "type": "multiple",
    },
    # 1rv7neu — non-defined multiple (6 source languages)
    {
        "author": "test_user_d",
        "author_messaged": False,
        "closed_out": False,
        "created_utc": 1773662934,
        "direction": "english_to",
        "id": "1rv7neu",
        "image_hash": None,
        "is_defined_multiple": False,
        "is_identified": False,
        "is_long": False,
        "language_history": ["multiple"],
        "notified": ["test_notified_f", "test_notified_g"],
        "original_source_language_name": [
            "Zulu",
            "Arabic",
            "Finnish",
            "Hindi",
            "Japanese",
            "Chinese",
        ],
        "original_target_language_name": ["English"],
        "output_post_flair_css": None,
        "output_post_flair_text": None,
        "preferred_code": "multiple",
        "recorded_translators": [],
        "status": "untranslated",
        "time_delta": {},
        "title": "One World, One Nickelodeon  Bumper",
        "title_original": (
            "[Zulu, Arabic, Finnish, Hindi, Japanese, Mandarin > English] "
            "One World, One Nickelodeon  Bumper"
        ),
        "type": "multiple",
    },
]


# ===========================================================================
# TestAjoInitialization
# ===========================================================================


class TestAjoInitialization(unittest.TestCase):
    """Test Ajo class initialization and basic properties."""

    def setUp(self):
        self.ajo = Ajo()

    def test_ajo_creation(self):
        self.assertIsNotNone(self.ajo)
        self.assertIsNone(self.ajo.id)
        self.assertEqual(self.ajo.status, "untranslated")

    def test_ajo_default_values(self):
        self.assertIsNone(self.ajo.title_original)
        self.assertIsNone(self.ajo.title)
        self.assertIsNone(self.ajo.direction)
        self.assertFalse(self.ajo.is_identified)
        self.assertFalse(self.ajo.is_long)
        self.assertEqual(self.ajo.type, "single")
        self.assertFalse(self.ajo.is_defined_multiple)
        self.assertFalse(self.ajo.closed_out)
        self.assertEqual(self.ajo.recorded_translators, [])
        self.assertEqual(self.ajo.notified, [])
        self.assertEqual(self.ajo.time_delta, {})
        self.assertFalse(self.ajo.author_messaged)
        self.assertIsNone(self.ajo.image_hash)

    def test_ajo_repr(self):
        self.ajo.preferred_code = "en"
        self.ajo.initialize_lingvo()
        repr_str = repr(self.ajo)
        self.assertIn("Ajo", repr_str)

    def test_ajo_equality(self):
        ajo1 = Ajo()
        ajo1.preferred_code = "en"
        ajo1.status = "translated"

        ajo2 = Ajo()
        ajo2.preferred_code = "en"
        ajo2.status = "translated"

        self.assertEqual(ajo1, ajo2)

    def test_ajo_inequality(self):
        ajo1 = Ajo()
        ajo1.preferred_code = "en"

        ajo2 = Ajo()
        ajo2.preferred_code = "ja"

        self.assertNotEqual(ajo1, ajo2)


# ===========================================================================
# TestAjoImmutableProperties
# ===========================================================================


class TestAjoImmutableProperties(unittest.TestCase):
    """Test immutable properties of Ajo."""

    def test_id_immutable(self):
        ajo = Ajo()
        ajo.id = "test123"
        with self.assertRaises(AttributeError):
            ajo.id = "test456"

    def test_created_utc_immutable(self):
        ajo = Ajo()
        ajo.created_utc = 1234567890
        with self.assertRaises(AttributeError):
            ajo.created_utc = 9876543210

    def test_author_immutable(self):
        ajo = Ajo()
        ajo.author = "user1"
        with self.assertRaises(AttributeError):
            ajo.author = "user2"

    def test_id_settable_once(self):
        """ID should be settable when None."""
        ajo = Ajo()
        ajo.id = "abc"
        self.assertEqual(ajo.id, "abc")


# ===========================================================================
# TestAjoLanguageManagement
# ===========================================================================


class TestAjoLanguageManagement(unittest.TestCase):
    """Test language setting, lingvo delegation, and history tracking."""

    def setUp(self):
        self.ajo = Ajo()

    def test_set_language_single_by_code(self):
        self.ajo.set_language("ja")
        self.assertEqual(self.ajo.preferred_code, "ja")
        self.assertTrue(self.ajo.is_identified)
        self.assertEqual(self.ajo.type, "single")
        self.assertFalse(self.ajo.is_defined_multiple)

    def test_set_language_with_lingvo_object(self):
        lingvo = make_lingvo("Japanese", "ja", "jpn")
        self.ajo.set_language(lingvo)
        self.assertEqual(self.ajo.preferred_code, "ja")
        self.assertTrue(self.ajo.is_identified)

    def test_set_language_not_identified(self):
        self.ajo.set_language("fr", is_identified=False)
        self.assertFalse(self.ajo.is_identified)

    def test_set_language_multiple_list(self):
        """Setting a list of codes should create a defined multiple."""
        self.ajo.set_language(["zh", "vi"])
        self.assertEqual(self.ajo.preferred_code, "multiple")
        self.assertTrue(self.ajo.is_defined_multiple)
        self.assertEqual(self.ajo.type, "multiple")
        self.assertIsInstance(self.ajo.status, dict)
        self.assertIn("zh", self.ajo.status)
        self.assertIn("vi", self.ajo.status)
        self.assertEqual(self.ajo.status["zh"], "untranslated")

    def test_set_language_multiple_list_history(self):
        """History should contain the list of codes as a single entry."""
        self.ajo.set_language(["zh", "vi"])
        self.assertIn(["zh", "vi"], self.ajo.language_history)

    def test_set_language_multiple_list_no_duplicate_history(self):
        """Calling set_language with the same list twice should not duplicate history."""
        self.ajo.set_language(["zh", "vi"])
        self.ajo.set_language(["zh", "vi"])
        count = sum(1 for entry in self.ajo.language_history if entry == ["zh", "vi"])
        self.assertEqual(count, 1)

    def test_set_language_multiple_code_non_defined(self):
        """Setting code 'multiple' (not a list) produces a non-defined multiple."""
        self.ajo.set_language("multiple")
        self.assertEqual(self.ajo.preferred_code, "multiple")
        self.assertEqual(self.ajo.type, "multiple")
        self.assertFalse(self.ajo.is_defined_multiple)

    def test_set_language_resets_type_to_single(self):
        """Switching from multiple back to a single code resets type and flags."""
        self.ajo.set_language(["zh", "vi"])
        self.ajo.set_language("ja")
        self.assertEqual(self.ajo.type, "single")
        self.assertFalse(self.ajo.is_defined_multiple)

    def test_set_language_resets_dict_status_to_string(self):
        """Switching from a defined multiple to single converts dict status back to str."""
        self.ajo.set_language(["zh", "vi"])
        self.assertIsInstance(self.ajo.status, dict)
        self.ajo.set_language("ja")
        self.assertIsInstance(self.ajo.status, str)

    def test_set_language_preserves_translated_when_collapsing_multiple(self):
        """If any language was 'translated', the collapsed status should be 'translated'."""
        self.ajo.set_language(["zh", "vi"])
        self.ajo.status = {"zh": "translated", "vi": "untranslated"}
        self.ajo.set_language("ja")
        self.assertEqual(self.ajo.status, "translated")

    def test_set_language_preserves_doublecheck_when_collapsing_multiple(self):
        self.ajo.set_language(["zh", "vi"])
        self.ajo.status = {"zh": "doublecheck", "vi": "untranslated"}
        self.ajo.set_language("ja")
        self.assertEqual(self.ajo.status, "doublecheck")

    def test_language_history_appended_each_change(self):
        self.ajo.set_language("en")
        self.ajo.set_language("ja")
        self.assertIn("en", self.ajo.language_history)
        self.assertIn("ja", self.ajo.language_history)

    def test_language_history_no_consecutive_duplicates(self):
        self.ajo.set_language("ja")
        self.ajo.set_language("ja")
        count = sum(1 for c in self.ajo.language_history if c == "ja")
        self.assertEqual(count, 1)

    def test_initialize_lingvo_from_preferred_code(self):
        self.ajo.preferred_code = "en"
        self.ajo.initialize_lingvo()
        self.assertIsNotNone(self.ajo._lingvo)

    def test_lingvo_property_lazy_init(self):
        """Accessing .lingvo should initialize _lingvo if not yet set."""
        self.ajo.preferred_code = "ja"
        _ = self.ajo.lingvo  # trigger lazy init
        self.assertIsNotNone(self.ajo._lingvo)

    def test_set_language_uppercase_normalized(self):
        """Language codes passed as uppercase should be normalized to lowercase."""
        self.ajo.set_language("JA")
        self.assertEqual(self.ajo.preferred_code, "ja")


# ===========================================================================
# TestAjoStatusManagement
# ===========================================================================


class TestAjoStatusManagement(unittest.TestCase):
    """Test status setting and transitions (silent failure semantics)."""

    def setUp(self):
        self.ajo = Ajo()

    def test_set_status_valid_values(self):
        for status in ["inprogress", "missing", "untranslated"]:
            ajo = Ajo()
            ajo.set_status(status)
            self.assertEqual(ajo.status, status)

    def test_set_status_invalid_silently_ignored(self):
        """Invalid status should be silently ignored, not raise."""
        self.ajo.set_status("invalid_status")
        self.assertEqual(self.ajo.status, "untranslated")  # unchanged

    def test_status_translated_is_final_silently_ignored(self):
        """Trying to change away from 'translated' should be silently ignored."""
        self.ajo.set_status("translated")
        self.ajo.set_status("untranslated")
        self.assertEqual(self.ajo.status, "translated")  # unchanged

    def test_status_doublecheck_to_non_translated_silently_ignored(self):
        """Transitioning from 'doublecheck' to anything except 'translated' should be ignored."""
        self.ajo.set_status("doublecheck")
        self.ajo.set_status("inprogress")
        self.assertEqual(self.ajo.status, "doublecheck")  # unchanged

    def test_status_doublecheck_to_translated_allowed(self):
        self.ajo.set_status("doublecheck")
        self.ajo.set_status("translated")
        self.assertEqual(self.ajo.status, "translated")

    def test_set_status_translated_sets_closed_out(self):
        self.ajo.set_status("translated")
        self.assertTrue(self.ajo.closed_out)

    def test_set_status_doublecheck_sets_closed_out(self):
        self.ajo.set_status("doublecheck")
        self.assertTrue(self.ajo.closed_out)

    def test_set_status_inprogress_does_not_set_closed_out(self):
        self.ajo.set_status("inprogress")
        self.assertFalse(self.ajo.closed_out)

    def test_set_status_on_defined_multiple_silently_ignored(self):
        """set_status() on a defined multiple should do nothing (not raise)."""
        self.ajo.type = "multiple"
        self.ajo.is_defined_multiple = True
        self.ajo.status = {"zh": "untranslated"}
        self.ajo.set_status("translated")
        # Status dict should be unchanged
        self.assertIsInstance(self.ajo.status, dict)

    def test_set_defined_multiple_status(self):
        self.ajo.is_defined_multiple = True
        self.ajo.status = {}
        self.ajo.set_defined_multiple_status("zh", "translated")
        self.assertIsInstance(self.ajo.status, dict)
        self.assertEqual(self.ajo.status["zh"], "translated")

    def test_set_defined_multiple_status_invalid_raises(self):
        self.ajo.is_defined_multiple = True
        with self.assertRaises(ValueError):
            self.ajo.set_defined_multiple_status("zh", "invalid")

    def test_set_defined_multiple_status_on_non_multiple_raises(self):
        with self.assertRaises(ValueError):
            self.ajo.set_defined_multiple_status("zh", "translated")

    def test_set_defined_multiple_status_initializes_dict(self):
        """set_defined_multiple_status should coerce a non-dict status to a dict."""
        self.ajo.is_defined_multiple = True
        self.ajo.status = "untranslated"  # string
        self.ajo.set_defined_multiple_status("vi", "inprogress")
        self.assertIsInstance(self.ajo.status, dict)
        self.assertEqual(self.ajo.status["vi"], "inprogress")


# ===========================================================================
# TestAjoTyping
# ===========================================================================


class TestAjoTyping(unittest.TestCase):
    """Test post type management."""

    def setUp(self):
        self.ajo = Ajo()

    def test_set_type_single(self):
        self.ajo.set_type("single")
        self.assertEqual(self.ajo.type, "single")

    def test_set_type_multiple(self):
        self.ajo.set_type("multiple")
        self.assertEqual(self.ajo.type, "multiple")

    def test_set_type_invalid_raises(self):
        with self.assertRaises(ValueError):
            self.ajo.set_type("invalid")

    def test_type_change_to_single_resets_is_defined_multiple(self):
        self.ajo.is_defined_multiple = True
        self.ajo.set_type("single")
        self.assertFalse(self.ajo.is_defined_multiple)

    def test_type_change_to_multiple_does_not_reset_is_defined_multiple(self):
        self.ajo.is_defined_multiple = True
        self.ajo.set_type("multiple")
        self.assertTrue(self.ajo.is_defined_multiple)


# ===========================================================================
# TestAjoDefinedMultiple
# ===========================================================================


class TestAjoDefinedMultiple(unittest.TestCase):
    """Test defined multiple toggling and flag management."""

    def setUp(self):
        self.ajo = Ajo()

    def test_set_is_defined_multiple_true(self):
        self.ajo.set_is_defined_multiple(True)
        self.assertTrue(self.ajo.is_defined_multiple)

    def test_set_is_defined_multiple_false(self):
        self.ajo.is_defined_multiple = True
        self.ajo.set_is_defined_multiple(False)
        self.assertFalse(self.ajo.is_defined_multiple)

    def test_toggle_is_defined_multiple_off(self):
        self.ajo.is_defined_multiple = True
        result = self.ajo.toggle_is_defined_multiple()
        self.assertFalse(result)
        self.assertFalse(self.ajo.is_defined_multiple)

    def test_toggle_is_defined_multiple_on(self):
        self.ajo.is_defined_multiple = False
        result = self.ajo.toggle_is_defined_multiple()
        self.assertTrue(result)
        self.assertTrue(self.ajo.is_defined_multiple)


# ===========================================================================
# TestAjoSerialization
# ===========================================================================


class TestAjoSerialization(unittest.TestCase):
    """Test to_dict and from_dict, including roundtrips with real Ajo data."""

    def test_to_dict_basic_fields(self):
        ajo = Ajo()
        ajo.preferred_code = "zh"
        ajo.title = "jade pendant"
        ajo.status = "translated"

        d = ajo.to_dict()
        self.assertIsInstance(d, dict)
        self.assertEqual(d["preferred_code"], "zh")
        self.assertEqual(d["title"], "jade pendant")
        self.assertEqual(d["status"], "translated")

    def test_to_dict_excludes_private_attributes(self):
        ajo = Ajo()
        ajo.preferred_code = "en"
        d = ajo.to_dict()
        self.assertNotIn("_lingvo", d)
        self.assertNotIn("_submission", d)

    def test_to_dict_includes_all_expected_keys(self):
        expected = {
            "id",
            "created_utc",
            "author",
            "title_original",
            "title",
            "direction",
            "preferred_code",
            "language_history",
            "original_source_language_name",
            "original_target_language_name",
            "status",
            "output_post_flair_css",
            "output_post_flair_text",
            "is_identified",
            "is_long",
            "is_defined_multiple",
            "closed_out",
            "type",
            "image_hash",
            "recorded_translators",
            "notified",
            "time_delta",
            "author_messaged",
        }
        ajo = Ajo()
        d = ajo.to_dict()
        self.assertTrue(expected.issubset(d.keys()))

    def test_from_dict_basic(self):
        data = {
            "id": "abc123",
            "preferred_code": "en",
            "title": "Test",
            "status": "translated",
        }
        ajo = Ajo.from_dict(data)
        self.assertEqual(ajo.id, "abc123")
        self.assertEqual(ajo.preferred_code, "en")
        self.assertEqual(ajo.status, "translated")

    def test_from_dict_roundtrip_single(self):
        ajo1 = Ajo()
        ajo1.preferred_code = "ja"
        ajo1.title = "scan from a game"
        ajo1.is_long = True
        ajo1.status = "inprogress"

        ajo2 = Ajo.from_dict(ajo1.to_dict())
        self.assertEqual(ajo1.preferred_code, ajo2.preferred_code)
        self.assertEqual(ajo1.title, ajo2.title)
        self.assertEqual(ajo1.is_long, ajo2.is_long)
        self.assertEqual(ajo1.status, ajo2.status)

    def test_from_dict_roundtrip_multiple_status(self):
        data = {
            "preferred_code": "multiple",
            "status": {"vi": "untranslated", "zh": "untranslated"},
            "is_defined_multiple": True,
            "type": "multiple",
        }
        ajo = Ajo.from_dict(data)
        self.assertTrue(ajo.is_defined_multiple)
        self.assertIsInstance(ajo.status, dict)
        self.assertEqual(ajo.status["vi"], "untranslated")

    def test_from_dict_legacy_field_language_code_1(self):
        """Legacy 'language_code_1' field should be promoted to preferred_code."""
        data = {"language_code_1": "ja", "title": "Old format post"}
        ajo = Ajo.from_dict(data)
        self.assertEqual(ajo.preferred_code, "ja")

    def test_from_dict_legacy_field_output_oflair_css(self):
        """Legacy 'output_oflair_css' should be handled by ajo_loader normalization."""
        # The legacy rename happens in ajo_loader, not from_dict; verify the field
        # is at least not set on the Ajo when loading the modern key name
        data = {"preferred_code": "zh", "output_post_flair_css": "zh"}
        ajo = Ajo.from_dict(data)
        self.assertEqual(ajo.output_post_flair_css, "zh")

    # --- Real Ajo roundtrips ---

    def test_from_dict_real_unknown_untranslated(self):
        """Unknown language, still untranslated, has image hash."""
        data = REAL_AJOS[0]
        ajo = Ajo.from_dict(data)
        self.assertEqual(ajo.id, "1rw44gg")
        self.assertEqual(ajo.preferred_code, "unknown")
        self.assertEqual(ajo.status, "untranslated")
        self.assertFalse(ajo.closed_out)
        self.assertEqual(ajo.image_hash, "50d04c4c515551d4")
        self.assertIn("test_notified_a", ajo.notified)

    def test_from_dict_real_translated_chinese(self):
        """Chinese post marked as translated should have closed_out=True and time_delta."""
        data = REAL_AJOS[1]
        ajo = Ajo.from_dict(data)
        self.assertEqual(ajo.id, "1rvytkz")
        self.assertEqual(ajo.preferred_code, "zh")
        self.assertEqual(ajo.status, "translated")
        self.assertTrue(ajo.closed_out)
        self.assertIn("translated", ajo.time_delta)
        self.assertEqual(ajo.time_delta["translated"], 1773728764)

    def test_from_dict_real_defined_multiple(self):
        """Defined multiple (zh + vi) should load with dict status and proper history."""
        data = REAL_AJOS[2]
        ajo = Ajo.from_dict(data)
        self.assertEqual(ajo.id, "1ru6ced")
        self.assertTrue(ajo.is_defined_multiple)
        self.assertEqual(ajo.type, "multiple")
        self.assertIsInstance(ajo.status, dict)
        self.assertIn("zh", ajo.status)
        self.assertIn("vi", ajo.status)
        self.assertEqual(ajo.direction, "english_from")
        self.assertEqual(ajo.language_history, [["zh", "vi"]])

    def test_from_dict_real_non_defined_multiple(self):
        """Non-defined multiple (6 source languages) should load without dict status."""
        data = REAL_AJOS[3]
        ajo = Ajo.from_dict(data)
        self.assertEqual(ajo.id, "1rv7neu")
        self.assertFalse(ajo.is_defined_multiple)
        self.assertEqual(ajo.type, "multiple")
        self.assertEqual(ajo.status, "untranslated")
        self.assertEqual(ajo.preferred_code, "multiple")

    def test_to_dict_real_roundtrip_preserves_all_scalar_fields(self):
        """Roundtrip through to_dict/from_dict preserves key scalar fields."""
        data = REAL_AJOS[1]  # translated Chinese post
        ajo = Ajo.from_dict(data)
        d = ajo.to_dict()
        self.assertEqual(d["id"], data["id"])
        self.assertEqual(d["author"], data["author"])
        self.assertEqual(d["preferred_code"], data["preferred_code"])
        self.assertEqual(d["status"], data["status"])
        self.assertEqual(d["direction"], data["direction"])
        self.assertEqual(d["closed_out"], data["closed_out"])
        self.assertEqual(d["image_hash"], data["image_hash"])
        self.assertEqual(d["time_delta"], data["time_delta"])


# ===========================================================================
# TestAjoFromTitolo
# ===========================================================================


class TestAjoFromTitolo(unittest.TestCase):
    """Test Ajo.from_titolo construction from Titolo objects."""

    @staticmethod
    def _make_submission(sub_id="abc123", title="test", is_self=True):
        sub = MagicMock()
        sub.id = sub_id
        sub.title = title
        sub.created_utc = 1773728507
        sub.author = MagicMock()
        sub.author.__str__ = lambda s: "testuser"
        sub.is_self = is_self
        return sub

    def test_from_titolo_single_language(self):
        """Single-language Titolo should produce a type='single' Ajo."""
        titolo = make_titolo(
            source_codes=[("Chinese", "zh", "zho")],
            target_codes=[("English", "en", "eng")],
            final_code="zh",
            final_text="Chinese",
            direction="english_to",
            title_original="[Mandarin > English] jade pendant",
            title_actual="jade pendant",
        )
        ajo = Ajo.from_titolo(titolo)
        self.assertEqual(ajo.type, "single")
        self.assertFalse(ajo.is_defined_multiple)
        self.assertEqual(ajo.status, "untranslated")
        self.assertEqual(ajo.direction, "english_to")

    def test_from_titolo_single_history_uses_preferred_code_not_generic_bucket(self):
        """Single-language history should store the language code, not CSS buckets."""
        titolo = make_titolo(
            source_codes=[("English", "en", "eng")],
            target_codes=[("South Levantine Arabic", None, "ajp")],
            final_code="generic",
            final_text="South Levantine Arabic",
            direction="english_from",
            title_original="[English > Levantine Arabic] one sentence",
            title_actual="one sentence",
        )
        ajo = Ajo.from_titolo(titolo)
        self.assertEqual(ajo.preferred_code, "ajp")
        self.assertEqual(ajo.language_history, ["ajp"])

    def test_reset_single_history_uses_preferred_code_not_generic_bucket(self):
        """Reset should use the same history-code logic as initial construction."""
        ajo = Ajo()
        ajo.language_history = ["generic"]
        titolo = make_titolo(
            source_codes=[("English", "en", "eng")],
            target_codes=[("South Levantine Arabic", None, "ajp")],
            final_code="generic",
            final_text="South Levantine Arabic",
            direction="english_from",
        )
        ajo._reset_to_titolo(titolo)
        self.assertEqual(ajo.preferred_code, "ajp")
        self.assertEqual(ajo.language_history, ["ajp"])

    def test_from_titolo_single_sets_title(self):
        titolo = make_titolo(
            source_codes=[("Japanese", "ja", "jpn")],
            target_codes=[("English", "en", "eng")],
            final_code="ja",
            final_text="Japanese",
            title_actual="scan from a game",
        )
        ajo = Ajo.from_titolo(titolo)
        self.assertEqual(ajo.title, "scan from a game")

    def test_from_titolo_with_submission_sets_id_author_utc(self):
        titolo = make_titolo(
            source_codes=[("Japanese", "ja", "jpn")],
            target_codes=[("English", "en", "eng")],
            final_code="ja",
            final_text="Japanese",
        )
        sub = self._make_submission(sub_id="1rw6ll7")
        ajo = Ajo.from_titolo(titolo, submission=sub)
        self.assertEqual(ajo.id, "1rw6ll7")
        self.assertEqual(ajo.created_utc, 1773728507)
        self.assertEqual(ajo.author, "testuser")

    def test_from_titolo_defined_multiple_two_non_english_targets(self):
        """Two non-English targets should create a defined multiple."""
        titolo = make_titolo(
            source_codes=[("English", "en", "eng")],
            target_codes=[("Chinese", "zh", "zho"), ("Vietnamese", "vi", "vie")],
            final_code="multiple",
            final_text="Multiple Languages",
            direction="english_from",
        )
        ajo = Ajo.from_titolo(titolo)
        self.assertEqual(ajo.type, "multiple")
        self.assertTrue(ajo.is_defined_multiple)
        self.assertIsInstance(ajo.status, dict)
        self.assertIn("zh", ajo.status)
        self.assertIn("vi", ajo.status)

    def test_from_titolo_non_defined_multiple_code(self):
        """final_code='multiple' with one non-English target should be non-defined multiple."""
        titolo = make_titolo(
            source_codes=[("Zulu", None, "zul"), ("Arabic", "ar", "ara")],
            target_codes=[("English", "en", "eng")],
            final_code="multiple",
            final_text="Multiple Languages",
            direction="english_to",
        )
        ajo = Ajo.from_titolo(titolo)
        self.assertEqual(ajo.type, "multiple")
        self.assertFalse(ajo.is_defined_multiple)

    def test_from_titolo_unknown_language(self):
        titolo = make_titolo(
            source_codes=[("Unknown", None, None)],
            target_codes=[("English", "en", "eng")],
            final_code="unknown",
            final_text="Unknown",
        )
        ajo = Ajo.from_titolo(titolo)
        self.assertEqual(ajo.type, "single")
        self.assertEqual(ajo.status, "untranslated")

    def test_from_titolo_no_submission_leaves_id_none(self):
        titolo = make_titolo(
            source_codes=[("Japanese", "ja", "jpn")],
            target_codes=[("English", "en", "eng")],
            final_code="ja",
            final_text="Japanese",
        )
        ajo = Ajo.from_titolo(titolo)
        self.assertIsNone(ajo.id)

    def test_from_titolo_sets_source_and_target_language_names(self):
        titolo = make_titolo(
            source_codes=[("Chinese", "zh", "zho")],
            target_codes=[("English", "en", "eng")],
            final_code="zh",
            final_text="Chinese",
        )
        ajo = Ajo.from_titolo(titolo)
        self.assertIsNotNone(ajo.original_source_language_name)
        self.assertIsNotNone(ajo.original_target_language_name)
        self.assertEqual(len(ajo.original_source_language_name), 1)
        self.assertEqual(len(ajo.original_target_language_name), 1)

    def test_from_titolo_deleted_author(self):
        """Deleted author (None) should be stored as '[deleted]'."""
        titolo = make_titolo(
            source_codes=[("Japanese", "ja", "jpn")],
            target_codes=[("English", "en", "eng")],
            final_code="ja",
            final_text="Japanese",
        )
        sub = self._make_submission()
        sub.author = None
        ajo = Ajo.from_titolo(titolo, submission=sub)
        self.assertEqual(ajo.author, "[deleted]")


# ===========================================================================
# TestAjoMiscMethods
# ===========================================================================


class TestAjoMiscMethods(unittest.TestCase):
    """Test miscellaneous Ajo methods."""

    def setUp(self):
        self.ajo = Ajo()

    def test_set_is_long_true(self):
        self.ajo.set_is_long(True)
        self.assertTrue(self.ajo.is_long)

    def test_set_is_long_false(self):
        self.ajo.is_long = True
        self.ajo.set_is_long(False)
        self.assertFalse(self.ajo.is_long)

    def test_set_closed_out(self):
        self.ajo.set_closed_out(True)
        self.assertTrue(self.ajo.closed_out)

    def test_set_time_records_first_occurrence(self):
        self.ajo.set_time("translated", 1000)
        self.assertEqual(self.ajo.time_delta["translated"], 1000)

    def test_set_time_does_not_overwrite(self):
        """set_time should only record the first call for a given status."""
        self.ajo.set_time("translated", 1000)
        self.ajo.set_time("translated", 2000)
        self.assertEqual(self.ajo.time_delta["translated"], 1000)

    def test_set_time_multiple_statuses(self):
        self.ajo.set_time("inprogress", 100)
        self.ajo.set_time("translated", 200)
        self.assertEqual(self.ajo.time_delta["inprogress"], 100)
        self.assertEqual(self.ajo.time_delta["translated"], 200)

    def test_set_author_messaged_true(self):
        self.ajo.set_author_messaged(True)
        self.assertTrue(self.ajo.author_messaged)

    def test_set_author_messaged_false(self):
        self.ajo.author_messaged = True
        self.ajo.set_author_messaged(False)
        self.assertFalse(self.ajo.author_messaged)

    def test_add_translators_appends(self):
        self.ajo.add_translators("user1")
        self.ajo.add_translators("user2")
        self.assertIn("user1", self.ajo.recorded_translators)
        self.assertIn("user2", self.ajo.recorded_translators)

    def test_add_translators_no_duplicates(self):
        self.ajo.add_translators("user1")
        self.ajo.add_translators("user1")
        self.assertEqual(self.ajo.recorded_translators.count("user1"), 1)

    def test_add_notified_appends(self):
        self.ajo.add_notified(["alpha", "beta"])
        self.assertIn("alpha", self.ajo.notified)
        self.assertIn("beta", self.ajo.notified)

    def test_add_notified_no_duplicates(self):
        self.ajo.add_notified(["alpha"])
        self.ajo.add_notified(["alpha"])
        self.assertEqual(self.ajo.notified.count("alpha"), 1)

    def test_add_notified_empty_list(self):
        self.ajo.add_notified([])
        self.assertEqual(self.ajo.notified, [])


# ===========================================================================
# TestAjoCache
# ===========================================================================


class TestAjoCache(unittest.TestCase):
    """Test submission caching functionality."""

    def test_clear_submission_cache_returns_cached_value(self):
        ajo = Ajo()
        mock_sub = MagicMock()
        ajo._submission = mock_sub
        returned = ajo.clear_submission_cache()
        self.assertEqual(returned, mock_sub)
        self.assertIsNone(ajo._submission)

    def test_clear_submission_cache_when_empty(self):
        ajo = Ajo()
        returned = ajo.clear_submission_cache()
        self.assertIsNone(returned)
        self.assertIsNone(ajo._submission)

    def test_restore_submission_cache(self):
        ajo = Ajo()
        mock_sub = MagicMock()
        ajo.restore_submission_cache(mock_sub)
        self.assertEqual(ajo._submission, mock_sub)

    def test_clear_then_restore_roundtrip(self):
        ajo = Ajo()
        mock_sub = MagicMock()
        ajo._submission = mock_sub
        cached = ajo.clear_submission_cache()
        self.assertIsNone(ajo._submission)
        ajo.restore_submission_cache(cached)
        self.assertEqual(ajo._submission, mock_sub)


# ===========================================================================
# TestUtilityFunctions
# ===========================================================================


class TestUtilityFunctions(unittest.TestCase):
    """Test module-level utility functions."""

    # --- _normalize_lang_field ---

    def test_normalize_lingvo_list_passthrough(self):
        lingvo = make_lingvo("English", "en", "eng")
        result = _normalize_lang_field([lingvo])
        self.assertIsInstance(result, list)
        self.assertIsInstance(result[0], Lingvo)

    def test_normalize_string_single(self):
        result = _normalize_lang_field("English")
        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 1)
        self.assertIsInstance(result[0], Lingvo)

    def test_normalize_string_list(self):
        result = _normalize_lang_field(["English", "Japanese"])
        self.assertEqual(len(result), 2)
        self.assertTrue(all(isinstance(x, Lingvo) for x in result))

    def test_normalize_none_returns_empty(self):
        self.assertEqual(_normalize_lang_field(None), [])

    def test_normalize_empty_string_returns_empty(self):
        self.assertEqual(_normalize_lang_field(""), [])

    def test_normalize_empty_list_returns_empty(self):
        self.assertEqual(_normalize_lang_field([]), [])

    def test_normalize_mixed_list_skips_non_convertible(self):
        """Non-string, non-Lingvo items in a list should be silently skipped."""
        lingvo = make_lingvo("English", "en")
        result = _normalize_lang_field([lingvo, 42, None])
        # Only the Lingvo object should survive
        self.assertEqual(len(result), 1)
        self.assertIsInstance(result[0], Lingvo)

    # --- _convert_to_dict ---

    def test_convert_to_dict_python_literal(self):
        result = _convert_to_dict("{'key': 'value'}")
        self.assertEqual(result["key"], "value")

    def test_convert_to_dict_json(self):
        import json

        result = _convert_to_dict(json.dumps({"key": "value"}))
        self.assertEqual(result["key"], "value")

    def test_convert_to_dict_invalid_raises(self):
        with self.assertRaises(ValueError):
            _convert_to_dict("not a dict at all")

    def test_convert_to_dict_nested(self):
        import json

        data = {"outer": {"inner": [1, 2, 3]}}
        result = _convert_to_dict(json.dumps(data))
        self.assertEqual(result["outer"]["inner"], [1, 2, 3])

    # --- parse_ajo_data ---

    def test_parse_ajo_data_json(self):
        import json

        data = {"id": "123", "status": "translated"}
        result = parse_ajo_data(json.dumps(data))
        self.assertEqual(result["id"], "123")

    def test_parse_ajo_data_literal(self):
        result = parse_ajo_data("{'id': '123', 'status': 'translated'}")
        self.assertEqual(result["id"], "123")

    def test_parse_ajo_data_invalid_raises(self):
        with self.assertRaises(Exception):
            parse_ajo_data("this is not parseable !!!")


# ===========================================================================
# TestAjoDictFormatting
# ===========================================================================


class TestAjoDictFormatting(unittest.TestCase):
    """Test flair formatting for defined multiple posts."""

    def test_flair_formatter_single_translated(self):
        result = ajo_defined_multiple_flair_former({"en": "translated"})
        self.assertIn("[", result)
        self.assertIn("]", result)

    def test_flair_formatter_multiple_languages(self):
        result = ajo_defined_multiple_flair_former(
            {"zh": "translated", "vi": "inprogress", "ko": "untranslated"}
        )
        self.assertIn("[", result)
        self.assertIn("]", result)

    def test_flair_formatter_all_untranslated(self):
        result = ajo_defined_multiple_flair_former(
            {"zh": "untranslated", "vi": "untranslated"}
        )
        self.assertIsInstance(result, str)

    def test_flair_formatter_empty_dict(self):
        """Empty dict should not raise."""
        try:
            result = ajo_defined_multiple_flair_former({})
            self.assertIsInstance(result, (str, type(None)))
        except Exception as e:
            self.fail(f"ajo_defined_multiple_flair_former raised with empty dict: {e}")


# ===========================================================================
# Runner
# ===========================================================================


def run_all_tests():
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    test_classes = [
        TestAjoInitialization,
        TestAjoImmutableProperties,
        TestAjoLanguageManagement,
        TestAjoStatusManagement,
        TestAjoTyping,
        TestAjoDefinedMultiple,
        TestAjoSerialization,
        TestAjoFromTitolo,
        TestAjoMiscMethods,
        TestAjoCache,
        TestUtilityFunctions,
        TestAjoDictFormatting,
    ]
    for cls in test_classes:
        suite.addTests(loader.loadTestsFromTestCase(cls))
    runner = unittest.TextTestRunner(verbosity=2)
    return runner.run(suite)


if __name__ == "__main__":
    print("=" * 70)
    print("Ajo Module Test Suite")
    print("=" * 70)
    run_all_tests()
