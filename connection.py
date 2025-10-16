#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
Handles connections with Reddit.
"""
import praw
import requests
from praw.exceptions import RedditAPIException
from praw.models import Redditor
from prawcore import exceptions
from random_user_agent.params import OperatingSystem, SoftwareName
from random_user_agent.user_agent import UserAgent

from config import Paths, load_settings, logger


def reddit_login(credentials):

    reddit = praw.Reddit(
        client_id=credentials['ZIWEN_APP_ID'],
        client_secret=credentials['ZIWEN_APP_SECRET'],
        username=credentials['USERNAME'],
        password=credentials['PASSWORD'],
        user_agent='An assistant for r/translator'
    )

    return reddit


def reddit_helper_login(credentials):

    reddit = praw.Reddit(
        client_id=credentials['HUIBAN_APP_ID'],
        client_secret=credentials['HUIBAN_APP_SECRET'],
        username=credentials['HUIBAN_USERNAME'],
        password=credentials['HUIBAN_PASSWORD'],
        user_agent='Another assistant for r/translator'
    )

    return reddit


def chinese_reference_login(credentials):

    reddit = praw.Reddit(
        client_id=credentials['CHINESE_APP_ID'],
        client_secret=credentials['CHINESE_APP_SECRET'],
        username=credentials['CHINESE_USERNAME'],
        password=credentials['CHINESE_PASSWORD'],
        user_agent='Regular tasks on r/ChineseLanguage'
    )

    return reddit


def reddit_status_check():
    """
    Check if there are any unresolved Reddit incidents that may affect bot operation.
    API documentation: https://www.redditstatus.com/api

    :returns: True if the site has no incidents, False otherwise.
    """
    url = "https://www.redditstatus.com/api/v2/incidents/unresolved.json"

    try:
        response = requests.get(url, timeout=5)
        response.raise_for_status()
    except requests.RequestException as e:
        logger.warning(f"Could not connect to Reddit Status API: {e}")
        return False

    incidents = response.json().get("incidents", [])

    if incidents:
        for incident in incidents:
            logger.info(
                f"[Reddit Incident] {incident.get('name')} | "
                f"Status: {incident.get('status')} | "
                f"Created: {incident.get('created_at')} | "
                f"Updated: {incident.get('updated_at')}"
            )
        return False

    return True


def get_random_useragent():
    """
    Returns a dictionary with a random User-Agent and a
    default Accept header.
    """
    software_names = [SoftwareName.CHROME.value]
    operating_systems = [OperatingSystem.WINDOWS.value, OperatingSystem.LINUX.value]

    user_agent_rotator = UserAgent(software_names=software_names,
                                   operating_systems=operating_systems,
                                   limit=1)

    # Get Random User Agent String.
    user_agent = user_agent_rotator.get_random_user_agent()

    return {
        'User-Agent': user_agent,
        'Accept': (
            "text/html,application/json,application/xhtml+xml,"
            "application/xml;q=0.9,image/webp,*/*;q=0.8"
        )
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

    return username.lower() in (mod.name.lower() for mod in REDDIT.subreddit("translator").moderator())


def is_valid_user(username):
    """
    Simple function that tests if a Redditor is a valid user.
    Used to keep the notifications database clean.
    Note that `AttributeError` is returned if a user is *suspended* by Reddit.

    :param username: The username of a Reddit user.
    :return exists: A boolean. False if non-existent or shadowbanned,
                    True if a regular user.
    """

    try:
        # Just try to access fullname; no need to assign it if unused
        _ = REDDIT_HELPER.redditor(username).fullname
        return True
    except (exceptions.NotFound, AttributeError):
        logger.error(f"User {username} not found.")
        return False


def widget_update(widget_id, new_text):
    """
    Update a text widget on a subreddit with new content.

    Args:
        widget_id: ID of the widget to update
        new_text: New text content for the widget

    Returns:
        bool: True if update was successful, False otherwise
    """
    try:
        widgets = REDDIT.subreddit("translator").widgets
        widgets.progressive_images = True

        # Search for the widget in the sidebar
        active_widget = None
        for widget in widgets.sidebar:
            if isinstance(widget, praw.models.TextArea):
                if widget.id == widget_id:
                    logger.debug(f"Found widget with ID: {widget_id}")
                    active_widget = widget
                    break

        if active_widget is None:
            logger.info(f'Widget with ID {widget_id} not found.')
            return False

        # Update the widget
        try:
            active_widget.mod.update(text=new_text)
            logger.error(f"Successfully updated widget {widget_id}.")
            return True
        except RedditAPIException as e:
            logger.error(f'Error updating widget {widget_id}: {e}')
            return False

    except Exception as e:
        logger.error(f'Unexpected error in widget_update: {e}')
        return False


def _fetch_removal_reasons():
    """
    Fetches the removal reasons present on r/translator.
    :return: `None` if there's nothing, a dictionary containing tuples
    indexed by numbers otherwise.
    """

    reasons = [
        (removal_reason.title, removal_reason.id, removal_reason.message)
        for removal_reason in REDDIT.subreddit('translator').mod.removal_reasons
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


credentials_source = load_settings(Paths.AUTH['CREDENTIALS'])
REDDIT = reddit_login(credentials_source)
REDDIT_HELPER = reddit_helper_login(credentials_source)

if __name__ == "__main__":
    print(_fetch_removal_reasons())
    print(is_mod(REDDIT.redditor('kungming2')))
