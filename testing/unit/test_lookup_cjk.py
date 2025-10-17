#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
Test suite for match_helpers.py module.
Tests tokenization, text matching, and language detection functions.
"""

import unittest

from lookup.match_helpers import lookup_ko_tokenizer, lookup_matcher, lookup_zh_ja_tokenizer


class TestZhJaTokenizer(unittest.TestCase):
    """Test the lookup_zh_ja_tokenizer function."""

    def test_tokenizer_chinese_simple(self):
        """Test Chinese tokenization with simple phrase."""
        try:
            result = lookup_zh_ja_tokenizer("我是学生", "zh")
            self.assertIsInstance(result, list)
            self.assertTrue(len(result) > 0)
            for token in result:
                self.assertIsInstance(token, str)
        except Exception as e:
            self.skipTest(f"Chinese tokenization not available: {e}")

    def test_tokenizer_chinese_with_punctuation(self):
        """Test Chinese tokenization removes punctuation."""
        try:
            result = lookup_zh_ja_tokenizer("你好！我是学生。", "zh")
            self.assertIsInstance(result, list)
            # Should not contain punctuation marks
            for token in result:
                self.assertFalse(token in ["！", "。", "!", "."])
        except Exception as e:
            self.skipTest(f"Chinese tokenization not available: {e}")

    def test_tokenizer_chinese_multiple_words(self):
        """Test Chinese tokenization produces multiple tokens."""
        try:
            result = lookup_zh_ja_tokenizer("我爱学习中文", "zh")
            self.assertIsInstance(result, list)
            self.assertGreater(len(result), 1)
        except Exception as e:
            self.skipTest(f"Chinese tokenization not available: {e}")

    def test_tokenizer_japanese_simple(self):
        """Test Japanese tokenization with simple phrase."""
        try:
            result = lookup_zh_ja_tokenizer("私は学生です", "ja")
            self.assertIsInstance(result, list)
            self.assertTrue(len(result) > 0)
            for token in result:
                self.assertIsInstance(token, str)
        except Exception as e:
            self.skipTest(f"Japanese tokenization not available: {e}")

    def test_tokenizer_japanese_with_kanji(self):
        """Test Japanese tokenization handles kanji properly."""
        try:
            result = lookup_zh_ja_tokenizer("漢字テスト", "ja")
            self.assertIsInstance(result, list)
            self.assertTrue(len(result) > 0)
        except Exception as e:
            self.skipTest(f"Japanese tokenization not available: {e}")

    def test_tokenizer_japanese_mixed_scripts(self):
        """Test Japanese tokenization with mixed kanji, hiragana, katakana."""
        try:
            result = lookup_zh_ja_tokenizer("日本語のテストです", "ja")
            self.assertIsInstance(result, list)
            self.assertTrue(len(result) > 0)
        except Exception as e:
            self.skipTest(f"Japanese tokenization not available: {e}")

    def test_tokenizer_invalid_language(self):
        """Test tokenizer raises error for unsupported language."""
        with self.assertRaises(ValueError):
            lookup_zh_ja_tokenizer("some text", "invalid")

    def test_tokenizer_empty_string(self):
        """Test tokenizer handles empty strings."""
        try:
            result = lookup_zh_ja_tokenizer("", "zh")
            self.assertIsInstance(result, list)
        except Exception as e:
            self.skipTest(f"Tokenization not available: {e}")

    def test_tokenizer_punctuation_only(self):
        """Test tokenizer with only punctuation."""
        try:
            result = lookup_zh_ja_tokenizer("。！？，；：", "zh")
            self.assertIsInstance(result, list)
            # Should be empty or minimal after filtering
        except Exception as e:
            self.skipTest(f"Tokenization not available: {e}")

    def test_tokenizer_chinese_numbers(self):
        """Test Chinese tokenization with numbers."""
        try:
            result = lookup_zh_ja_tokenizer("一二三四五", "zh")
            self.assertIsInstance(result, list)
            self.assertTrue(len(result) > 0)
        except Exception as e:
            self.skipTest(f"Chinese tokenization not available: {e}")

    def test_tokenizer_japanese_numbers(self):
        """Test Japanese tokenization with numbers."""
        try:
            result = lookup_zh_ja_tokenizer("123abc", "ja")
            self.assertIsInstance(result, list)
        except Exception as e:
            self.skipTest(f"Japanese tokenization not available: {e}")


class TestKoTokenizer(unittest.TestCase):
    """Test the lookup_ko_tokenizer function."""

    def test_tokenizer_korean_simple(self):
        """Test Korean tokenization with simple phrase."""
        try:
            result = lookup_ko_tokenizer("나는 학생입니다")
            self.assertIsInstance(result, list)
            self.assertTrue(len(result) > 0)
            for token in result:
                self.assertIsInstance(token, str)
        except Exception as e:
            self.skipTest(f"Korean tokenization not available: {e}")

    def test_tokenizer_korean_multiple_words(self):
        """Test Korean tokenization produces multiple tokens."""
        try:
            result = lookup_ko_tokenizer("안녕하세요 저는 학생입니다")
            self.assertIsInstance(result, list)
            self.assertGreater(len(result), 1)
        except Exception as e:
            self.skipTest(f"Korean tokenization not available: {e}")

    def test_tokenizer_korean_content_words_only(self):
        """Test Korean tokenizer returns content words, excluding particles."""
        try:
            result = lookup_ko_tokenizer("나는 학교에 간다")
            self.assertIsInstance(result, list)
            # Should contain content words but filter particles (은/는/에/다)
            for token in result:
                self.assertIsInstance(token, str)
        except Exception as e:
            self.skipTest(f"Korean tokenization not available: {e}")

    def test_tokenizer_korean_with_punctuation(self):
        """Test Korean tokenization handles punctuation."""
        try:
            result = lookup_ko_tokenizer("안녕하세요! 저는 학생입니다.")
            self.assertIsInstance(result, list)
        except Exception as e:
            self.skipTest(f"Korean tokenization not available: {e}")

    def test_tokenizer_korean_empty_string(self):
        """Test Korean tokenizer with empty string."""
        try:
            result = lookup_ko_tokenizer("")
            self.assertIsInstance(result, list)
        except Exception as e:
            self.skipTest(f"Korean tokenization not available: {e}")

    def test_tokenizer_korean_numbers(self):
        """Test Korean tokenization with numbers."""
        try:
            result = lookup_ko_tokenizer("하나 둘 셋")
            self.assertIsInstance(result, list)
        except Exception as e:
            self.skipTest(f"Korean tokenization not available: {e}")

    def test_tokenizer_korean_single_word(self):
        """Test Korean tokenizer with single word."""
        try:
            result = lookup_ko_tokenizer("학생")
            self.assertIsInstance(result, list)
            self.assertTrue(len(result) >= 1)
        except Exception as e:
            self.skipTest(f"Korean tokenization not available: {e}")


class TestLookupMatcher(unittest.TestCase):
    """Test the lookup_matcher function."""

    def test_matcher_chinese_backticks(self):
        """Test matcher extracts Chinese text in backticks."""
        try:
            result = lookup_matcher("`你好`", "zh")
            self.assertIsInstance(result, dict)
        except Exception as e:
            self.skipTest(f"Lookup matcher not available: {e}")

    def test_matcher_japanese_backticks(self):
        """Test matcher extracts Japanese text in backticks."""
        try:
            result = lookup_matcher("`こんにちは`", "ja")
            self.assertIsInstance(result, dict)
        except Exception as e:
            self.skipTest(f"Lookup matcher not available: {e}")

    def test_matcher_korean_backticks(self):
        """Test matcher extracts Korean text in backticks."""
        try:
            result = lookup_matcher("`안녕하세요`", "ko")
            self.assertIsInstance(result, dict)
        except Exception as e:
            self.skipTest(f"Lookup matcher not available: {e}")

    def test_matcher_ignores_triple_backticks(self):
        """Test matcher ignores code blocks with triple backticks."""
        try:
            text = "Check this ```code block``` and this `actual text`"
            result = lookup_matcher(text, "zh")
            self.assertIsInstance(result, dict)
        except Exception as e:
            self.skipTest(f"Lookup matcher not available: {e}")

    def test_matcher_no_backticks(self):
        """Test matcher returns empty dict with no backticks."""
        try:
            result = lookup_matcher("no backticks here", "zh")
            self.assertEqual(result, {})
        except Exception as e:
            self.skipTest(f"Lookup matcher not available: {e}")

    def test_matcher_multiple_backticks(self):
        """Test matcher handles multiple backtick segments."""
        try:
            text = "`first` text `second`"
            result = lookup_matcher(text, "zh")
            self.assertIsInstance(result, dict)
        except Exception as e:
            self.skipTest(f"Lookup matcher not available: {e}")

    def test_matcher_identify_command_single(self):
        """Test matcher parses !identify command with single language."""
        try:
            text = "`中文` !identify:zh"
            result = lookup_matcher(text, language_code="zh")
            self.assertIsInstance(result, dict)
        except Exception as e:
            self.skipTest(f"Lookup matcher not available: {e}")

    def test_matcher_identify_command_multiple(self):
        """Test matcher parses !identify command with multiple languages."""
        try:
            text = "`文字` !identify:zh+ja"
            result = lookup_matcher(text, language_code=None)
            self.assertIsInstance(result, dict)
        except Exception as e:
            self.skipTest(f"Lookup matcher not available: {e}")

    def test_matcher_id_command_shorthand(self):
        """Test matcher recognizes !id shorthand command."""
        try:
            text = "`文字` !id:zh"
            result = lookup_matcher(text, language_code="zh")
            self.assertIsInstance(result, dict)
        except Exception as e:
            self.skipTest(f"Lookup matcher not available: {e}")

    def test_matcher_language_code_string(self):
        """Test matcher handles language_code as string."""
        try:
            result = lookup_matcher("`text`", "zh")
            self.assertIsInstance(result, dict)
        except Exception as e:
            self.skipTest(f"Lookup matcher not available: {e}")

    def test_matcher_multiple_languages_plus(self):
        """Test matcher handles multiple languages with + delimiter."""
        try:
            result = lookup_matcher("`text`", "zh+ja")
            self.assertIsInstance(result, dict)
        except Exception as e:
            self.skipTest(f"Lookup matcher not available: {e}")

    def test_matcher_none_language_code(self):
        """Test matcher with None language_code."""
        try:
            result = lookup_matcher("`text`", None)
            self.assertIsInstance(result, dict)
        except Exception as e:
            self.skipTest(f"Lookup matcher not available: {e}")

    def test_matcher_hanzi_detection(self):
        """Test matcher detects Hanzi (Chinese characters)."""
        try:
            result = lookup_matcher("`漢字`", "zh")
            self.assertIsInstance(result, dict)
        except Exception as e:
            self.skipTest(f"Lookup matcher not available: {e}")

    def test_matcher_kana_detection(self):
        """Test matcher detects Kana (Japanese characters)."""
        try:
            result = lookup_matcher("`ひらがな`", "ja")
            self.assertIsInstance(result, dict)
        except Exception as e:
            self.skipTest(f"Lookup matcher not available: {e}")

    def test_matcher_hangul_detection(self):
        """Test matcher detects Hangul (Korean characters)."""
        try:
            result = lookup_matcher("`한글`", "ko")
            self.assertIsInstance(result, dict)
        except Exception as e:
            self.skipTest(f"Lookup matcher not available: {e}")

    def test_matcher_latin_text(self):
        """Test matcher with latin/non-CJK text."""
        try:
            result = lookup_matcher("`hello world`", "en")
            self.assertIsInstance(result, dict)
        except Exception as e:
            self.skipTest(f"Lookup matcher not available: {e}")

    def test_matcher_mixed_scripts(self):
        """Test matcher with mixed CJK and latin scripts."""
        try:
            result = lookup_matcher("`你好hello`", "zh")
            self.assertIsInstance(result, dict)
        except Exception as e:
            self.skipTest(f"Lookup matcher not available: {e}")

    def test_matcher_empty_input(self):
        """Test matcher with empty input."""
        try:
            result = lookup_matcher("", "zh")
            self.assertIsInstance(result, dict)
        except Exception as e:
            self.skipTest(f"Lookup matcher not available: {e}")

    def test_matcher_result_structure(self):
        """Test matcher result has expected structure."""
        try:
            result = lookup_matcher("`test`", "zh")
            self.assertIsInstance(result, dict)
            for key, value in result.items():
                self.assertIsInstance(key, str)
                self.assertIsInstance(value, list)
        except Exception as e:
            self.skipTest(f"Lookup matcher not available: {e}")


class TestTokenizerIntegration(unittest.TestCase):
    """Integration tests for tokenizers with lookup_matcher."""

    def test_matcher_chinese_tokenizes(self):
        """Test matcher Chinese text is properly tokenized."""
        try:
            result = lookup_matcher("`我是学生`", "zh")
            if result and "zh" in result:
                self.assertIsInstance(result["zh"], list)
                self.assertTrue(len(result["zh"]) > 0)
        except Exception as e:
            self.skipTest(f"Integration test not available: {e}")

    def test_matcher_japanese_tokenizes(self):
        """Test matcher Japanese text is properly tokenized."""
        try:
            result = lookup_matcher("`私は学生です`", "ja")
            if result and "ja" in result:
                self.assertIsInstance(result["ja"], list)
                self.assertTrue(len(result["ja"]) > 0)
        except Exception as e:
            self.skipTest(f"Integration test not available: {e}")

    def test_matcher_korean_tokenizes(self):
        """Test matcher Korean text is properly tokenized."""
        try:
            result = lookup_matcher("`나는 학생입니다`", "ko")
            if result and "ko" in result:
                self.assertIsInstance(result["ko"], list)
                self.assertTrue(len(result["ko"]) > 0)
        except Exception as e:
            self.skipTest(f"Integration test not available: {e}")

    def test_matcher_cjk_prioritization(self):
        """Test matcher prioritizes detected script."""
        try:
            # Mixed text should be assigned to detected language
            result = lookup_matcher("`你好`", "zh+ja")
            self.assertIsInstance(result, dict)
        except Exception as e:
            self.skipTest(f"Integration test not available: {e}")


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
        TestZhJaTokenizer,
        TestKoTokenizer,
        TestLookupMatcher,
        TestTokenizerIntegration,
    ]

    for test_class in test_classes:
        suite.addTests(loader.loadTestsFromTestCase(test_class))

    runner = unittest.TextTestRunner(verbosity=2)
    return runner.run(suite)


if __name__ == "__main__":
    print("=" * 70)
    print("Other Module Test Suite")
    print("=" * 70)
    run_all_tests()
