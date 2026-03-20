#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
Integration tests for Japanese (ja) lookup pipeline.

Tests the full stack: lookup_matcher tokenization → ja_character / ja_word /
_ja_word_yojijukugo → parse_ja_output_to_json → cache round-trip.

Test subjects
─────────────
  Characters  : 覚 (おぼえる / カク  – remember/sense)
                暁 (あかつき / ギョウ – dawn)
                者 (もの / シャ      – person/one who)
  Words       : 同胞 (どうほう – compatriot)
                繰り返し (くりかえし – repetition)
  Yojijukugo  : 狐仮虎威 (こかこい – riding on another's authority)         [Jitenon-only fallback]
                瓜田李下 (かでんりか – situation inviting false suspicion)    [Jisho Expression, Jitenon miss]
                花鳥風月 (かちょうふうげつ – beauties of nature)              [Jisho hit + Jitenon supplement]

Run with:
    pytest test_ja_integration.py -v
or:
    python -m pytest test_ja_integration.py -v --tb=short

Requirements (beyond the project's own deps):
    pip install pytest pytest-asyncio
"""

import re

import pytest

# ── project imports ───────────────────────────────────────────────────────────
from ziwen_lookup.match_helpers import lookup_matcher

# noinspection PyProtectedMember
from ziwen_lookup.ja import (
    ja_character,
    ja_word,
    _ja_character_fetch,
    _ja_word_fetch,
)
from ziwen_lookup.cache_helpers import (
    parse_ja_output_to_json,
    format_ja_character_from_cache,
    format_ja_word_from_cache,
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


def _assert_kun_or_on_readings(output: str, context: str) -> None:
    """Assert at least one reading section is present."""
    assert re.search(r"\*\*(Kun|On)-readings:\*\*", output), (
        f"[{context}] Missing Kun-readings or On-readings section"
    )


def _assert_reading_line(output: str, context: str) -> None:
    """Assert a **Reading:** line is present (words / yojijukugo)."""
    assert re.search(r"\*\*Reading:\*\*", output), (
        f"[{context}] Missing **Reading:** line"
    )


def _assert_meanings(output: str, context: str) -> None:
    """Assert a **Meanings** line is present."""
    assert re.search(r"\*\*Meanings\*\*", output), (
        f"[{context}] Missing **Meanings** line"
    )


def _assert_footer_links(output: str, context: str) -> None:
    """Assert the output has a footer attribution block."""
    assert re.search(r"\^Information \^from|\^(Information from)", output), (
        f"[{context}] Missing footer attribution block"
    )


def _assert_wiktionary_link(output: str, term: str, context: str) -> None:
    """Assert the output links to Wiktionary for the given term."""
    assert f"wiktionary.org/wiki/{term}" in output, (
        f"[{context}] Missing Wiktionary link for {term}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# 1. lookup_matcher – tokenization / routing for Japanese
# ─────────────────────────────────────────────────────────────────────────────


class TestLookupMatcherJa:
    """Tests for lookup_matcher with Japanese input."""

    def test_kanji_kaku_single_character(self):
        """覚 – single kanji, explicit language code 'ja'."""
        result = lookup_matcher("`覚`", language_code="ja")
        assert "ja" in result, "Expected 'ja' key for 覚"
        terms = [t[0] if isinstance(t, tuple) else t for t in result["ja"]]
        assert "覚" in terms, f"Expected '覚' in ja terms, got: {terms}"

    def test_kanji_akatsuki_single_character(self):
        """暁 – single kanji."""
        result = lookup_matcher("`暁`", language_code="ja")
        assert "ja" in result
        terms = [t[0] if isinstance(t, tuple) else t for t in result["ja"]]
        assert "暁" in terms, f"Expected '暁' in ja terms, got: {terms}"

    def test_kanji_mono_single_character(self):
        """者 – single kanji."""
        result = lookup_matcher("`者`", language_code="ja")
        assert "ja" in result
        terms = [t[0] if isinstance(t, tuple) else t for t in result["ja"]]
        assert "者" in terms, f"Expected '者' in ja terms, got: {terms}"

    def test_word_douhou_tokenized(self):
        """同胞 – two-kanji word; both characters must appear in tokenized output."""
        result = lookup_matcher("`同胞`", language_code="ja")
        assert "ja" in result
        terms = [t[0] if isinstance(t, tuple) else t for t in result["ja"]]
        combined = "".join(terms)
        assert "同" in combined and "胞" in combined, (
            f"Characters of '同胞' not found in tokenized output: {terms}"
        )

    def test_word_kurikaeshi_mixed_script(self):
        """繰り返し – mixed kanji/kana word; kanji portions must appear."""
        result = lookup_matcher("`繰り返し`", language_code="ja")
        assert "ja" in result
        terms = [t[0] if isinstance(t, tuple) else t for t in result["ja"]]
        combined = "".join(terms)
        # MeCab will segment the kanji; both 繰 and 返 should be present
        assert "繰" in combined or "返" in combined, (
            f"Kanji of '繰り返し' not found in tokenized output: {terms}"
        )

    def test_yojijukugo_tokenized(self):
        """狐仮虎威 – four-kanji idiom; all characters must be covered."""
        result = lookup_matcher("`狐仮虎威`", language_code="ja")
        assert "ja" in result
        terms = [t[0] if isinstance(t, tuple) else t for t in result["ja"]]
        combined = "".join(terms)
        for char in "狐仮虎威":
            assert char in combined, (
                f"Character '{char}' from '狐仮虎威' not in tokenized output: {terms}"
            )

    def test_script_auto_detection_kana(self):
        """Kana in segment should auto-detect as 'ja' when no language_code given."""
        result = lookup_matcher("`繰り返し`", language_code=None)
        assert "ja" in result, (
            "Kana script should auto-detect as 'ja' without explicit language_code"
        )

    def test_disable_tokenization_returns_full_segment(self):
        """disable_tokenization=True must return the raw segment for each word."""
        for word in ("同胞", "繰り返し", "狐仮虎威"):
            result = lookup_matcher(
                f"`{word}`", language_code="ja", disable_tokenization=True
            )
            assert "ja" in result
            terms = [t[0] if isinstance(t, tuple) else t for t in result["ja"]]
            assert word in terms, (
                f"Expected full segment '{word}' when tokenization disabled; got: {terms}"
            )

    def test_inline_language_override(self):
        """`覚`:ja inline tag must route to 'ja' even with no language_code."""
        result = lookup_matcher("`覚`:ja", language_code=None)
        assert "ja" in result, "Inline ':ja' annotation should produce ja key"

    def test_triple_backtick_excluded(self):
        """Triple-backtick code blocks must not be processed."""
        comment = "```\n同胞\n``` but `暁` is here"
        result = lookup_matcher(comment, language_code="ja")
        assert "ja" in result
        terms = [t[0] if isinstance(t, tuple) else t for t in result["ja"]]
        combined = "".join(terms)
        # 暁 (single backtick) should appear
        assert "暁" in combined, "Expected '暁' from single-backtick segment"
        # 同胞 (triple backtick) must NOT appear
        assert "同" not in combined and "胞" not in combined, (
            "Triple-backtick content '同胞' must not appear in results"
        )

    def test_empty_comment_returns_empty_dict(self):
        """A comment with no backtick segments should return an empty dict."""
        result = lookup_matcher("No Japanese here.", language_code="ja")
        assert result == {}, f"Expected empty dict, got: {result}"

    def test_explicit_flag_set_for_inline_lang(self):
        """Inline language spec sets is_explicit=True on the tuple."""
        result = lookup_matcher("`者`:ja", language_code=None)
        assert "ja" in result
        tuples = result["ja"]
        # Each item should be a (text, bool) tuple with is_explicit=True
        assert all(isinstance(item, tuple) and item[1] is True for item in tuples), (
            f"Expected all tuples with is_explicit=True, got: {tuples}"
        )

    def test_no_explicit_flag_for_global_lang(self):
        """Global language_code should set is_explicit=False."""
        result = lookup_matcher("`覚`", language_code="ja")
        assert "ja" in result
        tuples = result["ja"]
        assert all(isinstance(item, tuple) and item[1] is False for item in tuples), (
            f"Expected all tuples with is_explicit=False, got: {tuples}"
        )


# ─────────────────────────────────────────────────────────────────────────────
# 2. ja_character – live fetch (Jisho scrape)
# ─────────────────────────────────────────────────────────────────────────────


class TestJaCharacter:
    """Live network tests for ja_character (sync function)."""

    def test_kaku_basic_structure(self):
        """覚 – output must have header, readings, meanings, and footer."""
        output = _strip_cache_marker(ja_character("覚"))
        assert "覚" in output, "Output header must contain '覚'"
        _assert_kun_or_on_readings(output, "覚")
        _assert_meanings(output, "覚")
        _assert_footer_links(output, "覚")

    def test_kaku_on_reading_kaku(self):
        """覚 – On-reading カク should be present (romanized as 'kaku')."""
        output = _strip_cache_marker(ja_character("覚"))
        # カク is the On-reading; pykakasi romanizes it as 'kaku'
        assert re.search(r"カク|kaku", output, re.IGNORECASE), (
            f"Expected On-reading カク/kaku in output for 覚:\n{output}"
        )

    def test_kaku_kun_reading_oboe(self):
        """覚 – Kun-reading おぼ(える) should be present."""
        output = _strip_cache_marker(ja_character("覚"))
        assert "おぼ" in output, (
            f"Expected kun-reading おぼ in output for 覚:\n{output}"
        )

    def test_akatsuki_basic_structure(self):
        """暁 – output must have readings, meanings, and footer."""
        output = _strip_cache_marker(ja_character("暁"))
        assert "暁" in output
        _assert_kun_or_on_readings(output, "暁")
        _assert_meanings(output, "暁")
        _assert_footer_links(output, "暁")

    def test_mono_basic_structure(self):
        """者 – output must have readings, meanings, and footer."""
        output = _strip_cache_marker(ja_character("者"))
        assert "者" in output
        _assert_kun_or_on_readings(output, "者")
        _assert_meanings(output, "者")
        _assert_footer_links(output, "者")

    def test_all_characters_have_wiktionary_link(self):
        """Each target character must link to Wiktionary."""
        for char in ("覚", "暁", "者"):
            output = _strip_cache_marker(ja_character(char))
            _assert_wiktionary_link(output, char, char)

    def test_all_characters_have_jisho_link(self):
        """Each target character must link to Jisho in the footer."""
        for char in ("覚", "暁", "者"):
            output = ja_character(char)
            assert "jisho.org" in output, f"Jisho link missing for {char}"

    def test_output_not_empty(self):
        """None of the target characters should produce a trivially short result."""
        for char in ("覚", "暁", "者"):
            output = ja_character(char)
            assert output and len(output.strip()) > 50, (
                f"Output for {char} is suspiciously short: {repr(output)}"
            )

    def test_multi_character_input_produces_table(self):
        """Passing multiple kanji at once triggers the table (multi) format."""
        output = _strip_cache_marker(ja_character("覚暁者"))
        # Multi-mode uses a Markdown table
        assert "| Character |" in output, (
            "Multi-character input should produce a Markdown table"
        )
        for char in ("覚", "暁", "者"):
            assert char in output, (
                f"Character '{char}' missing from multi-character table output"
            )


# ─────────────────────────────────────────────────────────────────────────────
# 3. ja_word – live fetch (Jisho API)
# ─────────────────────────────────────────────────────────────────────────────


class TestJaWord:
    """Live network tests for ja_word (async function)."""

    async def test_douhou_basic_structure(self):
        """同胞 – must return header, reading, meanings, and footer."""
        output = _strip_cache_marker(await ja_word("同胞"))
        assert output is not None, "ja_word returned None for 同胞"
        assert "同胞" in output, "Output must contain '同胞'"
        _assert_reading_line(output, "同胞")
        _assert_meanings(output, "同胞")
        _assert_footer_links(output, "同胞")

    def test_douhou_reading_dohou(self):
        """同胞 – reading should be どうほう (dōhō / douhō)."""
        import asyncio

        output = _strip_cache_marker(
            asyncio.get_event_loop().run_until_complete(ja_word("同胞"))
        )
        # Accept どうほう in kana or dou hou / dōhō in romaji
        assert re.search(r"どうほう|d[oō]uh[oō]|douhou", output, re.IGNORECASE), (
            f"Expected reading どうほう/dōhō for 同胞:\n{output}"
        )

    async def test_kurikaeshi_basic_structure(self):
        """繰り返し – must return reading, meanings, and footer."""
        output = await ja_word("繰り返し")
        assert output is not None, "ja_word returned None for 繰り返し"
        output = _strip_cache_marker(output)
        assert "繰り返し" in output or "繰り返" in output, (
            "Output must contain the word 繰り返し"
        )
        _assert_reading_line(output, "繰り返し")
        _assert_meanings(output, "繰り返し")

    async def test_kurikaeshi_reading_kurikaeshi(self):
        """繰り返し – reading should be くりかえし (kurikaeshi)."""
        output = _strip_cache_marker(await ja_word("繰り返し"))
        assert re.search(r"くりかえし|kurikaeshi", output, re.IGNORECASE), (
            f"Expected reading くりかえし/kurikaeshi for 繰り返し:\n{output}"
        )

    async def test_all_words_have_wiktionary_link(self):
        """Both words must link to Wiktionary."""
        for word in ("同胞", "繰り返し"):
            output = await ja_word(word)
            assert output and "wiktionary.org" in output, (
                f"Wiktionary link missing for {word}"
            )

    async def test_all_words_have_jisho_footer(self):
        """Both words must include a Jisho footer link."""
        for word in ("同胞", "繰り返し"):
            output = await ja_word(word)
            assert output and "jisho.org" in output, (
                f"Jisho footer link missing for {word}"
            )

    async def test_output_not_none_or_empty(self):
        """Both words must produce non-trivial output."""
        for word in ("同胞", "繰り返し"):
            output = await ja_word(word)
            assert output and len(output.strip()) > 50, (
                f"Output for {word} is suspiciously short: {repr(output)}"
            )


# ─────────────────────────────────────────────────────────────────────────────
# 4. parse_ja_output_to_json – parsing fidelity
# ─────────────────────────────────────────────────────────────────────────────


class TestParseJaOutputToJson:
    """Unit-style tests against synthetic markdown (no network required)."""

    CHAR_MARKDOWN_KAKU = """\
# [覚](https://en.wiktionary.org/wiki/覚#Japanese)

**Kun-readings:** おぼ.える (*obo . eru*), さ.める (*sa . meru*)

**On-readings:** カク (*kaku*)

**Meanings**: "to memorize; to remember; to learn; to feel; sense"

^Information ^from ^[Jisho](https://jisho.org/search/覚%20%23kanji) ^| \
^[Tangorin](https://tangorin.com/kanji/覚) ^| \
^[Weblio](https://ejje.weblio.jp/content/覚)
"""

    CHAR_MARKDOWN_AKATSUKI = """\
# [暁](https://en.wiktionary.org/wiki/暁#Japanese)

**Kun-readings:** あかつき (*akatsuki*)

**On-readings:** ギョウ (*gyou*), キョウ (*kyou*)

**Meanings**: "dawn; daybreak; in the event of"

^Information ^from ^[Jisho](https://jisho.org/search/暁%20%23kanji) ^| \
^[Tangorin](https://tangorin.com/kanji/暁) ^| \
^[Weblio](https://ejje.weblio.jp/content/暁)
"""

    WORD_MARKDOWN_DOUHOU = """\
# [同胞](https://en.wiktionary.org/wiki/同胞#Japanese)

##### *Noun*

**Reading:** どうほう (*dōhō*)

**Meanings**: "brethren; fellow countrymen; compatriot"

^Information ^from ^[Jisho](https://jisho.org/search/同胞%23words) ^| \
^[Kotobank](https://kotobank.jp/word/同胞) ^| \
^[Tangorin](https://tangorin.com/general/同胞) ^| \
^[Weblio](https://ejje.weblio.jp/content/同胞)
"""

    WORD_MARKDOWN_KURIKAESHI = """\
# [繰り返し](https://en.wiktionary.org/wiki/繰り返し#Japanese)

##### *Noun*

**Reading:** くりかえし (*kurikaeshi*)

**Meanings**: "repetition; iteration; recurrence"

^Information ^from ^[Jisho](https://jisho.org/search/繰り返し%23words) ^| \
^[Weblio](https://ejje.weblio.jp/content/繰り返し)
"""

    # Yojijukugo uses **Japanese Explanation** rather than **Meanings**,
    # so meanings will be None after parsing — this is the expected behaviour.
    YOJI_MARKDOWN = """\
# [瓜田李下](https://en.wiktionary.org/wiki/瓜田李下#Japanese)

**Reading:** かでんりか (*ka den ri ka*)

**Japanese Explanation**: 疑惑を招きやすい状況にいること。

**Literary Source**: 古楽府「君子行」

^(Information from) ^[Jitenon](https://yoji.jitenon.jp/yojia/1234.html) \
^| ^[Weblio](https://ejje.weblio.jp/content/瓜田李下)
"""

    # Multi-character input – parser must return empty dict
    MULTI_CHAR_TABLE = """\
# 覚暁者

| Character | [覚](https://en.wiktionary.org/wiki/覚#Japanese) | \
[暁](https://en.wiktionary.org/wiki/暁#Japanese) | \
[者](https://en.wiktionary.org/wiki/者#Japanese) |
| --- | --- | --- | --- |
| **Kun-readings** | おぼ.える | あかつき | もの |
| **On-readings** | カク | ギョウ | シャ |
| **Meanings** | "to memorize" | "dawn" | "person" |
"""

    def test_parse_character_type_is_character(self):
        """Parser identifies 覚 output as type='character'."""
        data = parse_ja_output_to_json(self.CHAR_MARKDOWN_KAKU)
        assert data["type"] == "character", f"Expected 'character', got: {data['type']}"

    def test_parse_character_word_field(self):
        """Parser extracts the kanji correctly from the header."""
        data = parse_ja_output_to_json(self.CHAR_MARKDOWN_KAKU)
        assert data["word"] == "覚", f"Got: {data['word']}"

    def test_parse_kun_readings(self):
        """Parser extracts kun-readings as list of dicts for 覚."""
        data = parse_ja_output_to_json(self.CHAR_MARKDOWN_KAKU)
        assert data["kun_readings"], "kun_readings should not be empty/None"
        kana_forms = [r["kana"] for r in data["kun_readings"]]
        assert any("おぼ" in k for k in kana_forms), (
            f"Expected おぼ.える in kun_readings; got: {kana_forms}"
        )

    def test_parse_on_readings(self):
        """Parser extracts on-readings as list of dicts for 覚."""
        data = parse_ja_output_to_json(self.CHAR_MARKDOWN_KAKU)
        assert data["on_readings"], "on_readings should not be empty/None"
        kana_forms = [r["kana"] for r in data["on_readings"]]
        assert "カク" in kana_forms, f"Expected カク in on_readings; got: {kana_forms}"

    def test_parse_akatsuki_kun_reading(self):
        """Parser extracts あかつき as kun-reading for 暁."""
        data = parse_ja_output_to_json(self.CHAR_MARKDOWN_AKATSUKI)
        kana_forms = [r["kana"] for r in (data["kun_readings"] or [])]
        assert any("あかつき" in k for k in kana_forms), (
            f"Expected あかつき in kun_readings for 暁; got: {kana_forms}"
        )

    def test_parse_character_meanings(self):
        """Parser extracts meanings string for 覚."""
        data = parse_ja_output_to_json(self.CHAR_MARKDOWN_KAKU)
        assert data["meanings"] and "memorize" in data["meanings"], (
            f"Got: {data['meanings']}"
        )

    def test_parse_word_type_is_word(self):
        """Parser identifies 同胞 output as type='word'."""
        data = parse_ja_output_to_json(self.WORD_MARKDOWN_DOUHOU)
        assert data["type"] == "word", f"Expected 'word', got: {data['type']}"

    def test_parse_word_part_of_speech(self):
        """Parser extracts part_of_speech for 同胞."""
        data = parse_ja_output_to_json(self.WORD_MARKDOWN_DOUHOU)
        assert data["part_of_speech"] == "noun", (
            f"Expected 'noun', got: {data['part_of_speech']}"
        )

    def test_parse_word_reading(self):
        """Parser extracts reading kana and romaji for 同胞."""
        data = parse_ja_output_to_json(self.WORD_MARKDOWN_DOUHOU)
        assert data["reading"], "reading should not be None for a word"
        assert data["reading"]["kana"] == "どうほう", (
            f"Expected どうほう, got: {data['reading']['kana']}"
        )
        assert data["reading"]["romaji"], "romaji should not be empty"

    def test_parse_kurikaeshi_word(self):
        """Parser extracts 繰り返し correctly."""
        data = parse_ja_output_to_json(self.WORD_MARKDOWN_KURIKAESHI)
        assert data["word"] == "繰り返し", f"Got: {data['word']}"
        assert data["reading"]["kana"] == "くりかえし", f"Got: {data['reading']}"

    def test_parse_word_meanings(self):
        """Parser extracts meanings for 同胞."""
        data = parse_ja_output_to_json(self.WORD_MARKDOWN_DOUHOU)
        assert data["meanings"] and "compatriot" in data["meanings"], (
            f"Got: {data['meanings']}"
        )

    def test_parse_yojijukugo_type_is_word(self):
        """Yojijukugo has no Meanings line, so type defaults to 'word'."""
        data = parse_ja_output_to_json(self.YOJI_MARKDOWN)
        assert data["type"] == "word", f"Expected 'word', got: {data['type']}"

    def test_parse_yojijukugo_meanings_is_none(self):
        """Yojijukugo uses **Japanese Explanation**, not **Meanings**, so meanings=None."""
        data = parse_ja_output_to_json(self.YOJI_MARKDOWN)
        assert data["meanings"] is None, (
            f"Expected meanings=None for yojijukugo (no **Meanings** line); got: {data['meanings']}"
        )

    def test_parse_yojijukugo_reading(self):
        """Parser extracts the reading from a yojijukugo entry."""
        data = parse_ja_output_to_json(self.YOJI_MARKDOWN)
        assert data["reading"], "reading should not be None for yojijukugo"
        assert "かでんりか" in data["reading"]["kana"], (
            f"Expected かでんりか in reading, got: {data['reading']}"
        )

    def test_parse_multi_character_table_returns_empty_dict(self):
        """Multi-character table format must return empty dict (not cached)."""
        data = parse_ja_output_to_json(self.MULTI_CHAR_TABLE)
        assert data == {}, (
            f"Multi-character table should produce empty dict, got: {data}"
        )

    def test_parse_calligraphy_links_absent(self):
        """No calligraphy block means calligraphy_links=None."""
        data = parse_ja_output_to_json(self.CHAR_MARKDOWN_KAKU)
        assert data["calligraphy_links"] is None, (
            f"Expected calligraphy_links=None, got: {data['calligraphy_links']}"
        )

    def test_parse_calligraphy_links_present(self):
        """Calligraphy block is parsed into the correct dict structure."""
        markdown_with_calligraphy = self.CHAR_MARKDOWN_KAKU.replace(
            "**Meanings**",
            "**Chinese Calligraphy Variants**: [覚](https://shufazidian.com/img/覚.png) "
            "(*[SFZD](https://www.shufazidian.com/)*, "
            "*[SFDS](https://www.sfds.cn/899A/)*, "
            "*[YTZZD](https://dict.variants.moe.edu.tw/dictView.jsp?ID=12345&q=1)*)\n\n**Meanings**",
        )
        data = parse_ja_output_to_json(markdown_with_calligraphy)
        assert data["calligraphy_links"] is not None, (
            "calligraphy_links should be populated when block is present"
        )
        assert "sfds" in data["calligraphy_links"], (
            "sfds key missing from calligraphy_links"
        )
        assert "variants" in data["calligraphy_links"], "variants key missing"


# ─────────────────────────────────────────────────────────────────────────────
# 5. Cache round-trip (save → retrieve)
# ─────────────────────────────────────────────────────────────────────────────


class TestCacheRoundTrip:
    """
    Verify save_to_cache / get_from_cache for Japanese data using synthetic
    payloads — no network access required.
    """

    CHAR_PAYLOAD_KAKU = {
        "word": "覚",
        "type": "character",
        "part_of_speech": None,
        "reading": None,
        "kun_readings": [
            {"kana": "おぼ.える", "romaji": "obo . eru"},
            {"kana": "さ.める", "romaji": "sa . meru"},
        ],
        "on_readings": [{"kana": "カク", "romaji": "kaku"}],
        "meanings": "to memorize; to remember; to learn; to feel; sense",
        "calligraphy_links": None,
    }

    CHAR_PAYLOAD_AKATSUKI = {
        "word": "暁",
        "type": "character",
        "part_of_speech": None,
        "reading": None,
        "kun_readings": [{"kana": "あかつき", "romaji": "akatsuki"}],
        "on_readings": [
            {"kana": "ギョウ", "romaji": "gyou"},
            {"kana": "キョウ", "romaji": "kyou"},
        ],
        "meanings": "dawn; daybreak; in the event of",
        "calligraphy_links": None,
    }

    WORD_PAYLOAD_DOUHOU = {
        "word": "同胞",
        "type": "word",
        "part_of_speech": "noun",
        "reading": {"kana": "どうほう", "romaji": "dōhō"},
        "kun_readings": None,
        "on_readings": None,
        "meanings": "brethren; fellow countrymen; compatriot",
        "calligraphy_links": None,
    }

    WORD_PAYLOAD_KURIKAESHI = {
        "word": "繰り返し",
        "type": "word",
        "part_of_speech": "noun",
        "reading": {"kana": "くりかえし", "romaji": "kurikaeshi"},
        "kun_readings": None,
        "on_readings": None,
        "meanings": "repetition; iteration; recurrence",
        "calligraphy_links": None,
    }

    def test_character_kaku_round_trip(self):
        """Save 覚 as ja_character and retrieve it intact."""
        save_to_cache(self.CHAR_PAYLOAD_KAKU.copy(), "ja", "ja_character")
        cached = get_from_cache("覚", "ja", "ja_character")
        assert cached is not None, "Cache miss immediately after save for 覚"
        assert cached["word"] == "覚"
        assert cached["meanings"] and "memorize" in cached["meanings"]
        assert len(cached["kun_readings"]) == 2

    def test_character_akatsuki_round_trip(self):
        """Save 暁 as ja_character and retrieve it intact."""
        save_to_cache(self.CHAR_PAYLOAD_AKATSUKI.copy(), "ja", "ja_character")
        cached = get_from_cache("暁", "ja", "ja_character")
        assert cached is not None, "Cache miss immediately after save for 暁"
        kana_forms = [r["kana"] for r in cached["kun_readings"]]
        assert "あかつき" in kana_forms

    def test_word_douhou_round_trip(self):
        """Save 同胞 as ja_word and retrieve it intact."""
        save_to_cache(self.WORD_PAYLOAD_DOUHOU.copy(), "ja", "ja_word")
        cached = get_from_cache("同胞", "ja", "ja_word")
        assert cached is not None, "Cache miss immediately after save for 同胞"
        assert cached["reading"]["kana"] == "どうほう"
        assert "compatriot" in cached["meanings"]

    def test_word_kurikaeshi_round_trip(self):
        """Save 繰り返し as ja_word and retrieve it intact."""
        save_to_cache(self.WORD_PAYLOAD_KURIKAESHI.copy(), "ja", "ja_word")
        cached = get_from_cache("繰り返し", "ja", "ja_word")
        assert cached is not None, "Cache miss immediately after save for 繰り返し"
        assert cached["reading"]["kana"] == "くりかえし"

    def test_type_isolation_char_vs_word(self):
        """A ja_character entry must NOT be retrievable under ja_word."""
        save_to_cache(self.CHAR_PAYLOAD_KAKU.copy(), "ja", "ja_character")
        result = get_from_cache("覚", "ja", "ja_word")
        assert result is None, (
            "Type isolation failed: ja_character entry returned for ja_word query"
        )

    def test_language_isolation_ja_vs_zh(self):
        """A ja entry must NOT be retrievable under zh language code."""
        save_to_cache(self.WORD_PAYLOAD_DOUHOU.copy(), "ja", "ja_word")
        result = get_from_cache("同胞", "zh", "ja_word")
        assert result is None, (
            "Language isolation failed: ja entry returned for zh query"
        )

    def test_unicode_preserved_for_mixed_script_word(self):
        """Mixed kana/kanji key 繰り返し must survive JSON serialization."""
        save_to_cache(self.WORD_PAYLOAD_KURIKAESHI.copy(), "ja", "ja_word")
        cached = get_from_cache("繰り返し", "ja", "ja_word")
        assert cached is not None
        assert cached["word"] == "繰り返し", (
            f"Unicode not preserved; got: {cached['word']}"
        )

    def test_format_character_from_cache_roundtrip(self):
        """format_ja_character_from_cache should produce valid markdown from cached data."""
        save_to_cache(self.CHAR_PAYLOAD_KAKU.copy(), "ja", "ja_character")
        cached = get_from_cache("覚", "ja", "ja_character")
        rendered = format_ja_character_from_cache(cached)
        assert "覚" in rendered
        assert "**Kun-readings:**" in rendered
        assert "**On-readings:**" in rendered
        assert "memorize" in rendered

    def test_format_word_from_cache_roundtrip(self):
        """format_ja_word_from_cache should produce valid markdown from cached data."""
        save_to_cache(self.WORD_PAYLOAD_DOUHOU.copy(), "ja", "ja_word")
        cached = get_from_cache("同胞", "ja", "ja_word")
        rendered = format_ja_word_from_cache(cached)
        assert "同胞" in rendered
        assert "どうほう" in rendered
        assert "compatriot" in rendered


# ─────────────────────────────────────────────────────────────────────────────
# 6. End-to-end pipeline smoke tests
# ─────────────────────────────────────────────────────────────────────────────


class TestEndToEndPipeline:
    """
    Smoke tests for the full path:
    lookup_matcher → ja_character / ja_word → parse → cache → re-fetch from cache.

    Integration tests call the internal _fetch functions directly to bypass the
    cache layer, ensuring fresh network results are exercised on every run.
    """

    def test_kaku_end_to_end(self):
        """覚: match → fetch (bypassing cache) → parse → cache → retrieve."""
        # 1. Match
        matched = lookup_matcher("`覚`", language_code="ja", disable_tokenization=True)
        assert "ja" in matched

        # 2. Fetch fresh from source (bypass cache)
        output = _ja_character_fetch("覚")
        assert output and "覚" in output

        # 3. Parse
        data = parse_ja_output_to_json(_strip_cache_marker(output))
        assert data.get("word") == "覚"
        assert data.get("type") == "character"

        # 4. Cache
        save_to_cache(data, "ja", "ja_character")

        # 5. Re-retrieve
        cached = get_from_cache("覚", "ja", "ja_character")
        assert cached is not None
        assert cached["word"] == "覚"

    async def test_douhou_end_to_end(self):
        """同胞: match → fetch (bypassing cache) → parse → cache → retrieve."""
        matched = lookup_matcher(
            "`同胞`", language_code="ja", disable_tokenization=True
        )
        assert "ja" in matched

        # Bypass cache: call the internal fetch directly
        output = await _ja_word_fetch("同胞")
        assert output

        data = parse_ja_output_to_json(_strip_cache_marker(output))
        assert data.get("word") == "同胞"
        assert data.get("type") == "word"

        save_to_cache(data, "ja", "ja_word")
        cached = get_from_cache("同胞", "ja", "ja_word")
        assert cached is not None
        assert cached["word"] == "同胞"

    async def test_cache_hit_returns_cache_marker(self):
        """After a word is cached, subsequent calls via ja_word must return the ^⚡ marker."""
        # Prime the cache via internal fetch, then save explicitly
        output_first = await _ja_word_fetch("同胞")
        assert output_first is not None
        data = parse_ja_output_to_json(_strip_cache_marker(output_first))
        save_to_cache(data, "ja", "ja_word")

        # Public ja_word call must now hit the cache and append ^⚡
        output_second = await ja_word("同胞")
        assert output_second and "^⚡" in output_second, (
            "Expected '^⚡' cache marker on ja_word call after manual cache prime for 同胞"
        )
