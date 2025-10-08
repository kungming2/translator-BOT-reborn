#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""Simple command wrapper for CJK languages lookup."""
import random
import time

from config import logger, load_settings, Paths
from lookup.ja import ja_character, ja_word
from lookup.ko import ko_word
from lookup.zh import zh_character, zh_word
from reddit_sender import comment_reply
from responses import RESPONSE


def get_cjk_languages():
    """Load and return CJK language configuration."""
    language_settings = load_settings(Paths.SETTINGS['LANGUAGES_MODULE_SETTINGS'])
    return language_settings['CJK_LANGUAGES']


def find_cjk_language(preferred_code):
    """Find CJK language category from preferred language code."""
    cjk_languages = get_cjk_languages()

    for language, codes in cjk_languages.items():
        if preferred_code in codes:
            return language

    return None


def _lookup_chinese_term(term):
    """Perform Chinese character or word lookup."""
    if len(term) == 1:
        return zh_character(term)
    return zh_word(term)


def _lookup_japanese_term(term):
    """Perform Japanese character or word lookup."""
    if len(term) == 1:
        return ja_character(term)
    return ja_word(term)


def _lookup_korean_term(term):
    """Perform Korean word lookup."""
    return ko_word(term)


def _rate_limit_delay():
    """Add randomized delay between lookup requests."""
    time.sleep(random.randint(3, 10))


def _get_lookup_language(instruo, ajo):
    """Determine the language to use for lookup."""
    # Check if there's an identify command that specifies the language
    identify_komando = next(
        (k for k in instruo.commands if k.name == 'identify'),
        None
    )

    if identify_komando:
        logger.info(f"Found identify komando with data: {identify_komando.data}")
        return identify_komando.data[0]

    # Default to the Ajo's language
    return ajo.lingvo


def _perform_lookups(cjk_language, search_terms):
    """Perform lookups based on CJK language type."""
    lookup_functions = {
        'Chinese': _lookup_chinese_term,
        'Japanese': _lookup_japanese_term,
        'Korean': _lookup_korean_term
    }

    lookup_func = lookup_functions.get(cjk_language)
    if not lookup_func:
        return []

    results = []
    for term in search_terms:
        result = lookup_func(term)
        if result:
            results.append(result)
        _rate_limit_delay()

    return results


def _format_reply(ajo, lookup_results):
    """Format the reply body with lookup results."""
    formatted_results = '\n\n'.join(lookup_results)
    author_tag = (
        f"*u/{ajo.author} (OP), the following lookup results "
        "may be of interest to your request.*\n\n"
    )
    return author_tag + formatted_results + RESPONSE.BOT_DISCLAIMER


def handle(comment, instruo, komando, ajo):
    """
    Handle CJK lookup commands.

    Example:
        Komando(name='cjk_lookup', data=['成功'])
    """
    logger.info("CJK Lookup handler initiated.")
    logger.info(f"[ZW] Bot: COMMAND: CJK Lookup, from u/{comment.author}.")

    # Determine which language to use for lookup
    lookup_lingvo = _get_lookup_language(instruo, ajo)

    # Map the language code to a CJK language category
    cjk_language = find_cjk_language(lookup_lingvo.preferred_code)

    if not cjk_language:
        return

    # Perform lookups for all search terms
    lookup_results = _perform_lookups(cjk_language, komando.data)

    # Reply if we have information to provide
    if lookup_results:
        reply_body = _format_reply(ajo, lookup_results)
        comment_reply(comment, reply_body)
        logger.info(f"[ZW] Bot: >> Looked up the term(s) in {cjk_language}.")


if __name__ == "__main__":
    print(get_cjk_languages())
