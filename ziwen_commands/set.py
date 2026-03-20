#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
!set is a mod-accessible means of setting the post flair. The mod's
comment is removed by AutoModerator so it looks like nothing happened.

In addition to language-setting, mods can use !set to reclassify an
Ajo-tracked post as a Diskuto (internal/non-request post), e.g.:
    !set:meta
    !set:community

This migration is irreversible: the Ajo record is deleted and a new
Diskuto record is written to internal_posts.
...

Logger tag: [ZW:SET]
"""

import logging

from praw.models import Comment

from config import SETTINGS
from config import logger as _base_logger
from models.ajo import Ajo, ajo_delete
from models.diskuto import Diskuto, diskuto_writer
from models.instruo import Instruo
from models.komando import Komando
from models.kunulo import Kunulo
from reddit.connection import is_mod
from reddit.reddit_sender import message_send
from responses import RESPONSE

from . import update_language

logger = logging.LoggerAdapter(_base_logger, {"tag": "ZW:SET"})


def _handle_diskuto_reclassification(
    comment: Comment, ajo: Ajo, post_type: str
) -> "Diskuto | None":
    """
    Reclassify an Ajo-tracked post as a Diskuto internal post.

    Steps:
    1. Build a Diskuto from the submission, overriding post_type with the
       value the mod supplied (e.g. 'meta') rather than relying on the title tag.
    2. Write the Diskuto to internal_posts (main.db).
    3. Permanently delete the Ajo record from ajo_database (ajo.db).
    4. Message the mod confirming the migration.

    :param comment: The PRAW comment that triggered the command.
    :param ajo: The Ajo object for the post being reclassified.
    :param post_type: Lowercase diskuto type string, e.g. 'meta' or 'community'.
    """
    submission = ajo.submission
    post_id = ajo.id

    # Build Diskuto from the submission, then override post_type with the
    # mod-supplied value so it's always accurate regardless of title format.
    try:
        diskuto_obj = Diskuto.process_post(submission)
    except TypeError as e:
        logger.error(f"Failed to build Diskuto from submission `{post_id}`: {e}")
        message_send(
            comment.author,
            subject="!set reclassification failed",
            body=(
                f"Hello, moderator u/{comment.author},\n\n"
                f"Could not reclassify post `{post_id}` as a Diskuto — "
                f"the submission object was unavailable or invalid.\n\n"
                f"No changes were made."
            ),
        )
        return None

    diskuto_obj.post_type = post_type

    # Write to internal_posts first; only delete the Ajo if that succeeds.
    try:
        diskuto_writer(diskuto_obj)
    except Exception as e:
        logger.error(f"diskuto_writer failed for `{post_id}`: {type(e).__name__}: {e}")
        message_send(
            comment.author,
            subject="!set reclassification failed",
            body=(
                f"Hello, moderator u/{comment.author},\n\n"
                f"Could not write post `{post_id}` to the internal posts database. "
                f"No changes were made to the Ajo record."
            ),
        )
        return None

    # Diskuto is safely stored — now remove the Ajo record.
    if post_id is not None:
        ajo_delete(post_id)

    logger.info(
        f"Post `{post_id}` reclassified from Ajo to Diskuto "
        f"(type='{post_type}') by moderator u/{comment.author}."
    )

    message_send(
        comment.author,
        subject="!set reclassification successful",
        body=(
            f"Hello, moderator u/{comment.author},\n\n"
            f"The [post](https://www.reddit.com{submission.permalink}) has been "
            f"reclassified as a **{post_type}** internal post.\n\n"
            f"It has been removed from the translation request database and added "
            f"to the internal posts database. This change is permanent."
        ),
    )
    logger.info(f"Sent reclassification confirmation to u/{comment.author}.")

    return diskuto_obj


def handle(comment: Comment, _instruo: Instruo, komando: Komando, ajo: Ajo) -> None:
    """Command handler called by ziwen_commands()."""
    logger.info("Set handler initiated.")

    # Check to see if the person calling this command is a moderator
    if not is_mod(comment.author):
        logger.debug(f"u/{comment.author} is not a mod. Skipping...")
        return

    logger.info(f"!set, from moderator u/{comment.author} on `{ajo.id}`.")

    # Check whether this is a diskuto reclassification command (e.g. !set:meta).
    #
    # Convention: when the upstream parser cannot resolve the keyword as a
    # language it stores the raw lowercase string in komando.data as a plain
    # string rather than a list of Lingvo objects. We detect that here.
    raw_keyword: str | None = None
    if isinstance(komando.data, str):
        raw_keyword = komando.data.strip().lower()
    elif (
        isinstance(komando.data, list)
        and len(komando.data) == 1
        and isinstance(komando.data[0], str)
    ):
        raw_keyword = komando.data[0].strip().lower()

    if raw_keyword in SETTINGS["internal_post_types"]:
        logger.info(f"!set:{raw_keyword} — reclassifying `{ajo.id}` as Diskuto.")
        assert raw_keyword is not None
        diskuto_result = _handle_diskuto_reclassification(
            comment, ajo, post_type=raw_keyword
        )
        if diskuto_result:
            diskuto_result.update_reddit()

        return

    # --- Standard language-setting path below ---

    # Invalid identification data.
    if not komando.data or None in komando.data:
        logger.error(f"Invalid or missing Komando data: {komando.data}")
        message_send(
            comment.author,
            "Invalid !set language",
            RESPONSE.COMMENT_LANGUAGE_NO_RESULTS.format(id_comment_body=comment.body),
        )
        logger.info("Replied letting the mod know setting is invalid.")
        return

    # Update the Ajo's language(s) post.
    try:
        update_language(ajo, komando)
    except ValueError as e:
        logger.error(f"!set data is invalid: {e}")
        message_send(
            comment.author,
            "Invalid !set language",
            RESPONSE.COMMENT_LANGUAGE_NO_RESULTS.format(id_comment_body=comment.body),
        )
        logger.info("Replied letting the mod know setting is invalid.")
        return

    # Delete any pre-existing defined multiple or "Unknown" comment.
    delete_tags: list[str] = ["comment_defined_multiple", "comment_unknown"]
    kunulo_object: Kunulo = Kunulo.from_submission(ajo.submission)
    for tag in delete_tags:
        kunulo_object.delete(tag)

    # Message the mod who called this command.
    languages = komando.data  # List of Lingvo objects
    logger.info(f"Building !set success message for {len(languages)} language(s).")

    set_msg: str
    if len(languages) == 1:
        new_language = languages[0]
        set_msg = (
            f"{new_language.greetings}, moderator u/{comment.author},\n\n"
            f"The [post](https://www.reddit.com{ajo.submission.permalink}) has been set to the language "
            f"{new_language.name} (`{new_language.preferred_code}`)."
        )
        logger.info(f"Single-language message built for {new_language.preferred_code}.")
    else:
        # Multiple languages - collate greetings (excluding "Hello")
        greetings = [lang.greetings for lang in languages if lang.greetings != "Hello"]
        greeting_string = " / ".join(greetings) if greetings else "Hello"

        # Build the language list string
        lang_parts = [f"{lang.name} (`{lang.preferred_code}`)" for lang in languages]
        lang_string = ", ".join(lang_parts[:-1]) + f", and {lang_parts[-1]}"

        set_msg = (
            f"{greeting_string}, moderator u/{comment.author},\n\n"
            f"The [post](https://www.reddit.com{ajo.submission.permalink}) has been set to the languages "
            f"{lang_string}."
        )
        logger.info("Multi-language message built.")

    logger.info(f"Sending !set success message to u/{comment.author}.")
    try:
        message_send(
            comment.author,
            subject="!set command successful",
            body=set_msg,
        )
        logger.info(
            f"Successfully informed moderator u/{comment.author} of command success."
        )
    except Exception as e:
        logger.error(
            f"Failed to send message to u/{comment.author}: {type(e).__name__}: {e}"
        )
