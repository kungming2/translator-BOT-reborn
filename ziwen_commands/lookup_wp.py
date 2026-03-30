#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
Simple command wrapper for Wikipedia lookup.
...

Logger tag: [ZW:WP]
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
from ziwen_lookup.wp_utils import wikipedia_lookup

logger = logging.LoggerAdapter(_base_logger, {"tag": "ZW:WP"})


# ─── Reply formatting ─────────────────────────────────────────────────────────


def _format_wp_reply(
    reply_parts: list[str], parent_comment_id: str | None = None
) -> str:
    """
    Assemble the Wikipedia reply body.

    Args:
        reply_parts: List of per-language lookup result strings.
        parent_comment_id: The Reddit comment ID of the user comment that
            triggered this reply. When provided, an invisible anchor
            ``[](#wp_parent_XXXX)`` is embedded so Kunulo can later
            identify which bot reply belongs to which user comment,
            enabling edit-on-reprocess rather than a duplicate reply.

    Returns:
        Formatted reply body string.
    """
    anchor = RESPONSE.ANCHOR_WIKIPEDIA
    if parent_comment_id:
        anchor += f"[](#wp_parent_{parent_comment_id})"
    return "\n".join(reply_parts) + anchor


# ─── Command handler ──────────────────────────────────────────────────────────


def handle(comment: Comment, _instruo: Instruo, komando: Komando, _ajo: Ajo) -> None:
    """
    Command handler called by ziwen_commands().

    On reprocessing triggered by the edit tracker (e.g. the user changed
    a ``{{term}}:lang`` suffix), the handler detects an existing bot reply
    for this comment and edits it in place rather than posting a new reply.

    Examples of data:
        Komando(name='lookup_wp', data=[('Forbidden City', None)])
        Komando(name='lookup_wp', data=[('紫禁城', 'zh'), ('Eiffel Tower', None)])
    """
    logger.info("Wikipedia Lookup handler initiated.")
    logger.info(f"Wikipedia Lookup, from u/{comment.author}.")

    if not komando.data:
        logger.info("> No lookup terms provided. Ignoring.")
        return

    # ── Check for an existing bot reply to this comment ───────────────────────

    kunulo = Kunulo.from_submission(comment.submission)
    existing_bot_reply_id = kunulo.find_wp_reply_for_comment(comment.id)

    if existing_bot_reply_id:
        logger.info(
            f"Found existing Wikipedia reply `{existing_bot_reply_id}` for comment "
            f"`{comment.id}` — will edit in place rather than post a new reply."
        )

    # ── Group terms by resolved language code ─────────────────────────────────

    # Terms with no language suffix default to English.
    grouped: defaultdict[str, list[str]] = defaultdict(list)
    for entry in komando.data:
        term, raw_lang = entry if isinstance(entry, tuple) else (entry, None)
        if raw_lang:
            lingvo = converter(raw_lang)
            lang_code = lingvo.preferred_code if lingvo is not None else "en"
        else:
            lang_code = "en"
        grouped[lang_code].append(term)

    # ── Perform lookups ───────────────────────────────────────────────────────

    reply_parts: list[str] = []
    for lang_code, terms in grouped.items():
        result = wikipedia_lookup(terms, language_code=lang_code)
        if result:
            reply_parts.append(result)

    if not reply_parts:
        logger.info("> No Wikipedia results returned. Nothing to reply with.")
        return

    body = _format_wp_reply(reply_parts, parent_comment_id=comment.id)

    # ── Send or edit ──────────────────────────────────────────────────────────

    if existing_bot_reply_id:
        reddit_edit(existing_bot_reply_id, body)
        logger.info(
            f"Edited existing Wikipedia reply `{existing_bot_reply_id}` for "
            f"comment `{comment.id}`."
        )
    else:
        reddit_reply(comment, body)
        logger.info(f"> Replied to comment `{comment.id}`.")
