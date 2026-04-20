#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
Simple command wrapper for Wiktionary lookup.
...

Logger tag: [ZW:WT]
"""

import logging
from collections import defaultdict

from praw.models import Comment

from config import logger as _base_logger
from lang.languages import converter
from models.ajo import Ajo
from models.instruo import Instruo
from models.komando import Komando
from models.kunulo import Kunulo
from reddit.reddit_sender import reddit_edit, reddit_reply
from responses import RESPONSE
from ziwen_lookup.wiktionary import format_wiktionary_markdown, wiktionary_search

logger = logging.LoggerAdapter(_base_logger, {"tag": "ZW:WT"})

_AMBIGUOUS_CODES: frozenset[str] = frozenset({"multiple", "generic", "unknown"})


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
    return "\n\n".join(reply_parts) + anchor


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
    for language_name, terms in grouped.items():
        for term in terms:
            result = wiktionary_search(term, language_name)
            if result:
                formatted = format_wiktionary_markdown(result, term, language_name)
                reply_parts.append(formatted)
            else:
                logger.info(f"> No Wiktionary result for '{term}' ({language_name}).")

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
