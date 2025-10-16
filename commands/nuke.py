#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
This handles the !nuke command, which bans a username and removes
all their posts and comments. It can only be called by a mod.
"""

from praw.models import Comment, Submission

from connection import REDDIT, is_mod, logger
from reddit_sender import message_send


def handle(comment, _instruo, _komando, _ajo):
    """
    Fetches a moderator's command comment to 'nuke' a user. This removes all
    comments and posts by the author of the parent item (post or comment)
    that the mod replied to, and bans the user. This extreme action should
    only be used on serial troll accounts.
    """
    logger.info("Nuke handler initiated...")

    mod_caller = comment.author

    # Check to see if the person calling this command is actually a mod.
    if not is_mod(mod_caller):
        logger.info(f"> u/{mod_caller} is not a mod. Ignoring.")
        return

    logger.info(f"> Nuke command called by u/{mod_caller}.")

    # Fetch the person to be nuked by looking at the parent of the comment.
    parent = comment.parent()
    nuked_person = parent.author
    logger.info(f"> User to nuke: u/{nuked_person}.")

    # Log the parent permalink for clarity.
    if isinstance(parent, Comment):
        logger.info(f">> Parent comment: {parent.permalink}")
    elif isinstance(parent, Submission):
        logger.info(f">> Parent submission: {parent.permalink}")

    # Ban the user.
    REDDIT.subreddit("translator").banned.add(
        nuked_person, ban_reason=f"Mod u/{mod_caller} nuked this user."
    )
    logger.info(f">> Banned u/{nuked_person}.")

    # Helper function to remove all items in a generator (posts/comments).
    def remove_items(generator, item_type: str):
        for item in generator:
            if item.subreddit.display_name.lower() == "translator":
                item.mod.remove()
        logger.info(f">> Removed all {item_type} from u/{nuked_person}.")

    # Remove any and all posts or comments on the subreddit.
    remove_items(nuked_person.submissions.new(limit=None), "submissions")
    remove_items(nuked_person.comments.new(limit=None), "comments")

    logger.info(f">> Completely nuked u/{nuked_person}.")

    # Message the moderator who issued the command.
    # As this is a mod-only command, this does not require the testing
    # wrapper.
    message_send(
        mod_caller,
        subject=f"Nuked u/{nuked_person}",
        body=(
            f"Banned and removed all comments and posts from u/{nuked_person}. "
            f"Command called by you [here](https://www.reddit.com{comment.permalink})."
        ),
    )
    logger.info(f">> Notified mod u/{mod_caller} via messages.")

    return
