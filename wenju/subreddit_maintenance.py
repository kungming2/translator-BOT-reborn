#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""Maintain r/translator wiki, sticky, flair, and modmail state."""

import logging
import re
from datetime import UTC, datetime

import prawcore

from config import SETTINGS
from config import logger as _base_logger
from integrations.discord_utils import send_discord_alert
from lang.languages import converter
from reddit.connection import REDDIT, USERNAME
from reddit.verification import get_verified_thread
from time_handling import get_current_utc_date, time_convert_to_string_seconds
from wenju import WENJU_SETTINGS, task

logger = logging.LoggerAdapter(_base_logger, {"tag": "WJ:SUBMAINT"})


@task(schedule="weekly")
def update_verified_list() -> None:
    """
    Update the subreddit wiki page 'verified' with a sorted list of verified
    users organized by language. Also flags users with problematic flairs
    (e.g., missing brackets, incorrect flair class, or misuse of verified emoji).
    """
    formatted_text = []
    users_to_fix = []
    master_list = {}
    users_by_flair: dict[str, list[str]] = {}

    for flair in REDDIT.subreddit(SETTINGS["subreddit"]).flair(limit=None):
        flair_text = flair.get("flair_text")
        if flair_text:
            master_list[str(flair["user"])] = (
                flair_text,
                flair.get("flair_css_class"),
            )

    for user, (flair_text, flair_css) in master_list.items():
        if flair_css == "verified":
            match = re.findall(r"\[(.*?)]", flair_text)
            if not match:
                users_to_fix.append(user)
                continue

            verified_for = match[0]
            clean_text = re.sub(r"[^\w\s]", " ", verified_for)
            for word in clean_text.split():
                converter_result = converter(word, False)
                if converter_result:
                    result = converter_result.preferred_code
                    if result:
                        users_by_flair.setdefault(result, []).append(user)

        elif flair_css not in {"verified", "moderator"} and ":verified:" in flair_text:
            users_to_fix.append(user)

    for language_code in sorted(users_by_flair):
        if language_code == "en":
            continue

        _lingvo = converter(language_code)
        language_name = _lingvo.name if _lingvo is not None else language_code
        unique_users = sorted({u.lower() for u in users_by_flair[language_code]})
        header = f"\n###### `{language_code}` {language_name} ({len(unique_users)})"
        formatted_text.append(header)
        formatted_text.extend(f"* u/{user}" for user in unique_users)

    final_text = "\n".join(formatted_text)

    if users_to_fix:
        user_links = [
            f"* [u/{username}](https://www.reddit.com/user/{username})"
            for username in users_to_fix
        ]
        user_list = "\n".join(user_links)
        mod_fix_alert = (
            f"The following users have irregular verified flairs:\n{user_list}"
        )
        send_discord_alert("Irregular Verified User Flairs", mod_fix_alert, "alert")

    verified_page = REDDIT.subreddit(SETTINGS["subreddit"]).wiki["verified"]
    anchor = "## List of Verified Translators on r/translator"

    upper_portion = verified_page.content_md.split(anchor, 1)[0]
    date_stamp = f"\n* *Last Updated {get_current_utc_date()}*\n"
    date_stamp += (
        f"* [Current Verification Thread](https://redd.it/{get_verified_thread()})\n"
    )
    final_update = "\n".join([upper_portion, anchor, date_stamp, final_text])

    verified_page.edit(content=final_update, reason="Updating the verified list.")
    logger.info("> Verified list on the wiki updated.")

    return


@task(schedule="monthly")
def monthly_statistics_unpinner() -> None:
    """Unpin the statistics posts if still pinned when the monthly routine runs."""
    sub = REDDIT.subreddit(SETTINGS["subreddit"])
    stickies = []

    for i in range(1, 3):  # Try sticky 1 and sticky 2
        try:
            sticky = sub.sticky(number=i)
            stickies.append(sticky)
        except prawcore.exceptions.NotFound:
            continue

    for sticky in stickies:
        print(sticky.title)
        if (
            "[Meta] r/translator Statistics" in sticky.title
            and sticky.author
            and sticky.author.name == USERNAME
        ):
            sticky.mod.sticky(state=False)
            logger.info("Monthly Statistics Unpinner: Unpinned monthly post.")

    return


@task(schedule="daily")
def archive_modmail() -> None:
    """Archive old modmail conversations in which a moderator participated."""
    days_max = WENJU_SETTINGS["modmail_archival_age"]

    logger.debug("Assessing modmail...")
    subreddit = REDDIT.subreddit(SETTINGS["subreddit"])

    mod_names = [mod.name.lower() for mod in subreddit.moderator()]
    logger.debug(f"Moderators: {mod_names}")

    unread_counts = subreddit.modmail.unread_count()
    for key, count in unread_counts.items():
        if count > 0:
            logger.debug(f"Current '{key}' in modmail: {count}")

    current_time = datetime.now(UTC)
    max_age_seconds = days_max * 86400

    for convo in subreddit.modmail.conversations():
        convo.read()

        last_updated = datetime.fromisoformat(convo.last_updated)
        convo_age = (current_time - last_updated).total_seconds()
        readable_age = time_convert_to_string_seconds(int(convo_age))

        participants = (
            [author.name for author in convo.authors] if convo.authors else []
        )
        mod_participant = next(
            (name for name in participants if name.lower() in mod_names), None
        )
        logger.debug(
            f"Conversation '{convo.subject}' | Age: {readable_age} | "
            f"Authors: {participants} | Mod participant: {mod_participant}"
        )

        if convo_age > max_age_seconds and mod_participant:
            convo.archive()
            logger.info(
                f"Conversation by u/{convo.participant} archived. "
                f"({readable_age} old, mod u/{mod_participant} participated)."
            )
        else:
            skip_reason = (
                "not old enough"
                if convo_age <= max_age_seconds
                else "no moderator participated"
            )
            logger.debug(
                f"Conversation by u/{convo.participant} not archived. "
                f"({readable_age}, {skip_reason.title()})."
            )
