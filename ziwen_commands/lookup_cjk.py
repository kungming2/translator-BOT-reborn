#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
Command wrapper for CJK languages lookup.
...

Logger tag: [ZW:CJK]
"""

import asyncio
import logging
import random

from praw.models import Comment

from config import Paths, load_settings
from config import logger as _base_logger
from models.ajo import Ajo
from models.instruo import Instruo
from models.komando import Komando
from models.kunulo import Kunulo
from reddit.reddit_sender import reddit_edit, reddit_reply
from responses import RESPONSE
from ziwen_lookup.ja import ja_character, ja_word
from ziwen_lookup.ko import ko_word
from ziwen_lookup.zh import zh_character, zh_word

logger = logging.LoggerAdapter(_base_logger, {"tag": "ZW:CJK"})


# ─── Language config helpers ──────────────────────────────────────────────────


def _get_cjk_languages() -> dict:
    """
    Load and return CJK language configuration. This config is a
    dictionary indexed by English-language names for CJK (e.g. Chinese)
    and contains language codes associated with each name. This allows
    topolects and dialects to be considered.
    """
    language_settings = load_settings(Paths.SETTINGS["LANGUAGES_SETTINGS"])
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


# ─── Per-language lookup functions ────────────────────────────────────────────


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


# ─── Reply formatting ─────────────────────────────────────────────────────────


def _format_reply(
    lookup_results: list[str],
    ajo: Ajo | None = None,
    parent_comment_id: str | None = None,
) -> str:
    """
    Format the reply body with lookup results.

    Args:
        lookup_results: List of formatted lookup result strings.
        ajo: The Ajo object for the post, used for OP mention. May be None.
        parent_comment_id: The Reddit comment ID of the user comment that
            triggered this reply. When provided, an invisible anchor
            ``[](#cjk_parent_XXXX)`` is embedded so Kunulo can later
            identify which bot reply belongs to which user comment,
            enabling edit-on-reprocess rather than a duplicate reply.
    """
    anchor_tag = RESPONSE.ANCHOR_CJK
    if parent_comment_id:
        anchor_tag += f"[](#cjk_parent_{parent_comment_id})"

    formatted_results: str = "\n\n".join(lookup_results)

    if not ajo:
        return formatted_results

    author_mention_tag: str = (
        (
            f"*u/{ajo.author} (OP), the following lookup results "
            "may be of interest to your request.*\n\n"
        )
        if ajo.author
        else ""
    )

    return author_mention_tag + formatted_results + RESPONSE.BOT_DISCLAIMER + anchor_tag


# ─── Duplicate detection ──────────────────────────────────────────────────────


def _check_for_duplicate_lookups(
    comment: Comment, search_terms: list[str], cjk_language: str
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

    kunulo = Kunulo.from_submission(comment.submission)
    existing = kunulo.check_existing_cjk_lookups(search_terms, exact_match=True)

    if existing:
        logger.info(
            f"Duplicate lookup detected for {existing['matched_terms']} "
            f"in {cjk_language}"
        )
        return existing

    return None


# ─── Edit-on-reprocess helper ─────────────────────────────────────────────────


def _find_existing_cjk_reply(kunulo: Kunulo, comment_id: str) -> str | None:
    """
    Return the bot comment ID of an existing CJK reply that was triggered
    by *comment_id*, or None if no such reply exists.

    This is used during edit-tracker reprocessing to locate the bot's
    previous reply so it can be updated in place rather than posted anew.

    Args:
        kunulo: A Kunulo instance already built from the submission.
        comment_id: The Reddit ID of the user comment being reprocessed.

    Returns:
        str or None: Bot comment ID to edit, or None.
    """
    return kunulo.find_cjk_reply_for_comment(comment_id)


# ─── Command handler ──────────────────────────────────────────────────────────


def handle(comment: Comment, instruo: Instruo, komando: Komando, ajo: Ajo) -> None:
    """
    Handle for CJK lookup commands.

    Supports multi-language lookups where different terms can have different languages.
    If an !identify command is present, it provides a default language for auto-detected terms,
    but explicitly marked terms (e.g., `term`:ko) keep their specified language.

    On reprocessing triggered by the edit tracker (e.g. the user changed
    backtick content to fix tokenization), the handler detects an existing
    bot reply for this comment and edits it in place rather than posting a
    new reply or emitting a spurious duplicate warning.

    Examples:
        - `可能` `시계`:ko with !identify:ja
          → data: [('zh', '可能', False), ('ko', '시계', True)]
          → Japanese: ['可能'], Korean: ['시계']
        - `可能` `麻将` (no !identify)
          → data: [('zh', '可能', False), ('zh', '麻将', False)]
          → Chinese: ['可能', '麻将'] (auto-detected)
    """
    logger.info("CJK Lookup handler initiated.")
    logger.info(f"CJK Lookup, from u/{comment.author}.")

    if not komando.data:
        logger.warning("No data in komando; nothing to look up.")
        return

    # ── Check for an existing bot reply to this comment ───────────────────────

    # Build Kunulo once here so both the edit-detection path and the
    # duplicate-check path share the same instance.
    kunulo = Kunulo.from_submission(comment.submission)
    existing_bot_reply_id = _find_existing_cjk_reply(kunulo, comment.id)

    if existing_bot_reply_id:
        logger.info(
            f"Found existing CJK reply `{existing_bot_reply_id}` for comment "
            f"`{comment.id}` — will edit in place rather than post a new reply."
        )

    # ── Resolve default language from a co-occurring !identify command ────────

    identify_komando = next((k for k in instruo.commands if k.name == "identify"), None)
    default_language = None

    if identify_komando and identify_komando.data:
        default_lingvo = identify_komando.data[0]
        default_language = _find_cjk_language(default_lingvo.preferred_code)
        if default_language:
            logger.info(
                f"!identify command found - using {default_language} "
                f"as default for auto-detected terms"
            )

    # ── Group terms by their CJK language category ────────────────────────────

    terms_by_language: dict[str, list[str]] = {}

    for entry in komando.data:
        # Handle both old format (lang, term) and new format (lang, term, explicit)
        if len(entry) == 3:
            lang_code, term, is_explicit = entry
        elif len(entry) == 2:
            lang_code, term = entry
            is_explicit = False  # Assume auto-detected for backward compatibility
        else:
            logger.warning(f"Invalid entry format: {entry}")
            continue

        if is_explicit:
            cjk_language = _find_cjk_language(lang_code)
            logger.debug(
                f"Term '{term}' explicitly marked as {lang_code} → {cjk_language}"
            )
        elif default_language:
            cjk_language = default_language
            logger.debug(
                f"Term '{term}' auto-detected, using !identify default → {cjk_language}"
            )
        else:
            cjk_language = _find_cjk_language(lang_code)
            logger.debug(f"Term '{term}' auto-detected as {lang_code} → {cjk_language}")

        if cjk_language:
            terms_by_language.setdefault(cjk_language, []).append(term)
        else:
            logger.warning(
                f"Could not map language code '{lang_code}' to a CJK language. "
                f"Skipping term '{term}'."
            )

    if not terms_by_language:
        logger.warning("No valid CJK terms found after language mapping.")
        return

    logger.info(f"Processing terms grouped by language: {terms_by_language}")

    # ── Perform lookups ───────────────────────────────────────────────────────

    # When editing an existing reply we skip the duplicate check entirely:
    # the "duplicate" IS the reply we're about to update.
    all_lookup_results = []
    duplicate_responses = []

    for cjk_language, search_terms in terms_by_language.items():
        logger.info(
            f"Processing {len(search_terms)} term(s) for {cjk_language}: {search_terms}"
        )

        if not existing_bot_reply_id:
            # Only run the duplicate check when this is a fresh (non-edit) post.
            duplicate_check = _check_for_duplicate_lookups(
                comment, search_terms, cjk_language
            )

            if duplicate_check:
                comment_id = duplicate_check["comment_id"]
                matched_terms = duplicate_check["matched_terms"]

                permalink = kunulo.get_comment_permalink(comment_id)
                chars_str = ", ".join(f"**{char}**" for char in matched_terms)

                duplicate_responses.append(
                    f"The {cjk_language} term(s) {chars_str} have already been looked up. "
                    f"Please see [this comment]({permalink})."
                )
                logger.info(
                    f"Duplicate found for {cjk_language} terms {matched_terms} "
                    f"in comment {comment_id}."
                )
                continue

        lookup_results = asyncio.run(perform_cjk_lookups(cjk_language, search_terms))
        all_lookup_results.extend(lookup_results)
        logger.info(f"Completed lookups for {cjk_language}.")

    # ── Assemble and send / edit reply ────────────────────────────────────────

    reply_parts = []

    if duplicate_responses:
        duplicate_section = "\n\n".join(duplicate_responses)
        duplicate_section += "\n\nIf this is in error, please let a moderator know."
        reply_parts.append(duplicate_section)

    if all_lookup_results:
        reply_parts.append(
            _format_reply(all_lookup_results, ajo, parent_comment_id=comment.id)
        )

    if not reply_parts:
        logger.warning("No results to reply with (all duplicates or no matches).")
        return

    final_reply = "\n\n---\n\n".join(reply_parts)
    if len(final_reply) > 10000:
        final_reply = (
            final_reply[:9000]
            + "\n\n*Lookup information has been truncated due to excessive length.*"
        )

    if existing_bot_reply_id and all_lookup_results:
        # Edit the existing reply in place.  Duplicate-response sections are
        # not included in edits: if the user fixed their comment, it's no
        # longer a duplicate situation.
        edit_body = _format_reply(all_lookup_results, ajo, parent_comment_id=comment.id)
        if len(edit_body) > 10000:
            edit_body = (
                edit_body[:9000]
                + "\n\n*Lookup information has been truncated due to excessive length.*"
            )
        reddit_edit(existing_bot_reply_id, edit_body)
        logger.info(
            f"Edited existing CJK reply `{existing_bot_reply_id}` with "
            f"{len(all_lookup_results)} updated lookup result(s)."
        )
    else:
        reddit_reply(comment, final_reply)
        logger.info(
            f"Replied with {len(all_lookup_results)} new lookup(s) "
            f"and {len(duplicate_responses)} duplicate notification(s)."
        )
