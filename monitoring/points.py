#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
Handles points calculations for contributors to the subreddit.

This module manages the entire points system for r/translator:
- Calculates point values based on language rarity (using wiki statistics)
- Tracks user contributions and awards points for various actions:
  * Translations and verifications (base + language multiplier)
  * Language identifications (3 points)
  * Helper commands like !claim, !page (1-2 points)
  * Long-form helpful comments (bonus points)
- Maintains monthly and all-time point records in the database
- Provides point summaries for users upon request

Point values are cached monthly and range from 4-20 depending on language
frequency. Rarer languages receive higher multipliers to encourage diverse
language support.
...

Logger tag: [POINTS]
"""

import logging
import re
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

import prawcore
from praw.exceptions import RedditAPIException
from praw.models import Comment

from config import SETTINGS
from config import logger as _base_logger
from database import db
from lang.languages import converter
from models.ajo import ajo_loader, ajo_writer
from models.instruo import Instruo
from models.komando import extract_commands_from_text
from reddit.connection import REDDIT_HELPER, USERNAME, create_mod_note
from reddit.wiki import fetch_wiki_statistics_page
from responses import RESPONSE
from time_handling import get_current_month

if TYPE_CHECKING:
    from praw.models import Submission

    from models.ajo import Ajo
    from models.lingvo import Lingvo

logger = logging.LoggerAdapter(_base_logger, {"tag": "POINTS"})


def points_user_retriever(username: str) -> str:
    """
    Fetches the total number of points earned by a user in the current month.
    Used with the messages routine to inform users of their point totals.

    :param username: The Reddit username as a string.
    :return: A string summarizing the user's point activity on r/translator.
    """
    current_month = get_current_month()

    cursor = db.cursor_main

    # Get current month's points
    cursor.execute(
        "SELECT * FROM total_points WHERE username = ? AND year_month = ?",
        (username, current_month),
    )
    month_rows = cursor.fetchall()

    # Get all historical points
    cursor.execute("SELECT * FROM total_points WHERE username = ?", (username,))
    all_rows = cursor.fetchall()

    if not all_rows:
        return RESPONSE.MSG_NO_POINTS  # User has no points listed.

    # Monthly points
    month_points = sum(row[3] for row in month_rows)

    # Total points and participation
    all_points = sum(row[3] for row in all_rows)
    unique_post_ids = {row[4] for row in all_rows}
    total_post_count = len(unique_post_ids)

    # Unique recorded months
    recorded_months = sorted({row[0] for row in all_rows})

    # Prepare message
    to_post = (
        f"You've earned **{month_points:,} points** on r/translator this month.\n\n"
        f"You've earned **{all_points:,} points** in total and participated in **{total_post_count:,} posts**.\n\n"
        "| Year/Month | Points | Number of Posts Participated |\n"
        "|------------|--------|------------------------------|"
    )

    for month in recorded_months:
        cursor.execute(
            "SELECT * FROM total_points WHERE username = ? AND year_month = ?",
            (username, month),
        )
        month_data = cursor.fetchall()
        points = sum(row[3] for row in month_data)
        posts = len({row[4] for row in month_data})
        to_post += f"\n| {month} | {points} | {posts} |"

    # Summary row
    to_post += f"\n| *Total* | {all_points} | {total_post_count} |"
    return to_post


def points_post_retriever(post_id: str) -> list[tuple[str, str, int]] | None:
    """
    Fetches all point awards associated with a specific post ID.

    :param post_id: The Reddit post ID to look up.
    :return: List of tuples (comment_id, username, points) or None if no records found.
    """
    cursor = db.cursor_main
    cursor.execute(
        "SELECT comment_id, username, points FROM total_points WHERE post_id = ?",
        (post_id,),
    )
    rows = cursor.fetchall()

    if not rows:
        return None

    # Convert rows to list of tuples for easier handling
    results = []
    for row in rows:
        comment_id = row[0] if isinstance(row, tuple) else row["comment_id"]
        username = row[1] if isinstance(row, tuple) else row["username"]
        points = row[2] if isinstance(row, tuple) else row["points"]
        results.append((comment_id, username, int(points)))
    logger.debug(f"Post points records - {len(results)} record(s) for post {post_id!r}")

    return results


def points_worth_determiner(lingvo_object: "Lingvo") -> int:
    """
    Determines the point value for translating a given language.
    This tops out at a max value of 20.

    :param lingvo_object: A Lingvo object to look up.
    :return: Integer value representing the points worth.
    """
    language_code = lingvo_object.preferred_code.lower()

    if language_code == "unknown":
        return 4  # Normalized value for unknown languages

    # Check cache first
    month_string = get_current_month()
    cursor = db.cursor_cache
    cursor.execute(
        "SELECT language_multiplier FROM multiplier_cache WHERE month_year = ? AND language_code = ?",
        (month_string, language_code),
    )
    row = cursor.fetchone()
    if row:
        logger.info(f"Found cached multiplier for `{language_code}`: {row[0]}")
        return int(row[0])

    logger.debug(f"No cached multiplier for {language_code!r}, fetching from wiki.")
    try:
        # Attempt to get the statistics wiki page URL
        page_url = fetch_wiki_statistics_page(lingvo_object)

        if page_url is None:
            raise ValueError("No wiki statistics page found.")

        # Extract the wiki page name from the URL
        parsed = urlparse(page_url)
        match = re.search(r"/wiki/([^/]+)$", parsed.path)
        if not match:
            raise ValueError("Could not extract wiki page name from URL.")

        wiki_page_name = match.group(1)
        overall_page = REDDIT_HELPER.subreddit(SETTINGS["subreddit"]).wiki[
            wiki_page_name
        ]
        overall_page_content = overall_page.content_md.strip()
        last_month_data = overall_page_content.split("\n")[-1]

        # Parse the percentage (e.g., "2017 | 08 | [Link] | 1%")
        total_percent = float(last_month_data.split(" | ")[3].rstrip("%"))

        # Calculate multiplier: (1 / percent) * 35
        raw_point_value = 35 * (1 / total_percent)
        final_point_value = int(round(raw_point_value))
        final_point_value = min(final_point_value, 20)

    except (
        prawcore.exceptions.NotFound,
        RedditAPIException,
        ValueError,
        IndexError,
        ZeroDivisionError,
    ) as e:
        logger.debug(f"Fallback for `{language_code}` due to error: {e}")
        final_point_value = 20  # Max score for unknown/rare/missing wiki entries

    # Cache the result
    insert_data = (month_string, language_code, final_point_value)
    db.cursor_cache.execute(
        "INSERT INTO multiplier_cache VALUES (?, ?, ?)", insert_data
    )
    db.conn_cache.commit()

    logger.debug(f"Multiplier for {language_code} is {final_point_value}")

    return final_point_value


def _credit_parent_as_translator(
    comment_author: str,
    parent_author: str,
    multiplier: int,
    points_status: list,
    translators_to_record: list,
    original_post: "Submission",
    original_post_lingvo: "Lingvo",
    commenter_label: str,
    commenter_note: str,
    log_message: str,
) -> int:
    """
    Credits the parent comment author as the translator and the commenter
    as the marker/verifier. Returns the points to add to the commenter's tally.
    """
    if parent_author not in translators_to_record:
        translators_to_record.append(parent_author)
    _update_points_status(points_status, parent_author, 1 + multiplier)

    logger.info(log_message)

    create_mod_note(
        label="SOLID_CONTRIBUTOR",
        username=parent_author,
        included_note=(
            f"Helped translate https://redd.it/{original_post.id} "
            f"({original_post_lingvo.name})"
        ),
    )
    create_mod_note(
        label=commenter_label,
        username=comment_author,
        included_note=commenter_note,
    )
    return 1  # Points for the commenter


def _update_points_status(
    status_list: list[list[Any]], username: str, points: int
) -> None:
    """
    Adds or updates a user's points total in the list.
    """
    for entry in status_list:
        if entry[0] == username:
            entry[1] += points
            return
    status_list.append([username, points])


def points_tabulator(
    comment: Comment,
    original_post: "Submission",
    original_post_lingvo: "Lingvo",
    ajo: "Ajo | None" = None,
) -> None:
    """
    Tabulates points for a Reddit comment based on detected translation
    actions and commands.

    :param comment: The PRAW comment object for which we are assessing points.
    :param original_post: The post on which the comment was originally posted.
    :param original_post_lingvo: The Lingvo associated with the original post.
    :param ajo: Optional Ajo object for the post. If not provided, will be loaded.
    """
    # Early return if lingvo is None
    if original_post_lingvo is None:
        logger.warning(f"Skipping comment `{comment.id}` - no Lingvo object provided")
        return

    cursor_main = db.cursor_main
    conn_main = db.conn_main

    month_string = get_current_month()

    instruo = Instruo.from_comment(comment, original_post_lingvo)
    if original_post and original_post.author:
        op_author = original_post.author.name
    else:
        op_author = "[deleted]"
    comment_author = instruo.author_comment

    if not comment_author or comment_author.lower() in (
        "automoderator",
        USERNAME.lower(),
    ):
        logger.debug(f"Ignoring bot or missing author for comment `{comment.id}`")
        return

    body = comment.body.strip().lower()

    # Load Ajo if not provided
    if ajo is None:
        ajo = ajo_loader(original_post.id)
        if ajo is None:
            logger.warning(f"Could not load Ajo for post `{original_post.id}`")
            # Continue without Ajo - we can still award points

    # Determine worth of the translation based on language
    logger.info(
        f"Processing comment by u/{comment_author} on post by u/{op_author} ({original_post_lingvo.name})"
    )
    language_name = original_post_lingvo.name
    try:
        multiplier = points_worth_determiner(original_post_lingvo)
    except ValueError:
        multiplier = 20

    logger.debug(f"{language_name}, multiplier: {multiplier}")

    commands = extract_commands_from_text(body)
    points_status: list[list] = []
    comment_id = instruo.id_comment

    points = 0
    translators_to_record: list[str] = []

    def get_parent_author(checked_comment: Comment) -> tuple[str | None, str | None]:
        try:
            parent = checked_comment.parent()
            if isinstance(parent, Comment) and parent.author:
                return parent.author.name, parent.id
        except Exception as e:
            logger.warning(f"Failed to get parent author: {e}")
        return None, None

    # Iterating over the Komando objects
    for cmd in commands:
        name = cmd.name

        if name in {"translated", "doublecheck"}:
            if instruo.author_comment != op_author:
                if (
                    len(body) < 60
                    and name == "translated"
                    and any(k in body for k in SETTINGS["verifying_keywords"])
                ):
                    # Verification case: crediting parent comment author
                    parent_author, parent_comment = get_parent_author(comment)
                    if parent_author:
                        points += _credit_parent_as_translator(
                            comment_author=comment_author,
                            parent_author=parent_author,
                            multiplier=multiplier,
                            points_status=points_status,
                            translators_to_record=translators_to_record,
                            original_post=original_post,
                            original_post_lingvo=original_post_lingvo,
                            commenter_label="HELPFUL_USER",
                            commenter_note=(
                                f"Verified translation on https://redd.it/{original_post.id} "
                                f"({original_post_lingvo.name})"
                            ),
                            log_message=(
                                f"Verify: u/{comment_author} confirms "
                                f"u/{parent_author} in {parent_comment}"
                            ),
                        )
                elif body.strip() == "!translated":
                    # Bare !translated as a reply: credit the parent comment author as translator
                    parent_author, parent_comment = get_parent_author(comment)
                    if parent_author and parent_author != comment_author:
                        points += _credit_parent_as_translator(
                            comment_author=comment_author,
                            parent_author=parent_author,
                            multiplier=multiplier,
                            points_status=points_status,
                            translators_to_record=translators_to_record,
                            original_post=original_post,
                            original_post_lingvo=original_post_lingvo,
                            commenter_label="HELPFUL_USER",
                            commenter_note=(
                                f"Marked translation as complete on https://redd.it/{original_post.id} "
                                f"({original_post_lingvo.name})"
                            ),
                            log_message=(
                                f"Bare !translated: u/{comment_author} credited "
                                f"u/{parent_author} in {parent_comment}"
                            ),
                        )
                    else:
                        # Parent author is same as commenter or not found — credit commenter
                        points += 1 + multiplier
                        if comment_author not in translators_to_record:
                            translators_to_record.append(comment_author)
                        logger.info(
                            f"Bare !translated (no distinct parent): credit u/{comment_author}"
                        )

                        translator_note = (
                            f"Helped translate https://redd.it/{original_post.id} "
                            f"({original_post_lingvo.name})"
                        )
                        create_mod_note(
                            label="SOLID_CONTRIBUTOR",
                            username=comment_author,
                            included_note=translator_note,
                        )
                else:
                    # Direct translation case: this user is the translator
                    points += 1 + multiplier
                    if comment_author not in translators_to_record:
                        translators_to_record.append(comment_author)
                    logger.info(f"Translation: Detected by u/{comment_author}")

                    # Create mod note for translator
                    translator_note = (
                        f"Helped translate https://redd.it/{original_post.id} "
                        f"({original_post_lingvo.name})"
                    )
                    create_mod_note(
                        label="SOLID_CONTRIBUTOR",
                        username=comment_author,
                        included_note=translator_note,
                    )

            elif comment.author and comment.author.name == op_author and len(body) > 13:
                # OP is marking a translation with explanation
                parent_author, parent_comment = get_parent_author(comment)
                if parent_author and parent_author != op_author:
                    if parent_author not in translators_to_record:
                        translators_to_record.append(parent_author)
                    _update_points_status(points_status, parent_author, 1 + multiplier)
                    logger.info(f"OP delegated !translated to u/{parent_author}")

                    # Create mod note for translator credited by OP
                    translator_note = (
                        f"Helped translate https://redd.it/{original_post.id} "
                        f"({original_post_lingvo.name})"
                    )
                    create_mod_note(
                        label="SOLID_CONTRIBUTOR",
                        username=parent_author,
                        included_note=translator_note,
                    )

            elif len(body) < 13:
                # Very short cleanup !translated post
                parent_author, parent_comment = get_parent_author(comment)
                if parent_author:
                    if parent_author not in translators_to_record:
                        translators_to_record.append(parent_author)

                    if parent_author != comment_author and comment_author != op_author:
                        points += 1
                        # Credit the person who helped mark the translation
                        helper_note = (
                            f"Marked translation as complete on https://redd.it/{original_post.id} "
                            f"({original_post_lingvo.name})"
                        )
                        create_mod_note(
                            label="HELPFUL_USER",
                            username=comment_author,
                            included_note=helper_note,
                        )

                    _update_points_status(points_status, parent_author, 1 + multiplier)
                    logger.info(
                        f"Cleanup mark: u/{comment_author} marked u/{parent_author}'s work."
                    )

                    # Create mod note for the translator being credited
                    translator_note = (
                        f"Helped translate https://redd.it/{original_post.id} "
                        f"({original_post_lingvo.name})"
                    )
                    create_mod_note(
                        label="SOLID_CONTRIBUTOR",
                        username=parent_author,
                        included_note=translator_note,
                    )
        elif name not in {
            cmd.lstrip("!").rstrip(":") for cmd in SETTINGS["commands_no_args"]
        }:
            default = 1
            # Special cases (identify, lookup_cjk) are in settings.yaml;
            # all others default to 1
            points += SETTINGS["command_points"].get(name, default)
        else:
            logger.debug(f"[Points] No point value for no-arg command: {name}")

    logger.info(
        f"Commands processed for comment `{comment.id}`: {len(commands)} commands, "
        f"total preliminary points {points}"
    )

    if len(body) > 120 and comment_author != op_author:
        points += 1 + int(round(0.25 * multiplier))

    # OP short thank-you cases
    if (
        comment_author == op_author
        and any(k in body for k in SETTINGS["thanks_keywords"])
        and len(body) < 20
    ):
        logger.info(f"OP short thank-you from u/{comment_author}")
        parent_author, parent_comment = get_parent_author(comment)
        if parent_author:
            if parent_author not in translators_to_record:
                translators_to_record.append(parent_author)

            # Check if we already awarded points to avoid double-crediting
            cursor_main.execute(
                "SELECT points, post_id FROM total_points WHERE username = ? AND post_id = ?",
                (parent_author, original_post.id),
            )
            already_credited = False
            for rec_points, rec_post_id in cursor_main.fetchall():
                if (
                    int(rec_points) == (1 + multiplier)
                    and rec_post_id == original_post.id
                ):
                    already_credited = True
                    break

            if not already_credited:
                _update_points_status(points_status, parent_author, 1 + multiplier)

            # Create mod note for translator credited by OP thank-you
            translator_note = (
                f"Helped translate https://redd.it/{original_post.id} "
                f"({original_post_lingvo.name})"
            )
            create_mod_note(
                label="SOLID_CONTRIBUTOR",
                username=parent_author,
                included_note=translator_note,
            )

    # Final points assignment for comment author
    _update_points_status(points_status, comment_author, points)

    # Filter out any 0-point entries
    results = [entry for entry in points_status if entry[1] != 0]

    # Record ALL translators to Ajo - FIX: Record multiple translators
    if translators_to_record and ajo:
        for translator in translators_to_record:
            ajo.add_translators(translator)
            logger.info(
                f"Added u/{translator} to Ajo translators for `{original_post.id}`"
            )

        # Write updated Ajo once after adding all translators
        ajo_writer(ajo)
        logger.info(
            f"Recorded {len(translators_to_record)} translator(s) to Ajo: {', '.join(translators_to_record)}"
        )

    # Write to DB
    logger.info(
        f"Writing {len(results)} point record(s) to DB for comment `{comment.id}`"
    )
    for username, user_points in results:
        logger.debug(f"Writing: ({username} with {user_points} points)")
        cursor_main.execute(
            "INSERT INTO total_points VALUES (?, ?, ?, ?, ?)",
            (month_string, comment_id, username, str(user_points), original_post.id),
        )
    conn_main.commit()
    logger.info(f"Points tabulation complete for comment `{comment.id}`")

    return


def show_menu():
    print("\nSelect a test to run:")
    print("1. Points worth determiner (enter a language to get its point value)")
    print("2. Points user retriever (enter a username to get their point totals)")
    print("3. Points post retriever (enter a post ID to get its point records)")
    print("x. Exit")


if __name__ == "__main__":
    while True:
        show_menu()
        choice = input("Enter your choice (1-3 or x): ")

        if choice == "x":
            print("Exiting...")
            break

        if choice not in ["1", "2", "3"]:
            print("Invalid choice, please try again.")
            continue

        if choice == "1":
            my_search = input("Enter a language name or code: ")
            my_lingvo = converter(my_search)
            if my_lingvo:
                my_points_result = points_worth_determiner(my_lingvo)
                print(
                    f"Language: {my_lingvo.name} ({my_lingvo.preferred_code}) → Points worth: {my_points_result}"
                )
            else:
                print(f"Could not find a language matching: {my_search}")

        elif choice == "2":
            my_username = input("Enter a Reddit username: ")
            my_user_result = points_user_retriever(my_username)
            print(my_user_result)

        elif choice == "3":
            my_post_id = input("Enter a Reddit post ID: ")
            my_post_result = points_post_retriever(my_post_id)
            if my_post_result:
                print(f"Point records for post {my_post_id}:")
                for my_comment_id, my_username, my_points in my_post_result:
                    print(
                        f"  Comment {my_comment_id} | u/{my_username} | {my_points} points"
                    )
            else:
                print(f"No point records found for post ID: {my_post_id}")
