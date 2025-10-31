#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
Handles messaging retrieval and sending functions.
This is Reddit-native, rather than Discord.
"""

import praw
from praw.exceptions import APIException
from praw.models import Message
from wasabi import msg

from config import Paths, load_settings, logger
from connection import REDDIT, USERNAME, is_valid_user
from discord_utils import send_discord_alert
from languages import parse_language_list
from notifications import (
    notifier_language_list_editor,
    notifier_language_list_retriever,
)
from points import points_retriever
from reddit_sender import message_reply, message_send
from responses import RESPONSE
from usage_statistics import (
    action_counter,
    generate_language_frequency_markdown,
    user_statistics_loader,
)


def notify_op_translated_post(author, permalink):
    """
    Send a notification message to the OP that their post has been translated.

    :param author: Reddit username of the OP.
    :param permalink: Permalink of the OP's post.
    :return: None
    """
    if author == USERNAME:
        return  # Don't message the bot itself

    subject = "[Notification] Your request has been translated on r/translator!"
    body = (
        RESPONSE.MSG_TRANSLATED.format(author=author, permalink=permalink)
        + RESPONSE.BOT_DISCLAIMER
    )

    try:
        message_send(redditor_obj=REDDIT.redditor(author), subject=subject, body=body)
    except APIException:
        # User doesn't allow messages or other API exceptions - fail silently
        pass

    logger.info(
        f"[ZW] messaging_translated_message: Messaged the OP "
        f"u/{author} about their translated post."
    )


"""ZIWEN MESSAGES"""


def handle_subscribe(message, message_author):
    """Handle subscription requests."""
    body_text = message.body

    # We want to omit common 3-letter words (like 'and')
    title_settings = load_settings(Paths.SETTINGS["TITLE_MODULE_SETTINGS"])
    commonly_excluded = title_settings["ENGLISH_3_WORDS"]

    logger.info(f"[ZW] Messages: New subscription request from u/{message_author}.")
    language_matches = parse_language_list(body_text)  # Returns Lingvo objects.
    lingvo_names_formatted = []

    # Remove commonly excluded 3-letter words.
    language_matches = [
        x for x in language_matches if x.preferred_code not in commonly_excluded
    ]

    # No valid matches.
    if not language_matches:  # There are no valid codes to subscribe.
        message_reply(
            message,
            reply_text=RESPONSE.MSG_CANNOT_PROCESS.format(RESPONSE.MSG_SUBSCRIBE_LINK)
            + RESPONSE.BOT_DISCLAIMER,
        )
        logger.warning(
            f"[ZW] Messages: Subscription languages listed are not valid: {body_text}"
        )
        return

    # Insert the relevant codes.
    notifier_language_list_editor(language_matches, message_author, "insert")

    # Get the language names of those codes for use in the reply message.
    for lingvo in language_matches:
        lingvo_names_formatted.append(lingvo.name)

    # Add the various components of the reply.
    thanks_phrase = getattr(
        language_matches[0], "thanks", "Thank you"
    )  # Custom thank you
    bullet_list = "\n* ".join(lingvo_names_formatted)
    frequency_table = generate_language_frequency_markdown(language_matches)

    # Pull it all together with the template.
    main_body = RESPONSE.MSG_SUBSCRIBE.format(
        thanks_phrase, bullet_list, frequency_table
    )

    # Reply to the subscribing user.
    message_reply(
        message,
        reply_text=main_body
        + RESPONSE.BOT_DISCLAIMER
        + RESPONSE.MSG_UNSUBSCRIBE_BUTTON,
    )
    logger.info(
        f"[ZW] Messages: Added notification subscriptions for u/{message_author}."
    )
    action_counter(len(language_matches), "Subscriptions")


def handle_unsubscribe(message, message_author):
    """Handle unsubscription requests."""
    logger.info(f"[ZW] Messages: New unsubscription request from u/{message_author}.")

    # User wishes to unsubscribe from everything.
    if message.body.lower().strip().endswith("all"):
        # Pass an empty list.
        notifier_language_list_editor([], message_author, "purge")
        message_reply(
            message,
            reply_text=RESPONSE.MSG_UNSUBSCRIBE_ALL.format(
                "all", RESPONSE.MSG_SUBSCRIBE_LINK
            )
            + RESPONSE.BOT_DISCLAIMER,
        )
        action_counter(1, "Unsubscriptions")
        return

    # Continue processing the message.
    language_matches = parse_language_list(message.body)  # Returns Lingvo objects.
    if language_matches is None:  # There are no valid codes to unsubscribe them from.
        message_reply(
            message,
            reply_text=RESPONSE.MSG_CANNOT_PROCESS.format(RESPONSE.MSG_SUBSCRIBE_LINK)
            + RESPONSE.BOT_DISCLAIMER,
        )
        send_discord_alert(
            f"Unsuccessful Notifications Unsubscribe Attempt: u/{message_author}",
            f"Forwarded message:`{message.body}`",
            "alert",
        )
        logger.info(
            "[ZW] Messages: Unsubscription languages listed are invalid. Replied w/ more info."
        )
        return

    final_match_names = []  # For formatting
    notifier_language_list_editor(language_matches, message_author, "delete")
    for lingvo in language_matches:
        final_match_names.append(lingvo.name)

    bullet_list = "\n* ".join(final_match_names)

    message_reply(
        message,
        reply_text=RESPONSE.MSG_UNSUBSCRIBE_ALL.format(
            bullet_list, RESPONSE.MSG_SUBSCRIBE_LINK
        )
        + RESPONSE.BOT_DISCLAIMER
        + RESPONSE.MSG_UNSUBSCRIBE_BUTTON,
    )
    logger.info(
        f"[ZW] Messages: Removed notification subscriptions for u/{message_author}."
    )
    action_counter(len(language_matches), "Unsubscriptions")


def handle_status(message, message_author):
    """Handle status requests."""
    logger.info(f"[ZW] Messages: New status request from u/{message_author}.")

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
            f"{entry.name}{' (Script)' if 'unknown-' in entry else ''}"
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

    user_commands_statistics_data = user_statistics_loader(message_author)
    if user_commands_statistics_data is not None:
        commands_component = (
            "\n\n### User Commands Statistics\n\n" + user_commands_statistics_data
        )
    else:
        commands_component = ""

    compilation = "### Notifications\n\n" + status_component + commands_component

    action_counter(1, "Status checks")
    message_reply(
        message,
        reply_text=compilation
        + RESPONSE.BOT_DISCLAIMER
        + RESPONSE.MSG_UNSUBSCRIBE_BUTTON,
    )

    return


def handle_add(message, message_author):
    """Handle add requests for notifications from moderators."""
    logger.info(
        f"[ZW] Messages: New username addition message from "
        f"moderator u/{message_author}."
    )

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
        match_codes_print = ", ".join(lang.name for lang in language_matches)

        addition_message = (
            f"Added the language codes **{match_codes_print}** "
            f"for u/{add_username} into the notifications database."
        )
        # Only send Reddit reply if this is a PRAW message object
        if isinstance(message, Message):
            message_reply(message, reply_text=addition_message)


def handle_remove(message, message_author):
    """Handle remove requests for notifications from moderators."""
    logger.info(
        f"[ZW] Messages: New username removal message from moderator u/{message_author}."
    )

    body = message.body.strip()
    if "USERNAME:" in body:
        remove_username = body.split("USERNAME:", 1)[1].strip()
    else:
        logger.warning(
            "[ZW] USERNAME: not found in message body; using full message instead."
        )
        remove_username = body

    # Retrieve subscriptions from the database
    subscribed_codes = notifier_language_list_retriever(remove_username)

    # Purge all subscriptions for the user
    notifier_language_list_editor([], remove_username, "purge")

    subscribed_codes = [x.preferred_code for x in subscribed_codes]
    final_match_codes_print = ", ".join(subscribed_codes)
    removal_message = (
        f"Removed the subscriptions for u/{remove_username} from the notifications database. "
        f"(**{final_match_codes_print}**)"
    )
    # Only send Reddit reply if this is a PRAW message object
    if isinstance(message, Message):
        message_reply(message, reply_text=removal_message)


def handle_points(message, message_author):
    """Handle points requests."""
    logger.info(f"[ZW] Messages: New points status request from u/{message_author}.")

    user_points_output = "### Points on r/translator\n\n" + points_retriever(
        message_author.name
    )
    user_commands_statistics_data = user_statistics_loader(message_author)
    if user_commands_statistics_data is not None:
        commands_component = (
            "\n\n### Commands Statistics\n\n" + user_commands_statistics_data
        )
    else:
        commands_component = ""

    try:
        message_reply(
            message,
            reply_text=user_points_output
            + commands_component
            + RESPONSE.BOT_DISCLAIMER,
        )
    except praw.exceptions.RedditAPIException:
        logger.error("[ZW] Messages: Rate limit reached.")
    else:
        action_counter(1, "Points checks")


if __name__ == "__main__":
    user_check = is_valid_user(USERNAME)
    if user_check:
        msg.good("This user exists!")
    else:
        msg.fail("This user does not exist!")
