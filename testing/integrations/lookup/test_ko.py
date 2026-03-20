#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
Integration tests for Korean (ko) lookup pipeline.

Tests the full stack: lookup_matcher tokenization → ko_word / _ko_word_fetch
→ parse_ko_output_to_json → cache round-trip.

Test subjects
─────────────
  Sino-Korean : 대지 (大地  – earth, ground)                [noun, origin present]
                저주 (詛呪  – curse, hex)                   [noun, origin present]
                세계 (世界  – world)                        [noun, origin present]
  Native      : 불길 (– flames; ominous omen)              [noun, no origin]
                불   (– fire, flame)                       [noun, no origin]
                힘차다 (– vigorous, powerful, full of energy) [adjective, no origin]

Words drawn from 임을 위한 행진곡 (March for the Beloved):
    정의는 분화구의 불길처럼 힘차게 타온다
    대지의 저주받은 땅에 새 세계를 펼칠 때

Run with:
    pytest test_ko.py -v
or:
    python -m pytest test_ko.py -v --tb=short

Requirements (beyond the project's own deps):
    pip install pytest pytest-asyncio
"""

import re

import pytest

# ── project imports ───────────────────────────────────────────────────────────
from ziwen_lookup.match_helpers import lookup_matcher

# noinspection PyProtectedMember
from ziwen_lookup.ko import ko_word, _ko_word_fetch, _ko_search_raw
from ziwen_lookup.cache_helpers import (
    parse_ko_output_to_json,
    format_ko_word_from_cache,
    get_from_cache,
    save_to_cache,
)

# ── pytest-asyncio mode ───────────────────────────────────────────────────────
pytestmark = pytest.mark.asyncio


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


def _strip_cache_marker(text: str) -> str:
    """Remove the ' ^⚡' cache-hit suffix so assertions are source-agnostic."""
    return text.replace(" ^⚡", "").strip()


def _assert_romanization(output: str, context: str) -> None:
    """Assert a **Romanization:** line is present."""
    assert re.search(r"\*\*Romanization:\*\*", output), (
        f"[{context}] Missing **Romanization:** line"
    )


def _assert_meanings(output: str, context: str) -> None:
    """Assert a **Meanings**: block is present."""
    assert re.search(r"\*\*Meanings\*\*:", output), (
        f"[{context}] Missing **Meanings**: block"
    )


def _assert_footer_links(output: str, context: str) -> None:
    """Assert KRDict and Naver footer links are present."""
    assert "krdict" in output.lower(), f"[{context}] Missing KRDict footer link"
    assert "naver" in output.lower(), f"[{context}] Missing Naver footer link"


def _assert_wiktionary_link(output: str, term: str, context: str) -> None:
    """Assert the output links to Wiktionary for the given term."""
    assert f"wiktionary.org/wiki/{term}" in output, (
        f"[{context}] Missing Wiktionary link for {term}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# 1. lookup_matcher – tokenization / routing for Korean
# ─────────────────────────────────────────────────────────────────────────────


class TestLookupMatcherKo:
    """Tests for lookup_matcher with Korean input."""

    def test_bulgil_single_word(self):
        """`불길` – single Hangul word routed to 'ko'."""
        result = lookup_matcher("`불길`", language_code="ko")
        assert "ko" in result, "Expected 'ko' key for 불길"
        terms = [t[0] if isinstance(t, tuple) else t for t in result["ko"]]
        assert "불길" in terms, f"Expected '불길' in ko terms, got: {terms}"

    def test_bul_single_word(self):
        """`불` – single Hangul word routed to 'ko'."""
        result = lookup_matcher("`불`", language_code="ko")
        assert "ko" in result, "Expected 'ko' key for 불"
        terms = [t[0] if isinstance(t, tuple) else t for t in result["ko"]]
        assert "불" in terms, f"Expected '불' in ko terms, got: {terms}"

    def test_daiji_single_word(self):
        """`대지` – single Hangul word routed to 'ko'."""
        result = lookup_matcher("`대지`", language_code="ko")
        assert "ko" in result
        terms = [t[0] if isinstance(t, tuple) else t for t in result["ko"]]
        assert "대지" in terms, f"Expected '대지' in ko terms, got: {terms}"

    def test_segye_single_word(self):
        """`세계` – single Hangul word routed to 'ko'."""
        result = lookup_matcher("`세계`", language_code="ko")
        assert "ko" in result
        terms = [t[0] if isinstance(t, tuple) else t for t in result["ko"]]
        assert "세계" in terms, f"Expected '세계' in ko terms, got: {terms}"

    def test_inline_language_override(self):
        """`저주`:ko inline tag must route to 'ko' even with no language_code."""
        result = lookup_matcher("`저주`:ko", language_code=None)
        assert "ko" in result, "Inline ':ko' annotation should produce ko key"

    def test_explicit_flag_set_for_inline_lang(self):
        """Inline language spec sets is_explicit=True on the tuple."""
        result = lookup_matcher("`세계`:ko", language_code=None)
        assert "ko" in result
        tuples = result["ko"]
        assert all(isinstance(item, tuple) and item[1] is True for item in tuples), (
            f"Expected all tuples with is_explicit=True, got: {tuples}"
        )

    def test_no_explicit_flag_for_global_lang(self):
        """Global language_code should set is_explicit=False."""
        result = lookup_matcher("`불길`", language_code="ko")
        assert "ko" in result
        tuples = result["ko"]
        assert all(isinstance(item, tuple) and item[1] is False for item in tuples), (
            f"Expected all tuples with is_explicit=False, got: {tuples}"
        )

    def test_disable_tokenization_returns_full_segment(self):
        """disable_tokenization=True must return the raw segment."""
        for word in ("불", "대지", "세계"):
            result = lookup_matcher(
                f"`{word}`", language_code="ko", disable_tokenization=True
            )
            assert "ko" in result
            terms = [t[0] if isinstance(t, tuple) else t for t in result["ko"]]
            assert word in terms, (
                f"Expected full segment '{word}' when tokenization disabled; got: {terms}"
            )

    def test_empty_comment_returns_empty_dict(self):
        """A comment with no backtick segments should return an empty dict."""
        result = lookup_matcher("No Korean here.", language_code="ko")
        assert result == {}, f"Expected empty dict, got: {result}"

    def test_triple_backtick_excluded(self):
        """Triple-backtick code blocks must not be processed."""
        comment = "```\n세계\n``` but `저주` is here"
        result = lookup_matcher(comment, language_code="ko")
        assert "ko" in result
        terms = [t[0] if isinstance(t, tuple) else t for t in result["ko"]]
        combined = "".join(terms)
        assert "저주" in combined, "Expected '저주' from single-backtick segment"
        assert "세계" not in combined, (
            "Triple-backtick content '세계' must not appear in results"
        )


# ─────────────────────────────────────────────────────────────────────────────
# 2. _ko_search_raw – raw API results
# ─────────────────────────────────────────────────────────────────────────────


class TestKoSearchRaw:
    """Unit-style tests for _ko_search_raw (live API, no formatting)."""

    def test_bulgil_returns_list(self):
        """불길 – raw search must return a non-empty list."""
        data = _ko_search_raw("불길")
        assert isinstance(data, list) and len(data) > 0, (
            f"Expected non-empty list for 불길, got: {data}"
        )

    def test_bulgil_word_field(self):
        """불길 – every entry must have word == '불길'."""
        data = _ko_search_raw("불길")
        for entry in data:
            assert entry["word"] == "불길", (
                f"Entry word mismatch: expected '불길', got '{entry['word']}'"
            )

    def test_bulgil_no_origin(self):
        """불길 – native Korean word should have no origin field."""
        data = _ko_search_raw("불길")
        origins = [e.get("origin") for e in data if e.get("origin")]
        assert not origins, (
            f"Expected no origin for native Korean 불길; got: {origins}"
        )

    def test_daiji_is_noun(self):
        """대지 – part_of_speech should be '명사' (noun)."""
        data = _ko_search_raw("대지")
        pos_values = [e["part_of_speech"] for e in data]
        assert "명사" in pos_values, (
            f"Expected '명사' in part_of_speech for 대지; got: {pos_values}"
        )

    def test_himchada_is_adjective(self):
        """힘차다 – part_of_speech should be '형용사' (adjective)."""
        data = _ko_search_raw("힘차다")
        pos_values = [e["part_of_speech"] for e in data]
        assert "형용사" in pos_values, (
            f"Expected '형용사' in part_of_speech for 힘차다; got: {pos_values}"
        )

    def test_himchada_no_origin(self):
        """힘차다 – native Korean word should have no origin field."""
        data = _ko_search_raw("힘차다")
        origins = [e.get("origin") for e in data if e.get("origin")]
        assert not origins, (
            f"Expected no origin for native Korean 힘차다; got: {origins}"
        )

    def test_definitions_have_english_translations(self):
        """세계 – definitions must include at least one 영어 translation."""
        data = _ko_search_raw("세계")
        english_found = False
        for entry in data:
            for defn in entry.get("definitions", []):
                for t in defn.get("translations", []):
                    if t.get("language") == "영어":
                        english_found = True
        assert english_found, "Expected at least one 영어 translation for 세계"

    def test_invalid_word_returns_empty_list(self):
        """A nonsense Hangul string should return an empty list gracefully."""
        data = _ko_search_raw("ㅎㅎㅎㅎ")
        assert data == [], f"Expected empty list for invalid input, got: {data}"


# ─────────────────────────────────────────────────────────────────────────────
# 3. _ko_word_fetch – formatted output (cache-bypassed)
# ─────────────────────────────────────────────────────────────────────────────


class TestKoWordFetch:
    """Live API tests against _ko_word_fetch (bypasses cache)."""

    def test_bulgil_basic_structure(self):
        """불길 – output must have header, romanization, meanings, and footer."""
        output = _ko_word_fetch("불길")
        assert output is not None, "_ko_word_fetch returned None for 불길"
        assert "불길" in output, "Output header must contain '불길'"
        _assert_romanization(output, "불길")
        _assert_meanings(output, "불길")
        _assert_footer_links(output, "불길")

    def test_bulgil_wiktionary_link(self):
        """불길 – output must link to Wiktionary."""
        output = _ko_word_fetch("불길")
        assert output is not None
        _assert_wiktionary_link(output, "불길", "불길")

    def test_bulgil_no_origin_link(self):
        """불길 – native Korean word must not have a hanja origin link."""
        output = _ko_word_fetch("불길")
        assert output is not None
        assert not re.search(
            r"\[.+]\(https://en\.wiktionary\.org/wiki/.+\):\s", output
        ), "Native Korean word 불길 must not have a hanja origin link"

    def test_bul_basic_structure(self):
        """불 – native Korean noun must have romanization, meanings, and footer."""
        output = _ko_word_fetch("불")
        assert output is not None, "_ko_word_fetch returned None for 불"
        assert "불" in output
        _assert_romanization(output, "불")
        _assert_meanings(output, "불")
        _assert_footer_links(output, "불")

    def test_daiji_pos_noun(self):
        """대지 – output must include a Noun POS header."""
        output = _ko_word_fetch("대지")
        assert output is not None, "_ko_word_fetch returned None for 대지"
        assert re.search(r"##### \*Noun\*", output), (
            f"Expected '##### *Noun*' section for 대지:\n{output}"
        )

    def test_daiji_origin_in_output(self):
        """대지 – sino-Korean origin must appear in the definitions."""
        output = _ko_word_fetch("대지")
        assert output is not None
        assert re.search(r"\[.+]\(https://en\.wiktionary\.org/wiki/.+\):", output), (
            "Expected hanja origin link in definitions for 대지"
        )

    def test_juju_basic_structure(self):
        """저주 – output must have header, romanization, meanings, and footer."""
        output = _ko_word_fetch("저주")
        assert output is not None, "_ko_word_fetch returned None for 저주"
        assert "저주" in output
        _assert_romanization(output, "저주")
        _assert_meanings(output, "저주")
        _assert_footer_links(output, "저주")

    def test_segye_basic_structure(self):
        """세계 – output must have header, romanization, meanings, and footer."""
        output = _ko_word_fetch("세계")
        assert output is not None, "_ko_word_fetch returned None for 세계"
        assert "세계" in output
        _assert_romanization(output, "세계")
        _assert_meanings(output, "세계")
        _assert_footer_links(output, "세계")

    def test_himchada_basic_structure(self):
        """힘차다 – native Korean adjective must have romanization and meanings."""
        output = _ko_word_fetch("힘차다")
        assert output is not None, "_ko_word_fetch returned None for 힘차다"
        assert "힘차다" in output
        _assert_romanization(output, "힘차다")
        _assert_meanings(output, "힘차다")

    def test_himchada_pos_adjective(self):
        """힘차다 – output must include an Adjective POS header."""
        output = _ko_word_fetch("힘차다")
        assert output is not None
        assert re.search(r"##### \*Adjective\*", output), (
            f"Expected '##### *Adjective*' section for 힘차다:\n{output}"
        )

    def test_himchada_no_origin_link(self):
        """힘차다 – native word must not have a hanja origin link."""
        output = _ko_word_fetch("힘차다")
        assert output is not None
        # The origin-prefixed pattern should be absent
        assert not re.search(
            r"\[.+]\(https://en\.wiktionary\.org/wiki/.+\):\s", output
        ), "Native Korean word 힘차다 must not have a hanja origin link"

    def test_invalid_word_returns_none(self):
        """A nonsense Hangul string should return None gracefully."""
        result = _ko_word_fetch("ㅎㅎㅎㅎ")
        assert result is None, (
            f"Expected None for invalid input, got: {repr(result)}"
        )

    def test_output_not_short(self):
        """All target words must produce non-trivial output."""
        for word in ("불길", "불", "대지", "저주", "세계", "힘차다"):
            output = _ko_word_fetch(word)
            assert output and len(output.strip()) > 50, (
                f"Output for {word} is suspiciously short: {repr(output)}"
            )


# ─────────────────────────────────────────────────────────────────────────────
# 4. parse_ko_output_to_json – parsing fidelity
# ─────────────────────────────────────────────────────────────────────────────


class TestParseKoOutputToJson:
    """Unit-style tests against synthetic Markdown (no network required)."""

    BULGIL_MARKDOWN = """\
# [불길](https://en.wiktionary.org/wiki/불길#Korean)

##### *Noun*

**Romanization:** *bulgil*

**Meanings**:
* flames; blaze; fire

^Information ^from ^[KRDict](https://krdict.korean.go.kr/eng/dicMarinerSearch/search?nation=eng&nationCode=6\
&ParaWordNo=&mainSearchWord=불길&lang=eng) ^| ^[Naver](https://korean.dict.naver.com/koendict/#/search?query=불길) \
^| ^[Collins](https://www.collinsdictionary.com/dictionary/korean-english/불길)
"""

    HIMCHADA_MARKDOWN = """\
# [힘차다](https://en.wiktionary.org/wiki/힘차다#Korean)

##### *Adjective*

**Romanization:** *himchada*

**Meanings**:
* full of energy; powerful; vigorous

^Information ^from ^[KRDict](https://krdict.korean.go.kr/eng/dicMarinerSearch/search?nation=eng&nationCode=6\
&ParaWordNo=&mainSearchWord=힘차다&lang=eng) ^| ^[Naver](https://korean.dict.naver.com/koendict/#/search?query=힘차다) \
^| ^[Collins](https://www.collinsdictionary.com/dictionary/korean-english/힘차다)
"""

    SEGYE_MARKDOWN = """\
# [세계](https://en.wiktionary.org/wiki/세계#Korean)

##### *Noun*

**Romanization:** *segye*

**Meanings**:
* [世界](https://en.wiktionary.org/wiki/世界): the world; the earth; the globe

^Information ^from ^[KRDict](https://krdict.korean.go.kr/eng/dicMarinerSearch/search?nation=eng&nationCode=6\
&ParaWordNo=&mainSearchWord=세계&lang=eng) ^| ^[Naver](https://korean.dict.naver.com/koendict/#/search?query=세계) \
^| ^[Collins](https://www.collinsdictionary.com/dictionary/korean-english/세계)
"""

    def test_parse_bulgil_word_field(self):
        """Parser extracts the word correctly from the header."""
        data = parse_ko_output_to_json(self.BULGIL_MARKDOWN)
        assert data["word"] == "불길", f"Got: {data['word']}"

    def test_parse_bulgil_has_entries(self):
        """Parser produces a non-empty entries list for 불길."""
        data = parse_ko_output_to_json(self.BULGIL_MARKDOWN)
        assert data.get("entries") and len(data["entries"]) > 0, (
            f"Expected non-empty entries for 불길; got: {data}"
        )

    def test_parse_bulgil_part_of_speech(self):
        """Parser extracts part_of_speech as 'noun' inside entries for 불길."""
        data = parse_ko_output_to_json(self.BULGIL_MARKDOWN)
        pos_values = [e["part_of_speech"] for e in data.get("entries", [])]
        assert "noun" in pos_values, (
            f"Expected 'noun' in entries part_of_speech for 불길; got: {pos_values}"
        )

    def test_parse_bulgil_romanization(self):
        """Parser extracts romanization for 불길."""
        data = parse_ko_output_to_json(self.BULGIL_MARKDOWN)
        assert data.get("romanization"), "romanization should not be None/empty"
        assert "bulgil" in data["romanization"], (
            f"Expected 'bulgil' in romanization, got: {data['romanization']}"
        )

    def test_parse_bulgil_meanings(self):
        """Parser extracts meanings inside entries for 불길."""
        data = parse_ko_output_to_json(self.BULGIL_MARKDOWN)
        all_defs = [
            d["definition"]
            for e in data.get("entries", [])
            for d in e.get("meanings", [])
        ]
        assert all_defs, "meanings list should not be empty for 불길"
        combined = " ".join(all_defs).lower()
        assert any(w in combined for w in ("flame", "blaze", "fire")), (
            f"Expected flame/blaze/fire in meanings for 불길; got: {all_defs}"
        )

    def test_parse_himchada_part_of_speech(self):
        """Parser extracts part_of_speech as 'adjective' inside entries for 힘차다."""
        data = parse_ko_output_to_json(self.HIMCHADA_MARKDOWN)
        pos_values = [e["part_of_speech"] for e in data.get("entries", [])]
        assert "adjective" in pos_values, (
            f"Expected 'adjective' in entries part_of_speech for 힘차다; got: {pos_values}"
        )

    def test_parse_himchada_romanization(self):
        """Parser extracts romanization for 힘차다."""
        data = parse_ko_output_to_json(self.HIMCHADA_MARKDOWN)
        assert data.get("romanization") and "himchada" in data["romanization"], (
            f"Expected 'himchada' in romanization, got: {data.get('romanization')}"
        )

    def test_parse_segye_word_field(self):
        """Parser extracts the word correctly for 세계."""
        data = parse_ko_output_to_json(self.SEGYE_MARKDOWN)
        assert data["word"] == "세계", f"Got: {data['word']}"

    def test_parse_segye_meanings(self):
        """Parser extracts meanings inside entries for 세계."""
        data = parse_ko_output_to_json(self.SEGYE_MARKDOWN)
        all_defs = [
            d["definition"]
            for e in data.get("entries", [])
            for d in e.get("meanings", [])
        ]
        assert all_defs, "meanings list should not be empty for 세계"
        assert any("world" in d.lower() for d in all_defs), (
            f"Expected 'world' in meanings for 세계; got: {all_defs}"
        )


# ─────────────────────────────────────────────────────────────────────────────
# 5. Cache round-trip (save → retrieve)
# ─────────────────────────────────────────────────────────────────────────────


class TestCacheRoundTrip:
    """
    Verify save_to_cache / get_from_cache for Korean data using synthetic
    payloads — no network access required.
    """

    BULGIL_PAYLOAD = {
        "word": "불길",
        "romanization": "bulgil",
        "entries": [
            {
                "part_of_speech": "noun",
                "meanings": [
                    {"definition": "A streak of fire burning furiously."},
                    {"definition": "(figurative) A strong surge of feeling or passion."},
                ],
            }
        ],
    }

    BUL_PAYLOAD = {
        "word": "불",
        "romanization": "bul",
        "entries": [
            {
                "part_of_speech": "noun",
                "meanings": [
                    {"definition": "Burning heat and light produced by combustion; fire; flame."},
                ],
            }
        ],
    }

    HIMCHADA_PAYLOAD = {
        "word": "힘차다",
        "romanization": "himchada",
        "entries": [
            {
                "part_of_speech": "adjective",
                "meanings": [
                    {"definition": "Lively and energetic."},
                ],
            }
        ],
    }

    SEGYE_PAYLOAD = {
        "word": "세계",
        "romanization": "segye",
        "entries": [
            {
                "part_of_speech": "noun",
                "meanings": [
                    {"definition": "The earth or globe considered as a planet; the world."},
                ],
            }
        ],
    }

    def test_bulgil_round_trip(self):
        """Save 불길 and retrieve it intact."""
        save_to_cache(self.BULGIL_PAYLOAD.copy(), "ko", "ko_word")
        cached = get_from_cache("불길", "ko", "ko_word")
        assert cached is not None, "Cache miss immediately after save for 불길"
        assert cached["word"] == "불길"
        assert cached["entries"][0]["part_of_speech"] == "noun"

    def test_bul_round_trip(self):
        """Save 불 and retrieve it intact."""
        save_to_cache(self.BUL_PAYLOAD.copy(), "ko", "ko_word")
        cached = get_from_cache("불", "ko", "ko_word")
        assert cached is not None, "Cache miss immediately after save for 불"
        assert cached["word"] == "불"
        assert cached["romanization"] == "bul"

    def test_himchada_round_trip(self):
        """Save 힘차다 and retrieve it intact."""
        save_to_cache(self.HIMCHADA_PAYLOAD.copy(), "ko", "ko_word")
        cached = get_from_cache("힘차다", "ko", "ko_word")
        assert cached is not None, "Cache miss immediately after save for 힘차다"
        assert cached["romanization"] == "himchada"
        assert cached["entries"][0]["part_of_speech"] == "adjective"

    def test_segye_round_trip(self):
        """Save 세계 and retrieve it intact."""
        save_to_cache(self.SEGYE_PAYLOAD.copy(), "ko", "ko_word")
        cached = get_from_cache("세계", "ko", "ko_word")
        assert cached is not None, "Cache miss immediately after save for 세계"
        assert any(
            "world" in d["definition"].lower()
            for d in cached["entries"][0]["meanings"]
        )

    def test_language_isolation_ko_vs_ja(self):
        """A ko entry must NOT be retrievable under ja language code."""
        save_to_cache(self.BULGIL_PAYLOAD.copy(), "ko", "ko_word")
        result = get_from_cache("불길", "ja", "ko_word")
        assert result is None, (
            "Language isolation failed: ko entry returned for ja query"
        )

    def test_unicode_preserved(self):
        """Hangul key must survive JSON serialization."""
        save_to_cache(self.SEGYE_PAYLOAD.copy(), "ko", "ko_word")
        cached = get_from_cache("세계", "ko", "ko_word")
        assert cached is not None
        assert cached["word"] == "세계", (
            f"Unicode not preserved; got: {cached['word']}"
        )

    def test_format_word_from_cache_roundtrip(self):
        """format_ko_word_from_cache should produce valid markdown from cached data."""
        save_to_cache(self.BULGIL_PAYLOAD.copy(), "ko", "ko_word")
        cached = get_from_cache("불길", "ko", "ko_word")
        rendered = format_ko_word_from_cache(cached)
        assert "불길" in rendered
        assert "krdict" in rendered.lower() or "naver" in rendered.lower(), (
            "Rendered output must include footer attribution links"
        )


# ─────────────────────────────────────────────────────────────────────────────
# 6. End-to-end pipeline smoke tests
# ─────────────────────────────────────────────────────────────────────────────


class TestEndToEndPipeline:
    """
    Smoke tests for the full path:
    lookup_matcher → _ko_word_fetch (cache-bypassed) → parse → cache → re-fetch.

    Integration tests call _ko_word_fetch directly to bypass the cache layer,
    ensuring fresh API results are exercised on every run.
    """

    def test_bulgil_end_to_end(self):
        """불길: match → fetch (bypassing cache) → parse → cache → retrieve."""
        # 1. Match
        matched = lookup_matcher("`불길`", language_code="ko", disable_tokenization=True)
        assert "ko" in matched

        # 2. Fetch fresh from API (bypass cache)
        output = _ko_word_fetch("불길")
        assert output and "불길" in output

        # 3. Parse
        data = parse_ko_output_to_json(_strip_cache_marker(output))
        assert data.get("word") == "불길"
        assert data.get("entries") and data["entries"][0]["part_of_speech"] == "noun"

        # 4. Cache
        save_to_cache(data, "ko", "ko_word")

        # 5. Re-retrieve
        cached = get_from_cache("불길", "ko", "ko_word")
        assert cached is not None
        assert cached["word"] == "불길"

    def test_himchada_end_to_end(self):
        """힘차다: match → fetch (bypassing cache) → parse → cache → retrieve."""
        matched = lookup_matcher(
            "`힘차다`", language_code="ko", disable_tokenization=True
        )
        assert "ko" in matched

        output = _ko_word_fetch("힘차다")
        assert output and "힘차다" in output

        data = parse_ko_output_to_json(_strip_cache_marker(output))
        assert data.get("word") == "힘차다"
        assert data.get("entries") and data["entries"][0]["part_of_speech"] == "adjective"

        save_to_cache(data, "ko", "ko_word")
        cached = get_from_cache("힘차다", "ko", "ko_word")
        assert cached is not None
        assert cached["word"] == "힘차다"

    def test_cache_hit_returns_cache_marker(self):
        """After a word is cached, ko_word must return the ^⚡ marker."""
        # Prime the cache via internal fetch, then save explicitly
        output_first = _ko_word_fetch("세계")
        assert output_first is not None
        data = parse_ko_output_to_json(_strip_cache_marker(output_first))
        save_to_cache(data, "ko", "ko_word")

        # Public ko_word call must now hit the cache and append ^⚡
        output_second = ko_word("세계")
        assert output_second and "^⚡" in output_second, (
            "Expected '^⚡' cache marker on ko_word call after manual cache prime for 세계"
        )
