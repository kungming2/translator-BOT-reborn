#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
Test suite for title_handling.py, titolo.py, and title_ai.py.

Covers:
  - Titolo class construction and field defaults
  - main_posts_filter(): pass/fail codes (1, 1A, 1B, 2, EE-style)
  - process_title(): language extraction, direction, flair from real titles
  - Multiple-language posts: defined multiple, general multiple, preferred_code
  - English-only posts via is_english_only()
  - _determine_title_direction() directly
  - extract_lingvos_from_text()
  - AI fallback path via mocked title_ai_parser
"""

import unittest
from collections.abc import Callable
from typing import Any
from unittest.mock import MagicMock, patch

from models.titolo import Titolo
# noinspection PyProtectedMember
from title.title_handling import (_determine_title_direction,
                                  extract_lingvos_from_text, is_english_only,
                                  main_posts_filter, process_title)

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


def _codes(lingvo_list: list) -> list[str]:
    """Return preferred_codes from a list of Lingvo objects."""
    return [lng.preferred_code for lng in lingvo_list]


def _names(lingvo_list: list) -> list[str]:
    """Return names from a list of Lingvo objects."""
    return [lng.name for lng in lingvo_list]


# ---------------------------------------------------------------------------
# Titolo class
# ---------------------------------------------------------------------------


class TestTitoloDefaults(unittest.TestCase):
    """Titolo initialises with correct empty/None defaults."""

    def test_source_is_empty_list(self) -> None:
        titolo = Titolo()
        self.assertEqual(titolo.source, [])

    def test_target_is_empty_list(self) -> None:
        titolo = Titolo()
        self.assertEqual(titolo.target, [])

    def test_final_code_is_none(self) -> None:
        titolo = Titolo()
        self.assertIsNone(titolo.final_code)

    def test_final_text_is_none(self) -> None:
        titolo = Titolo()
        self.assertIsNone(titolo.final_text)

    def test_direction_is_none(self) -> None:
        titolo = Titolo()
        self.assertIsNone(titolo.direction)

    def test_ai_assessed_is_false(self) -> None:
        titolo = Titolo()
        self.assertFalse(titolo.ai_assessed)

    def test_notify_languages_is_empty_list(self) -> None:
        titolo = Titolo()
        self.assertEqual(titolo.notify_languages, [])

    def test_final_code_assignment(self) -> None:
        titolo = Titolo()
        titolo.final_code = "fr"
        self.assertEqual(titolo.final_code, "fr")

    def test_final_text_assignment(self) -> None:
        titolo = Titolo()
        titolo.final_text = "French"
        self.assertEqual(titolo.final_text, "French")

    def test_repr_contains_arrow(self) -> None:
        titolo = Titolo()
        self.assertIn(">", repr(titolo))

    def test_str_contains_field_names(self) -> None:
        titolo = Titolo()
        rendered = str(titolo)
        for field in ("source", "target", "final_code", "direction"):
            self.assertIn(field, rendered)


# ---------------------------------------------------------------------------
# main_posts_filter()
# ---------------------------------------------------------------------------


class TestMainPostsFilterPasses(unittest.TestCase):
    """Titles that should pass the filter."""

    @_skip_if_no_data
    def test_bracketed_arrow_format_passes(self) -> None:
        ok, title, reason = main_posts_filter("Vietnamese > English")
        self.assertTrue(ok)
        self.assertIsNone(reason)

    @_skip_if_no_data
    def test_standard_bracket_format_passes(self) -> None:
        ok, title, reason = main_posts_filter(
            "[Japanese > English] silk embroidered panels"
        )
        self.assertTrue(ok)
        self.assertIsNone(reason)

    @_skip_if_no_data
    def test_unknown_bracket_format_passes(self) -> None:
        ok, title, reason = main_posts_filter("[unknown > English] some text here")
        self.assertTrue(ok)
        self.assertIsNone(reason)

    @_skip_if_no_data
    def test_arrow_format_with_description_passes(self) -> None:
        ok, title, reason = main_posts_filter(
            "Japanese > English Still from Kurosawa's Idiot"
        )
        self.assertTrue(ok)
        self.assertIsNone(reason)


class TestMainPostsFilterFailCode1(unittest.TestCase):
    """Titles with no recognisable language keywords — code '1'.

    Per FILTER_REASONS: 'Missing required keywords.'
    """

    @_skip_if_no_data
    def test_generic_request_no_language(self) -> None:
        _, _, reason = main_posts_filter("Can someone please translate?")
        self.assertEqual(reason, "1")

    @_skip_if_no_data
    def test_tattoo_no_language(self) -> None:
        _, _, reason = main_posts_filter("can someone translate this tattoo please.")
        self.assertEqual(reason, "1")

    @_skip_if_no_data
    def test_what_does_this_say(self) -> None:
        _, _, reason = main_posts_filter("What does this say? Please help a guy out!")
        self.assertEqual(reason, "1")

    @_skip_if_no_data
    def test_completely_off_topic(self) -> None:
        _, _, reason = main_posts_filter("How do I read this tape measure?")
        self.assertEqual(reason, "1")

    @_skip_if_no_data
    def test_single_word_translate(self) -> None:
        _, _, reason = main_posts_filter("Translate")
        self.assertEqual(reason, "1")

    @_skip_if_no_data
    def test_30_year_old_tattoo(self) -> None:
        _, _, reason = main_posts_filter("30 year old tattoo")
        self.assertEqual(reason, "1")

    @_skip_if_no_data
    def test_translation_please(self) -> None:
        _, _, reason = main_posts_filter("Translation please?")
        self.assertEqual(reason, "1")

    @_skip_if_no_data
    def test_freelance_rates_no_language_pair(self) -> None:
        _, _, reason = main_posts_filter(
            "What are the usual freelance rates for translators hiring "
            "(Spanish, Portuguese, French, German, Chinese, Japanese, etc.)?"
        )
        self.assertEqual(reason, "1")

    @_skip_if_no_data
    def test_kuwait_wall_no_language(self) -> None:
        _, _, reason = main_posts_filter(
            "I went to Kuwait and got a picture of this on the wall at the mall. "
            "Can anyone tell me what is says? Google lens seems to struggle with brick lines."
        )
        self.assertEqual(reason, "1")

    @_skip_if_no_data
    def test_looking_for_cartoons_to_improve_english(self) -> None:
        _, _, reason = main_posts_filter(
            "Looking for cartoons or anime to improve my English – any suggestions?"
        )
        self.assertEqual(reason, "1")

    @_skip_if_no_data
    def test_old_photo_german_no_direction(self) -> None:
        _, _, reason = main_posts_filter("Old photo (German)")
        self.assertEqual(reason, "1")

    @_skip_if_no_data
    def test_how_to_translate_horse_eye(self) -> None:
        _, _, reason = main_posts_filter('How to translate "horse eye"')
        self.assertEqual(reason, "1")

    @_skip_if_no_data
    def test_tattoo_idea_no_language(self) -> None:
        _, _, reason = main_posts_filter("Tattoo idea")
        self.assertEqual(reason, "1")

    @_skip_if_no_data
    def test_arabic_tattoo_no_direction(self) -> None:
        _, _, reason = main_posts_filter("Arabic tattoo from a passed friend")
        self.assertEqual(reason, "1")

    @_skip_if_no_data
    def test_deepl_alternatives_off_topic(self) -> None:
        _, _, reason = main_posts_filter("What are the best alternatives to DeepL?")
        self.assertEqual(reason, "1")


class TestMainPostsFilterFailCode1A(unittest.TestCase):
    """Titles that bury the lede: language pair present but too late/unbracketed — code '1A'.

    Per FILTER_REASONS: '"to Language" phrasing not early in the title.'
    The title contains a recognisable language pair but places it after a long
    preamble rather than at the front in brackets.
    """

    @_skip_if_no_data
    def test_looking_for_translators_japanese_to_english(self) -> None:
        _, _, reason = main_posts_filter(
            "Looking for translators (Japanese to English) for Kore wa Uso"
        )
        self.assertEqual(reason, "1A")

    @_skip_if_no_data
    def test_can_someone_translate_to_english(self) -> None:
        _, _, reason = main_posts_filter("Can someone translate it to English")
        self.assertEqual(reason, "1A")

    @_skip_if_no_data
    def test_thai_to_english_buried(self) -> None:
        _, _, reason = main_posts_filter(
            "Can some help me translate this from Thai to English."
        )
        self.assertEqual(reason, "1A")

    @_skip_if_no_data
    def test_food_allergy_english_to_japanese(self) -> None:
        _, _, reason = main_posts_filter(
            "Need help translating food allergy list from English to Japanese"
        )
        self.assertEqual(reason, "1A")

    @_skip_if_no_data
    def test_mcm_plates_japanese_to_english(self) -> None:
        _, _, reason = main_posts_filter(
            "Mcm enameled copper frog and owl plates Japanese to English"
        )
        self.assertEqual(reason, "1A")

    @_skip_if_no_data
    def test_russian_to_english_buried(self) -> None:
        _, _, reason = main_posts_filter("Translation help from Russian to english?")
        self.assertEqual(reason, "1A")

    @_skip_if_no_data
    def test_dzongkha_to_english(self) -> None:
        _, _, reason = main_posts_filter(
            "Can anyone translate a text from Dzongkha to English"
        )
        self.assertEqual(reason, "1A")

    @_skip_if_no_data
    def test_english_to_marathi(self) -> None:
        _, _, reason = main_posts_filter(
            "trying to communicate with my boyfriend mom, english to marathi"
        )
        self.assertEqual(reason, "1A")


class TestMainPostsFilterFailCode2(unittest.TestCase):
    """Titles with '>' present but poorly placed — code '2'."""

    @_skip_if_no_data
    def test_arrow_buried_late_in_title(self) -> None:
        _, _, reason = main_posts_filter(
            "Can someone translate what this stuff on my carpet is saying ? Arabic->English"
        )
        self.assertEqual(reason, "2")


class TestMainPostsFilterFailCode1B(unittest.TestCase):
    """Short, generic titles where no valid non-English language is detected — code '1B'.

    Per FILTER_REASONS: 'Too short and generic (no valid language detected).'
    The title has a "to English" phrase early enough to pass the 1A check,
    but is under 35 characters with no identifiable non-English language.
    """

    @_skip_if_no_data
    def test_translation_to_english_short(self) -> None:
        _, _, reason = main_posts_filter("Translation to English")
        self.assertEqual(reason, "1B")


# ---------------------------------------------------------------------------
# process_title() — passing titles
# ---------------------------------------------------------------------------


class TestProcessTitleLanguageExtraction(unittest.TestCase):
    """Passing titles produce correct source/target Lingvo objects."""

    @_skip_if_no_data
    def test_vietnamese_to_english(self) -> None:
        titolo = process_title("Vietnamese > English", discord_notify=False)
        self.assertIn("Vietnamese", _names(titolo.source))
        self.assertIn("English", _names(titolo.target))

    @_skip_if_no_data
    def test_japanese_to_english_bracketed(self) -> None:
        titolo = process_title(
            "[Japanese > English] silk embroidered panels", discord_notify=False
        )
        self.assertIn("Japanese", _names(titolo.source))
        self.assertIn("English", _names(titolo.target))

    @_skip_if_no_data
    def test_unknown_to_english_bracketed(self) -> None:
        titolo = process_title(
            "[unknown > English] I need help figuring out what this says",
            discord_notify=False,
        )
        self.assertIn("English", _names(titolo.target))

    @_skip_if_no_data
    def test_chinese_to_english_bracketed(self) -> None:
        titolo = process_title(
            "[Chinese? > English] funny cat statue my mom got me",
            discord_notify=False,
        )
        self.assertIn("English", _names(titolo.target))

    @_skip_if_no_data
    def test_neo_aramaic_to_english(self) -> None:
        titolo = process_title(
            "[Neo-Aramaic > English] Back of family photo", discord_notify=False
        )
        self.assertIn("English", _names(titolo.target))

    @_skip_if_no_data
    def test_luxembourgish_to_english(self) -> None:
        titolo = process_title(
            "Luxembourgish > English Translating a 16th cent. coded message",
            discord_notify=False,
        )
        self.assertIn("Luxembourgish", _names(titolo.source))
        self.assertIn("English", _names(titolo.target))

    @_skip_if_no_data
    def test_unknown_to_spanish(self) -> None:
        titolo = process_title("unknown > spanish", discord_notify=False)
        self.assertIn("Spanish", _names(titolo.target))


class TestProcessTitleTitoloFields(unittest.TestCase):
    """process_title populates Titolo metadata fields correctly."""

    @_skip_if_no_data
    def test_title_original_preserved(self) -> None:
        raw = "[Japanese > English] decorative scroll found at thrift store"
        titolo = process_title(raw, discord_notify=False)
        self.assertEqual(titolo.title_original, raw)

    @_skip_if_no_data
    def test_title_processed_is_set(self) -> None:
        titolo = process_title("Vietnamese > English", discord_notify=False)
        self.assertIsNotNone(titolo.title_processed)

    @_skip_if_no_data
    def test_final_code_is_set(self) -> None:
        titolo = process_title("[Japanese > English] test", discord_notify=False)
        self.assertIsNotNone(titolo.final_code)

    @_skip_if_no_data
    def test_final_text_is_set(self) -> None:
        titolo = process_title("[Japanese > English] test", discord_notify=False)
        self.assertIsNotNone(titolo.final_text)

    @_skip_if_no_data
    def test_returns_titolo_instance(self) -> None:
        titolo = process_title("[Japanese > English] test", discord_notify=False)
        self.assertIsInstance(titolo, Titolo)


# ---------------------------------------------------------------------------
# Direction detection
# ---------------------------------------------------------------------------


class TestProcessTitleDirection(unittest.TestCase):
    """Direction field is set correctly for passing titles."""

    @_skip_if_no_data
    def test_japanese_to_english_is_english_to(self) -> None:
        titolo = process_title("[Japanese > English] test", discord_notify=False)
        self.assertEqual(titolo.direction, "english_to")

    @_skip_if_no_data
    def test_english_to_target_is_english_from(self) -> None:
        titolo = process_title("[English > French] test", discord_notify=False)
        self.assertEqual(titolo.direction, "english_from")

    @_skip_if_no_data
    def test_non_english_both_sides_is_english_none(self) -> None:
        titolo = process_title("[Japanese > French] test", discord_notify=False)
        self.assertEqual(titolo.direction, "english_none")

    @_skip_if_no_data
    def test_unknown_to_english_is_english_to(self) -> None:
        titolo = process_title("[unknown > English] some image", discord_notify=False)
        self.assertEqual(titolo.direction, "english_to")


class TestDetermineTitleDirectionDirect(unittest.TestCase):
    """Unit tests for _determine_title_direction with mock Lingvo objects."""

    @staticmethod
    def _make_lingvo(name: str) -> MagicMock:
        """Return a minimal mock Lingvo with the given name."""
        mock = MagicMock()
        mock.name = name
        return mock

    def test_english_source_only_is_english_from(self) -> None:
        src = [self._make_lingvo("English")]
        tgt = [self._make_lingvo("French")]
        self.assertEqual(_determine_title_direction(src, tgt), "english_from")

    def test_english_target_only_is_english_to(self) -> None:
        src = [self._make_lingvo("Japanese")]
        tgt = [self._make_lingvo("English")]
        self.assertEqual(_determine_title_direction(src, tgt), "english_to")

    def test_english_both_sides_is_english_both(self) -> None:
        src = [self._make_lingvo("English")]
        tgt = [self._make_lingvo("English")]
        self.assertEqual(_determine_title_direction(src, tgt), "english_both")

    def test_no_english_is_english_none(self) -> None:
        src = [self._make_lingvo("Japanese")]
        tgt = [self._make_lingvo("French")]
        self.assertEqual(_determine_title_direction(src, tgt), "english_none")

    def test_empty_lists_is_english_none(self) -> None:
        self.assertEqual(_determine_title_direction([], []), "english_none")

    def test_english_bias_removal_only_triggers_when_english_on_both_sides(
        self,
    ) -> None:
        # English + French source vs German target: bias removal does NOT fire
        # because English is only on the source side, not both sides.
        # English stays in src → result is english_from.
        src = [self._make_lingvo("English"), self._make_lingvo("French")]
        tgt = [self._make_lingvo("German")]
        result = _determine_title_direction(src, tgt)
        self.assertEqual(result, "english_from")


# ---------------------------------------------------------------------------
# extract_lingvos_from_text()
# ---------------------------------------------------------------------------


class TestExtractLingvosFromText(unittest.TestCase):
    @_skip_if_no_data
    def test_finds_japanese(self) -> None:
        result = extract_lingvos_from_text("Japanese lyrics from a song")
        self.assertIsNotNone(result)
        names = _names(result)
        self.assertIn("Japanese", names)

    @_skip_if_no_data
    def test_finds_german(self) -> None:
        result = extract_lingvos_from_text("German Club Nintendo 1996 article")
        self.assertIsNotNone(result)
        self.assertIn("German", _names(result))

    @_skip_if_no_data
    def test_english_excluded_by_default(self) -> None:
        result = extract_lingvos_from_text("Translate English text")
        # English is not supported for flair purposes, so should be absent
        # unless return_english=True
        if result:
            self.assertNotIn("English", _names(result))

    @_skip_if_no_data
    def test_english_included_with_flag(self) -> None:
        result = extract_lingvos_from_text(
            "Translate English text", return_english=True
        )
        if result:
            self.assertIn("English", _names(result))

    @_skip_if_no_data
    def test_no_languages_returns_none(self) -> None:
        result = extract_lingvos_from_text("How do I read this tape measure?")
        self.assertIsNone(result)

    @_skip_if_no_data
    def test_result_is_sorted(self) -> None:
        result = extract_lingvos_from_text("French and German translation needed")
        if result and len(result) > 1:
            names = _names(result)
            self.assertEqual(names, sorted(names))


# ---------------------------------------------------------------------------
# AI fallback path (mocked)
# ---------------------------------------------------------------------------


class TestProcessTitleAIFallback(unittest.TestCase):
    """AI fallback fires when no non-English language is found by rule-based parser."""

    @_skip_if_no_data
    @patch("title.title_handling.title_ai_parser")
    @patch("title.title_handling.update_titolo_from_ai_result")
    def test_ai_called_for_unidentifiable_title(
        self,
        _mock_update: MagicMock,
        mock_ai_parser: MagicMock,
    ) -> None:
        mock_ai_parser.return_value = ("error", "Confidence value too low")
        process_title("Can someone please translate?", discord_notify=False)
        mock_ai_parser.assert_called_once()

    @_skip_if_no_data
    @patch("title.title_handling.title_ai_parser")
    @patch("title.title_handling.update_titolo_from_ai_result")
    def test_ai_not_called_for_parseable_title(
        self,
        _mock_update: MagicMock,
        mock_ai_parser: MagicMock,
    ) -> None:
        process_title("[Japanese > English] test", discord_notify=False)
        mock_ai_parser.assert_not_called()

    @_skip_if_no_data
    @patch("title.title_handling.title_ai_parser")
    @patch("title.title_handling.update_titolo_from_ai_result")
    def test_ai_success_calls_update(
        self,
        mock_update: MagicMock,
        mock_ai_parser: MagicMock,
    ) -> None:
        ai_payload = {
            "source_language": {"code": "ja", "name": "Japanese"},
            "target_language": {"code": "en", "name": "English"},
            "confidence": 0.92,
        }
        mock_ai_parser.return_value = ai_payload
        process_title("Can someone please translate?", discord_notify=False)
        mock_update.assert_called_once()

    @_skip_if_no_data
    @patch("title.title_handling.title_ai_parser")
    @patch("title.title_handling.update_titolo_from_ai_result")
    def test_ai_failure_calls_update_for_alert_path(
        self,
        mock_update: MagicMock,
        mock_ai_parser: MagicMock,
    ) -> None:
        mock_ai_parser.return_value = ("error", "Confidence value too low")
        process_title("Can someone please translate?", discord_notify=False)
        mock_update.assert_called_once()
        args = mock_update.call_args.args
        self.assertEqual(args[1], ("error", "Confidence value too low"))

    @_skip_if_no_data
    @patch("title.title_handling.title_ai_parser")
    @patch("title.title_handling.update_titolo_from_ai_result")
    def test_ai_failure_still_returns_titolo(
        self,
        _mock_update: MagicMock,
        mock_ai_parser: MagicMock,
    ) -> None:
        mock_ai_parser.return_value = ("error", "Confidence value too low")
        result = process_title("Can someone please translate?", discord_notify=False)
        self.assertIsInstance(result, Titolo)

    @_skip_if_no_data
    @patch("title.title_ai.send_discord_alert")
    def test_ai_failure_assigns_generic_and_sends_discord_report(
        self,
        mock_alert: MagicMock,
    ) -> None:
        from title.title_ai import update_titolo_from_ai_result

        post = MagicMock()
        post.title = "Can someone please translate?"
        post.id = "abc123"
        post.permalink = "/r/translator/comments/abc123/test/"
        result = Titolo()

        update_titolo_from_ai_result(
            result,
            ("error", "Confidence value too low"),
            post,
            True,
            determine_flair_fn=lambda _result: None,
            determine_direction_fn=lambda _source, _target: "english_none",
            get_notification_languages_fn=lambda _result: [],
        )

        self.assertEqual(result.final_code, "generic")
        self.assertEqual(result.final_text, "Generic")
        mock_alert.assert_called_once()
        self.assertEqual(
            mock_alert.call_args.args[0],
            "AI Unable to Parse Title; No Language Assigned",
        )
        self.assertEqual(mock_alert.call_args.args[2], "report")


# ---------------------------------------------------------------------------
# Multiple-language posts
# ---------------------------------------------------------------------------


class TestProcessTitleDefinedMultiple(unittest.TestCase):
    """Defined multiple posts: specific list of target languages."""

    @_skip_if_no_data
    def test_defined_multiple_final_code(self) -> None:
        titolo = process_title(
            "[English > German, French, Italian] My genealogical records",
            discord_notify=False,
        )
        self.assertEqual(titolo.final_code, "multiple")

    @_skip_if_no_data
    def test_defined_multiple_final_text_contains_codes(self) -> None:
        titolo = process_title(
            "[English > German, French, Italian] My genealogical records",
            discord_notify=False,
        )
        self.assertIsNotNone(titolo.final_text)
        assert titolo.final_text is not None  # narrow for mypy
        self.assertIn("Multiple Languages", titolo.final_text)

    @_skip_if_no_data
    def test_defined_multiple_preferred_code_is_multiple_not_mul(self) -> None:
        # The spec requires 'multiple', not the ISO 639-3 code 'mul'
        titolo = process_title("[English > German, French] test", discord_notify=False)
        self.assertEqual(titolo.final_code, "multiple")
        self.assertNotEqual(titolo.final_code, "mul")

    @_skip_if_no_data
    def test_multiple_source_languages_not_parsed_as_multiple(self) -> None:
        # [Chinese/Japanese > English]: ambiguous source → should NOT be 'multiple'
        titolo = process_title(
            "[Chinese/Japanese > English] what language is this?",
            discord_notify=False,
        )
        self.assertNotEqual(titolo.final_code, "multiple")

    @_skip_if_no_data
    def test_english_among_targets_not_defined_multiple(self) -> None:
        # [Chinese > English/Spanish]: English in targets → not defined multiple
        titolo = process_title("[Chinese > English/Spanish] test", discord_notify=False)
        self.assertNotEqual(titolo.final_code, "multiple")

    @_skip_if_no_data
    def test_trailing_prose_all_does_not_create_defined_multiple(self) -> None:
        titolo = process_title(
            "English > Spanish; Is this translated correctly at all?",
            discord_notify=False,
        )
        self.assertEqual(titolo.final_code, "es")
        self.assertEqual(titolo.title_actual, "Is this translated correctly at all ?")
        self.assertEqual(_codes(titolo.target), ["es"])
        self.assertEqual(_codes(titolo.notify_languages), ["es"])


class TestProcessTitleGeneralMultiple(unittest.TestCase):
    """General multiple posts: 'any', 'all', 'every' keywords."""

    @_skip_if_no_data
    def test_any_language_keyword_is_multiple(self) -> None:
        titolo = process_title(
            "[Unknown > Any] Can anyone identify this script?",
            discord_notify=False,
        )
        self.assertEqual(titolo.final_code, "multiple")

    @_skip_if_no_data
    def test_all_languages_keyword_is_multiple(self) -> None:
        titolo = process_title(
            "Trying to translate 'vote' into all languages",
            discord_notify=False,
        )
        self.assertEqual(titolo.final_code, "multiple")


# ---------------------------------------------------------------------------
# English-only posts
# ---------------------------------------------------------------------------


class TestIsEnglishOnly(unittest.TestCase):
    """is_english_only() correctly identifies English-only Titolo objects.

    EE (English-to-English) posts pass main_posts_filter and reach process_title.
    is_english_only() is the downstream check that identifies them.
    """

    @staticmethod
    def _make_english_lingvo() -> MagicMock:
        """Return a mock Lingvo representing English."""
        mock = MagicMock()
        mock.preferred_code = "en"
        mock.name = "English"
        return mock

    @staticmethod
    def _make_french_lingvo() -> MagicMock:
        """Return a mock Lingvo representing French."""
        mock = MagicMock()
        mock.preferred_code = "fr"
        mock.name = "French"
        return mock

    def test_both_sides_english_is_english_only(self) -> None:
        titolo = Titolo()
        english = self._make_english_lingvo()
        titolo.source = [english]
        titolo.target = [english]
        self.assertTrue(is_english_only(titolo))

    def test_empty_titolo_is_not_english_only(self) -> None:
        self.assertFalse(is_english_only(Titolo()))

    def test_empty_source_is_not_english_only(self) -> None:
        titolo = Titolo()
        titolo.source = []
        titolo.target = [self._make_english_lingvo()]
        self.assertFalse(is_english_only(titolo))

    def test_empty_target_is_not_english_only(self) -> None:
        titolo = Titolo()
        titolo.source = [self._make_english_lingvo()]
        titolo.target = []
        self.assertFalse(is_english_only(titolo))

    def test_english_source_non_english_target_is_not_english_only(self) -> None:
        titolo = Titolo()
        titolo.source = [self._make_english_lingvo()]
        titolo.target = [self._make_french_lingvo()]
        self.assertFalse(is_english_only(titolo))

    def test_non_english_both_sides_is_not_english_only(self) -> None:
        titolo = Titolo()
        french = self._make_french_lingvo()
        titolo.source = [french]
        titolo.target = [french]
        self.assertFalse(is_english_only(titolo))

    @_skip_if_no_data
    def test_english_to_english_via_process_title(self) -> None:
        titolo = process_title(
            "[English > English] seak out meaning", discord_notify=False
        )
        self.assertTrue(is_english_only(titolo))

    @_skip_if_no_data
    def test_japanese_to_english_is_not_english_only(self) -> None:
        titolo = process_title("[Japanese > English] test", discord_notify=False)
        self.assertFalse(is_english_only(titolo))


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


def run_all_tests() -> unittest.TestResult:
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    for cls in (
        TestTitoloDefaults,
        TestMainPostsFilterPasses,
        TestMainPostsFilterFailCode1,
        TestMainPostsFilterFailCode1A,
        TestMainPostsFilterFailCode1B,
        TestMainPostsFilterFailCode2,
        TestProcessTitleLanguageExtraction,
        TestProcessTitleTitoloFields,
        TestProcessTitleDirection,
        TestDetermineTitleDirectionDirect,
        TestExtractLingvosFromText,
        TestProcessTitleDefinedMultiple,
        TestProcessTitleGeneralMultiple,
        TestIsEnglishOnly,
        TestProcessTitleAIFallback,
    ):
        suite.addTests(loader.loadTestsFromTestCase(cls))
    runner = unittest.TextTestRunner(verbosity=2)
    return runner.run(suite)


if __name__ == "__main__":
    print("=" * 70)
    print("Title Handling Test Suite")
    print("=" * 70)
    run_all_tests()
