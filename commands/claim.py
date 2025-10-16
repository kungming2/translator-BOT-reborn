#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
This handles the !claim command, which allows someone to alert others
that they are currently working on translating a request.
"""
import re
import time
from datetime import datetime, timezone

from connection import REDDIT, logger
from languages import converter
from models.kunulo import Kunulo
from reddit_sender import comment_reply, message_reply
from responses import RESPONSE

from . import update_status


def handle(comment, _instruo, komando, ajo):
    logger.info("Claim handler initiated.")
    status_type = 'inprogress'

    # Set time variables.
    current_time = int(time.time())
    utc_time = datetime.fromtimestamp(current_time, tz=timezone.utc)
    time_formatted = utc_time.isoformat(timespec='seconds').replace('+00:00', 'Z')

    logger.info(f"[ZW] Bot: COMMAND: !claim ({status_type}), from "
                f"u/{comment.author}.")

    # This is in an unlikely scenario where someone edits their original
    # claim comment with the translation, then marks it as !translated
    # or !doublecheck. We just want to ignore it then.
    if '!translated' in comment.body or '!doublecheck' in comment.body:
        logger.info("[ZW] Bot: Claim comment contains a translated or "
                    "doublecheck status change.")
        return

    # Fetch the kunulo and determine the languages we'll process claims for.
    parent_submission = ajo.submission
    kunulo_object = Kunulo.from_submission(parent_submission)
    included_languages = komando.data  # Lingvos attached with the command.
    claimed_languages = []

    # A generic !claim for posts is reduced to a single-item list.
    languages_to_check = included_languages or [ajo.lingvo]

    # Check for previously claimed status.
    for language in languages_to_check:
        existing_claim_comment = REDDIT.comment(kunulo_object.get_tag('comment_claim'))
        if existing_claim_comment:
            logger.info("[ZW] Bot: Pre-existing claim comment found.")

            # Pass current_time to the parser
            claim_info = parse_claim_comment(existing_claim_comment, current_time)

            # Check if the claim languages match.
            if language == claim_info['language']:
                if claim_info['claimer'] == comment.author:
                    # Same user trying to re-claim
                    comment_reply(comment, RESPONSE.COMMENT_SELF_ALREADY_CLAIMED)
                    logger.info("[ZW] Bot: >> But this post is already claimed by them. Replied to them.")
                else:
                    # Different user
                    remaining_minutes = claim_info['claim_time_diff'] // 60
                    reply_text = RESPONSE.COMMENT_CURRENTLY_CLAIMED.format(
                        language_name=claim_info['language'].name,
                        language_code=claim_info['language'].preferred_code,
                        claimer_name=claim_info['claimer'],
                        remaining_time=remaining_minutes,
                    )
                    comment_reply(comment, reply_text)

            claimed_languages.append(language)

    # If there isn't, we can claim it for the user and
    # update the post status.
    update_status(ajo, komando, status_type, claimed_languages)

    # Leave and format a claim in progress comment
    for language in claimed_languages:
        claim_text = RESPONSE.COMMENT_CLAIM.format(
            claimer=comment.author,
            time=time_formatted,
            language_name=language.name,
            language_code=language.preferred_code,
        ) + RESPONSE.BOT_DISCLAIMER
        claim_comment = message_reply(parent_submission, claim_text)

        # Sticky the comment if there is only one language, as there can
        # only be one stickied comment at a time.
        claim_comment.mod.distinguish(sticky=(len(claimed_languages) == 1))
        logger.info(f"[ZW] Bot: > Left a claim comment for u/{comment.author}.")

    return


def parse_claim_comment(comment_text, current_time):
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

    result = {
        'claimer': None,
        'time': None,
        'language': None,
        'claim_time_diff': 0  # in seconds
    }

    # Extract claimer username (after u/)
    claimer_match = re.search(r'\*\*Claimer:\*\* u/(\S+)', comment_text)
    if claimer_match:
        result['claimer'] = claimer_match.group(1)

    # Extract time (before " UTC")
    time_match = re.search(r'at (.+?) UTC', comment_text)
    if time_match is not None:
        time_str = time_match.group(1)
        result['time'] = time_str

        # Calculate time difference if current_time is provided
        if current_time is not None:
            try:
                # Parse ISO 8601 format: "2025-10-09T14:30:00Z"
                # Replace 'Z' with '+00:00' for fromisoformat compatibility
                claim_time = datetime.fromisoformat(time_str.replace('Z', '+00:00'))
                claim_timestamp = int(claim_time.timestamp())
                result['claim_time_diff'] = int(claim_timestamp - current_time)
            except (ValueError, AttributeError):
                pass

    # Extract language code (inside backticks with parentheses)
    lang_code_match = re.search(r'\(`([^`]+)`\)', comment_text)
    if lang_code_match:
        result['language'] = converter(lang_code_match.group(1))

    return result
