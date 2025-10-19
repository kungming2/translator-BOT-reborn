#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
Handles points calculations for contributors to the subreddit.
"""

import datetime
import re
import time
from urllib.parse import urlparse

import prawcore
from praw.exceptions import RedditAPIException
from praw.models import Comment

from config import SETTINGS, logger
from connection import REDDIT_HELPER, USERNAME
from database import db
from languages import converter
from models.ajo import ajo_loader, ajo_writer
from models.instruo import Instruo
from models.komando import extract_commands_from_text
from responses import RESPONSE
from time_handling import get_current_month
from wiki import fetch_wiki_statistics_page


def points_retriever(username: str) -> str:
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
        "SELECT * FROM total_points WHERE username = ? AND month_year = ?",
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
            "SELECT * FROM total_points WHERE username = ? AND month_year = ?",
            (username, month),
        )
        month_data = cursor.fetchall()
        points = sum(row[3] for row in month_data)
        posts = len({row[4] for row in month_data})
        to_post += f"\n| {month} | {points} | {posts} |"

    # Summary row
    to_post += f"\n| *Total* | {all_points} | {total_post_count} |"
    return to_post


def points_worth_determiner(lingvo_object) -> int:
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
    month_string = datetime.datetime.fromtimestamp(time.time()).strftime("%Y-%m")
    cursor = db.cursor_cache
    cursor.execute(
        "SELECT language_multiplier FROM multiplier_cache WHERE month_year = ? AND language_code = ?",
        (month_string, language_code),
    )
    row = cursor.fetchone()
    if row:
        logger.info(
            f"[ZW] Points determiner: Found cached multiplier for {language_code}: {row[0]}"
        )
        return int(row[0])

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
        logger.debug(
            f"[ZW] Points determiner: Fallback for `{language_code}` due to error: {e}"
        )
        final_point_value = 20  # Max score for unknown/rare/missing wiki entries

    # Cache the result
    current_zeit = time.time()
    month_string = datetime.datetime.fromtimestamp(current_zeit).strftime("%Y-%m")
    insert_data = (month_string, language_code, final_point_value)
    db.cursor_cache.execute(
        "INSERT INTO multiplier_cache VALUES (?, ?, ?)", insert_data
    )
    db.conn_cache.commit()

    logger.debug(
        f"[ZW] Points determiner: Multiplier for {language_code} is {final_point_value}"
    )

    return final_point_value


def _update_points_status(status_list, username, points):
    """
    Adds or updates a user's points total in the list.
    """
    for entry in status_list:
        if entry[0] == username:
            entry[1] += points
            return
    status_list.append([username, points])


def points_tabulator(comment, original_post, original_post_lingvo):
    """
    Tabulates points for a Reddit comment based on detected translation
    actions and commands.

    :param comment: The PRAW comment object for which we are assessing points.
    :param original_post: The post on which the comment was originally posted.
    :param original_post_lingvo: The Lingvo associated with the original post.
                                 Note that this is a single object; since
                                 points are allocated depending on a language.
    """
    cursor_main = db.cursor_main
    conn_main = db.conn_main

    current_time = time.time()
    month_string = datetime.datetime.fromtimestamp(current_time).strftime("%Y-%m")

    instruo = Instruo.from_comment(comment, original_post_lingvo)
    op_author = original_post.author.name
    comment_author = instruo.author_comment  # String, not a PRAW object.

    if not comment_author or comment_author.lower() in (
        "automoderator",
        USERNAME.lower(),
    ):
        # Ignore bot comments.
        logger.info(f"[ZW] Ignoring bot or missing author for comment `{comment.id}`")
        return

    body = comment.body.strip().lower()

    if (
        comment_author == op_author
        and any(k in body for k in SETTINGS["thanks_keywords"])
        and len(body) < 20
    ):
        logger.info(f"[ZW] Skipping short OP thank-you comment `{comment.id}`")
        return  # Short thank-you from the OP, not meaningful

    # Determine worth of the translation based on language
    logger.info(
        f"[ZW] Processing comment by u/{comment_author} on post by u/{op_author} ({original_post_lingvo.name})"
    )
    language_name = original_post_lingvo.name
    try:
        multiplier = points_worth_determiner(original_post_lingvo)
    except ValueError:
        # It's a language not marked on the wiki.
        multiplier = 20

    logger.debug(f"[ZW] Points tabulator: {language_name}, multiplier: {multiplier}")

    commands = extract_commands_from_text(body)  # Returns a List[Komando]
    translator_to_add = None
    points_status = []
    comment_id = instruo.id_comment

    points = 0
    final_translator = None
    final_translator_points = 0

    def get_parent_author(checked_comment):
        """
        Given a PRAW comment object, returns the author's name and
        ID of the parent comment (if applicable).

        Returns:
            (author_name, parent_id) if the parent is a comment,
            (None, None) if parent is deleted or a submission.
        """
        try:
            parent = checked_comment.parent()
            if isinstance(parent, Comment) and parent.author:
                return parent.author.name, parent.id
        except Exception as e:
            logger.warning(f"Failed to get parent author: {e}")
        return None, None

    # Iterating over the Komando objects.
    for cmd in commands:
        name = cmd.name  # We only need the name of the command.

        if name in {"translated", "doublecheck"}:
            if instruo.author_comment != op_author:
                if (
                    len(body) < 60
                    and name == "translated"
                    and any(k in body for k in SETTINGS["verifying_keywords"])
                ):
                    # Likely a verification for another translation.
                    parent_author, parent_comment = get_parent_author(comment)
                    if parent_author:
                        final_translator = parent_author
                        final_translator_points += 1 + multiplier
                        points += 1
                        logger.debug(
                            f"[ZW] Verify: u/{comment_author} confirms u/{final_translator} in {parent_comment}"
                        )
                else:
                    translator_to_add = comment_author
                    points += 1 + multiplier
                    logger.debug(f"[ZW] Translation: Detected by u/{comment_author}")
            elif comment.author and comment.author.name == op_author and len(body) > 13:
                # OP is marking a translation but is giving more explanation
                parent_author, parent_comment = get_parent_author(comment)
                if parent_author and parent_author != op_author:
                    final_translator = parent_author
                    final_translator_points += 1 + multiplier
                    logger.debug(
                        f"[ZW] OP delegated !translated to u/{final_translator}"
                    )
            elif len(body) < 13:
                # Very short cleanup !translated post
                parent_author, parent_comment = get_parent_author(comment)
                if parent_author:
                    final_translator = parent_author
                    if final_translator != comment_author:
                        points += 1
                    final_translator_points += 1 + multiplier
                    logger.debug(
                        f"[ZW] Cleanup mark: u/{comment_author} marked u/{final_translator}'s work."
                    )
        elif name == "identify":
            points += 3
        elif name in {"claim", "page", "search", "missing"}:
            points += 1
        elif name == "cjk_lookup":
            points += 2
        elif name == "wikipedia_lookup":
            points += 1
        else:
            logger.debug(f"[Points] No point value set for command: {name}")
    logger.info(
        f"[ZW] Commands processed for comment {comment.id}: {len(commands)} commands, "
        f"total preliminary points {points}"
    )

    if len(body) > 120 and comment_author != op_author:
        # Long-form comments (not from OP)
        points += 1 + int(round(0.25 * multiplier))

    # OP short thank-you cases.
    if (
        comment_author == op_author
        and any(k in body for k in SETTINGS["thanks_keywords"])
        and len(body) < 20
    ):
        logger.debug(f"[ZW] OP short thank-you from u/{comment_author}")
        parent_author, parent_comment = get_parent_author(comment)
        if parent_author:
            final_translator = parent_author
            final_translator_points += 1 + multiplier
            cursor_main.execute(
                "SELECT points, post_id FROM total_points WHERE username = ? AND post_id = ?",
                (final_translator, original_post.id),
            )
            for rec_points, rec_post_id in cursor_main.fetchall():
                if (
                    int(rec_points) == final_translator_points
                    and rec_post_id == original_post.id
                ):
                    final_translator_points = 0

    # Points assignment
    _update_points_status(points_status, comment_author, points)

    if final_translator_points:
        _update_points_status(points_status, final_translator, final_translator_points)
        translator_to_add = translator_to_add or final_translator

    # Filter out any 0-point entries
    results = [entry for entry in points_status if entry[1] != 0]

    # Record translator to Ajo
    if translator_to_add:
        ajo_w_points = ajo_loader(original_post.id)
        if ajo_w_points:
            ajo_w_points.add_translators(translator_to_add)
            ajo_writer(ajo_w_points)

    # Write to DB
    logger.info(
        f"[ZW] Writing {len(results)} point record(s) to DB for comment `{comment.id}`"
    )
    for username, user_points in results:
        logger.debug(f"[ZW] Writing: ({username}, {user_points})")
        cursor_main.execute(
            "INSERT INTO total_points VALUES (?, ?, ?, ?, ?)",
            (month_string, comment_id, username, str(user_points), original_post.id),
        )
    conn_main.commit()
    logger.info(f"[ZW] Points tabulation complete for comment `{comment.id}`")

    return


if __name__ == "__main__":
    while True:
        my_search = input("Search query: ")
        print(points_worth_determiner(converter(my_search)))
