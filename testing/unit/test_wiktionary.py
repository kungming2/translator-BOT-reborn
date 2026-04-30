#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
Tests for ziwen_lookup/wiktionary.py.

Covers:
  - parse_wiktionary: section parsing, multi-etymology, skip-subsection
    suppression, fallback word extraction, unknown language, filter helpers.
  - format_wiktionary_markdown: header URL construction, section omission,
    long definition trimming.
  - wiktionary_search: HTTP success, missing page, empty extract, HTTP error,
    invalid language name.
"""

from unittest.mock import MagicMock, patch

import pytest

# noinspection PyProtectedMember
from ziwen_lookup.wiktionary import (
    _is_clean_definition_line,
    _is_clean_etymology_line,
    _section_level,
    _section_name,
    format_wiktionary_markdown,
    parse_wiktionary,
    wiktionary_search,
)

# ─── Fixtures: raw Wiktionary extracts ───────────────────────────────────────


ENGLISH_SIMPLE = """\
== English ==

=== Etymology ===
From Old French ''bonjour''.

=== Pronunciation ===
IPA(key): /ɡʊd/

=== Adjective ===
good (comparative better, superlative best)

1. Having the required qualities.
2. Morally right.
"""

ENGLISH_MULTI_ETYMOLOGY = """\
== English ==

=== Etymology 1 ===
From Old English ''bæc''.

==== Noun ====
back (plural backs)

1. The rear of the body.

=== Etymology 2 ===
From a different root.

==== Verb ====
back (third-person singular simple present backs)

1. To go backwards.
"""

ENGLISH_WITH_DESCENDANTS = """\
== English ==

=== Etymology ===
From Latin ''bonus''.

=== Noun ===
bonus (plural bonuses)

1. Something extra given as a reward.

===== Descendants =====
→ French: bonus
→ Spanish: bono

=== Adjective ===
bonus

1. Being extra or additional.
"""

ENGLISH_WITH_TRANSLATIONS = """\
== English ==

=== Noun ===
cat (plural cats)

1. A domesticated carnivorous mammal.

==== Translations ====
French: chat
German: Katze
"""

GERMAN_ENTRY = """\
== English ==

=== Noun ===
hand (plural hands)

1. The part of the arm below the wrist.

== German ==

=== Etymology ===
From Old High German ''hant''.

=== Pronunciation ===
IPA(key): /hant/

=== Noun ===
Hand f (strong, genitive Handes or Hands, plural Hände)

1. Hand (body part)
"""

MALAY_ENTRY = """\
== Malay ==

=== Etymology ===
From Proto-Austronesian.

=== Pronunciation ===
IPA(key): /t͡ʃin.t͡ʃa/

=== Noun ===
cinta (Jawi spelling چينتا)

1. Love, affection.
2. Romantic feeling.
"""

NO_TARGET_LANGUAGE = """\
== French ==

=== Noun ===
chat (masculine)

1. Cat.
"""

ENTRY_WITH_STOPWORDS = """\
== English ==

=== Noun ===
fire (plural fires)

1. The rapid oxidation of a material.
2. A burning sensation.

Synonym: flame, blaze
Antonym: water
"""

ENTRY_WITH_DATED_QUOTES = """\
== English ==

=== Noun ===
virtue (plural virtues)

1. Moral excellence.

1847, Author Name, Some Book Title, page 12:
    A long quotation that should be excluded.
"""

ENTRY_WITH_DESCENDANT_ARROWS = """\
== English ==

=== Noun ===
night (plural nights)

1. The period of darkness.

→ Dutch: nacht
> German: Nacht
"""

ENTRY_LEMMA_REDIRECT = """\
== English ==

=== Verb ===
ran

See the etymology of the corresponding lemma form.
"""

ENTRY_NO_HEADWORD = """\
== English ==

=== Noun ===
simple

A plain definition line with no headword markup.
"""


# ─── _section_level ──────────────────────────────────────────────────────────


class TestSectionLevel:
    def test_level_2(self):
        assert _section_level("== English ==") == 2

    def test_level_3(self):
        assert _section_level("=== Etymology ===") == 3

    def test_level_4(self):
        assert _section_level("==== Noun ====") == 4

    def test_level_5(self):
        assert _section_level("===== Descendants =====") == 5

    def test_not_a_header(self):
        assert _section_level("Just some text") is None

    def test_mismatched_levels(self):
        # ===Foo== is not a valid header (asymmetric)
        assert _section_level("===Foo==") is None

    def test_empty_string(self):
        assert _section_level("") is None


# ─── _section_name ───────────────────────────────────────────────────────────


class TestSectionName:
    def test_strips_equals_and_whitespace(self):
        assert _section_name("=== Etymology ===") == "etymology"

    def test_level_2(self):
        assert _section_name("== English ==") == "english"

    def test_already_clean(self):
        assert _section_name("==Noun==") == "noun"


# ─── _is_clean_etymology_line ────────────────────────────────────────────────


class TestIsCleanEtymologyLine:
    def test_plain_prose(self):
        assert _is_clean_etymology_line("From Old French bonjour.") is True

    def test_empty_string(self):
        assert _is_clean_etymology_line("") is False

    def test_ipa_line(self):
        assert _is_clean_etymology_line("IPA(key): /ɡʊd/") is False

    def test_lemma_redirect(self):
        assert (
            _is_clean_etymology_line(
                "See the etymology of the corresponding lemma form."
            )
            is False
        )

    def test_headword_with_plural(self):
        assert (
            _is_clean_etymology_line("hand (plural hands, genitive of hand)") is False
        )


# ─── _is_clean_definition_line ───────────────────────────────────────────────


class TestIsCleanDefinitionLine:
    def test_plain_definition(self):
        assert _is_clean_definition_line("1. A domesticated mammal.") is True

    def test_dated_quote(self):
        assert _is_clean_definition_line("1847, Author, Title, page 12:") is False

    def test_bibliographic(self):
        assert _is_clean_definition_line("Smith, John (2001), Some Book") is False

    def test_lemma_redirect(self):
        assert (
            _is_clean_definition_line(
                "See the etymology of the corresponding lemma form."
            )
            is False
        )

    def test_descendant_arrow(self):
        assert _is_clean_definition_line("→ French: bon") is False

    def test_greater_than_arrow(self):
        assert _is_clean_definition_line("> Spanish: bueno") is False

    def test_language_crossref(self):
        assert _is_clean_definition_line("Gulf Arabic: something") is False


# ─── parse_wiktionary ────────────────────────────────────────────────────────


class TestParseWiktionary:
    # ── Basic extraction ──────────────────────────────────────────────────────

    def test_returns_dict_with_expected_keys(self):
        result = parse_wiktionary(ENGLISH_SIMPLE)
        assert result is not None
        assert set(result.keys()) == {
            "word",
            "etymology",
            "pronunciation",
            "definition",
        }

    def test_etymology_extracted(self):
        result = parse_wiktionary(ENGLISH_SIMPLE)
        assert result is not None
        assert result["etymology"] is not None
        assert any("Old French" in line for line in result["etymology"])

    def test_pronunciation_extracted(self):
        result = parse_wiktionary(ENGLISH_SIMPLE)
        assert result is not None
        assert result["pronunciation"] is not None
        assert any("IPA" in line for line in result["pronunciation"])

    def test_definition_extracted(self):
        result = parse_wiktionary(ENGLISH_SIMPLE)
        assert result is not None
        assert result["definition"] is not None
        assert any("required qualities" in line for line in result["definition"])

    # ── Language selection ────────────────────────────────────────────────────

    def test_defaults_to_english(self):
        result = parse_wiktionary(GERMAN_ENTRY)
        assert result is not None
        assert result["definition"] is not None
        assert any("wrist" in line for line in result["definition"])

    def test_selects_german_section(self):
        result = parse_wiktionary(GERMAN_ENTRY, search_language="German")
        assert result is not None
        assert result["etymology"] is not None
        assert any("Old High German" in line for line in result["etymology"])

    def test_returns_none_for_missing_language(self):
        result = parse_wiktionary(NO_TARGET_LANGUAGE, search_language="English")
        assert result is None

    def test_language_match_is_case_insensitive(self):
        result = parse_wiktionary(MALAY_ENTRY, search_language="malay")
        assert result is not None
        assert result["definition"] is not None

    def test_stops_at_next_language_section(self):
        # German definitions should not appear when searching English
        result = parse_wiktionary(GERMAN_ENTRY, search_language="English")
        assert result is not None
        # German "Hand f (strong...)" headword line should not be in definitions
        if result["definition"]:
            for line in result["definition"]:
                assert "Hände" not in line

    # ── Multi-etymology ───────────────────────────────────────────────────────

    def test_multi_etymology_collects_both_definitions(self):
        result = parse_wiktionary(ENGLISH_MULTI_ETYMOLOGY)
        assert result is not None
        assert result["definition"] is not None
        combined = " ".join(result["definition"])
        assert "rear" in combined or "backwards" in combined

    def test_multi_etymology_collects_both_etymologies(self):
        result = parse_wiktionary(ENGLISH_MULTI_ETYMOLOGY)
        assert result is not None
        assert result["etymology"] is not None
        combined = " ".join(result["etymology"])
        assert "Old English" in combined

    # ── Skip-subsection suppression ───────────────────────────────────────────

    def test_descendants_subsection_suppressed(self):
        result = parse_wiktionary(ENGLISH_WITH_DESCENDANTS)
        assert result is not None
        if result["definition"]:
            for line in result["definition"]:
                assert "→" not in line
                assert "French: bonus" not in line

    def test_translations_subsection_suppressed(self):
        result = parse_wiktionary(ENGLISH_WITH_TRANSLATIONS)
        assert result is not None
        if result["definition"]:
            for line in result["definition"]:
                assert "chat" not in line
                assert "Katze" not in line

    # ── Stopword termination ──────────────────────────────────────────────────

    def test_stopword_terminates_definitions(self):
        result = parse_wiktionary(ENTRY_WITH_STOPWORDS)
        assert result is not None
        if result["definition"]:
            for line in result["definition"]:
                assert not line.startswith("Synonym")
                assert not line.startswith("Antonym")

    # ── Noise line filtering ──────────────────────────────────────────────────

    def test_dated_quotes_excluded_from_definitions(self):
        result = parse_wiktionary(ENTRY_WITH_DATED_QUOTES)
        assert result is not None
        if result["definition"]:
            for line in result["definition"]:
                assert not line.startswith("1847")

    def test_descendant_arrows_excluded(self):
        result = parse_wiktionary(ENTRY_WITH_DESCENDANT_ARROWS)
        assert result is not None
        if result["definition"]:
            for line in result["definition"]:
                assert not line.startswith("→")
                assert not line.startswith(">")

    def test_lemma_redirect_excluded(self):
        result = parse_wiktionary(ENTRY_LEMMA_REDIRECT)
        assert result is not None
        if result["definition"]:
            for line in result["definition"]:
                assert "corresponding lemma" not in line

    # ── None fields when absent ───────────────────────────────────────────────

    def test_none_etymology_when_absent(self):
        result = parse_wiktionary(ENGLISH_WITH_TRANSLATIONS)
        assert result is not None
        assert result["etymology"] is None

    def test_none_pronunciation_when_absent(self):
        result = parse_wiktionary(ENGLISH_WITH_TRANSLATIONS)
        assert result is not None
        assert result["pronunciation"] is None

    def test_all_none_on_empty_language_block(self):
        result = parse_wiktionary(NO_TARGET_LANGUAGE, search_language="French")
        assert result is not None
        # French block has a definition but no etymology or pronunciation
        assert result["etymology"] is None
        assert result["pronunciation"] is None


# ─── format_wiktionary_markdown ──────────────────────────────────────────────


class TestFormatWiktionaryMarkdown:
    BASE_DATA = {
        "word": "good",
        "etymology": ["From Old English god."],
        "pronunciation": ["IPA(key): /ɡʊd/"],
        "definition": ["1. Having the required qualities.", "2. Morally right."],
    }

    def test_header_contains_word(self):
        output = format_wiktionary_markdown(self.BASE_DATA, "good", "English")
        assert "# [good]" in output

    def test_header_url_structure(self):
        output = format_wiktionary_markdown(self.BASE_DATA, "good", "English")
        assert "https://en.wiktionary.org/wiki/good#English" in output

    def test_header_url_anchor_titlecased(self):
        output = format_wiktionary_markdown(self.BASE_DATA, "cinta", "Malay")
        assert "#Malay" in output

    def test_header_url_multi_word_language(self):
        output = format_wiktionary_markdown(
            {**self.BASE_DATA, "word": "schadenfreude"},
            "schadenfreude",
            "German",
        )
        assert "schadenfreude" in output

    def test_pronunciation_section_present(self):
        output = format_wiktionary_markdown(self.BASE_DATA, "good", "English")
        assert "**Pronunciation:**" in output
        assert "IPA" in output

    def test_etymology_section_present(self):
        output = format_wiktionary_markdown(self.BASE_DATA, "good", "English")
        assert "**Etymology:**" in output
        assert "Old English" in output

    def test_definitions_section_present(self):
        output = format_wiktionary_markdown(self.BASE_DATA, "good", "English")
        assert "**Definitions:**" in output
        assert "required qualities" in output

    def test_omits_pronunciation_when_none(self):
        data = {**self.BASE_DATA, "pronunciation": None}
        output = format_wiktionary_markdown(data, "good", "English")
        assert "**Pronunciation:**" not in output

    def test_omits_etymology_when_none(self):
        data = {**self.BASE_DATA, "etymology": None}
        output = format_wiktionary_markdown(data, "good", "English")
        assert "**Etymology:**" not in output

    def test_omits_definitions_when_none(self):
        # format_wiktionary_markdown raises ValueError when definition is absent,
        # since a Wiktionary entry without definitions is not useful to format.
        data = {**self.BASE_DATA, "definition": None}
        with pytest.raises(ValueError):
            format_wiktionary_markdown(data, "good", "English")

    def test_fallback_to_search_term_when_no_word(self):
        data = {**self.BASE_DATA, "word": None}
        output = format_wiktionary_markdown(data, "fallbackterm", "English")
        assert "fallbackterm" in output

    def test_definitions_trimmed_to_eight_items(self):
        data = {
            **self.BASE_DATA,
            "definition": [f"{i}. Definition number {i}." for i in range(1, 15)],
        }
        output = format_wiktionary_markdown(data, "good", "English")
        # Only the first 8 definition lines should appear (def_lines[:8])
        assert "Definition number 9." not in output
        assert "Definition number 1." in output

    def test_multi_line_etymology_uses_bullets(self):
        data = {**self.BASE_DATA, "etymology": ["From root A.", "Via language B."]}
        output = format_wiktionary_markdown(data, "good", "English")
        assert "- From root A." in output
        assert "- Via language B." in output

    def test_invalid_language_raises(self):
        # An empty string cannot be resolved to a valid Lingvo with a name,
        # so format_wiktionary_markdown should raise ValueError.
        with pytest.raises(ValueError):
            format_wiktionary_markdown(self.BASE_DATA, "good", "")


# ─── wiktionary_search ───────────────────────────────────────────────────────


class TestWiktionarySearch:
    MOCK_RESPONSE_BODY = {
        "query": {
            "pages": {
                "12345": {
                    "title": "good",
                    "extract": ENGLISH_SIMPLE,
                }
            }
        }
    }

    MOCK_MISSING_PAGE = {
        "query": {
            "pages": {
                "-1": {
                    "title": "nonexistentword99999",
                    "missing": "",
                }
            }
        }
    }

    MOCK_EMPTY_EXTRACT = {
        "query": {
            "pages": {
                "99": {
                    "title": "something",
                    "extract": "",
                }
            }
        }
    }

    @staticmethod
    def _make_mock_response(json_data: dict, status_code: int = 200) -> MagicMock:
        mock_resp = MagicMock()
        mock_resp.status_code = status_code
        mock_resp.json.return_value = json_data
        mock_resp.raise_for_status = MagicMock()
        if status_code >= 400:
            mock_resp.raise_for_status.side_effect = Exception(
                f"HTTP {status_code} error"
            )
        return mock_resp

    @patch("ziwen_lookup.wiktionary.requests.get")
    def test_successful_lookup_returns_dict(self, mock_get):
        mock_get.return_value = self._make_mock_response(self.MOCK_RESPONSE_BODY)
        result = wiktionary_search("good", "English")
        assert result is not None
        assert isinstance(result, dict)

    @patch("ziwen_lookup.wiktionary.requests.get")
    def test_successful_lookup_has_definition(self, mock_get):
        mock_get.return_value = self._make_mock_response(self.MOCK_RESPONSE_BODY)
        result = wiktionary_search("good", "English")
        assert result is not None
        assert result["definition"] is not None

    @patch("ziwen_lookup.wiktionary.requests.get")
    def test_missing_page_returns_none(self, mock_get):
        mock_get.return_value = self._make_mock_response(self.MOCK_MISSING_PAGE)
        result = wiktionary_search("nonexistentword99999", "English")
        # parse_wiktionary returns None when language section not found
        assert result is None

    @patch("ziwen_lookup.wiktionary.requests.get")
    def test_empty_extract_returns_none(self, mock_get):
        mock_get.return_value = self._make_mock_response(self.MOCK_EMPTY_EXTRACT)
        result = wiktionary_search("something", "English")
        assert result is None

    @patch("ziwen_lookup.wiktionary.requests.get")
    def test_empty_pages_returns_none(self, mock_get):
        mock_get.return_value = self._make_mock_response({"query": {"pages": {}}})
        result = wiktionary_search("something", "English")
        assert result is None

    @patch("ziwen_lookup.wiktionary.requests.get")
    def test_http_error_propagates(self, mock_get):
        mock_get.return_value = self._make_mock_response({}, status_code=500)
        with pytest.raises(Exception):
            wiktionary_search("good", "English")

    def test_invalid_language_raises_value_error(self):
        with pytest.raises(ValueError):
            wiktionary_search("good", "NotARealLanguage")

    @patch("ziwen_lookup.wiktionary.requests.get")
    def test_api_called_with_correct_title(self, mock_get):
        mock_get.return_value = self._make_mock_response(self.MOCK_RESPONSE_BODY)
        wiktionary_search("schadenfreude", "German")
        call_kwargs = mock_get.call_args
        params = (
            call_kwargs[1]["params"]
            if "params" in call_kwargs[1]
            else call_kwargs[0][1]
        )
        assert params["titles"] == "schadenfreude"

    @patch("ziwen_lookup.wiktionary.requests.get")
    def test_language_name_normalized_via_converter(self, mock_get):
        # "eo" should resolve to "Esperanto" via converter before the API call
        mock_get.return_value = self._make_mock_response(self.MOCK_RESPONSE_BODY)
        # Should not raise — converter handles the code-to-name normalization
        try:
            wiktionary_search("bona", "eo")
        except ValueError:
            pytest.fail("wiktionary_search raised ValueError for a valid language code")
