#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
Handles the text matching and tokenizing functions for the other lookup
functions. Serves as a consolidator of detecting matching strings.

For Japanese, The full UniDic provides more comprehensive linguistic
information, but it requires a separate larger download.

To install it, run:

pip install unidic
python -m unidic download
"""

import os
import re
from typing import Any

import rjieba as jieba
import MeCab
import unidic  # or unidic-lite
from kiwipiepy import Kiwi

from config import Paths, load_settings
from connection import get_random_useragent, logger
from languages import converter
from title_handling import extract_lingvos_from_text

useragent = get_random_useragent()

"""MATCHING TEXT"""


def lookup_zh_ja_tokenizer(phrase: str, language_code: str) -> list[str]:
    """
    Tokenizes a given phrase in Chinese or Japanese using appropriate libraries:
    - Chinese ('zh'): Uses Jieba with Traditional Chinese conversion to Simplified.
    - Japanese ('ja'): Uses MeCab.

    This function is called by `lookup_matcher`.

    :param phrase: The text to be tokenized.
    :param language_code: Language code, either 'zh' or 'ja'.
    :return: A list of tokenized words, excluding kana (optional) and punctuation.
    """

    def is_valid_token(token: str) -> bool:
        """Returns True if the token is not a punctuation character."""
        return not re.match(
            r"[.!/_,$%^*+\"\'\[\]—！，。？、~@#￥…&（）：" "《》»「」『』％]+〔〕",
            token,
        )

    if language_code == "zh":
        from lookup.zh import simplify

        # Simplify Traditional Chinese to Simplified for better tokenization
        simplified_phrase = simplify(phrase)
        simplified_tokens: list[str] = list(jieba.cut(simplified_phrase))

        # Map simplified tokens back to original Traditional Chinese characters
        tokens: list[str] = []
        original_idx = 0

        for simp_token in simplified_tokens:
            token_len = len(simp_token)
            # Extract corresponding substring from original phrase
            original_token = phrase[original_idx : original_idx + token_len]
            tokens.append(original_token)
            original_idx += token_len

    elif language_code == "ja":
        dic_dir: str = unidic.DICDIR  # or unidic-lite
        mecab_rc_path: str = os.path.join(dic_dir, "mecabrc")
        tagger: MeCab.Tagger = MeCab.Tagger(f'-r "{mecab_rc_path}" -d "{dic_dir}"')
        tagger.parse(phrase)  # Workaround for Unicode bug in MeCab
        node: Any = tagger.parseToNode(phrase.strip())

        tokens: list[str] = []
        while node:
            surface: str = node.surface
            if surface:
                # Exclude single-character kana
                if not (len(surface) == 1 and re.match(r"[\u3040-\u309f]", surface)):
                    tokens.append(surface)
            node = node.next

    else:
        raise ValueError("Unsupported language code. Use 'zh' or 'ja'.")

    # Filter out punctuation
    return [token for token in tokens if is_valid_token(token)]


def lookup_ko_tokenizer(phrase: str) -> list[str]:
    """
    Tokenizes a Korean phrase using Kiwi and returns only content words
    (nouns, verbs, adjectives), excluding particles, grammatical endings,
    and punctuation. Historically, Korean tokenizers have been less
    reliable, and this is kept separate from Chinese and Japanese so that
    updating may be easier in the future.

    :param phrase: Korean text to tokenize
    :return: List of content words
    """
    kiwi: Kiwi = Kiwi()
    # Tokenize with normalization to handle coda endings properly
    tokens = kiwi.tokenize(phrase, normalize_coda=True)

    # Keep nouns (NN*), verbs (VV), adjectives (VA),
    # foreign words (SL), and exclamations (IC)
    content_tags: set[str] = {"NNG", "NNP", "NNB", "VV", "VA", "SL", "IC"}

    content_words: list[str] = [
        token.form for token in tokens if token.tag in content_tags
    ]

    return content_words


def lookup_matcher(
    content_text: str, language_code: str | None, disable_tokenization: bool = False
) -> dict[str, list[str]]:
    """
    Evaluate a comment for lookup and return detected text keyed by language code.
    Only text enclosed in backticks (`) is processed, excluding triple-backtick code blocks.
    Tokenizes Chinese ('zh'), Japanese ('ja'), and Korean ('ko') appropriately.
    Supports !identify or !id commands with multiple languages (e.g., !identify:zh+ja).
    Supports inline language specification (e.g., `文化`:ja).

    :param content_text: Text of the comment to search.
    :param language_code: Language code ('zh', 'ja', 'ko') or None. Can be a string like 'zh+ja'.
    :param disable_tokenization: If True, skip tokenization and return full text segments.
    :return: Dict mapping language code to list of terms.
    """

    def map_cjk_code(cjk_code: str, cjk_lang_dict: dict) -> str:
        """Map language codes to 2-letter CJK language codes if applicable."""
        if "CJK_LANGUAGES" in cjk_lang_dict:
            cjk_lang_dict = cjk_lang_dict["CJK_LANGUAGES"]

        for lang_name, codes in cjk_lang_dict.items():
            if not isinstance(codes, list):
                continue
            if cjk_code.lower() in [c.lower() for c in codes]:
                if "Chinese" in lang_name:
                    return "zh"
                elif "Japanese" in lang_name:
                    return "ja"
                elif "Korean" in lang_name:
                    return "ko"
        return cjk_code

    original_text: str = str(content_text)

    # Remove all triple-backtick blocks (```...```)
    content_text = re.sub(r"```.*?```", "", content_text, flags=re.DOTALL)

    cjk_languages: dict = load_settings(Paths.SETTINGS["LANGUAGES_MODULE_SETTINGS"])

    # --- Handle !identify or !id command ---
    match: re.Match | None = re.search(r"!(?:identify|id):\s*(\S+)", original_text)
    if match:
        raw_codes: list[str] = match.group(1).split("+")
        language_codes: list[str] = []
        for code in raw_codes:
            parsed: str = converter(code).preferred_code
            parsed = map_cjk_code(parsed, cjk_languages)
            if parsed not in language_codes:
                language_codes.append(parsed)
    elif language_code:
        if isinstance(language_code, str):
            language_codes: list[str] = language_code.split("+")
        else:
            language_codes: list[str] = [language_code]
    else:
        mentions = extract_lingvos_from_text(content_text)
        if mentions and len(mentions) == 1:
            language_codes: list[str] = [mentions[0].preferred_code]
        else:
            language_codes: list[str] = []

    # --- Extract all segments between backticks with optional inline language spec ---
    backtick_pattern: str = r"`([^`]+?)`(?::([^!\s]+))?"
    backtick_matches: list[re.Match] = list(re.finditer(backtick_pattern, content_text))

    match_details: list[tuple[str, str | None]] = [
        (m.group(1), m.group(2)) for m in backtick_matches
    ]
    logger.debug(f"Backtick matches: {match_details}.")
    logger.debug(f"Match count: {len(backtick_matches)}. Content text: {content_text}")

    matches: list[str] = []
    inline_language_codes: list[str | None] = []

    for match_obj in backtick_matches:
        text: str = match_obj.group(1)
        inline_lang: str | None = match_obj.group(2)
        matches.append(text)

        if inline_lang:
            parsed: str = converter(inline_lang).preferred_code
            parsed = map_cjk_code(parsed, cjk_languages)
            inline_language_codes.append(parsed)
            logger.debug(f"Inline language found: {inline_lang} → {parsed}")
        else:
            inline_language_codes.append(None)
            logger.debug(f"No inline language for: {text}")

    if not matches:
        logger.debug("No matches found after backtick extraction")
        return {}

    logger.debug(f"Segment language codes: {list(zip(matches, inline_language_codes))}")

    result: dict[str, list[str | tuple[str, bool]]] = {}

    # Process each backtick segment individually
    for match_text, inline_lang in zip(matches, inline_language_codes):
        # Track whether language was explicitly specified
        is_explicit = inline_lang is not None

        # Detect scripts for THIS segment only
        has_hanzi: bool = bool(
            re.search(r"[\u2E80-\u9FFF\U00020000-\U0002EBEF]", match_text)
        )
        has_kana: bool = bool(re.search(r"[\u3041-\u309f\u30a0-\u30ff]", match_text))
        has_hangul: bool = bool(re.search(r"[\uac00-\ud7af]", match_text))

        logger.debug(
            f"Segment '{match_text}' - Hanzi: {has_hanzi}, Kana: {has_kana}, "
            f"Hangul: {has_hangul}, Explicit: {is_explicit}"
        )

        # Determine which language codes apply to this segment
        if inline_lang:
            seg_language_codes: list[str] = [inline_lang]
        else:
            seg_language_codes: list[str] = language_codes

        # If no language codes determined yet, infer from script detection FOR THIS SEGMENT
        if not seg_language_codes:
            if has_hangul:
                seg_language_codes = ["ko"]
            elif has_kana:
                seg_language_codes = ["ja"]
            elif has_hanzi:
                seg_language_codes = ["zh"]

        logger.debug(
            f"Processing segment '{match_text}' with language codes: {seg_language_codes}"
        )

        # --- If tokenization is disabled, return full segments ---
        if disable_tokenization:
            for code in seg_language_codes:
                if code not in result:
                    result[code] = []
                result[code].append((match_text, is_explicit))
            logger.debug(
                f"Added untokenized text '{match_text}' (explicit={is_explicit}) for codes: {seg_language_codes}"
            )
            continue

        # --- Handle Chinese and Japanese ---
        if has_hanzi or has_kana:
            cjk_tokens: list[str] = []
            segments: list[str] = re.findall(
                r"[\u2E80-\u9FFF\U00020000-\U0002EBEF]+", match_text
            )
            cjk_tokens.extend(segments)

            tokenized: list[str] = []
            for token in cjk_tokens:
                if len(token) >= 2:
                    if "zh" in seg_language_codes and not has_kana:
                        new_tokens: list[str] = lookup_zh_ja_tokenizer(token, "zh")
                    elif "ja" in seg_language_codes or has_kana:
                        new_tokens: list[str] = lookup_zh_ja_tokenizer(token, "ja")
                    else:
                        new_tokens: list[str] = [token]
                    tokenized.extend(new_tokens)
                else:
                    tokenized.append(token)

            # Assign tokenized text to all requested CJK languages
            # Each token gets the same explicit flag as the original segment
            for code in seg_language_codes:
                if code in ["zh", "ja"]:
                    if code not in result:
                        result[code] = []
                    for token in tokenized:
                        result[code].append((token, is_explicit))

        # --- Handle Korean ---
        if has_hangul:
            hangul_segments: list[str] = re.findall(r"[\uac00-\ud7af]+", match_text)
            hangul_tokens: list[str] = []
            for segment in hangul_segments:
                tokens: list[str] = lookup_ko_tokenizer(segment)
                hangul_tokens.extend(tokens)

            if "ko" in seg_language_codes:
                if "ko" not in result:
                    result["ko"] = []
                for token in hangul_tokens:
                    result["ko"].append((token, is_explicit))
                logger.debug(
                    f"Added Korean tokens (explicit={is_explicit}): {hangul_tokens}"
                )

        # --- Handle non-CJK languages ---
        all_cjk_codes: set[str] = {"zh", "ja", "ko"}
        non_cjk_codes: list[str] = [
            code for code in seg_language_codes if code not in all_cjk_codes
        ]
        if non_cjk_codes:
            for code in non_cjk_codes:
                if code not in result:
                    result[code] = []
                result[code].append((match_text, is_explicit))

    logger.info(f"Lookup Matcher Result: {result}")

    return result


if __name__ == "__main__":
    while True:
        print("=" * 30)
        print("Note: Backticks will be automatically added around your phrase.\n")

        test_phrase = input("Enter phrase: ")
        lang_code = input("Enter language code (zh/ja/ko): ")

        # Add backticks around the phrase
        phrase_with_backticks = f"`{test_phrase.strip()}`"

        test_result = lookup_matcher(phrase_with_backticks, lang_code)
        print(f"\nResult: {test_result}")
