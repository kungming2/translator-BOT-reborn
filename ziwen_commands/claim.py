#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
This handles the !claim command, which allows someone to alert others
that they are currently working on translating a request.
...

Logger tag: [ZW:CLAIM]
"""

import logging
import re
import time
from datetime import datetime
from typing import Any

from praw.models import Comment

from config import logger as _base_logger
from lang.languages import converter
from models.ajo import Ajo
from models.instruo import Instruo
from models.komando import Komando
from models.kunulo import Kunulo
from reddit.connection import REDDIT
from reddit.reddit_sender import reddit_reply
from responses import RESPONSE
from time_handling import get_current_utc_time

from . import update_status

logger = logging.LoggerAdapter(_base_logger, {"tag": "ZW:CLAIM"})


# ─── Internal helpers ─────────────────────────────────────────────────────────


def parse_claim_comment(comment_text: str, current_time: int) -> dict[str, Any]:
    """
    Parse a claim comment to extract claimer username, time,
    and language code.

    Args:
        comment_text: The comment body text containing claim information
        current_time: Current Unix timestamp

    Returns:
        dict: Dictionary with keys 'claimer', 'time', 'language_code', 'claim_time_diff'
              Returns None for any value that couldn't be extracted
              claim_time_diff is in seconds (positive if claim time is
              in the future, negative if in the past)
    """
    result: dict[str, Any] = {
        "claimer": None,
        "time": None,
        "language": None,
        "claim_time_diff": 0,  # in seconds
    }

    # Extract claimer username (after u/)
    claimer_match = re.search(r"\*\*Claimer:\*\* u/(\S+)", comment_text)
    if claimer_match:
        result["claimer"] = claimer_match.group(1)

    # Extract time (before " UTC")
    time_match = re.search(r"at (.+?) UTC", comment_text)
    if time_match is not None:
        time_str = time_match.group(1)
        result["time"] = time_str

        if current_time is not None:
            try:
                # Parse ISO 8601 format: "2025-10-09T14:30:00Z"
                # Replace 'Z' with '+00:00' for fromisoformat compatibility
                claim_time = datetime.fromisoformat(time_str.replace("Z", "+00:00"))
                claim_timestamp = int(claim_time.timestamp())
                result["claim_time_diff"] = int(claim_timestamp - current_time)
            except (ValueError, AttributeError):
                pass

    # Extract language code (inside backticks with parentheses)
    lang_code_match = re.search(r"\(`([^`]+)`\)", comment_text)
    if lang_code_match:
        result["language"] = converter(lang_code_match.group(1))

    return result


# ─── Command handler ──────────────────────────────────────────────────────────


def handle(comment: Comment, _instruo: Instruo, komando: Komando, ajo: Ajo) -> None:
    """Command handler called by ziwen_commands()."""
    logger.info("Claim handler initiated.")
    status_type = "inprogress"

    current_time = int(time.time())
    time_formatted = get_current_utc_time()

    logger.info(f"!claim ({status_type}), from u/{comment.author}.")

    # If someone edits their original claim comment with the translation
    # and then marks it as !translated or !doublecheck, just ignore it.
    if "!translated" in comment.body or "!doublecheck" in comment.body:
        logger.info("Claim comment contains a translated or doublecheck status change.")
        return

    parent_submission = ajo.submission
    kunulo_object = Kunulo.from_submission(parent_submission)
    included_languages = komando.data  # Lingvos attached with the command.
    claimed_languages: list = []

    # A generic !claim is reduced to a single-item list.
    languages_to_check = included_languages or [ajo.lingvo]

    # Check for previously claimed status per language.
    for language in languages_to_check:
        claim_comment_id = kunulo_object.get_tag("comment_claim")

        if claim_comment_id:
            logger.info(f"Pre-existing claim comment `{claim_comment_id}` found.")
            existing_claim_comment = REDDIT.comment(claim_comment_id)
            claim_info = parse_claim_comment(existing_claim_comment.body, current_time)

            if language == claim_info["language"]:
                if claim_info["claimer"] == comment.author.name:
                    reddit_reply(comment, RESPONSE.COMMENT_SELF_ALREADY_CLAIMED)
                    logger.info(
                        ">> But this post is already claimed by them. Replied to them."
                    )
                else:
                    remaining_minutes = claim_info["claim_time_diff"] // 60
                    reply_text = RESPONSE.COMMENT_CURRENTLY_CLAIMED.format(
                        language_name=claim_info["language"].name,
                        language_code=claim_info["language"].preferred_code,
                        claimer_name=claim_info["claimer"],
                        remaining_time=remaining_minutes,
                    )
                    reddit_reply(comment, reply_text)

                continue  # language is already claimed

        claimed_languages.append(language)

    update_status(ajo, komando, status_type, claimed_languages)

    # Leave a claim-in-progress comment for each newly claimed language.
    for language in claimed_languages:
        claim_text = (
            RESPONSE.COMMENT_CLAIM.format(
                claimer=comment.author,
                time=time_formatted,
                language_name=language.name,
                language_code=language.preferred_code,
            )
            + RESPONSE.BOT_DISCLAIMER
        )
        claim_comment = reddit_reply(parent_submission, claim_text)

        # Sticky only when there is a single language (one sticky at a time).
        if isinstance(claim_comment, Comment):
            claim_comment.mod.distinguish(sticky=(len(claimed_languages) == 1))
            logger.info(f"> Left a claim comment for u/{comment.author}.")
        else:
            logger.error(f"> Unresolved claim comment by u/{comment.author}.")

    return
