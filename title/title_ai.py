#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
AI-assisted title parsing and correction for r/translator posts.

This module handles the fallback path triggered when the rule-based title
parser in title_handling.py cannot identify any non-English language from a
post title. It calls an external AI service (OpenAI) to assess the title,
optionally using an attached image for additional context, and writes the
result back into a Titolo object.

It also provides format_title_correction_comment, which constructs a Reddit
comment suggesting a reformatted title when a post fails the filter.

This module is intentionally isolated from the rule-based parsing logic.
Its only dependency on the title package is the Titolo type annotation used
in _update_titolo_from_ai_result; it does not import process_title or any
parser internals.

Key components:
    title_ai_parser              -- Call AI service and return parsed language data.
    format_title_correction_comment -- Build a correction comment for bad titles.
    update_titolo_from_ai_result -- Write AI result back into a Titolo object.

Logger tag: [TITLE:AI]
"""

import json
import logging
from typing import TYPE_CHECKING, Any, Optional, Union

from praw.models import Submission

from config import logger as _base_logger
from integrations.ai import ai_query, openai_access
from integrations.discord_utils import send_discord_alert
from lang.languages import converter
from responses import RESPONSE

if TYPE_CHECKING:
    from title.title_handling import Titolo

logger = logging.LoggerAdapter(_base_logger, {"tag": "TITLE:AI"})


def title_ai_parser(
    title: str, post: Optional[Submission] = None
) -> Union[dict[str, Any], tuple[str, str]]:
    """
    Passes a malformed title to an AI to assess, and returns the non-English
    language (code and name) if confidence is sufficient.

    Optionally includes image data from the post (direct image or first gallery
    image) to improve AI assessment accuracy.

    Args:
        title: Title of a Reddit post to be parsed.
        post: A PRAW submission object containing optional image data, or None.

    Returns:
        On success: A dictionary containing:
            - 'source_language': dict with 'code' and 'name' keys
            - 'target_language': dict with 'code' and 'name' keys
            - 'confidence': float between 0.0 and 1.0
        On failure: A tuple of ("error", error_message_string)

    Note:
        Returns an error tuple if AI confidence is below 0.7 threshold.
    """
    logger.info(f"AI Parser: AI service is now assessing title: {title}")
    image_url: Optional[str] = None

    if post:
        # Check if post has an image (gallery or direct image)
        if hasattr(post, "post_hint") and post.post_hint == "image":
            image_url = post.url
        elif hasattr(post, "is_gallery") and post.is_gallery:
            # Get first image from gallery
            media_metadata: dict[str, Any] = getattr(post, "media_metadata", {})
            if media_metadata:
                first_item = next(iter(media_metadata.values()))
                if "s" in first_item and "u" in first_item["s"]:
                    image_url = first_item["s"]["u"].replace("&amp;", "&")

    query_input: str = RESPONSE.TITLE_PARSING_QUERY + title

    logger.info("Passing information to AI service...")
    query_kwargs: dict[str, Any] = {
        "service": "openai",
        "behavior": "You are assessing a technical identification",
        "query": query_input,
        "client_object": openai_access(),
    }

    if image_url:
        query_kwargs["image_url"] = image_url

    query_data: str = ai_query(**query_kwargs)

    if query_data is None:
        logger.error("AI service returned no data for title parsing.")
        return "error", "Service returned no data"

    try:
        query_dict: dict[str, Any] = json.loads(query_data)
    except json.decoder.JSONDecodeError:
        logger.error(f"Failed to parse query data: `{query_data}`")
        return "error", "Service returned invalid JSON"

    confidence: float = query_dict.get("confidence", 0.0)
    if confidence < 0.7:
        logger.warning("AI confidence value too low for title.")
        return "error", "Confidence value too low"

    logger.info(f"AI Parser: AI service returned data: {query_dict}")
    return query_dict


def format_title_correction_comment(title_text: str, author: str) -> str:
    """
    Constructs a comment suggesting a new, properly formatted post title,
    along with a resubmit link that includes the revised title. This helps
    streamline the process of resubmitting a post to r/translator.

    :param title_text: The filtered title that lacked required keywords.
    :param author: The OP of the post.
    :return: A formatted comment for ziwen_posts to reply with.
    """
    query_input = RESPONSE.TITLE_REFORMATTING_QUERY + title_text

    query_kwargs = {
        "service": "openai",
        "behavior": "You are checking data entry",
        "query": query_input,
        "client_object": openai_access(),
    }

    query_data = ai_query(**query_kwargs)

    if not query_data:
        logger.error(
            f"AI service returned no data for title reformatting: {title_text!r}"
        )
        return ""

    suggested_title = query_data

    url_safe_title = (
        suggested_title.replace(" ", "%20").replace(")", r"\)").replace(">", "%3E")
    )

    reformat_comment = RESPONSE.COMMENT_BAD_TITLE.format(
        author=author, new_url=url_safe_title, new_title=suggested_title
    )

    return reformat_comment


def update_titolo_from_ai_result(
    result: "Titolo",
    ai_result: dict[str, Any],
    post: Optional[Submission],
    discord_notify: bool,
    determine_flair_fn,
    determine_direction_fn,
    get_notification_languages_fn,
) -> None:
    """
    Apply an AI parser result to a Titolo object, then send a Discord alert.

    Handles both the success and failure paths: on success, writes source,
    target, direction, notify_languages, flair, and ai_assessed back to the
    Titolo; on failure, assigns generic flair. Sends a Discord alert in either
    case if discord_notify is True and a post object is available.

    This function is called exclusively from process_title in title_handling.py.
    The flair, direction, and notification helpers are passed in as arguments
    to avoid importing title_handling internals here.

    Args:
        result: The Titolo object to update in place.
        ai_result: Return value of title_ai_parser — either a dict on success
                   or a tuple ("error", message) on failure.
        post: The PRAW submission object, or None in test mode.
        discord_notify: Whether to send a Discord alert after processing.
        determine_flair_fn: _determine_flair from title_handling.
        determine_direction_fn: _determine_title_direction from title_handling.
        get_notification_languages_fn: _get_notification_languages from title_handling.
    """
    if isinstance(ai_result, dict):
        try:
            src: Optional[dict[str, Any]] = ai_result.get("source_language")
            tgt: Optional[dict[str, Any]] = ai_result.get("target_language")

            if src and "code" in src:
                result.source = [converter(src["code"])]
            if tgt and "code" in tgt:
                result.target = [converter(tgt["code"])]

            result.direction = determine_direction_fn(result.source, result.target)
            result.notify_languages = get_notification_languages_fn(result) or []
            result.ai_assessed = True

            logger.info(
                f"AI updated source: {result.source}, target: {result.target}, "
                f"direction: {result.direction}"
            )

            determine_flair_fn(result)
            logger.info(
                f"AI determined flair: {result.final_code=}; {result.final_text=}"
            )

        except Exception as e:
            logger.error(f"Failed to update Titolo from AI result: {e}")
            return

        if post:
            updating_subject = "AI Parsed Title and Assigned Language to Post"
            updating_reason = (
                f"Passed to AI service; AI assessed it as **{result.final_text}** "
                f"(`{result.final_code}`). "
                f"If incorrect, please assign [this post](https://www.reddit.com{post.permalink}) "
                f"a different and accurate language category."
                f"\n\n**Post Title**: [{post.title}](https://www.reddit.com{post.permalink})"
            )
            logger.info(
                f"AI assessment of title performed for '{post.title}' | `{post.id}`."
            )
        else:
            updating_subject = "AI Parsed Title and Assigned Language (Test Mode)"
            updating_reason = (
                f"Passed to AI service; AI assessed it as **{result.final_text}** "
                f"(`{result.final_code}`). Test mode - no post object available."
            )
            logger.info("AI assessment of title performed for test title.")

    else:
        # AI parsing failed — assign generic flair
        result.add_final_code("generic")
        result.add_final_text("Generic")

        if post:
            updating_subject = "AI Unable to Parse Title; No Language Assigned"
            updating_reason = (
                "Completely unable to parse this post's language; assigned a generic category. "
                f"Please check and assign [this post](https://www.reddit.com{post.permalink}) "
                f"a language category."
                f"\n\n**Post Title**: [{post.title}](https://www.reddit.com{post.permalink})"
            )
            logger.info(
                f"AI assessment of title failed for '{post.title}' | `{post.id}`. "
                "Assigned completely generic category."
            )
        else:
            updating_subject = "AI Unable to Parse Title (Test Mode)"
            updating_reason = (
                "Completely unable to parse this post's language; assigned a generic category. "
                "Test mode - no post object available."
            )
            logger.info(
                "AI assessment of title failed for test title. "
                "Assigned completely generic category."
            )

    if discord_notify and post:
        send_discord_alert(updating_subject, updating_reason, "report")
