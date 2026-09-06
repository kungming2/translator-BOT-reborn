#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
Simple command wrapper for Wiktionary lookup.
...

Logger tag: [ZW:WT]
"""

import logging
import math
import time
from collections import defaultdict

from praw.models import Comment
from requests.exceptions import HTTPError

from config import SETTINGS
from config import logger as _base_logger
from lang.code_standards import PROJECT_LANGUAGE_CODES
from lang.languages import converter
from models.ajo import Ajo
from models.instruo import Instruo
from models.komando import Komando
from models.kunulo import Kunulo
from reddit.reddit_sender import reddit_edit, reddit_reply
from responses import RESPONSE
from ziwen_lookup.wiktionary import format_wiktionary_markdown, wiktionary_search

logger = logging.LoggerAdapter(_base_logger, {"tag": "ZW:WT"})

_AMBIGUOUS_CODES: frozenset[str] = PROJECT_LANGUAGE_CODES
_DEFAULT_429_RETRY_DELAY_SECONDS = 60.0
_MAX_429_RETRY_DELAY_SECONDS = 60.0


def _retry_after_seconds(error: HTTPError) -> float:
    """Return a usable Retry-After delay, falling back to sixty seconds."""
    response = error.response
    retry_after = response.headers.get("Retry-After") if response is not None else None
    if retry_after is not None:
        try:
            parsed = float(retry_after)
        except ValueError:
            pass
        else:
            if math.isfinite(parsed) and parsed > 0:
                return parsed
    return _DEFAULT_429_RETRY_DELAY_SECONDS


def _is_rate_limit_error(error: HTTPError) -> bool:
    """Return whether an HTTP error represents a Wiktionary rate limit."""
    return error.response is not None and error.response.status_code == 429


# ─── Reply formatting ─────────────────────────────────────────────────────────


def _format_wt_reply(
    reply_parts: list[str], parent_comment_id: str | None = None
) -> str:
    """
    Assemble the final Wiktionary reply body from formatted lookup sections.

    Joins *reply_parts* with double newlines, then appends the standard
    Wiktionary anchor.  If *parent_comment_id* is supplied, an invisible
    edit-tracking anchor (``[](#wt_parent_<id>)``) is also appended so
    that a future Kunulo can locate and edit this reply in place.
    """
    anchor = RESPONSE.ANCHOR_WIKTIONARY
    if parent_comment_id:
        anchor += f"[](#wt_parent_{parent_comment_id})"
    return "\n\n".join(reply_parts) + RESPONSE.BOT_DISCLAIMER + anchor


# ─── Command handler ──────────────────────────────────────────────────────────


def handle(comment: Comment, _instruo: Instruo, komando: Komando, ajo: Ajo) -> None:
    """
    Command handler called by ziwen_commands().

    Looks up each backtick-enclosed term via Wiktionary. The language used
    for each term is resolved in priority order:
      1. Inline suffix on the backtick term (e.g. `kunulo`:eo → Esperanto)
      2. Language of the post (ajo.language_name), if unambiguous
      3. English as a last resort

    Terms sharing the same resolved language are grouped into a single
    lookup call and reply section.

    Examples of komando.data:
        [('eo', 'kunulo', True)]          # explicit inline suffix
        [('und', 'schadenfreude', False)]  # no suffix, post language used
    """
    logger.info("Wiktionary Lookup handler initiated.")
    logger.info(f"Wiktionary Lookup, from u/{comment.author}.")

    if not komando.data:
        logger.info("> No lookup terms provided. Ignoring.")
        return

    max_lookups = int(SETTINGS.get("max_wiktionary_lookups_per_comment", 5))
    if len(komando.data) > max_lookups:
        logger.warning(
            "Ignoring Wiktionary lookup bundle for comment `%s`: %s terms exceed "
            "the per-comment maximum of %s.",
            comment.id,
            len(komando.data),
            max_lookups,
        )
        return

    # ── Check for an existing bot reply to this comment ───────────────────────

    kunulo = Kunulo.from_submission(comment.submission)
    existing_bot_reply_id = kunulo.find_wt_reply_for_comment(comment.id)

    if existing_bot_reply_id:
        logger.info(
            f"Found existing Wiktionary reply `{existing_bot_reply_id}` for comment "
            f"`{comment.id}` — will edit in place rather than post a new reply."
        )

    # ── Resolve post-level fallback language ──────────────────────────────────

    post_language_name: str = "English"
    if ajo.language_name and ajo.language_name not in _AMBIGUOUS_CODES:
        post_language_name = ajo.language_name

    # ── Group terms by resolved language name ─────────────────────────────────

    grouped: defaultdict[str, list[str]] = defaultdict(list)
    for entry in komando.data:
        lang_code, term, is_explicit = entry if len(entry) == 3 else (*entry, False)

        if (
            is_explicit
            and isinstance(lang_code, str)
            and lang_code not in _AMBIGUOUS_CODES
        ):
            lingvo = converter(lang_code)
            language_name = (
                lingvo.name
                if (lingvo is not None and lingvo.name is not None)
                else post_language_name
            )
        else:
            language_name = post_language_name

        grouped[language_name].append(term)

    # ── Perform lookups ───────────────────────────────────────────────────────

    reply_parts: list[str] = []
    rate_limit_retry_available = True
    stop_lookups = False
    for language_name, terms in grouped.items():
        for term in terms:
            try:
                result = wiktionary_search(term, language_name)
            except HTTPError as error:
                if not _is_rate_limit_error(error):
                    raise

                if not rate_limit_retry_available:
                    logger.warning(
                        "Wiktionary remained rate limited while looking up '%s' "
                        "(%s); stopping this comment's lookup bundle.",
                        term,
                        language_name,
                    )
                    stop_lookups = True
                    break

                retry_delay = _retry_after_seconds(error)
                if retry_delay > _MAX_429_RETRY_DELAY_SECONDS:
                    logger.warning(
                        "Wiktionary requested a %.1f-second retry delay while "
                        "looking up '%s' (%s), exceeding the %.1f-second comment "
                        "budget; stopping this lookup bundle.",
                        retry_delay,
                        term,
                        language_name,
                        _MAX_429_RETRY_DELAY_SECONDS,
                    )
                    stop_lookups = True
                    break

                rate_limit_retry_available = False
                logger.warning(
                    "Wiktionary rate limited lookup '%s' (%s); retrying once in "
                    "%.1f seconds.",
                    term,
                    language_name,
                    retry_delay,
                )
                time.sleep(retry_delay)
                try:
                    result = wiktionary_search(term, language_name)
                except HTTPError as retry_error:
                    if not _is_rate_limit_error(retry_error):
                        raise
                    logger.warning(
                        "Wiktionary remained rate limited after the single retry "
                        "for '%s' (%s); stopping this comment's lookup bundle.",
                        term,
                        language_name,
                    )
                    stop_lookups = True
                    break

            if result and result.get("definition"):
                formatted = format_wiktionary_markdown(result, term, language_name)
                reply_parts.append(formatted)
            elif result:
                logger.info(
                    f"> Wiktionary result for '{term}' ({language_name}) has no "
                    "definitions. Skipping."
                )
            else:
                logger.info(f"> No Wiktionary result for '{term}' ({language_name}).")
        if stop_lookups:
            break

    if not reply_parts:
        logger.info("> No Wiktionary results returned. Nothing to reply with.")
        return

    body = _format_wt_reply(reply_parts, parent_comment_id=comment.id)

    # ── Send or edit ──────────────────────────────────────────────────────────

    if existing_bot_reply_id:
        reddit_edit(existing_bot_reply_id, body)
        logger.info(
            f"Edited existing Wiktionary reply `{existing_bot_reply_id}` for "
            f"comment `{comment.id}`."
        )
    else:
        reddit_reply(comment, body)
        logger.info(f"> Replied to comment `{comment.id}`.")
