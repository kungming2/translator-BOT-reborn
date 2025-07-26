#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
Functions that deal with the verification process on r/translator.
There is usually only one valid verification post to analyze and
watch for.
TODO INCOMPLETE
"""
import re
import time

from config import logger, SETTINGS
from connection import REDDIT, is_mod
from languages import converter


def get_verified_thread():
    """
    Return the ID of the most recent 'Verified' meta thread in r/translator.

    :return: The verification post ID as a string, or None if not found.
    """
    search = REDDIT.subreddit("translator").search(
        "title:verified AND flair:meta", time_filter="year", sort="new", limit=1
    )
    return next((post.id for post in search), None)


def set_user_flair(user, verified_language):
    """
    Checks a user's flair and sets it to the desired standards.

    :param user: A Redditor object.
    :param verified_language: The language name to verify the user for.
    :return:
    """
    subreddit_object = REDDIT.subreddit(SETTINGS['subreddit'])

    # Retrieve the original flair's text.
    user_flairs = list(subreddit_object.flair(redditor=user))
    user_flair = user_flairs[0] if user_flairs else {}
    user_original_flair = user_flair.get('flair_text') or ''
    user_new_flair = str(user_original_flair)
    logger.info(f">> u/{user}'s original flair is `{user_new_flair}`.")

    # Define the elements we want to pick out.
    # Then reconstitute the flair.
    verified_language_code = f":{converter(verified_language).preferred_code}:"
    if verified_language_code in user_original_flair:
        user_new_flair = user_original_flair.replace(verified_language_code, '')
    if verified_language in user_original_flair:
        user_new_flair = user_new_flair.replace(verified_language, '')
    verified_prefix = f":verified: [{verified_language_code} {verified_language}] "
    user_new_flair = verified_prefix + user_new_flair
    user_new_flair = user_new_flair.replace('  ', '')

    # Set the new flair.
    subreddit_object.flair.set(user, text=user_new_flair,
                               flair_template_id="1e041384-e741-11e9-9794-0e7e958770bc")

    logger.info(f">> Set u/{user}'s verified flair to `{user_new_flair}`.")

    return


def process_verification(confirming_comment):
    """
    A function that checks for a !verify command to verify a user in a
    language, and then assigns them the appropriate flair while
    reformatting their flair to match the standards.

    :param confirming_comment: The comment by a mod verifying the user.
    :return: Nothing.
    """

    mod_caller = confirming_comment.author
    if not is_mod(REDDIT, mod_caller):
        logger.error(f"u{mod_caller} is NOT a mod.")
        return None

    logger.info(f"> Verify command called by u/{mod_caller}.")
    confirming_comment.save()

    # Exit if we've processed this already.
    if confirming_comment.saved:
        return None

    # Fetch the person to be nuked by looking at the parent of the
    # comment. This is the person to whom the mod replied.
    parent_comment = confirming_comment.parent()
    verified_person = parent_comment.author
    logger.info(f"> User to verify: u/{verified_person}.")

    # Code to interact with user flair here.
    language_to_verify = parent_comment.body.split('\n')[0].strip().title()  # Get the language name.
    logger.info(f"> Language to verify them for: {language_to_verify}.")

    # Pass it to the function to set it.
    set_user_flair(verified_person, language_to_verify)
    parent_comment.mod.approve()

    # Message the mod.
    mod_caller.message(subject=f"Verified u/{verified_person}",
                       message=f"Verified u/{verified_person} for {language_to_verify}. Command called by you "
                               f"[here]({confirming_comment.permalink}?context=10000).")
    logger.info(f">> Notified mod u/{mod_caller} via messages.")
    logger.info("> Verified procedure complete.")

    return parent_comment


def verification_parser():
    """
    Top-level function to collect requests for verified flairs. Ziwen will write their information into a log
    and also report their comment to the moderators for inspection and verification.

    :return: None
    """
    if not VERIFIED_POST_ID:
        return

    submission = reddit.submission(id=VERIFIED_POST_ID)
    try:
        submission.comments.replace_more(limit=None)
    except ValueError:
        return

    for comment in submission.comments.list():
        comment_id = comment.id
        comment_body = comment.body.strip()

        try:
            author_name = comment.author.name
            author_string = f"u/{author_name}"
        except AttributeError:
            # Author is deleted; skip this comment
            continue

        # Skip if comment already processed
        cursor_main.execute('SELECT 1 FROM old_comments WHERE ID=?', (comment_id,))
        if cursor_main.fetchone():
            continue

        cursor_main.execute('INSERT INTO old_comments VALUES (?)', (comment_id,))
        conn_main.commit()

        comment.save()  # Mark comment as processed on Reddit (bot ignores saved comments)

        # Skip old comments (>5 minutes) or already saved (processed) comments
        if int(time.time()) - int(comment.created_utc) >= 300 or comment.saved:
            continue

        # Normalize comment body for parsing
        normalized_body = comment_body.replace('\n', '|').replace('||', '|')
        components = [comp.strip() for comp in normalized_body.split('|') if comp.strip()]

        url_pattern = r'https?://(?:www\.)?[-a-zA-Z0-9@:%._\+~#=]{2,256}\.[a-z]{2,6}\b(?:[-a-zA-Z0-9@:%_\+.~#?&//=]*)'

        try:
            language_name = components[0]
            url_1 = re.search(url_pattern, components[1]).group(0)
            url_2 = re.search(url_pattern, components[2]).group(0)
            url_3 = re.search(url_pattern, components[3]).group(0)
            notes = components[4] if len(components) > 4 else ""
        except (IndexError, AttributeError):
            # Malformed comment - ignore and stop processing
            return

        language_code = converter(language_name).preferred_code
        thanks_phrase = MAIN_LANGUAGES.get(language_code, {}).get('thanks', 'Thank you')

        # Format verification log entry
        entry = f"| {author_string} | {language_name} | [1]({url_1}), [2]({url_2}), [3]({url_3}) | {notes} |"
        wiki_page = reddit.subreddit(SUBREDDIT).wiki["verification_log"]
        updated_content = f"{wiki_page.content_md}\n{entry}"

        wiki_page.edit(content=updated_content,
                       reason=f'Updating the verification log with a new request from {author_string}')

        comment_reply(comment, COMMENT_VERIFICATION_RESPONSE.format(thanks_phrase, author_name) + BOT_DISCLAIMER)

        _discord_alert.send_discord_alert(
            f'New Verification Request for **{language_name}**',
            f"Please check [this verification request](https://www.reddit.com{comment.permalink}) "
            f"from [{author_string}](https://www.reddit.com/user/{author_name}).",
            'verification'
        )
        logger.info(f'[ZW] Updated the verification log with a new request from {author_string}.')


VERIFIED_POST_ID = get_verified_thread()


if __name__ == "__main__":
    print(get_verified_thread())
