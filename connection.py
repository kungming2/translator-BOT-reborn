#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
Handles connections with Reddit.
"""

import random
import requests

import praw
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
    Returns a dictionary with a random User-Agent and a default Accept header.
    """
    ua_data = load_settings(Paths.AUTH['USER_AGENT'])

    random_ua = random.choice(ua_data['ua'])
    return {
        'User-Agent': random_ua,
        'Accept': (
            "text/html,application/json,application/xhtml+xml,"
            "application/xml;q=0.9,image/webp,*/*;q=0.8"
        )
    }


def is_mod(reddit_object, user: str) -> bool:
    """
    Checks whether the given user is a moderator of r/translator.

    :param reddit_object: Reddit object from PRAW.
    :param user: Reddit username to check.
    :return: True if user is a moderator, False otherwise.
    """
    return user.lower() in (mod.name.lower() for mod in reddit_object.moderator())


credentials_source = load_settings(Paths.AUTH['CREDENTIALS'])
REDDIT = reddit_login(credentials_source)
REDDIT_HELPER = reddit_helper_login(credentials_source)

if __name__ == "__main__":
    print(get_random_useragent())
