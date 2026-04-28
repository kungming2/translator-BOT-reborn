#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
This handles the !nuke command, which bans a username and removes
all their posts and comments. It can only be called by a mod.
...

Logger tag: [ZW:NUKE]
"""

import logging
from collections.abc import Generator

from praw.models import Comment, Submission

from config import SETTINGS
from config import logger as _base_logger
from models.ajo import Ajo
from models.instruo import Instruo
from models.komando import Komando
from reddit.connection import REDDIT, create_mod_note, is_mod, remove_content
from reddit.reddit_sender import message_send
from responses import RESPONSE

logger = logging.LoggerAdapter(_base_logger, {"tag": "ZW:NUKE"})


# ─── Internal helpers ─────────────────────────────────────────────────────────


def _remove_items(
    generator: Generator,
    item_type: str,
    subreddit: str,
    nuke_reason: str,
    nuked_person: str,
) -> None:
    """Remove all subreddit items from a generator (submissions or comments)."""
    for item in generator:
        if item.subreddit.display_name.lower() == subreddit:
            remove_content(item, "spam", nuke_reason)
    logger.info(f">> Removed all {item_type} from u/{nuked_person}.")


# ─── Command handler ──────────────────────────────────────────────────────────


def handle(comment: Comment, _instruo: Instruo, _komando: Komando, _ajo: Ajo) -> None:
    """
    Command handler called by ziwen_commands().

    Fetches a moderator's command comment to 'nuke' a user. This removes all
    comments and posts by the author of the parent item (post or comment)
    that the mod replied to, and bans the user. This extreme action should
    only be used on serial troll accounts.
    """
    logger.info("Nuke handler initiated...")

    mod_caller = comment.author

    if not is_mod(mod_caller):
        logger.info(f"> u/{mod_caller} is not a mod. Ignoring.")
        return

    logger.info(f"> Nuke command called by u/{mod_caller}.")

    parent: Comment | Submission = comment.parent()
    nuked_person = parent.author
    logger.info(f"> User to nuke: u/{nuked_person}.")

    if isinstance(parent, Comment):
        logger.info(f">> Parent comment: {parent.permalink}")
    elif isinstance(parent, Submission):
        logger.info(f">> Parent submission: {parent.permalink}")

    nuke_reason = f"Mod u/{mod_caller} nuked this user."
    subreddit = SETTINGS["subreddit"]

    REDDIT.subreddit(subreddit).banned.add(nuked_person, ban_reason=nuke_reason)
    logger.info(f">> Banned u/{nuked_person}.")

    _remove_items(
        nuked_person.submissions.new(limit=None),
        "submissions",
        subreddit,
        nuke_reason,
        nuked_person,
    )
    _remove_items(
        nuked_person.comments.new(limit=None),
        "comments",
        subreddit,
        nuke_reason,
        nuked_person,
    )

    logger.info(f">> Completely nuked u/{nuked_person}.")

    # This is a mod-only command so no testing-mode wrapper is needed.
    message_send(
        mod_caller,
        subject=RESPONSE.MSG_NUKE_SUCCESS_SUBJECT.format(username=nuked_person),
        body=RESPONSE.MSG_NUKE_SUCCESS.format(
            username=nuked_person,
            permalink=comment.permalink,
        ),
    )
    logger.info(f">> Notified mod u/{mod_caller} via messages.")

    command_note = f"Mod u/{mod_caller} nuked u/{nuked_person}."
    create_mod_note("PERMA_BAN", nuked_person.name, command_note)
