#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
Functions that deal with the verification process on r/translator.
There is usually only one valid verification post to analyze and
watch for, and verification requests are submitted as comment replies
to that post.
"""

import re
import sqlite3
import time
from typing import TYPE_CHECKING

from config import SETTINGS, logger
from connection import REDDIT, create_mod_note, is_mod
from database import db
from discord_utils import send_discord_alert
from languages import converter
from reddit_sender import message_reply, message_send
from responses import RESPONSE

if TYPE_CHECKING:
    from praw.models import Comment, Redditor


def get_verified_thread() -> str | None:
    """
    Return the ID of the most recent 'Verified' meta thread in r/translator
    that was posted by a moderator.

    :return: The verification post ID as a string, or None if not found or author is not a mod.
    """
    search = REDDIT.subreddit(SETTINGS["subreddit"]).search(
        "title:verified AND flair:meta", time_filter="year", sort="new", limit=1
    )

    for post in search:
        if is_mod(post.author):
            return post.id

    return None


def _set_user_flair(user: "Redditor", verified_language: str) -> None:
    """
    Checks a user's flair and sets it to the desired standards.

    :param user: A Redditor object.
    :param verified_language: The language name to verify the user for.
    :return:
    """
    subreddit_object = REDDIT.subreddit(SETTINGS["subreddit"])

    # Retrieve the original flair's text.
    user_flairs = list(subreddit_object.flair(redditor=user))
    user_flair = user_flairs[0] if user_flairs else {}
    user_original_flair = user_flair.get("flair_text") or ""
    user_new_flair = str(user_original_flair)
    logger.info(f">> u/{user}'s original flair is `{user_new_flair}`.")

    # Define the elements we want to pick out.
    # Then reconstitute the flair.
    verified_language_code = f":{converter(verified_language).preferred_code}:"
    if verified_language_code in user_original_flair:
        user_new_flair = user_original_flair.replace(verified_language_code, "")
    if verified_language in user_original_flair:
        user_new_flair = user_new_flair.replace(verified_language, "")
    verified_prefix = f":verified: [{verified_language_code} {verified_language}] "
    user_new_flair = verified_prefix + user_new_flair
    user_new_flair = user_new_flair.replace("  ", "")

    # Set the new flair.
    subreddit_object.flair.set(
        user,
        text=user_new_flair,
        flair_template_id="1e041384-e741-11e9-9794-0e7e958770bc",  # verified flair template
    )

    logger.info(f">> Set u/{user}'s verified flair to `{user_new_flair}`.")

    return


def process_verification(confirming_comment: "Comment") -> None:
    """
    A function that checks for a !verify command to verify a user in a
    language, and then assigns them the appropriate flair while
    reformatting their flair to match the standards.

    :param confirming_comment: The comment by a mod verifying the user.
    :return: Nothing.
    """

    mod_caller = confirming_comment.author
    if not is_mod(mod_caller):
        logger.warning(f"u{mod_caller} is NOT a mod.")
        return

    logger.info(f"> Verify command called by u/{mod_caller}.")

    # Extract comment data
    comment_id = confirming_comment.id
    created_utc = int(confirming_comment.created_utc)
    author_name = mod_caller.name if mod_caller else "[deleted]"

    # Check if we've already processed this verification
    query = "SELECT comment_id FROM acted_comments WHERE comment_id = ?"
    already_acted = db.fetch_main(query, (comment_id,))

    if already_acted:
        logger.info(f"> Verification comment {comment_id} already processed. Skipping.")
        return

    # Fetch the person to be verified by looking at the parent of the
    # comment. This is the person to whom the mod replied.
    parent_comment = confirming_comment.parent()
    verified_person = parent_comment.author
    logger.info(f"> User to verify: u/{verified_person}.")

    # Code to interact with user flair here.
    language_to_verify = (
        parent_comment.body.split("\n")[0].strip().title()
    )  # Get the language name.
    logger.info(f"> Language to verify them for: {language_to_verify}.")

    # Pass it to the function to set it.
    _set_user_flair(verified_person, language_to_verify)
    parent_comment.mod.approve()

    # Message the mod.
    message_send(
        mod_caller,
        subject=f"Verified u/{verified_person}",
        body=f"Verified u/{verified_person} for {language_to_verify}. Command called by you "
        f"[here](https://www.reddit.com{confirming_comment.permalink}?context=10000).",
    )
    logger.info(f">> Notified mod u/{mod_caller} via messages.")

    # Record this action in the database
    insert_query = """
                   INSERT INTO acted_comments (comment_id, created_utc, comment_author_username, action_type)
                   VALUES (?, ?, ?, ?) \
                   """
    cursor = db.cursor_main
    cursor.execute(
        insert_query, (comment_id, created_utc, author_name, "process_verification")
    )
    db.conn_main.commit()

    logger.info("> Verified procedure complete.")

    return


def verification_parser() -> None:
    """
    Top-level function to collect new requests for verified flairs.
    Ziwen will write their information into a log and also report their
    comment to the moderators for inspection and verification.

    :return: None
    """
    if not VERIFIED_POST_ID:
        return

    submission = REDDIT.submission(id=VERIFIED_POST_ID)
    try:
        submission.comments.replace_more(limit=None)
    except ValueError:
        return

    cursor = db.cursor_main

    for comment in submission.comments.list():
        comment_body = comment.body.strip()

        try:
            author_name = comment.author.name
            author_string = f"u/{author_name}"
        except AttributeError:
            # Author is deleted; skip this comment
            continue

        # Check if comment has already been processed in the database
        existing = db.fetch_main(
            "SELECT verification_comment_id FROM verification_database WHERE verification_comment_id = ?",
            (comment.id,),
        )
        if existing:
            continue

        # Skip old comments past our window
        verification_request_age = SETTINGS["verification_request_age"] * 60
        if int(time.time()) - int(comment.created_utc) >= verification_request_age:
            continue

        # Normalize comment body for parsing
        normalized_body = comment_body.replace("\n", "|").replace("||", "|")
        components = [
            comp.strip() for comp in normalized_body.split("|") if comp.strip()
        ]

        url_pattern = r"https?://(?:www\.)?[-a-zA-Z0-9@:%._\+~#=]{2,256}\.[a-z]{2,6}\b(?:[-a-zA-Z0-9@:%_\+.~#?&//=]*)"

        try:
            language_name = components[0]

            # Find all URLs in the components (skip the first one which is language name)
            urls = []
            notes = ""

            for i, comp in enumerate(components[1:], start=1):
                if re.search(url_pattern, comp):
                    urls.append(re.search(url_pattern, comp).group(0))
                else:
                    # If it's not a URL, treat everything from here as notes
                    notes = " ".join(components[i:])
                    break

            # Require at least 3 URLs
            if len(urls) < 3:
                raise ValueError("Not enough URLs")

        except (IndexError, AttributeError, ValueError):
            # Malformed comment - stop processing
            if comment.is_root:
                redo_reply = RESPONSE.COMMENT_INVALID_VERIFICATION_RESPONSE.format(
                    username=author_name,
                    request_link=comment.permalink,
                )
                message_reply(comment, redo_reply)
                logger.info(
                    f"Unable to parse verification request at https://www.reddit.com{comment.permalink}. "
                    f"Replied to {author_string} requesting them to start over."
                )
            else:
                logger.debug(
                    f"Skipping nested comment by {author_string} at https://www.reddit.com{comment.permalink}."
                )
            continue

        language_lingvo = converter(language_name)

        # Insert into database to mark as processed
        try:
            cursor.execute(
                """
                INSERT INTO verification_database 
                (verification_comment_id, post_id, created_utc, username, language_code)
                VALUES (?, ?, ?, ?, ?)
            """,
                (
                    comment.id,
                    VERIFIED_POST_ID,
                    int(comment.created_utc),
                    author_name,
                    language_lingvo.preferred_code,
                ),
            )
            db.conn_main.commit()
        except sqlite3.Error as e:
            logger.error(f"Database error for comment {comment.id}: {e}")
            continue

        # Reply to the person who asked for verification.
        reply_text = (
            RESPONSE.COMMENT_VERIFICATION_RESPONSE.format(
                language_lingvo.thanks, author_name, language_lingvo.name
            )
            + RESPONSE.BOT_DISCLAIMER
        )
        message_reply(comment, reply_text)

        # Credit the person who helped mark the translation
        verified_note = f"Requested verification for ({language_lingvo.name})"

        create_mod_note(
            label="HELPFUL_USER",
            username=author_name,
            included_note=verified_note,
        )

        send_discord_alert(
            f"New Verification Request for **{language_name}**",
            f"Please check [this verification request](https://www.reddit.com{comment.permalink}) "
            f"from [{author_string}](https://www.reddit.com/user/{author_name})."
            f"\n\nIncluded notes from user: *{notes if notes else 'None'}*",
            "verification",
        )
        logger.info(
            f"[ZW] Notified moderators about a new verification request from u/{author_string}."
        )

    return


VERIFIED_POST_ID = get_verified_thread()

if __name__ == "__main__":
    print(get_verified_thread())
