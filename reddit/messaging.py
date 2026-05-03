#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
Handles messaging retrieval and sending functions.
This is Reddit-native, rather than Discord.
...

Logger tag: [MESSAGING]
"""

import contextlib
import logging
import re

import praw
from praw.exceptions import APIException
from praw.models import Message, Redditor

from config import SETTINGS, Paths, load_settings
from config import logger as _base_logger
from integrations.discord_utils import send_discord_alert
from lang.languages import parse_language_list
from monitoring.points import points_user_retriever
from monitoring.usage_statistics import (
    action_counter,
    generate_language_frequency_markdown,
    user_statistics_loader,
)
from reddit.connection import REDDIT, USERNAME
from reddit.notifications import (
    notifier_language_list_editor,
    notifier_language_list_retriever,
)
from reddit.reddit_sender import message_send, reddit_reply
from responses import RESPONSE

logger = logging.LoggerAdapter(_base_logger, {"tag": "MESSAGING"})

NOTIFICATION_LIST_DELIMITER_PATTERN = re.compile(r"[,+/\n:;\s]+")


def _notification_request_text(body_text: str) -> str:
    """Return the user-editable notification list text from a message body."""
    if "LANGUAGES:" in body_text:
        return body_text.rpartition("LANGUAGES:")[-1].strip()

    return "\n".join(
        line for line in body_text.splitlines() if not line.lstrip().startswith("#")
    ).strip()


def _parse_internal_notification_types(body_text: str) -> list[str]:
    """Extract configured internal notification types from a request body."""
    request_text = _notification_request_text(body_text).lower()
    internal_types = {str(item).lower() for item in SETTINGS["internal_post_types"]}

    matches = []
    for item in NOTIFICATION_LIST_DELIMITER_PATTERN.split(request_text):
        item = item.strip()
        if item in internal_types:
            matches.append(item)

    return sorted(set(matches))


# ─── OP notification ──────────────────────────────────────────────────────────


def notify_op_translated_post(author: str, permalink: str) -> None:
    """
    Send a notification message to the OP that their post has been translated.

    :param author: Reddit username of the OP.
    :param permalink: Permalink of the OP's post.
    :return: None
    """
    if author == USERNAME:
        return  # Don't message the bot itself

    subject = "Your request has been translated on r/translator!"
    body = (
        RESPONSE.MSG_TRANSLATED.format(author=author, permalink=permalink)
        + RESPONSE.BOT_DISCLAIMER
    )

    # User doesn't allow messages or other API exceptions - fail silently
    with contextlib.suppress(APIException):
        message_send(redditor_obj=REDDIT.redditor(author), subject=subject, body=body)

    action_counter(1, "OP translated notifications")
    logger.info(f"Messaged the OP u/{author} about their translated post.")


# ─── Subscription message handlers ───────────────────────────────────────────


def handle_subscribe(message: Message, message_author: Redditor) -> None:
    """Handle subscription requests."""
    body_text = message.body
    logger.debug(f"[SUB] Body text: {repr(body_text[:100])}...")  # First 100 chars

    # We want to omit common 3-letter words (like 'and')
    title_settings = load_settings(Paths.SETTINGS["TITLE_SETTINGS"])
    commonly_excluded_str = title_settings["ENGLISH_3_WORDS"]
    commonly_excluded = (
        commonly_excluded_str.split()
    )  # Split on whitespace to create a list
    logger.debug(f"[SUB] commonly_excluded list length: {len(commonly_excluded)}")
    logger.debug(f"[SUB] First 10 excluded words: {commonly_excluded[:10]}")

    logger.info(f"New subscription request from u/{message_author}.")
    request_text = _notification_request_text(body_text)
    language_matches = parse_language_list(request_text)  # Returns Lingvo objects.
    internal_matches = _parse_internal_notification_types(body_text)
    logger.debug(f"[SUB] After parse_language_list: {len(language_matches)} matches")
    logger.debug(
        f"[SUB] Lingvo preferred_codes: {[x.preferred_code for x in language_matches]}"
    )
    logger.debug(f"[SUB] Internal notification types: {internal_matches}")

    lingvo_names_formatted = []

    # Remove commonly excluded 3-letter words.
    language_matches = [
        x for x in language_matches if x.preferred_code not in commonly_excluded
    ]
    logger.debug(
        f"[SUB] After filtering commonly_excluded: {len(language_matches)} matches"
    )
    logger.debug(
        f"[SUB] Remaining preferred_codes: {[x.preferred_code for x in language_matches]}"
    )

    # No valid matches.
    if not language_matches and not internal_matches:
        logger.warning("[SUB] No valid matches after filtering - rejecting request")
        reddit_reply(
            message,
            reply_text=RESPONSE.MSG_CANNOT_PROCESS.format(RESPONSE.MSG_SUBSCRIBE_LINK)
            + RESPONSE.BOT_DISCLAIMER,
        )
        logger.warning(f"Subscription languages listed are not valid: {body_text}")
        return

    logger.debug(
        f"[SUB] Proceeding with subscription for {len(language_matches)} languages"
    )

    # Insert the relevant codes.
    notifier_language_list_editor(
        language_matches + internal_matches, message_author, "insert"
    )

    # Get the language names of those codes for use in the reply message.
    for lingvo in language_matches:
        if lingvo.name is not None:
            lingvo_names_formatted.append(lingvo.name)
    logger.debug(f"[SUB] Language names: {lingvo_names_formatted}")

    # Add the various components of the reply.
    thanks_phrase = getattr(
        language_matches[0] if language_matches else None, "thanks", "Thank you"
    )  # Custom thank you
    internal_names_formatted = [
        f"{post_type.capitalize()} posts" for post_type in internal_matches
    ]
    bullet_list = "\n* ".join(lingvo_names_formatted + internal_names_formatted)
    if language_matches:
        frequency_table = generate_language_frequency_markdown(language_matches)
    else:
        frequency_table = "No language frequency statistics are shown for internal post notifications."

    # Pull it all together with the template.
    main_body = RESPONSE.MSG_SUBSCRIBE.format(
        thanks_phrase, bullet_list, frequency_table
    )

    # Reply to the subscribing user.
    reddit_reply(
        message,
        reply_text=main_body
        + RESPONSE.BOT_DISCLAIMER
        + RESPONSE.MSG_NOTIFICATIONS_FOOTER,
    )
    logger.info(f"Added notification subscriptions for u/{message_author}.")
    action_counter(len(language_matches) + len(internal_matches), "Subscriptions")


def handle_unsubscribe(message: Message, message_author: Redditor) -> None:
    """Handle unsubscription requests."""
    logger.info(f"New unsubscription request from u/{message_author}.")
    body_text = message.body

    # User wishes to unsubscribe from everything.
    if body_text.lower().strip().endswith("all"):
        # Pass an empty list.
        notifier_language_list_editor([], message_author, "purge")
        reddit_reply(
            message,
            reply_text=RESPONSE.MSG_UNSUBSCRIBE_ALL.format(
                "all", RESPONSE.MSG_SUBSCRIBE_LINK
            )
            + RESPONSE.BOT_DISCLAIMER,
        )
        action_counter(1, "Unsubscriptions")
        return

    # Continue processing the message.
    request_text = _notification_request_text(body_text)
    language_matches = parse_language_list(request_text)  # Returns Lingvo objects.
    internal_matches = _parse_internal_notification_types(body_text)

    # There are no valid codes or internal notification types to unsubscribe from.
    if not language_matches and not internal_matches:
        reddit_reply(
            message,
            reply_text=RESPONSE.MSG_CANNOT_PROCESS.format(RESPONSE.MSG_SUBSCRIBE_LINK)
            + RESPONSE.BOT_DISCLAIMER,
        )
        send_discord_alert(
            f"Unsuccessful Notifications Unsubscribe Attempt: u/{message_author}",
            f"Forwarded message:`{body_text}`",
            "alert",
        )
        logger.info(
            "Unsubscription languages listed are invalid. Replied w/ more info."
        )
        return

    final_match_names = []  # For formatting
    notifier_language_list_editor(
        language_matches + internal_matches, message_author, "delete"
    )
    for lingvo in language_matches:
        if lingvo.name is not None:
            final_match_names.append(lingvo.name)
    final_match_names.extend(
        f"{post_type.capitalize()} posts" for post_type in internal_matches
    )

    bullet_list = "\n* ".join(final_match_names)

    reddit_reply(
        message,
        reply_text=RESPONSE.MSG_UNSUBSCRIBE_ALL.format(
            bullet_list, RESPONSE.MSG_SUBSCRIBE_LINK
        )
        + RESPONSE.BOT_DISCLAIMER
        + RESPONSE.MSG_NOTIFICATIONS_FOOTER,
    )
    logger.info(f"Removed notification subscriptions for u/{message_author}.")
    action_counter(len(language_matches) + len(internal_matches), "Unsubscriptions")


def handle_status(message: Message, message_author: Redditor) -> None:
    """Handle status requests."""
    logger.info(f"New status request from u/{message_author}.")

    # Get language subscriptions
    final_match_entries = notifier_language_list_retriever(message_author)

    # Get internal subscriptions (meta, community)
    internal_entries = notifier_language_list_retriever(message_author, internal=True)

    if not final_match_entries and not internal_entries:
        status_component = RESPONSE.MSG_NO_SUBSCRIPTIONS.format(
            RESPONSE.MSG_SUBSCRIBE_LINK
        )
    else:
        # Process language subscriptions
        final_match_names_set = {
            f"{entry.name}{' (Script)' if len(entry.preferred_code) == 4 else ''}"
            for entry in final_match_entries
        }
        final_match_names = sorted(list(final_match_names_set), key=lambda x: x.lower())

        # Process internal subscriptions and annotate them
        internal_names = [
            f"{post_type.capitalize()} (Internal)" for post_type in internal_entries
        ]

        # Combine both lists
        all_subscriptions = sorted(
            final_match_names + internal_names, key=lambda x: x.lower()
        )

        status_message = (
            "You're subscribed to notifications on r/translator for:\n\n* {}"
        )
        status_component = status_message.format("\n* ".join(all_subscriptions))

    user_commands_statistics_data = user_statistics_loader(message_author.name)
    if user_commands_statistics_data is not None:
        commands_component = (
            "\n\n### User Commands Statistics\n\n" + user_commands_statistics_data
        )
    else:
        commands_component = ""

    compilation = "### Notifications\n\n" + status_component + commands_component

    action_counter(1, "Status checks")
    reddit_reply(
        message,
        reply_text=compilation
        + RESPONSE.BOT_DISCLAIMER
        + RESPONSE.MSG_NOTIFICATIONS_FOOTER,
    )

    return


# ─── Moderator message handlers ───────────────────────────────────────────────


def handle_add(message: Message, message_author: Redditor) -> None:
    """Handle add requests for notifications from moderators."""
    logger.info(f"New username addition message from moderator u/{message_author}.")

    body = message.body

    # Extract username
    add_username = body.split("USERNAME:", 1)[1]
    add_username = add_username.split("LANGUAGES", 1)[0].strip()

    # Extract language codes
    language_component = body.rpartition("LANGUAGES:")[-1].strip()
    language_matches = parse_language_list(language_component)

    if language_matches:
        notifier_language_list_editor(language_matches, add_username, "insert")
        # Join the name attributes if they exist, otherwise use the items as-is
        match_codes_print = ", ".join(
            lang.name or lang.preferred_code for lang in language_matches
        )

        addition_message = RESPONSE.MSG_NOTIFICATIONS_ADD_SUCCESS.format(
            language_codes=match_codes_print,
            username=add_username,
        )
        # Only send Reddit reply if this is a PRAW message object
        if isinstance(message, Message):
            reddit_reply(message, reply_text=addition_message)

        logger.debug(
            f"handle_add: extracted username={add_username!r}, {len(language_matches)} language(s)"
        )


def handle_remove(message: Message, message_author: Redditor) -> None:
    """Handle remove requests for notifications from moderators."""
    logger.info(f"New username removal message from moderator u/{message_author}.")

    body = message.body.strip()
    if "USERNAME:" in body:
        remove_username = body.split("USERNAME:", 1)[1].strip()
    else:
        logger.warning(
            "USERNAME: not found in message body; using full message instead."
        )
        remove_username = body

    # Retrieve subscriptions from the database
    subscribed_codes = notifier_language_list_retriever(remove_username)

    # Purge all subscriptions for the user
    notifier_language_list_editor([], remove_username, "purge")

    subscribed_codes = [x.preferred_code for x in subscribed_codes]
    final_match_codes_print = ", ".join(subscribed_codes)
    removal_message = RESPONSE.MSG_NOTIFICATIONS_REMOVE_SUCCESS.format(
        username=remove_username,
        language_codes=final_match_codes_print,
    )
    # Only send Reddit reply if this is a PRAW message object
    if isinstance(message, Message):
        reddit_reply(message, reply_text=removal_message)

    logger.debug(f"handle_remove: extracted username={remove_username!r}")


# ─── Points handler ───────────────────────────────────────────────────────────


def handle_points(message: Message, message_author: Redditor) -> None:
    """Handle points requests."""
    logger.info(f"New points status request from u/{message_author}.")

    user_points_output = "### Points on r/translator\n\n" + points_user_retriever(
        message_author.name
    )
    user_commands_statistics_data = user_statistics_loader(message_author.name)
    if user_commands_statistics_data is not None:
        commands_component = (
            "\n\n### Commands Statistics\n\n" + user_commands_statistics_data
        )
    else:
        commands_component = ""
    reply_body = user_points_output + commands_component
    has_commands = user_commands_statistics_data is not None

    try:
        reddit_reply(
            message,
            reply_text=reply_body + RESPONSE.BOT_DISCLAIMER,
        )
    except praw.exceptions.RedditAPIException:
        logger.error("Rate limit reached.")
    else:
        logger.info(
            f"Sent points summary to u/{message_author.name} "
            f"(commands stats included: {has_commands})"
        )
        action_counter(1, "Points checks")
