#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
Handles the text matching functions for the other lookup functions.
Serves as a consolidator of detecting matching strings.
"""
import re

import jieba
import MeCab
import unidic

from commands import command_parser
from config import logger, load_settings, Paths
from connection import get_random_useragent
from languages import converter
from title_handling import extract_lingvos_from_text
from zh import simplify

useragent = get_random_useragent()


def wiktionary_search() -> str | None:
    """This is going to have to be completely redone. In the meantime,
    disable Wiktionary search."""

    return


"""MATCHING TEXT"""


def lookup_zh_ja_tokenizer(phrase, language):
    """
    Tokenizes a given phrase in Chinese or Japanese using appropriate libraries:
    - Chinese ('zh'): Uses Jieba.
    - Japanese ('ja'): Uses MeCab.

    This function is called by `lookup_matcher`.

    :param phrase: The text to be tokenized.
    :param language: Language code, either 'zh' or 'ja'.
    :return: A list of tokenized words, excluding kana (optional) and punctuation.
    """

    def is_valid_token(token):
        """Returns True if the token is not a punctuation character."""
        return not re.match(r"[.!/_,$%^*+\"\'\[\]—！，。？、~@#￥…&（）：“”《》»〔〕「」％]+", token)

    if language == 'zh':
        tokens = list(jieba.cut(phrase, cut_all=False))

    elif language == 'ja':
        tagger = MeCab.Tagger(f'-d "{unidic.DICDIR}"')
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


def lookup_matcher(content_text, language_code):
    """
    Evaluate a comment for lookup and return detected text keyed by language code.
    Only text enclosed in backticks (`) is processed, excluding
    triple-backtick code blocks.
    Tokenizes Chinese ('zh'), Japanese ('ja'), and Korean ('ko') appropriately.

    :param content_text: Text of the comment to search.
    :param language_code: Language code ('zh', 'ja', 'ko'), or None to return list of terms in backticks.
    :return: Dict mapping language code to list of terms, or list if language_code is None.
    """
    original_text = str(content_text)
    # Remove all triple-backtick blocks (```...```)
    content_text = re.sub(r'```.*?```', '', content_text, flags=re.DOTALL)

    cjk_languages = load_settings(Paths.SETTINGS['LANGUAGES_MODULE_SETTINGS'])

    # Check for explicit identify command
    if "!identify:" in original_text:
        parsed = command_parser(original_text, "!identify:")[0]
        for key in ['Chinese', 'Japanese', 'Korean']:
            if len(parsed) == 4 and parsed.title() in cjk_languages[key]:  # TODO change to use codes
                parsed = key
        language_code = converter(parsed).preferred_code

    elif language_code is None:
        mentions = extract_lingvos_from_text(content_text)
        if mentions and len(mentions) == 1:
            language_code = mentions[0]

    # Extract all segments between backticks
    matches = re.findall(r'`(.*?)`', content_text, re.DOTALL)
    if not matches:
        return [] if language_code is None else {}

    combined_text = "".join(matches)

    # Unicode script detection
    has_hanzi = bool(re.search(r'[\u2E80-\u9FFF\U00020000-\U0002EBEF]', combined_text))
    has_kana = bool(re.search(r'[\u3041-\u309f\u30a0-\u30ff]', combined_text))
    has_hangul = bool(re.search(r'[\uac00-\ud7af]', combined_text))

    if language_code is None:
        return matches

    result = {}

    # Chinese and Japanese handling
    if has_hanzi or has_kana:
        cjk_tokens = []
        for match in matches:
            segments = re.findall(r'[\u2E80-\u9FFF\U00020000-\U0002EBEF]+', match)
            cjk_tokens.extend(segments)

        logger.debug(f"[ZW] Lookup_Matcher: Provisional: {cjk_tokens}")

        tokenized = []
        for token in cjk_tokens:
            if len(token) >= 2:
                if language_code == "zh" and not has_kana:
                    new_tokens = lookup_zh_ja_tokenizer(simplify(token), "zh")
                elif language_code == "ja" or has_kana:
                    new_tokens = lookup_zh_ja_tokenizer(token, "ja")
                else:
                    new_tokens = [token]
                tokenized.extend(new_tokens)
            else:
                tokenized.append(token)

        lang_key = "ja" if has_kana else language_code
        result[lang_key] = tokenized

    # Korean handling
    if has_hangul:
        hangul_tokens = []
        for match in matches:
            hangul_tokens.extend(re.findall(r'[\uac00-\ud7af]+', match))
        result["ko"] = hangul_tokens

    # Other languages (non-CJK)
    all_cjk_codes = {"zh", "ja", "ko"}
    if not (has_hanzi or has_kana or has_hangul) and language_code not in all_cjk_codes:
        seen = set()
        deduped = [term for term in matches if term not in seen and not seen.add(term)]
        result[language_code] = deduped

    return result


if __name__ == "__main__":
    print(lookup_matcher("`世界无产阶级人民万岁`", "zh"))
