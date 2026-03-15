#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
Handles connections with Reddit.
...

Logger tag: [CONN]
"""

import logging
import re

import praw
import requests
from praw.exceptions import RedditAPIException
from praw.models import Redditor
from prawcore import exceptions
from random_user_agent.params import OperatingSystem, SoftwareName
from random_user_agent.user_agent import UserAgent

from config import SETTINGS, Paths, load_settings
from config import logger as _base_logger

logger = logging.LoggerAdapter(_base_logger, {"tag": "CONN"})


def reddit_login(credentials):
    """
    Logs in to Reddit with the standard credentials.
    """
    reddit = praw.Reddit(
        client_id=credentials["ZIWEN_APP_ID"],
        client_secret=credentials["ZIWEN_APP_SECRET"],
        username=credentials["USERNAME"],
        password=credentials["PASSWORD"],
        user_agent="An assistant for r/translator",
    )

    return reddit


def reddit_helper_login(credentials):
    """
    Logs in to Reddit with the helper credentials. This is used for non-
    moderation tasks in order to reduce API calls.
    """
    reddit = praw.Reddit(
        client_id=credentials["HUIBAN_APP_ID"],
        client_secret=credentials["HUIBAN_APP_SECRET"],
        username=credentials["HUIBAN_USERNAME"],
        password=credentials["HUIBAN_PASSWORD"],
        user_agent="Another assistant for r/translator",
    )

    return reddit


def reddit_hermes_login(credentials):
    """
    Logs in to Reddit with Hermes's dedicated credentials.
    Hermes is a separate bot account for r/Language_Exchange matching.
    """
    reddit = praw.Reddit(
        client_id=credentials["HERMES_APP_ID"],
        client_secret=credentials["HERMES_APP_SECRET"],
        username=credentials["HERMES_USERNAME"],
        password=credentials["HERMES_PASSWORD"],
        user_agent=(
            f"Hermes, a language-exchange matching assistant for r/Language_Exchange. "
            f"u/{credentials['HERMES_USERNAME']}"
        ),
    )

    return reddit


def reddit_status_check() -> list[dict] | None:
    """
    Fetch unresolved Reddit incidents from their API.

    :returns:
        - list of incident dicts if incidents exist
        - empty list if no incidents
        - None if the API could not be reached
    """
    url = "https://www.redditstatus.com/api/v2/incidents/unresolved.json"

    try:
        response = requests.get(url, timeout=5)
        response.raise_for_status()
    except requests.RequestException as e:
        logger.warning(f"Could not connect to Reddit Status API: {e}")
        return None

    incidents = response.json().get("incidents", []) or []

    for incident in incidents:
        logger.info(
            f"Reddit incident: {incident.get('name')} | "
            f"Status: {incident.get('status')} | "
            f"Created: {incident.get('created_at')} | "
            f"Updated: {incident.get('updated_at')}"
        )

    return incidents


def get_random_useragent():
    """
    Returns a dictionary with a random User-Agent and a
    default Accept header. Generally used with website accessing
    requests.
    """
    software_names = [SoftwareName.CHROME.value]
    operating_systems = [OperatingSystem.WINDOWS.value, OperatingSystem.LINUX.value]

    user_agent_rotator = UserAgent(
        software_names=software_names, operating_systems=operating_systems, limit=1
    )

    # Get Random User Agent String.
    user_agent = user_agent_rotator.get_random_user_agent()

    return {
        "User-Agent": user_agent,
        "Accept": (
            "text/html,application/json,application/xhtml+xml,"
            "application/xml;q=0.9,image/webp,*/*;q=0.8"
        ),
    }


def is_mod(user) -> bool:
    """
    Checks whether the given user is a moderator of r/translator.

    :param user: Reddit username (str) or Redditor object.
    :return: True if user is a moderator, False otherwise.
    """
    if isinstance(user, Redditor):
        username = user.name
    elif isinstance(user, str):
        username = user
    else:
        raise TypeError("`user` must be a string or Redditor object")

    return username.lower() in (
        mod.name.lower() for mod in REDDIT.subreddit(SETTINGS["subreddit"]).moderator()
    )


def is_valid_user(username):
    """
    Simple function that tests if a Redditor is a valid user.
    Used to keep the notifications database clean.
    Note that `AttributeError` is returned if a user is *suspended* by
    Reddit, while NotFound is usually returned if the user is shadow-
    banned.

    :param username: The username of a Reddit user.
    :return exists: A boolean. False if non-existent or shadowbanned,
                    True if a regular user.
    """

    try:
        # Just try to access fullname; no need to assign it if unused
        _ = REDDIT_HELPER.redditor(username).fullname
        return True
    except exceptions.NotFound:
        logger.debug(f"User {username!r} not found (shadowbanned or deleted).")
        return False
    except AttributeError:
        logger.debug(f"User {username!r} is suspended.")
        return False


def is_internal_post(submission: "praw.models.Submission") -> bool:
    """
    Determines whether a PRAW submission is considered an internal post.

    Internal post if:
    1. Title starts with one of the internal post types in SETTINGS (case-insensitive), e.g. [META].
    2. Title contains 'translation challenge' (case-insensitive) AND the author is a mod.

    :param submission: PRAW Submission object.
    :return: True if submission is an internal post, False otherwise.
    """
    title = submission.title

    # Check for internal post types
    diskuto_pattern = r"^\s*\[(" + "|".join(SETTINGS["internal_post_types"]) + r")\]"
    if re.match(diskuto_pattern, title, flags=re.I):
        return True

    # Alternate condition: 'translation challenge' + mod author
    if "translation challenge" in title.lower():
        if is_mod(submission.author):
            return True

    return False


def create_mod_note(
    label: str,
    username: str,
    included_note: str,
) -> bool:
    """
    Creates a moderator note for a user.

    :param label: The label of the user in the note. See:
                  https://praw.readthedocs.io/en/stable/code_overview/other/mod_note.html
                  for current valid ones. These must be standard labels
                  (no user-created ones):
                      * ABUSE_WARNING
                      * BAN
                      * BOT_BAN
                      * HELPFUL_USER
                      * PERMA_BAN
                      * SOLID_CONTRIBUTOR
                      * SPAM_WARNING
                      * SPAM_WATCH
                      * None
    :param username: The username of the translator to create a note for.
    :param included_note: The note to include.
    :return: True if note was created successfully, False otherwise.
    """
    try:
        REDDIT.subreddit(SETTINGS["subreddit"]).mod.notes.create(
            label=label,
            note=included_note,
            redditor=REDDIT.redditor(username),
        )

        logger.info(f"Created {label} note for u/{username}: {included_note}")
        return True

    except Exception as e:
        logger.error(f"Failed to create note for u/{username}: {e}")
        return False


def widget_update(widget_id, new_text):
    """
    Update a text widget on the subreddit with new content.

    Args:
        widget_id: ID of the widget to update
        new_text: New text content for the widget

    Returns:
        bool: True if update was successful, False otherwise
    """
    try:
        widgets = REDDIT.subreddit(SETTINGS["subreddit"]).widgets
        widgets.progressive_images = True

        # Search for the widget in the sidebar
        active_widget = None
        for widget in widgets.sidebar:
            if isinstance(widget, praw.models.TextArea):
                if widget.id == widget_id:
                    logger.debug(f"Found widget with ID: `{widget_id}`")
                    active_widget = widget
                    break

        if active_widget is None:
            logger.warning(f"Widget with ID `{widget_id}` not found.")
            return False

        # Update the widget
        try:
            active_widget.mod.update(text=new_text)
            logger.info(f"Successfully updated widget `{widget_id}`.")
            return True
        except RedditAPIException as e:
            logger.error(f"Error updating widget `{widget_id}`: {e}")
            return False

    except Exception as e:
        logger.error(f"Unexpected error in widget_update: {e}")
        return False


"""REMOVAL REASONS"""


def _fetch_removal_reasons():
    global _removal_reasons_cache
    if _removal_reasons_cache is not None:
        return _removal_reasons_cache

    reasons = [
        (removal_reason.title, removal_reason.id, removal_reason.message)
        for removal_reason in REDDIT.subreddit(
            SETTINGS["subreddit"]
        ).mod.removal_reasons
    ]
    logger.debug(f"Fetched {len(reasons)} removal reason(s) from Reddit")

    _removal_reasons_cache = (
        {index + 1: value for index, value in enumerate(reasons)} if reasons else None
    )
    return _removal_reasons_cache


def _search_removal_reasons(prompt):
    """Takes a prompt and searches through removal reasons fetched from
    the subreddit, returning the specific removal reason ID if found.
    E.g. the prompt could be "spam".
    """

    reasons_dict = _fetch_removal_reasons()
    logger.debug(f"Removal reason IDs: {reasons_dict}")

    if not reasons_dict:
        return None

    for entry, entry_id, _description in reasons_dict.values():
        if prompt.lower().strip() in entry.lower():
            logger.info(f"Found removal reason ID for {entry}: {entry_id}")
            return entry_id
    return None


def remove_content(item, reason: str, mod_note: str = None):
    """Removes an item using PRAW's mod.remove(), searching for a matching removal reason.

    Args:
        item: A PRAW item (submission or comment) object to remove.
        reason: A string to search for in the subreddit's removal reasons (e.g. "duplicate").
        mod_note: Optional mod note to attach. Defaults to a generic removal message.
    """
    removal_reason_id = _search_removal_reasons(reason)

    removal_kwargs = {
        "reason_id": removal_reason_id,
        "mod_note": mod_note or f"Removed: {reason}",
    }

    logger.info(
        f"Removing post {item.id} with reason '{reason}' (reason_id={removal_reason_id})"
    )
    item.mod.remove(**removal_kwargs)


"""DEFINED GLOBALS"""


credentials_source = load_settings(Paths.AUTH["CREDENTIALS"])
REDDIT = reddit_login(credentials_source)
REDDIT_HELPER = reddit_helper_login(credentials_source)
REDDIT_HERMES = reddit_hermes_login(credentials_source)
USERNAME = credentials_source["USERNAME"]

_removal_reasons_cache = None


def show_menu():
    print("\nSelect an option to run:")
    print("1. Reddit status check (fetch unresolved incidents)")
    print("2. Search removal reasons (text search)")
    print("3. Get a random user agent")
    print("x. Exit")


if __name__ == "__main__":
    while True:
        show_menu()
        choice = input("Enter your choice (1-3): ").strip()

        if choice == "x":
            print("Exiting...")
            break

        if choice not in ["1", "2", "3"]:
            print("Invalid choice, please try again.")
            continue

        if choice == "1":
            result = reddit_status_check()
            if result is None:
                print("Could not reach the Reddit Status API.")
            elif not result:
                print("No unresolved Reddit incidents.")
            else:
                for test_incident in result:
                    print(
                        f"\n[{test_incident.get('status', '').upper()}] {test_incident.get('name')}"
                        f"\n  Created : {test_incident.get('created_at')}"
                        f"\n  Updated : {test_incident.get('updated_at')}"
                    )

        elif choice == "2":
            test_prompt = input("Enter search prompt for removal reasons: ").strip()
            if not test_prompt:
                print("No prompt entered.")
                continue
            reason_id = _search_removal_reasons(test_prompt)
            if reason_id:
                print(f"Found removal reason ID: {reason_id}")
            else:
                print(f"No removal reason found matching '{test_prompt}'.")

        elif choice == "3":
            ua = get_random_useragent()
            print(f"\nUser-Agent : {ua['User-Agent']}")
            print(f"Accept     : {ua['Accept']}")
