#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
Handles connections with Reddit.
"""

import re

import praw
import requests
from praw.exceptions import RedditAPIException
from praw.models import Redditor
from prawcore import exceptions
from random_user_agent.params import OperatingSystem, SoftwareName
from random_user_agent.user_agent import UserAgent

from config import SETTINGS, Paths, load_settings, logger


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
            f"[Reddit Incident] {incident.get('name')} | "
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
    except (exceptions.NotFound, AttributeError):
        logger.warning(f"User {username} not found.")
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

        logger.info(f"[ModNote] Created {label} note for u/{username}: {included_note}")
        return True

    except Exception as e:
        logger.error(f"[ModNote] Failed to create note for u/{username}: {e}")
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
            logger.info(f"Widget with ID `{widget_id}` not found.")
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


def _fetch_removal_reasons():
    """
    Fetches the removal reasons present on r/translator.
    :return: `None` if there's nothing, a dictionary containing tuples
    indexed by numbers otherwise.
    """

    reasons = [
        (removal_reason.title, removal_reason.id, removal_reason.message)
        for removal_reason in REDDIT.subreddit(
            SETTINGS["subreddit"]
        ).mod.removal_reasons
    ]

    if reasons:
        return {index + 1: value for index, value in enumerate(reasons)}
    else:
        return None


def search_removal_reasons(prompt):
    """Takes a prompt and searches through removal reasons fetched from
    the subreddit, returning the specific removal reason ID if found.
    E.g. the prompt could be "spam".
    """

    reasons_dict = _fetch_removal_reasons()
    logger.info(f"Removal reason IDs: {reasons_dict}")

    if not reasons_dict:
        return None

    for entry, entry_id, _description in reasons_dict.values():
        if prompt.lower().strip() in entry.lower():
            return entry_id
    return None


credentials_source = load_settings(Paths.AUTH["CREDENTIALS"])
REDDIT = reddit_login(credentials_source)
REDDIT_HELPER = reddit_helper_login(credentials_source)
USERNAME = credentials_source["USERNAME"]

if __name__ == "__main__":
    print(reddit_status_check())
