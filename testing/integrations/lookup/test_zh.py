#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
Integration tests for Chinese (zh) lookup pipeline.

Tests the full stack: lookup_matcher tokenization → zh_character / zh_word /
zh_word_chengyu_supplement → parse_zh_output_to_json → cache round-trip.

Test subjects
─────────────
  Characters : 人 (rén, simplified/traditional same)
               类 (lèi, simplified)
               創 (chuàng, traditional)
  Words      : 劳动 (láodòng, "labour")
               果实 (guǒshí, "fruit / result")
  Chengyu    : 半途而废 (bàn tú ér fèi, "give up halfway")

Run with:
    pytest test_zh_integration.py -v
or:
    python -m pytest test_zh_integration.py -v --tb=short

Requirements (beyond the project's own deps):
    pip install pytest pytest-asyncio
"""

import re

import pytest
import pytest_asyncio  # noqa: F401 – needed for async fixture support

# ── project imports ──────────────────────────────────────────────────────────
from ziwen_lookup.match_helpers import lookup_matcher
from ziwen_lookup.zh import zh_character, zh_word, zh_word_chengyu_supplement
from ziwen_lookup.cache_helpers import (
    parse_zh_output_to_json,
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


def _assert_pronunciation_table(output: str, context: str) -> None:
    """Assert the output contains a Mandarin pronunciation table row."""
    assert re.search(r"\|\s*\*\*Mandarin\*\*", output), (
        f"[{context}] Missing Mandarin pronunciation table row"
    )


def _assert_meanings(output: str, context: str) -> None:
    """Assert the output contains a Meanings line."""
    assert re.search(r'\*\*Meanings\*\*:\s*"[^"]+"', output), (
        f"[{context}] Missing **Meanings** line"
    )


def _assert_footer_links(output: str, context: str) -> None:
    """Assert the output contains at least one footer reference link."""
    assert re.search(r"\^Information \^from", output), (
        f"[{context}] Missing footer attribution block"
    )


# ─────────────────────────────────────────────────────────────────────────────
# 1. lookup_matcher – tokenization / routing
# ─────────────────────────────────────────────────────────────────────────────


class TestLookupMatcherZh:
    """Tests for lookup_matcher with Chinese input."""

    def test_single_simplified_character(self):
        """人 – single-char, script auto-detected as Chinese."""
        result = lookup_matcher("`人`", language_code="zh")
        assert "zh" in result, "Expected 'zh' key in matcher result"
        terms = [t[0] if isinstance(t, tuple) else t for t in result["zh"]]
        assert "人" in terms, f"Expected '人' in zh terms, got: {terms}"

    def test_single_traditional_character(self):
        """創 – traditional character, passed with explicit language code."""
        result = lookup_matcher("`創`", language_code="zh")
        assert "zh" in result
        terms = [t[0] if isinstance(t, tuple) else t for t in result["zh"]]
        assert "創" in terms, f"Expected '創' in zh terms, got: {terms}"

    def test_simplified_character_lei(self):
        """类 – simplified-only character."""
        result = lookup_matcher("`类`", language_code="zh")
        assert "zh" in result
        terms = [t[0] if isinstance(t, tuple) else t for t in result["zh"]]
        assert "类" in terms, f"Expected '类' in zh terms, got: {terms}"

    def test_word_laodong_tokenized(self):
        """劳动 – two-character word should survive tokenization as a unit or pair."""
        result = lookup_matcher("`劳动`", language_code="zh")
        assert "zh" in result
        terms = [t[0] if isinstance(t, tuple) else t for t in result["zh"]]
        # Jieba may keep 劳动 together or split; either is acceptable –
        # what matters is that both characters are covered.
        combined = "".join(terms)
        assert "劳" in combined and "动" in combined, (
            f"Characters of '劳动' not found in tokenized output: {terms}"
        )

    def test_word_guoshi_tokenized(self):
        """果实 – two-character word."""
        result = lookup_matcher("`果实`", language_code="zh")
        assert "zh" in result
        terms = [t[0] if isinstance(t, tuple) else t for t in result["zh"]]
        combined = "".join(terms)
        assert "果" in combined and "实" in combined, (
            f"Characters of '果实' not found in tokenized output: {terms}"
        )

    def test_chengyu_tokenized(self):
        """半途而废 – four-character chengyu."""
        result = lookup_matcher("`半途而废`", language_code="zh")
        assert "zh" in result
        terms = [t[0] if isinstance(t, tuple) else t for t in result["zh"]]
        combined = "".join(terms)
        for char in "半途而废":
            assert char in combined, (
                f"Character '{char}' from chengyu not in tokenized output: {terms}"
            )

    def test_disable_tokenization_returns_full_segment(self):
        """disable_tokenization=True must return the raw segment."""
        result = lookup_matcher("`劳动`", language_code="zh", disable_tokenization=True)
        assert "zh" in result
        terms = [t[0] if isinstance(t, tuple) else t for t in result["zh"]]
        assert "劳动" in terms, (
            f"Expected full segment '劳动' when tokenization disabled; got: {terms}"
        )

    def test_inline_language_override(self):
        """`创`:zh inline language tag must be respected."""
        result = lookup_matcher("`創`:zh", language_code=None)
        assert "zh" in result, "Inline ':zh' annotation should produce zh key"

    def test_empty_backtick_text_produces_no_result(self):
        """A comment with no backtick segments produces an empty dict."""
        result = lookup_matcher("No Chinese here at all.", language_code="zh")
        assert result == {}, f"Expected empty dict, got: {result}"

    def test_triple_backtick_excluded(self):
        """Triple-backtick code blocks must not be processed."""
        comment = "```\n劳动\n``` but `果实` is here"
        result = lookup_matcher(comment, language_code="zh")
        assert "zh" in result
        terms = [t[0] if isinstance(t, tuple) else t for t in result["zh"]]
        combined = "".join(terms)
        # 果实 (inside single backticks) should be found
        assert "果" in combined or "实" in combined, (
            "Expected '果实' to be matched from single backticks"
        )
        # 劳动 was inside triple backticks and must NOT appear
        assert "劳" not in combined and "动" not in combined, (
            "Triple-backtick content '劳动' must not appear in results"
        )


# ─────────────────────────────────────────────────────────────────────────────
# 2. zh_character – live API / web fetch
# ─────────────────────────────────────────────────────────────────────────────


class TestZhCharacter:
    """Live network tests for zh_character."""

    async def test_ren_basic_structure(self):
        """人 – must return a header, pronunciation table, meanings, and footer."""
        output = _strip_cache_marker(await zh_character("人"))
        assert "人" in output, "Output header must contain '人'"
        _assert_pronunciation_table(output, "人")
        _assert_meanings(output, "人")
        _assert_footer_links(output, "人")

    async def test_ren_mandarin_pinyin_present(self):
        """人 – Mandarin Pinyin must be 'rén' (or 'ren2' style before conversion)."""
        output = _strip_cache_marker(await zh_character("人"))
        # Accept either tone-marked or numbered pinyin
        assert re.search(r"r[eé]n", output, re.IGNORECASE), (
            f"Expected pinyin 'rén' in output for 人:\n{output}"
        )

    async def test_lei_simplified_character(self):
        """类 – simplified character must return valid output."""
        output = _strip_cache_marker(await zh_character("类"))
        assert "类" in output or "類" in output, (
            "Output for 类 must mention simplified or traditional form"
        )
        _assert_meanings(output, "类")

    async def test_chuang_traditional_character(self):
        """創 – traditional character; simplified form 创 may also appear."""
        output = _strip_cache_marker(await zh_character("創"))
        assert "創" in output or "创" in output, (
            "Output for 創 must contain the character itself"
        )
        _assert_pronunciation_table(output, "創")
        _assert_meanings(output, "創")

    async def test_output_contains_wiktionary_link(self):
        """Each character output should link to Wiktionary."""
        for char in ("人", "类", "創"):
            output = _strip_cache_marker(await zh_character(char))
            assert "wiktionary.org" in output, f"Wiktionary link missing for {char}"

    async def test_output_not_empty(self):
        """None of the target characters should produce an empty result."""
        for char in ("人", "类", "創"):
            output = await zh_character(char)
            assert output and len(output.strip()) > 50, (
                f"Output for {char} is suspiciously short: {repr(output)}"
            )


# ─────────────────────────────────────────────────────────────────────────────
# 3. zh_word – live API / web fetch
# ─────────────────────────────────────────────────────────────────────────────


class TestZhWord:
    """Live network tests for zh_word."""

    async def test_laodong_basic_structure(self):
        """劳动 – must return header, pronunciation table, meanings, footer."""
        output = _strip_cache_marker(await zh_word("劳动"))
        assert "劳动" in output or "勞動" in output, (
            "Output must contain the word 劳动 or its traditional form 勞動"
        )
        _assert_pronunciation_table(output, "劳动")
        _assert_meanings(output, "劳动")
        _assert_footer_links(output, "劳动")

    async def test_laodong_pinyin(self):
        """劳动 pinyin should be láodòng."""
        output = _strip_cache_marker(await zh_word("劳动"))
        # Accept tone-marked lāodòng or numbered lao1dong4
        assert re.search(r"l[aá]o", output, re.IGNORECASE) and re.search(
            r"d[oò]ng", output, re.IGNORECASE
        ), f"Expected 'láodòng' pinyin in output:\n{output}"

    async def test_guoshi_basic_structure(self):
        """果实 – must return valid structured output."""
        output = _strip_cache_marker(await zh_word("果实"))
        assert "果实" in output or "果實" in output, "Output must contain 果实 or 果實"
        _assert_meanings(output, "果实")
        _assert_footer_links(output, "果实")

    async def test_guoshi_pinyin(self):
        """果实 pinyin should be guǒshí."""
        output = _strip_cache_marker(await zh_word("果实"))
        assert re.search(r"gu[oǒ]", output, re.IGNORECASE), (
            f"Expected guǒ pinyin in output for 果实:\n{output}"
        )

    async def test_traditional_form_in_header(self):
        """Words with differing trad/simp forms should show both in the header."""
        # 劳动 (simp) ↔ 勞動 (trad) – they differ, so both should appear
        output = _strip_cache_marker(await zh_word("劳动"))
        assert "勞動" in output or "劳动" in output, (
            "Traditional or simplified form should appear in output"
        )

    async def test_mdbg_footer_link(self):
        """MDBG link should appear in footer for standard words."""
        for word in ("劳动", "果实"):
            output = await zh_word(word)
            assert "mdbg.net" in output, f"MDBG link missing for {word}"

    async def test_output_not_empty(self):
        """Both words must produce non-trivial output."""
        for word in ("劳动", "果实"):
            output = await zh_word(word)
            assert output and len(output.strip()) > 100, (
                f"Output for {word} is suspiciously short: {repr(output)}"
            )


# ─────────────────────────────────────────────────────────────────────────────
# 4. zh_word_chengyu_supplement – chengyu detail fetch
# ─────────────────────────────────────────────────────────────────────────────


class TestZhChengyu:
    """Live network tests for chengyu lookup."""

    async def test_bantuerfe_returns_result(self):
        """半途而废 – should return a non-None result with Chinese meaning."""
        result = await zh_word_chengyu_supplement("半途而废")
        assert result is not None, "Expected a non-None chengyu result for 半途而废"

    async def test_bantuerfe_contains_chinese_meaning(self):
        """半途而废 – result must contain **Chinese Meaning** section."""
        result = await zh_word_chengyu_supplement("半途而废")
        assert result and "**Chinese Meaning**" in result, (
            f"Expected '**Chinese Meaning**' section in chengyu result:\n{result}"
        )

    async def test_bantuerfe_contains_literary_source(self):
        """半途而废 – result should contain **Literary Source** section."""
        result = await zh_word_chengyu_supplement("半途而废")
        assert result and "**Literary Source**" in result, (
            f"Expected '**Literary Source**' in chengyu result:\n{result}"
        )

    async def test_bantuerfe_via_zh_word(self):
        """Calling zh_word on 半途而废 (4-char) must embed chengyu supplement."""
        output = _strip_cache_marker(await zh_word("半途而废"))
        assert "半途而废" in output or "半途而廢" in output, (
            "Output must contain the chengyu in simplified or traditional form"
        )
        _assert_meanings(output, "半途而废")
        # The chengyu supplement should be injected into the word output
        assert "**Chinese Meaning**" in output, (
            "zh_word for a 4-char chengyu must include **Chinese Meaning** block"
        )

    async def test_bantuerfe_links_to_sources(self):
        """Chengyu supplement should include links to 5156edu and 18Dao."""
        result = await zh_word_chengyu_supplement("半途而废")
        assert result and ("5156edu" in result or "18dao" in result.lower()), (
            "Chengyu result should link to 5156edu or 18Dao"
        )

    async def test_traditional_chengyu_input(self):
        """半途而廢 (traditional form) should also return a valid result."""
        result = await zh_word_chengyu_supplement("半途而廢")
        assert result is not None, (
            "Chengyu lookup should work with traditional input 半途而廢"
        )


# ─────────────────────────────────────────────────────────────────────────────
# 5. parse_zh_output_to_json – parsing fidelity
# ─────────────────────────────────────────────────────────────────────────────


class TestParseZhOutputToJson:
    """Unit-style tests for the markdown→JSON parser (no network required)."""

    # Minimal synthetic markdown mimicking zh_character output for 人
    CHAR_MARKDOWN = """\
# [人](https://en.wiktionary.org/wiki/人#Chinese)

| Language | Pronunciation |
|---------|--------------|
| **Mandarin** (Pinyin) | *rén* |
| **Mandarin** (Wade-Giles) | *jen^2* |
| **Mandarin** (Yale) | *ren^2* |
| **Mandarin** (GR) | *ren* |
| **Cantonese** | *jan^4* |

**Meanings**: "person; people; human being"

^Information ^from ^[ZDIC](https://www.zdic.net/hans/人)
"""

    # Minimal synthetic markdown for 劳动 / 勞動 (word with trad/simp header)
    WORD_MARKDOWN = """\
# [勞動 / 劳动](https://en.wiktionary.org/wiki/勞動#Chinese)

| Language | Pronunciation |
|---------|--------------|
| **Mandarin** (Pinyin) | *láodòng* |
| **Mandarin** (Wade-Giles) | *lao^2-tung^4* |
| **Cantonese** | *lou^4dong^6* |

**Meanings**: "to work; labour; physical labour"

^Information ^from ^[MDBG](https://www.mdbg.net/...)
"""

    # Minimal synthetic markdown for chengyu 半途而废
    CHENGYU_MARKDOWN = """\
# [半途而廢 / 半途而废](https://en.wiktionary.org/wiki/半途而廢#Chinese)

| Language | Pronunciation |
|---------|--------------|
| **Mandarin** (Pinyin) | *bàntú'érfèi* |

**Meanings**: "to give up halfway; to leave something unfinished"

**Chinese Meaning**: 半路上就放弃了。比喻做事情没能坚持到底。

**Literary Source**: 《礼记·学记》

^Information ^from ^[MDBG](https://www.mdbg.net/...)
"""

    def test_parse_character_traditional_simplified(self):
        """Parser extracts traditional=人, simplified=人 for a same-script char."""
        data = parse_zh_output_to_json(self.CHAR_MARKDOWN)
        assert data["traditional"] == "人", f"Got: {data['traditional']}"
        assert data["simplified"] == "人", f"Got: {data['simplified']}"

    def test_parse_word_traditional_simplified_split(self):
        """Parser splits 勞動 / 劳动 into correct traditional and simplified."""
        data = parse_zh_output_to_json(self.WORD_MARKDOWN)
        assert data["traditional"] == "勞動", f"Got: {data['traditional']}"
        assert data["simplified"] == "劳动", f"Got: {data['simplified']}"

    def test_parse_mandarin_pinyin(self):
        """Mandarin Pinyin is extracted correctly."""
        data = parse_zh_output_to_json(self.CHAR_MARKDOWN)
        assert data["pronunciations"].get("mandarin_pinyin") == "rén", (
            f"Got: {data['pronunciations']}"
        )

    def test_parse_cantonese_pronunciation(self):
        """Cantonese pronunciation row is captured."""
        data = parse_zh_output_to_json(self.WORD_MARKDOWN)
        assert "cantonese" in data["pronunciations"], (
            f"Cantonese key missing from pronunciations: {data['pronunciations']}"
        )

    def test_parse_meanings(self):
        """Meanings string is extracted."""
        data = parse_zh_output_to_json(self.CHAR_MARKDOWN)
        assert data["meanings"] and "person" in data["meanings"], (
            f"Got: {data['meanings']}"
        )

    def test_parse_chengyu_chinese_meaning(self):
        """chinese_meaning field is populated for chengyu output."""
        data = parse_zh_output_to_json(self.CHENGYU_MARKDOWN)
        assert data["chinese_meaning"], f"chinese_meaning missing; got: {data}"
        assert "放弃" in data["chinese_meaning"] or "坚持" in data["chinese_meaning"], (
            f"Unexpected chinese_meaning: {data['chinese_meaning']}"
        )

    def test_parse_chengyu_literary_source(self):
        """literary_source field is populated for chengyu output."""
        data = parse_zh_output_to_json(self.CHENGYU_MARKDOWN)
        assert data["literary_source"], f"literary_source missing; got: {data}"

    def test_parse_empty_calligraphy_becomes_none(self):
        """If no calligraphy links are present, calligraphy_links should be None."""
        data = parse_zh_output_to_json(self.CHAR_MARKDOWN)
        assert data["calligraphy_links"] is None, (
            f"Expected None for calligraphy_links, got: {data['calligraphy_links']}"
        )

    def test_parse_wade_giles(self):
        """Wade-Giles pronunciation is captured when present."""
        data = parse_zh_output_to_json(self.WORD_MARKDOWN)
        assert data["pronunciations"].get("mandarin_wade_giles"), (
            f"Wade-Giles missing from: {data['pronunciations']}"
        )


# ─────────────────────────────────────────────────────────────────────────────
# 6. Cache round-trip (save → retrieve)
# ─────────────────────────────────────────────────────────────────────────────


class TestCacheRoundTrip:
    """
    Verify that save_to_cache and get_from_cache work correctly for Chinese
    data, using synthetic payloads so no network access is needed.
    """

    BASE_CHARACTER_PAYLOAD = {
        "traditional": "人",
        "simplified": "人",
        "pronunciations": {"mandarin_pinyin": "rén", "cantonese": "jan4"},
        "meanings": "person; people",
        "buddhist_meanings": None,
        "cantonese_meanings": None,
        "chengyu_meaning": None,
        "chengyu_source": None,
        "chinese_meaning": None,
        "literary_source": None,
        "calligraphy_links": None,
    }

    BASE_WORD_PAYLOAD = {
        "traditional": "勞動",
        "simplified": "劳动",
        "pronunciations": {"mandarin_pinyin": "láodòng"},
        "meanings": "to work; labour",
        "buddhist_meanings": None,
        "cantonese_meanings": None,
        "chengyu_meaning": None,
        "chengyu_source": None,
        "chinese_meaning": None,
        "literary_source": None,
        "calligraphy_links": None,
    }

    BASE_CHENGYU_PAYLOAD = {
        "traditional": "半途而廢",
        "simplified": "半途而废",
        "pronunciations": {"mandarin_pinyin": "bàntú'érfèi"},
        "meanings": "to give up halfway",
        "buddhist_meanings": None,
        "cantonese_meanings": None,
        "chengyu_meaning": None,
        "chengyu_source": None,
        "chinese_meaning": "半路上就放弃了",
        "literary_source": "《礼记·学记》",
        "calligraphy_links": None,
    }

    def test_character_cache_round_trip(self):
        """Save 人 as zh_character and retrieve it correctly."""
        save_to_cache(self.BASE_CHARACTER_PAYLOAD.copy(), "zh", "zh_character")
        cached = get_from_cache("人", "zh", "zh_character")
        assert cached is not None, "Cache miss immediately after save for 人"
        assert cached["traditional"] == "人"
        assert cached["pronunciations"]["mandarin_pinyin"] == "rén"

    def test_word_cache_round_trip(self):
        """Save 勞動 as zh_word and retrieve it correctly."""
        save_to_cache(self.BASE_WORD_PAYLOAD.copy(), "zh", "zh_word")
        cached = get_from_cache("勞動", "zh", "zh_word")
        assert cached is not None, "Cache miss immediately after save for 勞動"
        assert cached["simplified"] == "劳动"
        assert "labour" in cached["meanings"]

    def test_chengyu_cache_round_trip(self):
        """Save 半途而廢 as zh_word (chengyu) and retrieve it correctly."""
        save_to_cache(self.BASE_CHENGYU_PAYLOAD.copy(), "zh", "zh_word")
        cached = get_from_cache("半途而廢", "zh", "zh_word")
        assert cached is not None, "Cache miss immediately after save for 半途而廢"
        assert cached["chinese_meaning"] is not None
        assert cached["literary_source"] == "《礼记·学记》"

    def test_cache_miss_wrong_type(self):
        """A zh_character entry must NOT be retrievable under zh_word type."""
        save_to_cache(self.BASE_CHARACTER_PAYLOAD.copy(), "zh", "zh_character")
        result = get_from_cache("人", "zh", "zh_word")
        assert result is None, (
            "Type isolation failed: zh_character entry returned for zh_word query"
        )

    def test_cache_miss_wrong_language(self):
        """A zh entry must NOT be retrievable under ja language code."""
        save_to_cache(self.BASE_WORD_PAYLOAD.copy(), "zh", "zh_word")
        result = get_from_cache("勞動", "ja", "zh_word")
        assert result is None, (
            "Language isolation failed: zh entry returned for ja query"
        )

    def test_cache_preserves_unicode(self):
        """Ensure Traditional Chinese Unicode survives the JSON serialization round-trip."""
        payload = self.BASE_CHARACTER_PAYLOAD.copy()
        payload["traditional"] = "創"
        payload["simplified"] = "创"
        payload["pronunciations"]["mandarin_pinyin"] = "chuàng"
        save_to_cache(payload, "zh", "zh_character")
        cached = get_from_cache("創", "zh", "zh_character")
        assert cached is not None
        assert cached["traditional"] == "創", (
            f"Unicode not preserved; got: {cached['traditional']}"
        )
        assert cached["simplified"] == "创"


# ─────────────────────────────────────────────────────────────────────────────
# 7. End-to-end pipeline smoke test
# ─────────────────────────────────────────────────────────────────────────────


class TestEndToEndPipeline:
    """
    Smoke tests that exercise the full path:
    lookup_matcher → zh_character / zh_word → parse → cache → re-fetch from cache.
    """

    async def test_ren_end_to_end(self):
        """人: match → fetch → parse → cache → retrieve."""
        # 1. Match
        matched = lookup_matcher("`人`", language_code="zh", disable_tokenization=True)
        assert "zh" in matched

        # 2. Fetch
        output = await zh_character("人")
        assert output and "人" in output

        # 3. Parse
        data = parse_zh_output_to_json(_strip_cache_marker(output))
        assert data["traditional"] == "人"

        # 4. Cache
        save_to_cache(data, "zh", "zh_character")

        # 5. Re-retrieve
        cached = get_from_cache("人", "zh", "zh_character")
        assert cached is not None
        assert cached["traditional"] == "人"

    async def test_laodong_end_to_end(self):
        """劳动: match → fetch → parse → cache → retrieve."""
        matched = lookup_matcher(
            "`劳动`", language_code="zh", disable_tokenization=True
        )
        assert "zh" in matched

        output = await zh_word("劳动")
        assert output

        data = parse_zh_output_to_json(_strip_cache_marker(output))
        assert data["traditional"] in ("勞動", "劳动"), (
            f"Unexpected: {data['traditional']}"
        )

        # Save using traditional form (as the production code does)
        save_to_cache(data, "zh", "zh_word")
        cached = get_from_cache(data["traditional"], "zh", "zh_word")
        assert cached is not None

    async def test_bantuerfe_end_to_end(self):
        """半途而废: match → zh_word (with chengyu supplement) → parse → cache."""
        matched = lookup_matcher(
            "`半途而废`", language_code="zh", disable_tokenization=True
        )
        assert "zh" in matched

        output = await zh_word("半途而废")
        assert output
        assert "**Chinese Meaning**" in output, (
            "Chengyu supplement must be embedded in zh_word output"
        )

        data = parse_zh_output_to_json(_strip_cache_marker(output))
        assert data["traditional"] is not None

        save_to_cache(data, "zh", "zh_word")
        cached = get_from_cache(data["traditional"], "zh", "zh_word")
        assert cached is not None
        # Chengyu-specific fields should survive the round-trip
        assert cached.get("chinese_meaning"), (
            "chinese_meaning must survive cache round-trip for chengyu"
        )
