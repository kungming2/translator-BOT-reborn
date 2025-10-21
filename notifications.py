#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
Handles translation notification-related functions for
the messaging system.
"""

import random
import sqlite3
import time
from usage_statistics import action_counter
from typing import List

import orjson
from praw import exceptions

from ai import fetch_image_description
from config import SETTINGS, logger
from connection import REDDIT, is_valid_user
from database import db, record_activity_csv
from languages import Lingvo, converter, country_converter, language_module_settings
from models.ajo import ajo_loader
from reddit_sender import message_send
from responses import RESPONSE
from startup import STATE
from time_handling import time_convert_to_string
from utility import check_url_extension

"""NOTIFICATIONS SUBSCRIPTIONS WITH DATABASE"""


def _process_language_code(code: str) -> str:
    """Process and validate language codes for database operations.
    The database stores values in a slightly different way."""
    if len(code) == 4:  # Script code case
        return f"unknown-{code}"  # Script codes have a prefix.
    if code == "en":  # Skip English
        return ""
    if not code:  # Skip empty
        return ""
    return code


def _notifier_duplicate_checker(
    code: str, username: str, internal: bool = False
) -> bool:
    """
    Check if a user is already signed up for a specific notification.

    Args:
        code: Either a language_code (notify_users) or a post_type (notify_internal)
        username: Reddit username
        internal: If True, checks the internal post_type table instead of language_code

    Returns:
        True if a matching entry exists, False otherwise.
    """
    # Determine target table/column
    table = "notify_internal" if internal else "notify_users"
    column = "post_type" if internal else "language_code"

    # Maintain legacy 4-char handling only for language codes
    if not internal and len(code) == 4:
        code = f"unknown-{code}"  # For script entries

    query = f"SELECT 1 FROM {table} WHERE {column} = ? AND username = ? LIMIT 1"
    params = (code.lower(), username)
    logger.debug(f"Executing: {query} with params: {params}")

    try:
        with db.conn_main:
            result = db.cursor_main.execute(query, params).fetchone()
            return result is not None
    except sqlite3.Error as e:
        logger.error(
            f"Database error in notifier_duplicate_checker (table={table}): {e}"
        )
        raise


def _prune_deleted_user_notifications(
    username: str, internal_posts: bool = False
) -> list[str] | None:
    """
    Remove notification subscriptions for a user who no longer exists on Reddit.

    If the user is valid, the function returns None and takes no action.
    If the user does not exist, their subscriptions are deleted from the database,
    and the list of previously subscribed languages is returned.

    :param username: The Reddit username to check and potentially prune.
                     Note this is a string, since a potentially deleted
                     individual may no longer have a Redditor object.
    :param internal_posts: If True, use the notify_internal table instead of notify_users.
    :return: None if the user exists; list of unsubscribed language codes if pruned.
    """

    if is_valid_user(username):
        logger.info(
            f"[ZW] prune_deleted_user_notifications: u/{username} exists. Skipping."
        )
        return None

    logger.info(
        f"[ZW] prune_deleted_user_notifications: Pruning u/{username} from the database..."
    )

    cursor = db.cursor_main
    conn = db.conn_main

    table_name = "notify_internal" if internal_posts else "notify_users"

    cursor.execute(f"SELECT * FROM {table_name} WHERE username = ?", (username,))
    subscriptions = cursor.fetchall()
    final_codes = [row[0] for row in subscriptions]

    if final_codes:
        formatted_list = ", ".join(f"`{code}`" for code in final_codes)
        cursor.execute(f"DELETE FROM {table_name} WHERE username = ?", (username,))
        conn.commit()
        logger.info(
            f"[ZW] prune_deleted_user_notifications: Deleted subscription info for u/{username}."
        )
        logger.info(
            f"[ZW] prune_deleted_user_notifications: User was subscribed to: {formatted_list}."
        )
    else:
        logger.info(
            f"[ZW] prune_deleted_user_notifications: No subscription info found for u/{username}."
        )

    return final_codes


def notifier_language_list_editor(
    language_list: list, user_object, mode: str = "insert"
) -> None:
    """
    Modify the notification database by inserting or deleting entries for a username.

    Args:
        language_list: List of Lingvo objects OR special strings ("meta", "community")
        user_object: Reddit username *object* to modify entries for
        mode: 'insert' adds, 'delete' removes, 'purge' removes all (languages only)
    """
    username = user_object.name

    # Purge all language notifications for this user (languages and internal)
    if mode == "purge":
        with db.conn_main:
            db.cursor_main.execute(
                "DELETE FROM notify_users WHERE username = ?", (username,)
            )
            db.cursor_main.execute(
                "DELETE FROM notify_internal WHERE username = ?", (username,)
            )
        return

    if not language_list:  # Nothing to process
        return

    for item in language_list:
        # Determine if this is an internal type (meta/community) or a
        # Lingvo language object
        if isinstance(item, str) and item.lower() in SETTINGS["internal_post_types"]:
            processed_code = item.lower()
            table, column, internal_flag = "notify_internal", "post_type", True
        else:
            processed_code = _process_language_code(item.preferred_code)
            table, column, internal_flag = "notify_users", "language_code", False

        if not processed_code:
            continue

        exists = _notifier_duplicate_checker(
            processed_code, username, internal=internal_flag
        )
        sql_params = (processed_code, username)

        if mode == "insert" and not exists:
            with db.conn_main:
                db.cursor_main.execute(
                    f"INSERT INTO {table} ({column}, username) VALUES (?, ?)",
                    sql_params,
                )
        elif mode == "delete" and exists:
            with db.conn_main:
                db.cursor_main.execute(
                    f"DELETE FROM {table} WHERE {column} = ? AND username = ?",
                    sql_params,
                )

    return


def notifier_language_list_retriever(user_object, internal: bool = False) -> List:
    """
    Retrieve the list of Lingvos a user is subscribed to for notifications.

    :param user_object: A Redditor object from PRAW
    :param internal: If True, returns internal post types; if False, returns language subscriptions
    :return: A list of Lingvo objects (if internal=False) or strings (if internal=True)
    """
    username = str(user_object)
    cursor = db.cursor_main

    if internal:
        # Get internal subscriptions (meta, community)
        cursor.execute(
            "SELECT post_type FROM notify_internal WHERE username = ?", (username,)
        )
        return [row[0] for row in cursor.fetchall()]
    else:
        # Get language subscriptions
        cursor.execute(
            "SELECT language_code FROM notify_users WHERE username = ?", (username,)
        )
        return [
            converter(row[0]) for row in cursor.fetchall()
        ]  # Convert results to Lingvos


def fetch_usernames_for_lingvo(lingvo, max_num=None) -> List[str]:
    """
    Fetch a list of usernames subscribed to the Lingvo object's
    language code, optionally including country variant (e.g., 'pt-BR').

    Args:
        lingvo: A Lingvo object with 'preferred_code' and optional 'country'.
        max_num: Maximum number of usernames to fetch. Randomly sample if needed.

    Returns:
        List of usernames subscribed to the language code or regional variant.
    """
    try:
        code = lingvo.preferred_code  # base code like 'pt' or 'por'
        logger.debug(f"Preferred code at start: {code}")
        if lingvo.country:
            # Normalize country code (with the country converter)
            country_code, _ = country_converter(lingvo.country)
            logger.debug(f"Country code: {country_code}")
            if country_code:
                code = f"{lingvo.preferred_code.lower()}-{country_code.upper()}"
                logger.debug(f"Regional code: {code}")
        elif len(code) == 4:  # Script codes
            code = f"unknown-{code}"

        logger.debug(f"Looking up users for code: {code}")
    except AttributeError:
        return []

    usernames = set()
    cursor = db.conn_main.cursor()
    logger.debug(f"Now executing search for {code}...")
    cursor.execute("SELECT username FROM notify_users WHERE language_code = ?", (code,))
    usernames.update(row["username"] for row in cursor.fetchall())

    usernames = list(usernames)

    if max_num is not None and max_num < len(usernames):
        usernames = random.sample(usernames, k=max_num)

    return usernames


def _notifier_specific_language_filter(lingvo_object) -> list[str]:
    """
    Given a regional Lingvo object (e.g., 'ar-LB' or 'apc'),
    returns a list of usernames who are subscribed to the *specific*
    regional variant but NOT to the broader language. That is, someone
    who is signed up for `pt-BR` will match, but only if they're *not*
    also signed up for regular `pt`.

    This ensures notifications are only sent to users who prefer a
    specific variant.

    :param lingvo_object: A Lingvo object representing a regional variant.
    :return: List of usernames who prefer the specific variant only.
    """
    language_country_associations = language_module_settings[
        "ISO_LANGUAGE_COUNTRY_ASSOCIATED"
    ]
    lingvo_code = lingvo_object.preferred_code
    specific_usernames = set()
    broader_usernames = set()

    if lingvo_object.country:
        country_code, _ = country_converter(lingvo_object.country)
        if not country_code:
            logger.warning(f"Could not normalize country '{lingvo_object.country}'")
            return []
        language_region_code = f"{lingvo_code}-{country_code}"
        iso_associated_code = language_country_associations.get(language_region_code)
        logger.info(
            f"Regional Lingvo: `{language_region_code}` "
            f"converted to ISO 639-3 code: `{iso_associated_code}`"
        )
    else:
        language_region_code = None
        iso_associated_code = None

    # Always get users subscribed to the regional code itself
    specific_usernames.update(fetch_usernames_for_lingvo(lingvo_object))

    # Only get users subscribed to ISO code if it exists and differs
    if (
        iso_associated_code
        and iso_associated_code.lower() != (language_region_code or "").lower()
    ):
        specific_usernames.update(
            fetch_usernames_for_lingvo(Lingvo(language_code_3=iso_associated_code))
        )

    # Broader language code (e.g. 'pt' from 'pt-BR')
    broader_code = language_region_code.split("-")[0] if language_region_code else None
    if broader_code:
        broader_usernames.update(
            fetch_usernames_for_lingvo(Lingvo(language_code_1=broader_code))
        )

    return list(specific_usernames - broader_usernames)


"""NOTIFICATION LIMITS ENFORCING"""


def _update_user_notification_count(
    username: str, lingvo_object, num_notifications: int = 1
) -> None:
    """
    Updates the count of notifications a user has received for a specific language.
    If no record exists, a new one is created. Data is stored as a json-encoded dictionary.

    :param username: Reddit username of the recipient.
    :param lingvo_object: Lingvo object associated with the notification (e.g. 'zh', 'ar').
    :param num_notifications: Number of notifications to record (default is 1).
    """
    cursor = db.cursor_main
    language_code = lingvo_object.preferred_code

    # Attempt to fetch existing notification records
    cursor.execute(
        "SELECT received FROM notify_cumulative WHERE username = ?", (username,)
    )
    row = cursor.fetchone()

    if row:
        try:
            monthly_data = orjson.loads(row["received"])
        except (orjson.JSONDecodeError, TypeError):
            monthly_data = {}
    else:
        monthly_data = {}

    # Update the dictionary
    monthly_data[language_code] = monthly_data.get(language_code, 0) + num_notifications

    # Serialize data using orjson
    orjson_data = orjson.dumps(monthly_data)

    # Update or insert into the database
    if row:
        cursor.execute(
            "UPDATE notify_cumulative SET received = ? WHERE username = ?",
            (orjson_data, username),
        )
    else:
        cursor.execute(
            "INSERT INTO notify_cumulative (username, received) VALUES (?, ?)",
            (username, orjson_data),
        )

    db.conn_main.commit()


def _notification_rate_limiter(
    subscribed_users: list, lingvo_object, monthly_limit: int
) -> list:
    """
    Equalizes notification volume for high-traffic languages to avoid
    spamming users.
    Tries to limit each user to receiving no more than `monthly_limit`
    notifications per month.

    Formula:
        users_to_notify_per_post = (total_notifications_allowed) / (average_monthly_posts)
                                 = (number_of_users * monthly_limit) / average_posts_per_month

    :param subscribed_users: List of users subscribed to this language
    :param lingvo_object: The Lingvo object of the language (e.g. 'zh', 'es', 'ko')
    :param monthly_limit: Max number of times each user should be notified per month
    :return: A list of selected users to notify
    """
    if not subscribed_users:  # There are no subscribed users.
        return []

    total_users = len(subscribed_users)
    max_language_users = SETTINGS["notifications_user_limit"]
    language_name = lingvo_object.name

    # Get the average number of posts per month for the language
    if language_name == "Unknown":
        average_posts_per_month = 260
    else:
        average_posts_per_month = getattr(lingvo_object, "rate_monthly", 1)
        if not average_posts_per_month:  # This doesn't have many requests.
            average_posts_per_month = 0

    # Calculate how many users to notify per post
    if average_posts_per_month == 0:
        num_users_to_notify = SETTINGS["notifications_user_limit"]
    else:
        total_allowed_notifications = total_users * monthly_limit
        num_users_to_notify = round(
            total_allowed_notifications / average_posts_per_month
        )
        num_users_to_notify = max(
            1, num_users_to_notify
        )  # Ensure at least one user is notified

    # Randomly sample if too many users would be notified.
    if num_users_to_notify < total_users:
        subscribed_users = random.sample(subscribed_users, num_users_to_notify)

    # Final cap to avoid exceeding the maximum allowed per post
    if len(subscribed_users) > max_language_users:
        subscribed_users = random.sample(subscribed_users, max_language_users)
        logger.info(
            f"[ZW] Notifier Equalizer: {max_language_users}+ users for {language_name} notifications. Randomized."
        )

    # Alphabetize final list
    return sorted(subscribed_users, key=lambda u: str(u).lower())


def _should_send_language_notification(lingvo, messaging_ajo_history):
    """
    Checks if notifications for the language represented by the Lingvo object
    have already been sent in the post's language history to avoid duplicate messaging.

    :param lingvo: Lingvo object representing the current language.
    :param messaging_ajo_history: List of language names representing previous classifications of the post.
    :return: True if notification should be sent for this language; False otherwise.
    """

    # Convert Lingvo to language name using the converter helper
    language_name = lingvo.name

    # Allow sending notification only if language is either not in history
    # or is the last classification (to prevent duplicate notifications).
    if (
        language_name in messaging_ajo_history
        and language_name != messaging_ajo_history[-1]
    ):
        return False
    return True


def is_user_over_submission_limit(username: str) -> bool:
    """
    Check if a user has submitted more than the allowed number of posts
    within the last 24 hours to prevent spam/abuse notifications.

    :param username: The username of a redditor (typically an OP).

    :return: True if user exceeded the limit, False otherwise.
    """
    limit = SETTINGS["user_submission_limit"]
    logger.debug(f"User submission limit: {limit}")

    # Count how many times the username appears in recent submitters
    frequency = STATE.recent_submitters.count(username)

    return frequency > limit


"""CLEAN FORMATTING ISSUES"""


def _notifier_title_cleaner(title: str) -> str:
    """
    Escapes common Markdown-sensitive characters in Reddit post titles
    for safe display in notifications.

    This includes characters like `[]()_*~` which can interfere with
    Markdown formatting.

    :param title: The original Reddit post title.
    :return: A cleaned-up version of the title with problematic characters escaped.
    """

    # Common Markdown-sensitive characters that might need escaping
    markdown_sensitive = ["[", "]", "(", ")", "*", "_", "~", "`"]

    for char in markdown_sensitive:
        title = title.replace(char, f"\\{char}")

    return title


"""MAIN FUNCTION"""


def notifier(lingvo, submission, mode="new_post"):
    """
    Notify users about posts in a language they’ve subscribed to.
    This function also handles curating the list of users who will be
    notified.

    :param lingvo: Lingvo object containing language information (e.g. code, name).
    :param submission: PRAW Submission object representing the Reddit post.
    :param mode: Notification context: "identify", "new_post", or "page".
    :return: List of usernames that were notified.
    """
    notify_users_list = []
    page_users_count = SETTINGS["num_users_page"]
    contacted = []  # Track users already contacted for this post
    post_type = "translation request"

    # Extract submission metadata
    post_title = submission.title
    post_permalink = submission.permalink
    post_author = submission.author.name if submission.author else None
    post_id = submission.id
    post_nsfw = submission.over_18

    # Get the language code and name from Lingvo
    search_code = lingvo.preferred_code
    language_name = lingvo.name
    language_greetings = lingvo.greetings.title()

    # Load post tracking data from AJO (includes contact history)
    ajo_data = ajo_loader(post_id)
    try:
        language_history = ajo_data.language_history
        contacted = ajo_data.notified
        logger.debug(f"Notifier: Already contacted u/{contacted}")
        permission_to_proceed = _should_send_language_notification(
            lingvo, language_history
        )
    except AttributeError:  # In rare cases
        permission_to_proceed = True

    # Stop notification if the same users were already contacted recently
    if not permission_to_proceed:
        return []

    # This is a country-specific request or a script request.
    if lingvo.country or lingvo.script_code:
        # Mark script-based matches explicitly
        if lingvo.script_code:
            search_code = f"unknown-{lingvo.preferred_code}"

        if lingvo.country:
            country_code = country_converter(lingvo.country)
            search_code = f"{lingvo.preferred_code}-{country_code}"

        # Append users subscribed to script/regional variants
        regional_data = _notifier_specific_language_filter(lingvo)
        if regional_data:
            notify_users_list.extend(regional_data)

    # Query for users subscribed to this language code
    sql_lc = "SELECT * FROM notify_users WHERE language_code = ?"
    cursor = db.conn_main.cursor()
    cursor.execute(sql_lc, (search_code,))
    notify_targets = cursor.fetchall()

    if not notify_targets and not notify_users_list:
        return []

    # Add retrieved usernames to list (avoiding duplicates)
    for target in notify_targets:
        username = target[1]
        notify_users_list.append(username)

    notify_users_list = list(set(notify_users_list))

    # Remove users already contacted for this post
    notify_users_list = [user for user in notify_users_list if user not in contacted]

    # Equalize distribution across popular languages
    notify_users_list = _notification_rate_limiter(
        notify_users_list, lingvo, SETTINGS["notifications_user_limit"]
    )

    # In 'page' mode, further limit to `page_users_count` users maximum
    if mode == "page" and len(notify_users_list) > page_users_count:
        notify_users_list = random.sample(notify_users_list, page_users_count)

    action_counter(len(notify_users_list), "Notifications")

    # Clean the post title before including it in messages
    post_title = _notifier_title_cleaner(post_title)

    if not notify_users_list:
        return []

    # Start timing the notification run
    messaging_start = time.time()

    # Shuffle username list in place
    random.shuffle(notify_users_list)

    for username in notify_users_list:
        # Choose the message template based on mode
        message_templates = {
            "identify": RESPONSE.MSG_NOTIFY_IDENTIFY,
            "page": RESPONSE.MSG_PAGE,
            "new_post": RESPONSE.MSG_NOTIFY,
        }

        # Default to "new_post" if mode is not found
        template = message_templates.get(mode, message_templates["new_post"])

        # If the post has an image, get a description.
        if check_url_extension(submission.url):
            image_description = fetch_image_description(submission.url, post_nsfw)
            image_description = f"Image description: *{image_description}*"
        else:
            image_description = ""

        # Format the message we wish to send.
        message = template.format(
            greetings=language_greetings,
            username=username,
            language_name=language_name,
            post_type=post_type,
            title=post_title,
            permalink=post_permalink,
            post_author=post_author,
            image_description=image_description,
        )

        # Tack on an NSFW warning if necessary.
        if post_nsfw:
            message += RESPONSE.MSG_NSFW_WARNING

        try:
            # Send message to user via Reddit messages
            message_subject = (
                f"[Notification] New {language_name} request on r/translator"
            )
            recipient = REDDIT.redditor(username)
            full_message = (
                f"{message}{RESPONSE.BOT_DISCLAIMER}{RESPONSE.MSG_UNSUBSCRIBE_BUTTON}"
            )
            message_send(
                redditor_obj=recipient, subject=message_subject, body=full_message
            )
            # Update notification count for this user/language
            _update_user_notification_count(username, lingvo)

        except exceptions.APIException as e:
            logger.info(
                f"[Notifier] Error sending message to u/{username}. Removing user."
            )
            logger.error(f"API Exception for u/{username}: {e}")
            _prune_deleted_user_notifications(username)

    # Record stats about the messaging session
    messaging_mins = (time.time() - messaging_start) / 60
    seconds_per_message = (time.time() - messaging_start) / len(notify_users_list)
    payload = (
        time_convert_to_string(messaging_start),
        "Messaging run",
        None,
        len(notify_users_list),
        None,
        language_name,
        round(messaging_mins, 2),
        round(seconds_per_message, 2),
    )
    record_activity_csv(payload)

    logger.info(
        f"[Notifier] Sent notifications to {len(notify_users_list)} "
        f"users signed up for {language_name}."
    )

    return notify_users_list


def notifier_internal(post_type, submission):
    """A stripped down version of notifier solely intended to send
    notifications regarding internal non-request posts, such as
    meta or community posts."""

    post_type_search = post_type.lower()
    original_post_author = submission.author.name if submission.author else None

    # Ensure only supported posts are acted upon.
    if post_type_search not in SETTINGS["internal_post_types"]:
        logger.error(
            f"Notifier Internal: `{post_type_search}` is not a supported post type."
        )
        return []

    # Exit if the author's invalid.
    if not original_post_author:
        return []

    # Query for users subscribed to this post type
    sql_pt = "SELECT * FROM notify_internal WHERE post_type = ?"
    cursor = db.conn_main.cursor()
    cursor.execute(sql_pt, (post_type_search,))
    notify_targets = cursor.fetchall()

    if not notify_targets:
        return []

    # Message people on the list.
    logger.info(
        f"Sending internal notifications to {len(notify_targets)} users. | `{submission.id}`"
    )
    for username in notify_targets:
        try:
            message_subject = (
                f"[Notification] New {post_type.title()} post on r/translator"
            )
            recipient = REDDIT.redditor(username)
            message_body = RESPONSE.MSG_NOTIFY.format(
                username=username,
                language_name=post_type,
                post_type="post",
                title=submission.title,
                permalink=submission.permalink,
                post_author=original_post_author,
            )
            full_message = f"{message_body}{RESPONSE.BOT_DISCLAIMER}{RESPONSE.MSG_UNSUBSCRIBE_BUTTON}"
            message_send(
                redditor_obj=recipient, subject=message_subject, body=full_message
            )

        except exceptions.APIException as e:
            logger.info(
                f"[Notifier] Error sending internal message to "
                f"u/{username}. Removing user."
            )
            logger.error(f"API Exception for u/{username}: {e}")
            _prune_deleted_user_notifications(username, True)

    return notify_targets


if __name__ == "__main__":
    while True:
        notifications_test = input(
            "Please enter the language you'd like to retrieve notifications for: "
        )
        print(fetch_usernames_for_lingvo(converter(notifications_test)))
