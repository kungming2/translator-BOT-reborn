#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
Handles the text matching and tokenizing functions for the other lookup
functions. Serves as a consolidator of detecting matching strings.
"""
import os
import re

import jieba
import MeCab
import unidic_lite
from kiwipiepy import Kiwi

from config import load_settings, Paths
from connection import get_random_useragent
from title_handling import extract_lingvos_from_text
from languages import converter
from lookup.zh import simplify

useragent = get_random_useragent()

"""MATCHING TEXT"""


def lookup_zh_ja_tokenizer(phrase, language_code):
    """
    Tokenizes a given phrase in Chinese or Japanese using appropriate libraries:
    - Chinese ('zh'): Uses Jieba.
    - Japanese ('ja'): Uses MeCab.

    This function is called by `lookup_matcher`.

    :param phrase: The text to be tokenized.
    :param language_code: Language code, either 'zh' or 'ja'.
    :return: A list of tokenized words, excluding kana (optional) and punctuation.
    """

    def is_valid_token(token):
        """Returns True if the token is not a punctuation character."""
        return not re.match(r"[.!/_,$%^*+\"\'\[\]—！，。？、~@#￥…&（）：“”《》»〔〕「」％]+", token)

    if language_code == 'zh':
        tokens = list(jieba.cut(phrase, cut_all=False))

    elif language_code == 'ja':
        dic_dir = unidic_lite.DICDIR
        mecab_rc_path = os.path.join(dic_dir, "mecabrc")
        tagger = MeCab.Tagger(f'-r "{mecab_rc_path}" -d "{dic_dir}"')
        tagger.parse(phrase)  # Workaround for Unicode bug in MeCab
        node = tagger.parseToNode(phrase.strip())

        tokens = []
        while node:
            surface = node.surface
            if surface:
                # Exclude single-character kana
                if not (len(surface) == 1 and re.match(r'[\u3040-\u309f]', surface)):
                    tokens.append(surface)
            node = node.next

    else:
        raise ValueError("Unsupported language code. Use 'zh' or 'ja'.")

    # Filter out punctuation
    return [token for token in tokens if is_valid_token(token)]


def lookup_ko_tokenizer(phrase):
    """
    Tokenizes a Korean phrase using Kiwi and returns only content words
    (nouns, verbs, adjectives), excluding particles, grammatical endings, and punctuation.

    :param phrase: Korean text to tokenize
    :return: List of content words
    """
    kiwi = Kiwi()
    # Tokenize with normalization to handle coda endings properly
    tokens = kiwi.tokenize(phrase, normalize_coda=True)

    # Keep only nouns (NN*), verbs (VV), and adjectives (VA)
    content_tags = {"NNG", "NNP", "NNB", "VV", "VA"}

    content_words = [token.form for token in tokens if token.tag in content_tags]

    return content_words


def lookup_matcher(content_text, language_code):
    """
    Evaluate a comment for lookup and return detected text keyed by language code.
    Only text enclosed in backticks (`) is processed, excluding triple-backtick code blocks.
    Tokenizes Chinese ('zh'), Japanese ('ja'), and Korean ('ko') appropriately.
    Supports !identify or !id commands with multiple languages (e.g., !identify:zh+ja).

    :param content_text: Text of the comment to search.
    :param language_code: Language code ('zh', 'ja', 'ko') or None. Can be a string like 'zh+ja'.
    :return: Dict mapping language code to list of terms.
    """
    original_text = str(content_text)

    # Remove all triple-backtick blocks (```...```)
    content_text = re.sub(r'```.*?```', '', content_text, flags=re.DOTALL)

    cjk_languages = load_settings(Paths.SETTINGS['LANGUAGES_MODULE_SETTINGS'])

    # --- Handle !identify or !id command ---
    match = re.search(r"!(?:identify|id):\s*(\S+)", original_text)
    if match:
        raw_codes = match.group(1).split("+")
        language_codes = []
        for code in raw_codes:
            parsed = converter(code).preferred_code
            # Map 4-letter SIL code to CJK if needed
            for key in ['zh', 'ja', 'ko']:
                if len(parsed) == 4 and parsed in cjk_languages[key]:
                    parsed = key
            if parsed not in language_codes:
                language_codes.append(parsed)
    elif language_code:
        # Convert string with + to list
        if isinstance(language_code, str):
            language_codes = language_code.split("+")
        else:
            language_codes = [language_code]
    else:
        mentions = extract_lingvos_from_text(content_text)
        if mentions and len(mentions) == 1:
            language_codes = [mentions[0].preferred_code]
        else:
            language_codes = []

    # --- Extract all segments between backticks ---
    matches = re.findall(r'`(.*?)`', content_text, re.DOTALL)
    if not matches:
        return {}

    combined_text = "".join(matches)

    # Unicode script detection
    has_hanzi = bool(re.search(r'[\u2E80-\u9FFF\U00020000-\U0002EBEF]', combined_text))
    has_kana = bool(re.search(r'[\u3041-\u309f\u30a0-\u30ff]', combined_text))
    has_hangul = bool(re.search(r'[\uac00-\ud7af]', combined_text))

    result = {}

    # --- Handle Chinese and Japanese ---
    if has_hanzi or has_kana:
        cjk_tokens = []
        for match_text in matches:
            segments = re.findall(r'[\u2E80-\u9FFF\U00020000-\U0002EBEF]+', match_text)
            cjk_tokens.extend(segments)

        tokenized = []
        for token in cjk_tokens:
            if len(token) >= 2:
                if 'zh' in language_codes and not has_kana:
                    new_tokens = lookup_zh_ja_tokenizer(simplify(token), "zh")
                elif 'ja' in language_codes or has_kana:
                    new_tokens = lookup_zh_ja_tokenizer(token, "ja")
                else:
                    new_tokens = [token]
                tokenized.extend(new_tokens)
            else:
                tokenized.append(token)

        # Assign tokenized text to all requested CJK languages
        for code in language_codes:
            if code in ['zh', 'ja']:
                result[code] = tokenized

    # --- Handle Korean ---
    if has_hangul:
        hangul_tokens = []
        for match_text in matches:
            # Use your tokenizer to get content words
            hangul_tokens.extend(lookup_ko_tokenizer(match_text))

        if 'ko' in language_codes:
            result['ko'] = hangul_tokens

    # --- Handle non-CJK languages ---
    all_cjk_codes = {"zh", "ja", "ko"}
    non_cjk_codes = [code for code in language_codes if code not in all_cjk_codes]
    if non_cjk_codes:
        seen = set()
        deduped = [term for term in matches if term not in seen and not seen.add(term)]
        for code in non_cjk_codes:
            result[code] = deduped

    return result


if __name__ == "__main__":
    print(lookup_matcher("`就一定要实现！`", "zh"))
    print(lookup_matcher("`連帯こそは普遍なれ`", "ja"))
    print(lookup_matcher("`민중이여 해방의 깃발 아래 서자`", "ko"))
