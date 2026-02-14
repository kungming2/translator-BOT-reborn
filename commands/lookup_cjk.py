#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""Command wrapper for CJK languages lookup."""

import asyncio
import random

from config import Paths, load_settings, logger
from models.kunulo import Kunulo
from languages import converter
from lookup.ja import ja_character, ja_word
from lookup.ko import ko_word
from lookup.zh import zh_character, zh_word
from reddit_sender import comment_reply
from responses import RESPONSE


def _get_cjk_languages() -> dict:
    """
    Load and return CJK language configuration. This config is a
    dictionary indexed by English-language names for CJK (e.g. Chinese)
    and contains language codes associated with each name. This allows
    topolects and dialects to be considered.
    """
    language_settings = load_settings(Paths.SETTINGS["LANGUAGES_MODULE_SETTINGS"])
    return language_settings["CJK_LANGUAGES"]


def _find_cjk_language(preferred_code: str) -> str | None:
    """Find CJK language category from preferred language code.
    E.g. `wuu` (for Wu Chinese) would return the English word 'Chinese'.
    """
    cjk_languages = _get_cjk_languages()

    for language, codes in cjk_languages.items():
        if preferred_code in codes:
            return language

    return None


async def _lookup_chinese_term(term: str) -> str | None:
    """Perform Chinese character or word lookup."""
    if len(term) == 1:
        return await zh_character(term)
    return await zh_word(term)


async def _lookup_japanese_term(term: str) -> str | None:
    """Perform Japanese character or word lookup."""
    if len(term) == 1:
        return await asyncio.to_thread(ja_character, term)
    return await ja_word(term)


async def _lookup_korean_term(term: str) -> str | None:
    """Perform Korean word lookup."""
    return await asyncio.to_thread(ko_word, term)  # Run sync function in thread pool


async def _rate_limit_delay() -> None:
    """Add randomized delay between lookup requests."""
    await asyncio.sleep(random.randint(3, 10))


async def perform_cjk_lookups(cjk_language: str, search_terms: list[str]) -> list[str]:
    """Perform lookups based on CJK language type.
    search_terms must be a list of strings."""
    lookup_functions = {
        "Chinese": _lookup_chinese_term,
        "Japanese": _lookup_japanese_term,
        "Korean": _lookup_korean_term,
    }

    lookup_func = lookup_functions.get(cjk_language)
    if not lookup_func:
        return []

    results: list[str] = []
    logger.info(f"Passing {search_terms} to the {cjk_language} lookup function...")
    for term in search_terms:
        result = await lookup_func(term)
        if result:
            results.append(result)
        await _rate_limit_delay()

    return results


def _format_reply(lookup_results: list[str], ajo=None) -> str:
    """Format the reply body with lookup results."""
    anchor_tag = RESPONSE.ANCHOR_CJK
    formatted_results: str = "\n\n".join(lookup_results)

    if not ajo:
        return formatted_results
    else:
        # Tag the author if there is one.
        if ajo.author:
            author_mention_tag: str = (
                f"*u/{ajo.author} (OP), the following lookup results "
                "may be of interest to your request.*\n\n"
            )
        else:
            author_mention_tag = ""
        return (
            author_mention_tag
            + formatted_results
            + RESPONSE.BOT_DISCLAIMER
            + anchor_tag
        )


def _check_for_duplicate_lookups(
    comment, search_terms: list[str], cjk_language: str
) -> dict | None:
    """
    Check if the requested CJK terms have already been looked up in this thread.
    Works for all CJK languages (Chinese, Japanese, Korean) and both characters and words.

    Args:
        comment: PRAW comment object
        search_terms: List of terms to look up (e.g., ['成功', '面粉'] or ['ばかり', '一人'])
        cjk_language: The CJK language category ('Chinese', 'Japanese', 'Korean')

    Returns:
        dict or None: If duplicates found, returns result from check_existing_cjk_lookups.
                     Otherwise returns None.
    """
    if not search_terms:
        return None

    # Create Kunulo instance from the submission
    submission = comment.submission
    kunulo = Kunulo.from_submission(submission)

    # Check for existing lookups (works for all CJK languages and all term types)
    existing = kunulo.check_existing_cjk_lookups(
        search_terms,
        exact_match=True,  # Change to False if you want subset matching
    )

    if existing:
        logger.info(
            f"[ZW] CJK Lookup: Duplicate lookup detected for {existing['matched_terms']} "
            f"in {cjk_language}"
        )
        return existing

    return None


def handle(comment, instruo, komando, ajo) -> None:
    """
    Handle for CJK lookup commands.

    Supports multi-language lookups where different terms can have different languages.
    If an !identify command is present, it provides a default language for auto-detected terms,
    but explicitly marked terms (e.g., `term`:ko) keep their specified language.

    Examples:
        - `可能` `시계`:ko with !identify:ja
          → data: [('zh', '可能', False), ('ko', '시계', True)]
          → Japanese: ['可能'], Korean: ['시계']
        - `可能` `麻将` (no !identify)
          → data: [('zh', '可能', False), ('zh', '麻将', False)]
          → Chinese: ['可能', '麻将'] (auto-detected)
    """
    logger.info("CJK Lookup handler initiated.")
    logger.info(f"[ZW] Bot: COMMAND: CJK Lookup, from u/{comment.author}.")

    # Check if there's an !identify command for auto-detected terms
    identify_komando = next((k for k in instruo.commands if k.name == "identify"), None)
    default_language = None

    if identify_komando and identify_komando.data:
        # Use the first language from !identify as default for auto-detected terms
        default_lingvo = identify_komando.data[0]
        default_language = _find_cjk_language(default_lingvo.preferred_code)
        if default_language:
            logger.info(
                f"[ZW] CJK Lookup: !identify command found - using {default_language} "
                f"as default for auto-detected terms"
            )

    # Group terms by their CJK language category
    # This allows handling mixed-language lookups like Chinese + Korean in one command
    terms_by_language = {}

    for entry in komando.data:
        # Handle both old format (lang, term) and new format (lang, term, explicit)
        if len(entry) == 3:
            lang_code, term, is_explicit = entry
        elif len(entry) == 2:
            lang_code, term = entry
            is_explicit = False  # Assume auto-detected for backward compatibility
        else:
            logger.warning(f"[ZW] CJK Lookup: Invalid entry format: {entry}")
            continue

        # Determine the language to use
        if is_explicit:
            # Explicitly marked - use the specified language
            cjk_language = _find_cjk_language(lang_code)
            logger.debug(
                f"Term '{term}' explicitly marked as {lang_code} → {cjk_language}"
            )
        elif default_language:
            # Auto-detected and we have a default from !identify - use default
            cjk_language = default_language
            logger.debug(
                f"Term '{term}' auto-detected, using !identify default → {cjk_language}"
            )
        else:
            # Auto-detected and no default - use auto-detected language
            cjk_language = _find_cjk_language(lang_code)
            logger.debug(f"Term '{term}' auto-detected as {lang_code} → {cjk_language}")

        if cjk_language:
            if cjk_language not in terms_by_language:
                terms_by_language[cjk_language] = []
            terms_by_language[cjk_language].append(term)
        else:
            logger.warning(
                f"[ZW] CJK Lookup: Could not map language code '{lang_code}' to a CJK language. "
                f"Skipping term '{term}'."
            )

    if not terms_by_language:
        logger.warning(
            "[ZW] CJK Lookup: No valid CJK terms found after language mapping."
        )
        return

    logger.info(
        f"[ZW] CJK Lookup: Processing terms grouped by language: {terms_by_language}"
    )

    # Process each language group separately
    all_lookup_results = []
    duplicate_responses = []

    for cjk_language, search_terms in terms_by_language.items():
        logger.info(
            f"[ZW] CJK Lookup: Processing {len(search_terms)} term(s) for {cjk_language}: {search_terms}"
        )

        # Check for duplicates for this language group
        duplicate_check = _check_for_duplicate_lookups(
            comment, search_terms, cjk_language
        )

        if duplicate_check:
            # Duplicate found - prepare response but don't return yet
            # (we might have other non-duplicate languages to process)
            comment_id = duplicate_check["comment_id"]
            matched_terms = duplicate_check["matched_terms"]

            # Get permalink using Kunulo
            kunulo = Kunulo.from_submission(comment.submission)
            permalink = kunulo.get_comment_permalink(comment_id)

            # Format the matched terms nicely
            chars_str = ", ".join(f"**{char}**" for char in matched_terms)

            # Store duplicate response
            duplicate_message = (
                f"The {cjk_language} term(s) {chars_str} have already been looked up. "
                f"Please see [this comment]({permalink})."
            )
            duplicate_responses.append(duplicate_message)

            logger.info(
                f"[ZW] CJK Lookup: Duplicate found for {cjk_language} terms {matched_terms} "
                f"in comment {comment_id}."
            )
            continue  # Skip to next language group

        # No duplicates - perform lookups for this language
        lookup_results = asyncio.run(perform_cjk_lookups(cjk_language, search_terms))
        all_lookup_results.extend(lookup_results)
        logger.info(f"[ZW] CJK Lookup: Completed lookups for {cjk_language}.")

    # Prepare and send reply
    reply_parts = []

    # Add duplicate notifications if any
    if duplicate_responses:
        duplicate_section = "\n\n".join(duplicate_responses)
        duplicate_section += "\n\nIf you need additional information or have questions, feel free to ask!"
        reply_parts.append(duplicate_section)

    # Add new lookup results if any
    if all_lookup_results:
        reply_body = _format_reply(all_lookup_results, ajo)
        reply_parts.append(reply_body)

    # Send reply if we have anything to say
    if reply_parts:
        final_reply = "\n\n---\n\n".join(reply_parts)
        comment_reply(comment, final_reply)
        logger.info(
            f"[ZW] CJK Lookup: Replied with {len(all_lookup_results)} new lookup(s) "
            f"and {len(duplicate_responses)} duplicate notification(s)."
        )
    else:
        logger.warning(
            "[ZW] CJK Lookup: No results to reply with (all duplicates or no matches)."
        )


if __name__ == "__main__":
    while True:
        my_language = input("Enter a CJK language code or name to use: ")
        my_input = input("Please enter a string to lookup: ")
        search_language = converter(my_language).name
        test_search_data: list[str] = asyncio.run(
            perform_cjk_lookups(search_language, [my_input])
        )
        print(_format_reply(test_search_data))
