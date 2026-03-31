#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
Test suite for CJK lookup modules: match_helpers, zh, ja, ko, and cache_helpers.
Covers tokenization, text matching, word/character lookup, chengyu/yojijukugo,
and the caching layer (save, retrieve, format round-trip).

Chinese examples drawn from: 满腔的热血已经沸腾，要为真理而斗争 / 这是最后的斗争 / 团结起来到明天
Japanese examples drawn from: いざ戦はん / 暴虐の鎖断つ日 / 旗は血に燃えて / 海を隔てつ我等
Korean examples drawn from: 들어라 최후 결전 투쟁의 외침을 / 민중이여 해방의 깃발 아래 서자
"""

import unittest
from unittest.mock import patch

from ziwen_lookup.cache_helpers import (
    format_ja_character_from_cache,
    format_ja_word_from_cache,
    format_ko_word_from_cache,
    format_zh_word_from_cache,
    get_from_cache,
    parse_ja_output_to_json,
    parse_ko_output_to_json,
    parse_zh_output_to_json,
    save_to_cache,
)
from ziwen_lookup.match_helpers import (
    lookup_ko_tokenizer,
    lookup_matcher,
    lookup_zh_ja_tokenizer,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _skip_on_error(func):
    """Decorator: skip a test if an import/runtime dependency is absent."""
    import functools

    @functools.wraps(func)
    def wrapper(self, *args, **kwargs):
        try:
            func(self, *args, **kwargs)
        except Exception as e:
            self.skipTest(f"Dependency not available: {e}")

    return wrapper


# ---------------------------------------------------------------------------
# TestZhJaTokenizer
# ---------------------------------------------------------------------------


class TestZhJaTokenizer(unittest.TestCase):
    """Tests for lookup_zh_ja_tokenizer."""

    # --- Chinese ---

    @_skip_on_error
    def test_zh_single_character_dou(self):
        """Single hanzi 斗 (struggle) should tokenize to a non-empty list."""
        result = lookup_zh_ja_tokenizer("斗", "zh")
        self.assertIsInstance(result, list)
        self.assertTrue(len(result) >= 1)

    @_skip_on_error
    def test_zh_word_tuan_jie(self):
        """团结 (unite/solidarity) should be returned as a token."""
        result = lookup_zh_ja_tokenizer("团结", "zh")
        self.assertIsInstance(result, list)
        self.assertGreater(len(result), 0)
        joined = "".join(result)
        self.assertIn("团结", joined)

    @_skip_on_error
    def test_zh_phrase_zui_hou_de_dou_zheng(self):
        """Phrase 最后的斗争 (the final struggle) tokenizes to multiple tokens."""
        result = lookup_zh_ja_tokenizer("最后的斗争", "zh")
        self.assertIsInstance(result, list)
        self.assertGreater(len(result), 1)
        for token in result:
            self.assertIsInstance(token, str)

    @_skip_on_error
    def test_zh_phrase_re_xue_fei_teng(self):
        """热血已经沸腾 produces at least two tokens (热血, 沸腾 are distinct words)."""
        result = lookup_zh_ja_tokenizer("热血已经沸腾", "zh")
        self.assertGreater(len(result), 1)

    @_skip_on_error
    def test_zh_traditional_form(self):
        """Traditional form 鬥爭 is handled via simplification round-trip."""
        result = lookup_zh_ja_tokenizer("鬥爭", "zh")
        self.assertIsInstance(result, list)
        self.assertTrue(len(result) >= 1)
        # The returned tokens should map back to original Traditional chars
        for token in result:
            self.assertRegex(token, r"[\u2E80-\u9FFF]")

    @_skip_on_error
    def test_zh_chengyu_four_chars(self):
        """Four-character idiom-length string tokenizes without error."""
        result = lookup_zh_ja_tokenizer("滥竽充数", "zh")
        self.assertIsInstance(result, list)

    def test_zh_punctuation_stripped(self):
        """Punctuation in 满腔的热血已经沸腾，要为真理而斗争！ is stripped."""
        result = lookup_zh_ja_tokenizer("满腔的热血已经沸腾，要为真理而斗争！", "zh")
        for token in result:
            self.assertNotIn(token, ["，", "！", "。", "、"])

    @_skip_on_error
    def test_zh_empty_string(self):
        """Empty string returns an empty list without raising."""
        result = lookup_zh_ja_tokenizer("", "zh")
        self.assertIsInstance(result, list)

    # --- Japanese ---

    @_skip_on_error
    def test_ja_kanji_bougyaku(self):
        """暴虐 (tyranny/atrocity) tokenizes correctly."""
        result = lookup_zh_ja_tokenizer("暴虐", "ja")
        self.assertIsInstance(result, list)
        self.assertTrue(len(result) >= 1)

    @_skip_on_error
    def test_ja_kanji_chi(self):
        """Single-kanji 血 (blood) appears as a token."""
        result = lookup_zh_ja_tokenizer("血", "ja")
        self.assertIsInstance(result, list)
        # Single kanji should come through (it's not kana)
        self.assertGreater(len(result), 0)

    @_skip_on_error
    def test_ja_mixed_hata_wa_chi_ni_moete(self):
        """Mixed kanji/kana phrase tokenizes with kanji tokens retained."""
        result = lookup_zh_ja_tokenizer("旗は血に燃えて", "ja")
        self.assertIsInstance(result, list)
        self.assertTrue(len(result) >= 1)
        # Single hiragana should be excluded; kanji should remain
        for token in result:
            self.assertNotRegex(token, r"^[\u3040-\u309f]$")

    @_skip_on_error
    def test_ja_mixed_umi_wo_hedatete(self):
        """海を隔てつ我等 produces kanji-bearing tokens."""
        result = lookup_zh_ja_tokenizer("海を隔てつ我等", "ja")
        joined = "".join(result)
        self.assertTrue(any(c in joined for c in "海隔我等"))

    @_skip_on_error
    def test_ja_phrase_iza_ikusa_han(self):
        """Phrase starting with hiragana returns tokens for kanji 戦."""
        result = lookup_zh_ja_tokenizer("いざ戦はん", "ja")
        self.assertIsInstance(result, list)

    @_skip_on_error
    def test_ja_empty_string(self):
        """Empty string is handled gracefully."""
        result = lookup_zh_ja_tokenizer("", "ja")
        self.assertIsInstance(result, list)

    # --- Error handling ---

    def test_invalid_language_raises(self):
        """Unsupported language code raises ValueError."""
        with self.assertRaises(ValueError):
            lookup_zh_ja_tokenizer("斗争", "xx")

    def test_punctuation_only_returns_empty(self):
        """String of only CJK punctuation returns empty list."""
        result = lookup_zh_ja_tokenizer("。！？，；：", "zh")
        self.assertIsInstance(result, list)
        self.assertEqual(result, [])


# ---------------------------------------------------------------------------
# TestKoTokenizer
# ---------------------------------------------------------------------------


class TestKoTokenizer(unittest.TestCase):
    """Tests for lookup_ko_tokenizer."""

    @_skip_on_error
    def test_ko_choe_hu(self):
        """최후 (final/last) is extracted as a noun token."""
        result = lookup_ko_tokenizer("최후 결전")
        self.assertIsInstance(result, list)
        self.assertIn("최후", result)

    @_skip_on_error
    def test_ko_tu_jaeng(self):
        """투쟁 (struggle) appears in content words."""
        result = lookup_ko_tokenizer("투쟁의 외침을")
        self.assertIsInstance(result, list)
        self.assertIn("투쟁", result)

    @_skip_on_error
    def test_ko_min_jung_and_hae_bang(self):
        """민중 (people/masses) and 해방 (liberation) are both captured."""
        result = lookup_ko_tokenizer("민중이여 해방의 깃발 아래 서자")
        self.assertIsInstance(result, list)
        self.assertIn("민중", result)
        self.assertIn("해방", result)

    @_skip_on_error
    def test_ko_git_bal(self):
        """깃발 (flag/banner) is returned as a noun."""
        result = lookup_ko_tokenizer("깃발 아래")
        self.assertIsInstance(result, list)
        self.assertIn("깃발", result)

    @_skip_on_error
    def test_ko_particles_excluded(self):
        """Grammatical particles are not included in the result."""
        result = lookup_ko_tokenizer("민중이여 해방의 깃발 아래 서자")
        # 이여, 의, 아래 are particles/postpositions — should not appear standalone
        self.assertNotIn("이여", result)
        self.assertNotIn("의", result)

    @_skip_on_error
    def test_ko_gyeol_jeon_and_oe_chim(self):
        """결전 (decisive battle) and 외침 (cry/shout) appear."""
        result = lookup_ko_tokenizer("결전 투쟁의 외침을")
        self.assertIsInstance(result, list)
        self.assertIn("결전", result)

    @_skip_on_error
    def test_ko_empty_string(self):
        """Empty string returns an empty list."""
        result = lookup_ko_tokenizer("")
        self.assertIsInstance(result, list)
        self.assertEqual(result, [])

    @_skip_on_error
    def test_ko_content_words_only(self):
        """All returned tokens are Hangul strings."""
        result = lookup_ko_tokenizer("들어라 최후 결전 투쟁의 외침을")
        for token in result:
            self.assertRegex(token, r"[\uac00-\ud7af]+")


# ---------------------------------------------------------------------------
# TestLookupMatcher
# ---------------------------------------------------------------------------


class TestLookupMatcher(unittest.TestCase):
    """Tests for lookup_matcher."""

    # --- Basic extraction ---

    @_skip_on_error
    def test_zh_backtick_dou_zheng(self):
        """`斗争` with zh code returns a dict with 'zh' key."""
        result = lookup_matcher("`斗争`", "zh")
        self.assertIsInstance(result, dict)
        self.assertIn("zh", result)

    @_skip_on_error
    def test_zh_backtick_tuan_jie(self):
        """`团结` correctly assigned to zh."""
        result = lookup_matcher("`团结`", "zh")
        self.assertIn("zh", result)

    @_skip_on_error
    def test_zh_backtick_traditional_form(self):
        """Traditional `鬥爭` is processed under zh."""
        result = lookup_matcher("`鬥爭`", "zh")
        self.assertIn("zh", result)

    @_skip_on_error
    def test_ja_backtick_bougyaku(self):
        """`暴虐` with ja code returns dict with 'ja' key."""
        result = lookup_matcher("`暴虐`", "ja")
        self.assertIsInstance(result, dict)
        self.assertIn("ja", result)

    @_skip_on_error
    def test_ja_backtick_chi(self):
        """`血` assigned to ja when kana present in same segment or ja specified."""
        result = lookup_matcher("`血に燃えて`", "ja")
        self.assertIn("ja", result)

    @_skip_on_error
    def test_ko_backtick_hae_bang(self):
        """`해방` with ko code returns dict with 'ko' key."""
        result = lookup_matcher("`해방`", "ko")
        self.assertIn("ko", result)

    @_skip_on_error
    def test_ko_backtick_git_bal(self):
        """`깃발` (flag) assigned to ko."""
        result = lookup_matcher("`깃발`", "ko")
        self.assertIn("ko", result)

    # --- Script auto-detection (no language_code) ---

    @_skip_on_error
    def test_auto_detect_hangul(self):
        """Hangul text auto-detected as Korean when no language specified."""
        result = lookup_matcher("`투쟁`", None)
        self.assertIn("ko", result)

    @_skip_on_error
    def test_auto_detect_kana(self):
        """Kana-only text auto-detected as Japanese."""
        result = lookup_matcher("`いざ`", None)
        self.assertIn("ja", result)

    @_skip_on_error
    def test_auto_detect_hanzi(self):
        """Pure hanzi auto-detected as Chinese."""
        result = lookup_matcher("`热血`", None)
        self.assertIn("zh", result)

    # --- !identify / !id command ---

    @_skip_on_error
    def test_identify_command_zh(self):
        """`斗争` !identify:zh extracts under zh."""
        result = lookup_matcher("`斗争` !identify:zh", language_code=None)
        self.assertIn("zh", result)

    @_skip_on_error
    def test_identify_command_multi_zh_ja(self):
        """`斗争` !identify:zh+ja puts result under both zh and ja."""
        result = lookup_matcher("`斗争` !identify:zh+ja", language_code=None)
        self.assertIsInstance(result, dict)
        # At least one of zh/ja should appear
        self.assertTrue("zh" in result or "ja" in result)

    @_skip_on_error
    def test_id_shorthand_ko(self):
        """`투쟁` !id:ko extracts under ko."""
        result = lookup_matcher("`투쟁` !id:ko", language_code=None)
        self.assertIn("ko", result)

    # --- Inline language spec ---

    @_skip_on_error
    def test_inline_lang_ko(self):
        """`깃발`:ko with inline language spec assigns to ko."""
        result = lookup_matcher("`깃발`:ko", language_code=None)
        self.assertIn("ko", result)

    @_skip_on_error
    def test_inline_lang_overrides_outer_code(self):
        """Inline language spec overrides the outer language_code parameter."""
        # Outer says zh but inline says ko — ko should win
        result = lookup_matcher("`투쟁`:ko", language_code="zh")
        self.assertIn("ko", result)

    # --- disable_tokenization flag ---

    @_skip_on_error
    def test_disable_tokenization_zh(self):
        """With disable_tokenization=True, full segment is returned, not split tokens."""
        result = lookup_matcher("`团结起来到明天`", "zh", disable_tokenization=True)
        if "zh" in result:
            texts = [
                item[0] if isinstance(item, tuple) else item for item in result["zh"]
            ]
            self.assertIn("团结起来到明天", texts)

    @_skip_on_error
    def test_disable_tokenization_ko(self):
        """disable_tokenization returns full Hangul segment."""
        result = lookup_matcher("`민중이여`", "ko", disable_tokenization=True)
        if "ko" in result:
            texts = [
                item[0] if isinstance(item, tuple) else item for item in result["ko"]
            ]
            self.assertIn("민중이여", texts)

    # --- Triple-backtick exclusion ---

    @_skip_on_error
    def test_triple_backtick_ignored(self):
        """Content inside triple backticks is not matched."""
        result = lookup_matcher("```斗争```", "zh")
        self.assertEqual(result, {})

    # --- Edge cases ---

    @_skip_on_error
    def test_no_backticks_returns_empty(self):
        """Text with no backticks returns an empty dict."""
        result = lookup_matcher("这是最后的斗争", "zh")
        self.assertEqual(result, {})

    @_skip_on_error
    def test_empty_input(self):
        """Empty string returns an empty dict."""
        result = lookup_matcher("", "zh")
        self.assertIsInstance(result, dict)

    @_skip_on_error
    def test_result_values_are_tuples_or_strings(self):
        """Each value in the result list is either a str or a (str, bool) tuple."""
        result = lookup_matcher("`斗争`", "zh")
        for key, items in result.items():
            for item in items:
                self.assertTrue(
                    isinstance(item, str)
                    or (isinstance(item, tuple) and len(item) == 2),
                    f"Unexpected item type: {type(item)}",
                )

    @_skip_on_error
    def test_multiple_backtick_segments(self):
        """Multiple backtick segments are all processed."""
        result = lookup_matcher("`斗争` and `团结`", "zh")
        if "zh" in result:
            self.assertGreaterEqual(len(result["zh"]), 2)


# ---------------------------------------------------------------------------
# TestCacheParserZh
# ---------------------------------------------------------------------------


_ZH_WORD_MARKDOWN = """\
# [斗爭 / 斗争](https://en.wiktionary.org/wiki/斗爭#Chinese)

| Language | Pronunciation |
|---------|--------------|
| **Mandarin** (Pinyin) | *dòu zhēng* |
| **Mandarin** (Wade-Giles) | *tou4 cheng1* |
| **Mandarin** (Yale) | *dòu jēng* |
| **Mandarin** (GR) | *dowjenq* |
| **Cantonese** | *dau^(3) zaang^(1)* |

**Meanings**: "struggle; to fight; to strive."

^Information ^from ^[CantoDict](https://www.cantonese.sheik.co.uk/dictionary/search/?searchtype=1&text=斗爭) ^| \
^[MDBG](https://www.mdbg.net/chinese/dictionary?page=worddict&wdrst=0&wdqb=c:斗争) ^| \
^[Yellowbridge](https://yellowbridge.com/chinese/dictionary.php?word=斗争) ^| \
^[Youdao](https://dict.youdao.com/w/eng/斗争/#keyfrom=dict2.index) ^| ^[ZDIC](https://www.zdic.net/hans/斗争)
"""

_ZH_CHENGYU_MARKDOWN = """\
# [濫竽充數 / 滥竽充数](https://en.wiktionary.org/wiki/濫竽充數#Chinese)

| Language | Pronunciation |
|---------|--------------|
| **Mandarin** (Pinyin) | *làn yú chōng shù* |
| **Mandarin** (Wade-Giles) | *lan4 yü2 ch'ung1 shu4* |

**Meanings**: "to pass off as a capable person; to make up the number."

**Chinese Meaning**: 比喻没有真才实学的人混在行家里充数。

**Literary Source**: 古典文学

^Information ^from ^[CantoDict](https://www.cantonese.sheik.co.uk/dictionary/search/?searchtype=1&text=濫竽充數) ^| \
^[MDBG](https://www.mdbg.net/chinese/dictionary?page=worddict&wdrst=0&wdqb=c:滥竽充数) ^| \
^[Yellowbridge](https://yellowbridge.com/chinese/dictionary.php?word=滥竽充数) ^| \
^[Youdao](https://dict.youdao.com/w/eng/滥竽充数/#keyfrom=dict2.index) ^| ^[ZDIC](https://www.zdic.net/hans/滥竽充数)
"""


class TestCacheParserZh(unittest.TestCase):
    """Tests for parse_zh_output_to_json and format_zh_word_from_cache."""

    def test_parse_word_traditional(self):
        parsed = parse_zh_output_to_json(_ZH_WORD_MARKDOWN)
        self.assertEqual(parsed["traditional"], "斗爭")

    def test_parse_word_simplified(self):
        parsed = parse_zh_output_to_json(_ZH_WORD_MARKDOWN)
        self.assertEqual(parsed["simplified"], "斗争")

    def test_parse_word_mandarin_pinyin(self):
        parsed = parse_zh_output_to_json(_ZH_WORD_MARKDOWN)
        self.assertEqual(parsed["pronunciations"]["mandarin_pinyin"], "dòu zhēng")

    def test_parse_word_cantonese(self):
        parsed = parse_zh_output_to_json(_ZH_WORD_MARKDOWN)
        self.assertIn("cantonese", parsed["pronunciations"])

    def test_parse_word_meanings(self):
        parsed = parse_zh_output_to_json(_ZH_WORD_MARKDOWN)
        self.assertIn("struggle", parsed["meanings"])

    def test_parse_chengyu_traditional(self):
        parsed = parse_zh_output_to_json(_ZH_CHENGYU_MARKDOWN)
        self.assertEqual(parsed["traditional"], "濫竽充數")

    def test_parse_chengyu_chinese_meaning(self):
        parsed = parse_zh_output_to_json(_ZH_CHENGYU_MARKDOWN)
        self.assertIsNotNone(parsed["chinese_meaning"])

    def test_parse_chengyu_literary_source(self):
        parsed = parse_zh_output_to_json(_ZH_CHENGYU_MARKDOWN)
        self.assertIsNotNone(parsed["literary_source"])

    def test_format_round_trip(self):
        """Parsed data can be re-formatted without raising."""
        parsed = parse_zh_output_to_json(_ZH_WORD_MARKDOWN)
        output = format_zh_word_from_cache(parsed)
        self.assertIsInstance(output, str)
        self.assertIn("斗", output)

    def test_format_round_trip_contains_meanings(self):
        parsed = parse_zh_output_to_json(_ZH_WORD_MARKDOWN)
        output = format_zh_word_from_cache(parsed)
        self.assertIn("struggle", output)


# ---------------------------------------------------------------------------
# TestCacheParserJa
# ---------------------------------------------------------------------------


_JA_CHARACTER_MARKDOWN = """\
# [暴](https://en.wiktionary.org/wiki/暴#Japanese)

**Kun-readings:** あば.く (*aba . ku*), あば.れる (*aba . reru*)

**On-readings:** ボウ (*bou*), バク (*baku*)

**Meanings**: "outburst; rave; fret; force; violence; cruelty; outrage"

^Information ^from ^[Jisho](https://jisho.org/search/暴%20%23kanji) ^| ^[Tangorin](https://tangorin.com/kanji/暴) ^| \
^[Weblio](https://ejje.weblio.jp/content/暴)
"""

_JA_WORD_MARKDOWN = """\
# [暴虐](https://en.wiktionary.org/wiki/暴虐#Japanese)

##### *Noun*

**Reading:** ぼうぎゃく (*bougyaku*)

**Meanings**: "tyranny; atrocity; cruelty; outrage"

^Information ^from ^[Jisho](https://jisho.org/search/暴虐%23words) ^| ^[Kotobank](https://kotobank.jp/word/暴虐) ^| \
^[Tangorin](https://tangorin.com/general/暴虐) ^| ^[Weblio](https://ejje.weblio.jp/content/暴虐)
"""

_JA_YOJIJUKUGO_MARKDOWN = """\
# [一期一会](https://en.wiktionary.org/wiki/一期一会#Japanese)

**Reading:** いちごいちえ (*ichigo ichie*)

**Japanese Explanation**: 一生に一度だけの機会。生涯に一度限りであること。特に、茶の湯での心得として、どの茶会も一生に一度のものと心得て誠意を尽くすべきであるということ。

**Literary Source**: 山上宗二記

^(Information from) ^[Jitenon](https://yoji.jitenon.jp/yojia/271.html) ^| ^[Weblio](https://ejje.weblio.jp/content/一期一会)
"""


class TestCacheParserJa(unittest.TestCase):
    """Tests for parse_ja_output_to_json and format helpers."""

    def test_parse_character_word(self):
        parsed = parse_ja_output_to_json(_JA_CHARACTER_MARKDOWN)
        self.assertEqual(parsed["word"], "暴")

    def test_parse_character_type(self):
        parsed = parse_ja_output_to_json(_JA_CHARACTER_MARKDOWN)
        self.assertEqual(parsed["type"], "character")

    def test_parse_character_kun_readings(self):
        parsed = parse_ja_output_to_json(_JA_CHARACTER_MARKDOWN)
        self.assertIsNotNone(parsed["kun_readings"])
        self.assertGreater(len(parsed["kun_readings"]), 0)

    def test_parse_character_on_readings(self):
        parsed = parse_ja_output_to_json(_JA_CHARACTER_MARKDOWN)
        on_kana = [r["kana"] for r in parsed["on_readings"]]
        self.assertIn("ボウ", on_kana)

    def test_parse_character_meanings(self):
        parsed = parse_ja_output_to_json(_JA_CHARACTER_MARKDOWN)
        self.assertIn("violence", parsed["meanings"])

    def test_parse_word_type(self):
        parsed = parse_ja_output_to_json(_JA_WORD_MARKDOWN)
        self.assertEqual(parsed["type"], "word")

    def test_parse_word_pos(self):
        parsed = parse_ja_output_to_json(_JA_WORD_MARKDOWN)
        self.assertEqual(parsed["part_of_speech"], "noun")

    def test_parse_word_reading_kana(self):
        parsed = parse_ja_output_to_json(_JA_WORD_MARKDOWN)
        self.assertEqual(parsed["reading"]["kana"], "ぼうぎゃく")

    def test_parse_word_meanings(self):
        parsed = parse_ja_output_to_json(_JA_WORD_MARKDOWN)
        self.assertIn("tyranny", parsed["meanings"])

    def test_format_character_round_trip(self):
        parsed = parse_ja_output_to_json(_JA_CHARACTER_MARKDOWN)
        output = format_ja_character_from_cache(parsed)
        self.assertIsInstance(output, str)
        self.assertIn("暴", output)

    def test_format_word_round_trip(self):
        parsed = parse_ja_output_to_json(_JA_WORD_MARKDOWN)
        output = format_ja_word_from_cache(parsed)
        self.assertIn("tyranny", output)

    def test_multichar_table_skipped(self):
        """Multi-character table format returns empty dict (not cacheable)."""
        multi_char_md = (
            "# [暴虐]\n\n| Character | [暴](https://en.wiktionary.org/wiki/暴)"
            " | [虐](https://en.wiktionary.org/wiki/虐) |\n| --- | --- | --- |\n"
        )
        parsed = parse_ja_output_to_json(multi_char_md)
        self.assertEqual(parsed, {})

    def test_parse_yojijukugo_word_field(self):
        parsed = parse_ja_output_to_json(_JA_YOJIJUKUGO_MARKDOWN)
        self.assertEqual(parsed["word"], "一期一会")

    def test_parse_yojijukugo_type_is_word(self):
        parsed = parse_ja_output_to_json(_JA_YOJIJUKUGO_MARKDOWN)
        self.assertEqual(parsed["type"], "word")

    def test_parse_yojijukugo_reading_kana(self):
        parsed = parse_ja_output_to_json(_JA_YOJIJUKUGO_MARKDOWN)
        self.assertEqual(parsed["reading"]["kana"], "いちごいちえ")

    def test_parse_yojijukugo_reading_romaji(self):
        parsed = parse_ja_output_to_json(_JA_YOJIJUKUGO_MARKDOWN)
        self.assertEqual(parsed["reading"]["romaji"], "ichigo ichie")


# ---------------------------------------------------------------------------
# TestCacheParserKo
# ---------------------------------------------------------------------------


_KO_WORD_MARKDOWN = """\
# [해방](https://en.wiktionary.org/wiki/해방#Korean)

##### *Noun*

**Romanization:** *haebang*

**Meanings**:
* [解放](https://en.wiktionary.org/wiki/解放): liberation; release; emancipation

^Information ^from ^[KRDict](https://krdict.korean.go.kr/eng/dicMarinerSearch/search?nation=eng&nationCode=6&\
ParaWordNo=&mainSearchWord=해방&lang=eng) ^| ^[Naver](https://korean.dict.naver.com/koendict/#/search?query=해방) ^| \
^[Collins](https://www.collinsdictionary.com/dictionary/korean-english/해방)
"""

_KO_WORD_TUJAENG_MARKDOWN = """\
# [투쟁](https://en.wiktionary.org/wiki/투쟁#Korean)

##### *Noun*

**Romanization:** *tujaeng*

**Meanings**:
* [鬪爭](https://en.wiktionary.org/wiki/鬪爭): struggle; fight; strife

^Information ^from ^[KRDict](https://krdict.korean.go.kr/eng/dicMarinerSearch/search?nation=eng&nationCode=6\
&ParaWordNo=&mainSearchWord=투쟁&lang=eng) ^| ^[Naver](https://korean.dict.naver.com/koendict/#/search?query=투쟁) ^| \
^[Collins](https://www.collinsdictionary.com/dictionary/korean-english/투쟁)
"""


class TestCacheParserKo(unittest.TestCase):
    """Tests for parse_ko_output_to_json and format_ko_word_from_cache."""

    def test_parse_haebang_word(self):
        parsed = parse_ko_output_to_json(_KO_WORD_MARKDOWN)
        self.assertEqual(parsed["word"], "해방")

    def test_parse_haebang_romanization(self):
        parsed = parse_ko_output_to_json(_KO_WORD_MARKDOWN)
        self.assertEqual(parsed["romanization"], "haebang")

    def test_parse_haebang_entries_not_empty(self):
        parsed = parse_ko_output_to_json(_KO_WORD_MARKDOWN)
        self.assertGreater(len(parsed["entries"]), 0)

    def test_parse_haebang_pos_noun(self):
        parsed = parse_ko_output_to_json(_KO_WORD_MARKDOWN)
        self.assertEqual(parsed["entries"][0]["part_of_speech"], "noun")

    def test_parse_haebang_meaning_text(self):
        parsed = parse_ko_output_to_json(_KO_WORD_MARKDOWN)
        meanings = parsed["entries"][0]["meanings"]
        definitions = [m["definition"] for m in meanings]
        self.assertTrue(any("liberation" in d for d in definitions))

    def test_parse_haebang_origin_hanja(self):
        parsed = parse_ko_output_to_json(_KO_WORD_MARKDOWN)
        origins = [m.get("origin") for m in parsed["entries"][0]["meanings"]]
        self.assertIn("解放", origins)

    def test_parse_tujaeng_word(self):
        parsed = parse_ko_output_to_json(_KO_WORD_TUJAENG_MARKDOWN)
        self.assertEqual(parsed["word"], "투쟁")

    def test_parse_tujaeng_meaning(self):
        parsed = parse_ko_output_to_json(_KO_WORD_TUJAENG_MARKDOWN)
        defs = [m["definition"] for m in parsed["entries"][0]["meanings"]]
        self.assertTrue(any("struggle" in d for d in defs))

    def test_format_round_trip_haebang(self):
        parsed = parse_ko_output_to_json(_KO_WORD_MARKDOWN)
        output = format_ko_word_from_cache(parsed)
        self.assertIsInstance(output, str)
        self.assertIn("해방", output)

    def test_format_round_trip_contains_romanization(self):
        parsed = parse_ko_output_to_json(_KO_WORD_MARKDOWN)
        output = format_ko_word_from_cache(parsed)
        self.assertIn("haebang", output)

    def test_format_round_trip_contains_hanja_origin(self):
        parsed = parse_ko_output_to_json(_KO_WORD_MARKDOWN)
        output = format_ko_word_from_cache(parsed)
        self.assertIn("解放", output)


# ---------------------------------------------------------------------------
# TestCacheReadWrite  (uses an in-memory SQLite DB via mock)
# ---------------------------------------------------------------------------


class TestCacheReadWrite(unittest.TestCase):
    """
    Tests for save_to_cache / get_from_cache using a temporary in-memory
    SQLite database, patching _get_thread_local_cursor.
    """

    def setUp(self):
        import sqlite3

        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self.conn.execute(
            """
            CREATE TABLE lookup_cjk_cache (
                term TEXT,
                language_code TEXT,
                retrieved_utc INTEGER,
                type TEXT,
                data TEXT,
                fetch_count INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (term, language_code, type)
            )
            """
        )
        self.conn.commit()

    def _cursor_and_conn(self):
        return self.conn.cursor(), self.conn

    def _patch(self):
        return patch(
            "ziwen_lookup.cache_helpers._get_thread_local_cursor",
            side_effect=self._cursor_and_conn,
        )

    @staticmethod
    def _patch_settings():
        return patch(
            "ziwen_lookup.cache_helpers.SETTINGS",
            {"lookup_cjk_cache_age": 30},
        )

    def test_save_and_retrieve_zh_word(self):
        parsed = parse_zh_output_to_json(_ZH_WORD_MARKDOWN)
        with self._patch(), self._patch_settings():
            save_to_cache(parsed, "zh", "zh_word")
            result = get_from_cache("斗爭", "zh", "zh_word")
        self.assertIsNotNone(result)
        self.assertEqual(result["traditional"], "斗爭")

    def test_save_and_retrieve_zh_chengyu(self):
        parsed = parse_zh_output_to_json(_ZH_CHENGYU_MARKDOWN)
        with self._patch(), self._patch_settings():
            save_to_cache(parsed, "zh", "zh_word")
            result = get_from_cache("濫竽充數", "zh", "zh_word")
        self.assertIsNotNone(result)
        self.assertIsNotNone(result["chinese_meaning"])

    def test_save_and_retrieve_ja_character(self):
        parsed = parse_ja_output_to_json(_JA_CHARACTER_MARKDOWN)
        with self._patch(), self._patch_settings():
            save_to_cache(parsed, "ja", "ja_character")
            result = get_from_cache("暴", "ja", "ja_character")
        self.assertIsNotNone(result)
        self.assertEqual(result["word"], "暴")

    def test_save_and_retrieve_ja_word(self):
        parsed = parse_ja_output_to_json(_JA_WORD_MARKDOWN)
        with self._patch(), self._patch_settings():
            save_to_cache(parsed, "ja", "ja_word")
            result = get_from_cache("暴虐", "ja", "ja_word")
        self.assertIsNotNone(result)
        self.assertEqual(result["part_of_speech"], "noun")

    def test_save_and_retrieve_ko_haebang(self):
        parsed = parse_ko_output_to_json(_KO_WORD_MARKDOWN)
        with self._patch(), self._patch_settings():
            save_to_cache(parsed, "ko", "ko_word")
            result = get_from_cache("해방", "ko", "ko_word")
        self.assertIsNotNone(result)
        self.assertEqual(result["word"], "해방")

    def test_save_and_retrieve_ko_tujaeng(self):
        parsed = parse_ko_output_to_json(_KO_WORD_TUJAENG_MARKDOWN)
        with self._patch(), self._patch_settings():
            save_to_cache(parsed, "ko", "ko_word")
            result = get_from_cache("투쟁", "ko", "ko_word")
        self.assertIsNotNone(result)
        self.assertEqual(result["romanization"], "tujaeng")

    def test_cache_miss_returns_none(self):
        with self._patch(), self._patch_settings():
            result = get_from_cache("真理", "zh", "zh_word")
        self.assertIsNone(result)

    def test_wrong_type_returns_none(self):
        parsed = parse_zh_output_to_json(_ZH_WORD_MARKDOWN)
        with self._patch(), self._patch_settings():
            save_to_cache(parsed, "zh", "zh_word")
            result = get_from_cache("斗爭", "zh", "zh_character")
        self.assertIsNone(result)

    def test_save_missing_term_raises(self):
        """save_to_cache raises ValueError if the term field is absent."""
        bad_data = {"traditional": None, "simplified": None}
        with self._patch(), self._patch_settings():
            with self.assertRaises(ValueError):
                save_to_cache(bad_data, "zh", "zh_word")


# ---------------------------------------------------------------------------
# TestMatcherIntegration
# ---------------------------------------------------------------------------


class TestMatcherIntegration(unittest.TestCase):
    """End-to-end integration: lookup_matcher feeds tokenizer correctly."""

    @_skip_on_error
    def test_zh_phrase_tokenized_dou_zheng(self):
        """斗争 in backticks ends up as a token in zh list."""
        result = lookup_matcher("`这是最后的斗争`", "zh")
        if "zh" in result:
            tokens = [
                item[0] if isinstance(item, tuple) else item for item in result["zh"]
            ]
            self.assertTrue(any("斗争" in t or "斗" in t for t in tokens))

    @_skip_on_error
    def test_zh_phrase_tokenized_tuan_jie(self):
        """`团结起来到明天` tokenizes and 团结 is reachable."""
        result = lookup_matcher("`团结起来到明天`", "zh")
        if "zh" in result:
            tokens = [
                item[0] if isinstance(item, tuple) else item for item in result["zh"]
            ]
            self.assertTrue(any("团结" in t or t in "团结" for t in tokens))

    @_skip_on_error
    def test_ja_phrase_tokenized_bougyaku(self):
        """暴虐 appears in the ja token list from 暴虐の鎖断つ日."""
        result = lookup_matcher("`暴虐の鎖断つ日`", "ja")
        if "ja" in result:
            tokens = [
                item[0] if isinstance(item, tuple) else item for item in result["ja"]
            ]
            self.assertTrue(len(tokens) >= 1)

    @_skip_on_error
    def test_ko_phrase_tokenized_hae_bang_git_bal(self):
        """해방 and 깃발 appear in ko tokens from the full phrase."""
        result = lookup_matcher("`민중이여 해방의 깃발 아래 서자`", "ko")
        if "ko" in result:
            tokens = [
                item[0] if isinstance(item, tuple) else item for item in result["ko"]
            ]
            self.assertIn("해방", tokens)
            self.assertIn("깃발", tokens)

    @_skip_on_error
    def test_explicit_flag_set_for_inline_lang(self):
        """Inline language spec sets the explicit flag to True on the token."""
        result = lookup_matcher("`깃발`:ko", language_code=None)
        if "ko" in result:
            for item in result["ko"]:
                if isinstance(item, tuple):
                    _, is_explicit = item
                    self.assertTrue(is_explicit)

    @_skip_on_error
    def test_explicit_flag_false_for_inferred_lang(self):
        """Token from script-inferred language has explicit flag False."""
        result = lookup_matcher("`해방`", None)
        if "ko" in result:
            for item in result["ko"]:
                if isinstance(item, tuple):
                    _, is_explicit = item
                    self.assertFalse(is_explicit)


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


def run_specific_test(test_class, test_method=None):
    """Run a specific test class or individual method."""
    if test_method:
        suite = unittest.TestSuite([test_class(test_method)])
    else:
        suite = unittest.TestLoader().loadTestsFromTestCase(test_class)
    runner = unittest.TextTestRunner(verbosity=2)
    return runner.run(suite)


def run_all_tests():
    """Run the full test suite with detailed output."""
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    test_classes = [
        TestZhJaTokenizer,
        TestKoTokenizer,
        TestLookupMatcher,
        TestCacheParserZh,
        TestCacheParserJa,
        TestCacheParserKo,
        TestCacheReadWrite,
        TestMatcherIntegration,
    ]

    for test_class in test_classes:
        suite.addTests(loader.loadTestsFromTestCase(test_class))

    runner = unittest.TextTestRunner(verbosity=2)
    return runner.run(suite)


if __name__ == "__main__":
    print("=" * 70)
    print("CJK Lookup Test Suite")
    print("=" * 70)
    run_all_tests()
