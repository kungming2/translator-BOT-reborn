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
    Ajo, parse_ajo_data, _normalize_lang_field,
    ajo_defined_multiple_flair_former, _convert_to_dict
)
from languages import Lingvo


class TestAjoInitialization(unittest.TestCase):
    """Test Ajo class initialization and basic properties."""

    def setUp(self):
        """Create a fresh Ajo for each test."""
        self.ajo = Ajo()

    def test_ajo_creation(self):
        """Test creating a basic Ajo object."""
        self.assertIsNotNone(self.ajo)
        self.assertIsNone(self.ajo.id)
        self.assertEqual(self.ajo.status, "untranslated")

    def test_ajo_default_values(self):
        """Test Ajo has correct default values."""
        self.assertIsNone(self.ajo.title_original)
        self.assertIsNone(self.ajo.title)
        self.assertIsNone(self.ajo.direction)
        self.assertFalse(self.ajo.is_identified)
        self.assertFalse(self.ajo.is_long)
        self.assertEqual(self.ajo.type, "single")
        self.assertFalse(self.ajo.is_defined_multiple)
        self.assertFalse(self.ajo.closed_out)

    def test_ajo_repr(self):
        """Test Ajo string representation."""
        self.ajo.preferred_code = "en"
        repr_str = repr(self.ajo)
        self.assertIn("Ajo", repr_str)

    def test_ajo_equality(self):
        """Test two Ajos with same data are equal."""
        ajo1 = Ajo()
        ajo1.preferred_code = "en"
        ajo1.status = "translated"

        ajo2 = Ajo()
        ajo2.preferred_code = "en"
        ajo2.status = "translated"

        self.assertEqual(ajo1, ajo2)

    def test_ajo_inequality(self):
        """Test two Ajos with different data are not equal."""
        ajo1 = Ajo()
        ajo1.preferred_code = "en"

        ajo2 = Ajo()
        ajo2.preferred_code = "ja"

        self.assertNotEqual(ajo1, ajo2)


class TestAjoImmutableProperties(unittest.TestCase):
    """Test immutable properties of Ajo."""

    def test_id_immutable(self):
        """Test that ID cannot be changed once set."""
        ajo = Ajo()
        ajo.id = "test123"
        with self.assertRaises(AttributeError):
            ajo.id = "test456"

    def test_created_utc_immutable(self):
        """Test that created_utc cannot be changed once set."""
        ajo = Ajo()
        ajo.created_utc = 1234567890
        with self.assertRaises(AttributeError):
            ajo.created_utc = 9876543210

    def test_author_immutable(self):
        """Test that author cannot be changed once set."""
        ajo = Ajo()
        ajo.author = "user1"
        with self.assertRaises(AttributeError):
            ajo.author = "user2"


class TestAjoLanguageManagement(unittest.TestCase):
    """Test language setting and retrieval."""

    def setUp(self):
        self.ajo = Ajo()

    def test_set_language_single(self):
        """Test setting a single language by code."""
        self.ajo.set_language("en")
        self.assertEqual(self.ajo.preferred_code, "en")
        self.assertTrue(self.ajo.is_identified)

    def test_set_language_with_lingvo(self):
        """Test setting language with Lingvo object."""
        lingvo = Lingvo(name="English", language_code_1="en", language_code_3="eng")
        self.ajo.set_language(lingvo)
        self.assertEqual(self.ajo.preferred_code, "en")

    def test_set_language_not_identified(self):
        """Test setting language with is_identified=False."""
        self.ajo.set_language("fr", is_identified=False)
        self.assertFalse(self.ajo.is_identified)

    def test_set_language_multiple(self):
        """Test setting multiple languages as list."""
        self.ajo.set_language(["en", "ja", "ko"])
        self.assertEqual(self.ajo.preferred_code, "multiple")
        self.assertTrue(self.ajo.is_defined_multiple)
        self.assertIsInstance(self.ajo.status, dict)

    def test_language_history_tracking(self):
        """Test that language changes are tracked in history."""
        self.ajo.set_language("en")
        self.ajo.set_language("ja")
        self.assertTrue(len(self.ajo.language_history) >= 2)

    def test_initialize_lingvo(self):
        """Test lingvo initialization from preferred_code."""
        self.ajo.preferred_code = "en"
        self.ajo.initialize_lingvo()
        self.assertIsNotNone(self.ajo._lingvo)


class TestAjoStatusManagement(unittest.TestCase):
    """Test status setting and transitions."""

    def setUp(self):
        self.ajo = Ajo()

    def test_set_status_valid(self):
        """Test setting valid status values."""
        for status in ["translated", "doublecheck", "inprogress", "missing", "untranslated"]:
            ajo = Ajo()
            ajo.set_status(status)
            self.assertEqual(ajo.status, status)

    def test_set_status_invalid(self):
        """Test that invalid status raises error."""
        with self.assertRaises(ValueError):
            self.ajo.set_status("invalid_status")

    def test_status_translated_is_final(self):
        """Test that 'translated' status cannot be changed."""
        self.ajo.set_status("translated")
        with self.assertRaises(ValueError):
            self.ajo.set_status("untranslated")

    def test_status_doublecheck_transition(self):
        """Test doublecheck can only transition to translated."""
        self.ajo.set_status("doublecheck")
        with self.assertRaises(ValueError):
            self.ajo.set_status("inprogress")

    def test_status_doublecheck_to_translated(self):
        """Test valid transition from doublecheck to translated."""
        self.ajo.set_status("doublecheck")
        self.ajo.set_status("translated")
        self.assertEqual(self.ajo.status, "translated")

    def test_closed_out_on_translated(self):
        """Test closed_out is set when status is translated."""
        self.ajo.set_status("translated")
        self.assertTrue(self.ajo.closed_out)

    def test_closed_out_on_doublecheck(self):
        """Test closed_out is set when status is doublecheck."""
        self.ajo.set_status("doublecheck")
        self.assertTrue(self.ajo.closed_out)

    def test_defined_multiple_status_error(self):
        """Test set_status raises error on defined multiple."""
        self.ajo.is_defined_multiple = True
        with self.assertRaises(ValueError):
            self.ajo.set_status("translated")

    def test_set_defined_multiple_status(self):
        """Test setting status for specific language in multiple."""
        self.ajo.is_defined_multiple = True
        self.ajo.set_defined_multiple_status("en", "translated")
        assert isinstance(self.ajo.status, dict)
        self.assertEqual(self.ajo.status.get("en"), "translated")

    def test_set_defined_multiple_status_invalid(self):
        """Test invalid status in defined multiple raises error."""
        self.ajo.is_defined_multiple = True
        with self.assertRaises(ValueError):
            self.ajo.set_defined_multiple_status("en", "invalid")

    def test_set_defined_multiple_status_not_multiple(self):
        """Test set_defined_multiple_status fails on non-multiple."""
        with self.assertRaises(ValueError):
            self.ajo.set_defined_multiple_status("en", "translated")


class TestAjoTyping(unittest.TestCase):
    """Test post type management."""

    def setUp(self):
        self.ajo = Ajo()

    def test_set_type_single(self):
        """Test setting type to single."""
        self.ajo.set_type("single")
        self.assertEqual(self.ajo.type, "single")

    def test_set_type_multiple(self):
        """Test setting type to multiple."""
        self.ajo.set_type("multiple")
        self.assertEqual(self.ajo.type, "multiple")

    def test_set_type_invalid(self):
        """Test invalid type raises error."""
        with self.assertRaises(ValueError):
            self.ajo.set_type("invalid")

    def test_type_change_resets_is_defined_multiple(self):
        """Test changing type to single resets is_defined_multiple."""
        self.ajo.is_defined_multiple = True
        self.ajo.set_type("single")
        self.assertFalse(self.ajo.is_defined_multiple)


class TestAjoDefinedMultiple(unittest.TestCase):
    """Test defined multiple functionality."""

    def setUp(self):
        self.ajo = Ajo()

    def test_set_is_defined_multiple(self):
        """Test setting is_defined_multiple."""
        self.ajo.set_is_defined_multiple(True)
        self.assertTrue(self.ajo.is_defined_multiple)

    def test_toggle_is_defined_multiple(self):
        """Test toggling is_defined_multiple."""
        initial = self.ajo.is_defined_multiple
        result = self.ajo.toggle_is_defined_multiple()
        self.assertEqual(result, not initial)
        self.assertEqual(self.ajo.is_defined_multiple, not initial)


class TestAjoSerialization(unittest.TestCase):
    """Test to_dict and from_dict conversion."""

    def test_to_dict_basic(self):
        """Test basic serialization to dict."""
        ajo = Ajo()
        ajo.preferred_code = "en"
        ajo.title = "Test Title"
        ajo.status = "translated"

        ajo_dict = ajo.to_dict()
        self.assertIsInstance(ajo_dict, dict)
        self.assertEqual(ajo_dict["preferred_code"], "en")
        self.assertEqual(ajo_dict["title"], "Test Title")

    def test_to_dict_excludes_internal(self):
        """Test to_dict excludes internal properties."""
        ajo = Ajo()
        ajo.preferred_code = "en"
        ajo_dict = ajo.to_dict()
        self.assertNotIn("_lingvo", ajo_dict)
        self.assertNotIn("_submission", ajo_dict)

    def test_from_dict_basic(self):
        """Test basic deserialization from dict."""
        data = {
            "id": "abc123",
            "preferred_code": "en",
            "title": "Test",
            "status": "translated"
        }
        ajo = Ajo.from_dict(data)
        self.assertEqual(ajo.id, "abc123")
        self.assertEqual(ajo.preferred_code, "en")
        self.assertEqual(ajo.title, "Test")

    def test_from_dict_roundtrip(self):
        """Test serialization and deserialization roundtrip."""
        ajo1 = Ajo()
        ajo1.preferred_code = "ja"
        ajo1.title = "Japanese Post"
        ajo1.status = "inprogress"
        ajo1.is_long = True

        data = ajo1.to_dict()
        ajo2 = Ajo.from_dict(data)

        self.assertEqual(ajo1.preferred_code, ajo2.preferred_code)
        self.assertEqual(ajo1.title, ajo2.title)
        self.assertEqual(ajo1.is_long, ajo2.is_long)

    def test_from_dict_backward_compat(self):
        """Test from_dict handles legacy field names."""
        data = {
            "language_code_1": "en",
            "title": "Test"
        }
        ajo = Ajo.from_dict(data)
        self.assertIsNotNone(ajo)

    def test_from_dict_multiple_status(self):
        """Test from_dict with multiple language status dict."""
        data = {
            "preferred_code": "multiple",
            "status": {"en": "translated", "ja": "inprogress"},
            "is_defined_multiple": True
        }
        ajo = Ajo.from_dict(data)
        self.assertTrue(ajo.is_defined_multiple)
        self.assertIsInstance(ajo.status, dict)


class TestAjoMiscMethods(unittest.TestCase):
    """Test miscellaneous Ajo methods."""

    def setUp(self):
        self.ajo = Ajo()

    def test_set_is_long(self):
        """Test setting is_long flag."""
        self.ajo.set_is_long(True)
        self.assertTrue(self.ajo.is_long)

    def test_set_time(self):
        """Test recording status change times."""
        timestamp = 1234567890
        self.ajo.set_time("translated", timestamp)
        self.assertEqual(self.ajo.time_delta.get("translated"), timestamp)

    def test_set_time_only_first(self):
        """Test time_delta only records first occurrence."""
        self.ajo.set_time("translated", 1000)
        self.ajo.set_time("translated", 2000)
        self.assertEqual(self.ajo.time_delta["translated"], 1000)

    def test_set_author_messaged(self):
        """Test setting author_messaged flag."""
        self.ajo.set_author_messaged(True)
        self.assertTrue(self.ajo.author_messaged)

    def test_add_translators(self):
        """Test adding translator names."""
        self.ajo.add_translators("user1")
        self.ajo.add_translators("user2")
        self.assertIn("user1", self.ajo.recorded_translators)
        self.assertIn("user2", self.ajo.recorded_translators)

    def test_add_translators_no_duplicates(self):
        """Test duplicate translator names not added."""
        self.ajo.add_translators("user1")
        self.ajo.add_translators("user1")
        self.assertEqual(len(self.ajo.recorded_translators), 1)

    def test_add_notified(self):
        """Test adding notified users."""
        self.ajo.add_notified(["user1", "user2"])
        self.assertIn("user1", self.ajo.notified)
        self.assertIn("user2", self.ajo.notified)

    def test_add_notified_no_duplicates(self):
        """Test duplicate notified users not added."""
        self.ajo.add_notified(["user1"])
        self.ajo.add_notified(["user1"])
        self.assertEqual(len(self.ajo.notified), 1)


class TestAjoCache(unittest.TestCase):
    """Test submission caching functionality."""

    def test_clear_submission_cache(self):
        """Test clearing submission cache."""
        ajo = Ajo()
        mock_submission = MagicMock()
        ajo._submission = mock_submission

        cleared = ajo.clear_submission_cache()
        self.assertEqual(cleared, mock_submission)
        self.assertIsNone(ajo._submission)

    def test_restore_submission_cache(self):
        """Test restoring submission cache."""
        ajo = Ajo()
        mock_submission = MagicMock()
        ajo.restore_submission_cache(mock_submission)
        self.assertEqual(ajo._submission, mock_submission)


class TestUtilityFunctions(unittest.TestCase):
    """Test module-level utility functions."""

    def test_normalize_lang_field_lingvo_list(self):
        """Test normalize with Lingvo list."""
        lingvo = Lingvo(name="English", language_code_1="en")
        result = _normalize_lang_field([lingvo])
        self.assertIsInstance(result, list)
        self.assertIsInstance(result[0], Lingvo)

    def test_normalize_lang_field_string(self):
        """Test normalize with string."""
        result = _normalize_lang_field("English")
        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 1)
        self.assertIsInstance(result[0], Lingvo)

    def test_normalize_lang_field_string_list(self):
        """Test normalize with string list."""
        result = _normalize_lang_field(["English", "Japanese"])
        self.assertEqual(len(result), 2)
        self.assertTrue(all(isinstance(x, Lingvo) for x in result))

    def test_normalize_lang_field_none(self):
        """Test normalize with None."""
        result = _normalize_lang_field(None)
        self.assertEqual(result, [])

    def test_convert_to_dict_python_dict(self):
        """Test _convert_to_dict with Python dict string."""
        input_str = "{'key': 'value'}"
        result = _convert_to_dict(input_str)
        self.assertEqual(result["key"], "value")

    def test_convert_to_dict_json(self):
        """Test _convert_to_dict with JSON string."""
        import json
        data = {"key": "value"}
        input_str = json.dumps(data)
        result = _convert_to_dict(input_str)
        self.assertEqual(result["key"], "value")

    def test_convert_to_dict_invalid(self):
        """Test _convert_to_dict with invalid input."""
        with self.assertRaises(ValueError):
            _convert_to_dict("not a dict or json")

    def test_parse_ajo_data_json(self):
        """Test parse_ajo_data with JSON."""
        import json
        data = {"id": "123", "status": "translated"}
        json_str = json.dumps(data)
        result = parse_ajo_data(json_str)
        self.assertEqual(result["id"], "123")

    def test_parse_ajo_data_literal(self):
        """Test parse_ajo_data with Python literal."""
        literal = "{'id': '123', 'status': 'translated'}"
        result = parse_ajo_data(literal)
        self.assertEqual(result["id"], "123")


class TestAjoDictFormatting(unittest.TestCase):
    """Test flair formatting for defined multiples."""

    def test_flair_formatter_single_lang(self):
        """Test flair formatter with single language."""
        flair_dict = {"en": "translated"}
        result = ajo_defined_multiple_flair_former(flair_dict)
        self.assertIn("[", result)
        self.assertIn("]", result)

    def test_flair_formatter_multiple_langs(self):
        """Test flair formatter with multiple languages."""
        flair_dict = {"en": "translated", "ja": "inprogress", "ko": "missing"}
        result = ajo_defined_multiple_flair_former(flair_dict)
        self.assertIn("[", result)
        self.assertIn("]", result)
        self.assertIn("EN", result)


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
        TestAjoInitialization,
        TestAjoImmutableProperties,
        TestAjoLanguageManagement,
        TestAjoStatusManagement,
        TestAjoTyping,
        TestAjoDefinedMultiple,
        TestAjoSerialization,
        TestAjoMiscMethods,
        TestAjoCache,
        TestUtilityFunctions,
        TestAjoDictFormatting,
    ]

    for test_class in test_classes:
        suite.addTests(loader.loadTestsFromTestCase(test_class))

    runner = unittest.TextTestRunner(verbosity=2)
    return runner.run(suite)


if __name__ == "__main__":
    print("=" * 70)
    print("Ajo Module Test Suite")
    print("=" * 70)
    run_all_tests()
