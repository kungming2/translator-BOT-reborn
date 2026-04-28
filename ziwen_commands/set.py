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


# ─── Internal helpers ─────────────────────────────────────────────────────────


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

    try:
        diskuto_obj = Diskuto.process_post(submission)
    except TypeError as e:
        logger.error(f"Failed to build Diskuto from submission `{post_id}`: {e}")
        message_send(
            comment.author,
            subject=RESPONSE.MSG_SET_RECLASSIFICATION_FAILED_SUBJECT,
            body=RESPONSE.MSG_SET_RECLASSIFICATION_INVALID.format(
                moderator=comment.author,
                post_id=post_id,
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
            subject=RESPONSE.MSG_SET_RECLASSIFICATION_FAILED_SUBJECT,
            body=RESPONSE.MSG_SET_RECLASSIFICATION_WRITE_FAILED.format(
                moderator=comment.author,
                post_id=post_id,
            ),
        )
        return None

    if post_id is not None:
        ajo_delete(post_id)

    logger.info(
        f"Post `{post_id}` reclassified from Ajo to Diskuto "
        f"(type='{post_type}') by moderator u/{comment.author}."
    )

    message_send(
        comment.author,
        subject=RESPONSE.MSG_SET_RECLASSIFICATION_SUCCESS_SUBJECT,
        body=RESPONSE.MSG_SET_RECLASSIFICATION_SUCCESS.format(
            moderator=comment.author,
            permalink=submission.permalink,
            post_type=post_type,
        ),
    )
    logger.info(f"Sent reclassification confirmation to u/{comment.author}.")

    return diskuto_obj


# ─── Command handler ──────────────────────────────────────────────────────────


def handle(comment: Comment, _instruo: Instruo, komando: Komando, ajo: Ajo) -> None:
    """Command handler called by ziwen_commands()."""
    logger.info("Set handler initiated.")

    if not is_mod(comment.author):
        logger.debug(f"u/{comment.author} is not a mod. Skipping...")
        return

    logger.info(f"!set, from moderator u/{comment.author} on `{ajo.id}`.")

    # Detect a Diskuto reclassification command (e.g. !set:meta).
    # When the upstream parser cannot resolve the keyword as a language
    # it stores the raw lowercase string in komando.data as a plain string
    # rather than a list of Lingvo objects.
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

    # Standard language-setting path.

    if not komando.data or None in komando.data:
        logger.error(f"Invalid or missing Komando data: {komando.data}")
        message_send(
            comment.author,
            RESPONSE.MSG_SET_INVALID_LANGUAGE_SUBJECT,
            RESPONSE.COMMENT_LANGUAGE_NO_RESULTS.format(id_comment_body=comment.body),
        )
        logger.info("Replied letting the mod know setting is invalid.")
        return

    try:
        update_language(ajo, komando)
    except ValueError as e:
        logger.error(f"!set data is invalid: {e}")
        message_send(
            comment.author,
            RESPONSE.MSG_SET_INVALID_LANGUAGE_SUBJECT,
            RESPONSE.COMMENT_LANGUAGE_NO_RESULTS.format(id_comment_body=comment.body),
        )
        logger.info("Replied letting the mod know setting is invalid.")
        return

    # Delete any pre-existing defined-multiple or Unknown comment.
    kunulo_object: Kunulo = Kunulo.from_submission(ajo.submission)
    for tag in ["comment_defined_multiple", "comment_unknown"]:
        kunulo_object.delete(tag)

    # Message the mod confirming the language change.
    languages = komando.data
    logger.info(f"Building !set success message for {len(languages)} language(s).")

    set_msg: str
    if len(languages) == 1:
        new_language = languages[0]
        set_msg = RESPONSE.MSG_SET_LANGUAGE_SUCCESS.format(
            greeting=new_language.greetings,
            moderator=comment.author,
            permalink=ajo.submission.permalink,
            language_name=new_language.name,
            language_code=new_language.preferred_code,
        )
        logger.info(f"Single-language message built for {new_language.preferred_code}.")
    else:
        greetings = [lang.greetings for lang in languages if lang.greetings != "Hello"]
        greeting_string = " / ".join(greetings) if greetings else "Hello"

        lang_parts = [f"{lang.name} (`{lang.preferred_code}`)" for lang in languages]
        lang_string = ", ".join(lang_parts[:-1]) + f", and {lang_parts[-1]}"

        set_msg = RESPONSE.MSG_SET_LANGUAGES_SUCCESS.format(
            greeting=greeting_string,
            moderator=comment.author,
            permalink=ajo.submission.permalink,
            languages=lang_string,
        )
        logger.info("Multi-language message built.")

    try:
        message_send(
            comment.author,
            subject=RESPONSE.MSG_SET_SUCCESS_SUBJECT,
            body=set_msg,
        )
        logger.info(
            f"Successfully informed moderator u/{comment.author} of command success."
        )
    except Exception as e:
        logger.error(
            f"Failed to send message to u/{comment.author}: {type(e).__name__}: {e}"
        )
