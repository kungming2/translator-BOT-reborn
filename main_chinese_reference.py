#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
Chinese Reference Bot for Chinese language learning subreddits.
Often referred to as cc_ref for short.

This asynchronous bot monitors a multireddit of Chinese language communities
and provides automated character and word lookups. Users can request lookups
by wrapping Chinese text in backticks (e.g., `汉字`).

Features:
- Monitors multiple Chinese language subreddits via a multireddit
- Detects Chinese characters/words marked with backticks
- Provides detailed lookups for:
  * Single characters (pronunciation, meanings, components)
  * Multi-character words (definitions, usage)
- Uses asyncpraw for efficient async processing
- Automatically tokenizes longer text into meaningful segments

The bot uses a separate Reddit account from the main translator bot
and is configured via CHINESE_* credentials in the config.
"""

import asyncio
import re
import traceback
from typing import TYPE_CHECKING

import asyncpraw
from asyncpraw import exceptions
from asyncprawcore import exceptions as asyncprawcore_exceptions
from wasabi import msg

from config import SETTINGS, logger
from connection import USERNAME, credentials_source
from error import error_log_extended
from lookup.match_helpers import lookup_zh_ja_tokenizer
from lookup.zh import zh_character, zh_word
from responses import RESPONSE

if TYPE_CHECKING:
    from asyncpraw import Reddit


async def _cc_ref(reddit: "Reddit") -> None:
    """Runtime for Chinese language subreddits."""
    try:
        multireddit = await reddit.multireddit(redditor=USERNAME, name="chinese")
    except asyncprawcore_exceptions.RequestException as e:
        logger.warning(
            f"[CC_REF]: Failed to fetch multireddit - network/auth error: {e}"
        )
        return
    except Exception as e:
        logger.error(f"[CC_REF]: Unexpected error fetching multireddit: {e}")
        return

    comments = []

    try:
        async for comment in multireddit.comments(limit=SETTINGS["max_posts"]):
            comments.append(comment)
    except asyncprawcore_exceptions.RequestException as e:
        logger.error(f"[CC_REF]: Failed to fetch comments - network/auth error: {e}")
        return
    except Exception as e:
        logger.error(f"[CC_REF]: Unexpected error fetching comments: {e}")
        return

    for comment in comments:
        body = comment.body

        # Skip already processed comments.
        if comment.saved:
            continue

        # Detected a possible match.
        if "`" in body:
            matches = re.findall(r"`([\u2E80-\u9FFF]+)`", body)
            await comment.save()  # To mark as processed

            if not matches:
                continue

            tokenized_matches = []
            for item in matches:
                if len(item) >= 2:
                    tokenized_matches.extend(
                        lookup_zh_ja_tokenizer(item, language_code="zh")
                    )
                else:
                    tokenized_matches.append(item)

            reply_parts = []
            for token in tokenized_matches:
                if len(token) == 1:
                    reply_parts.append(await zh_character(token))
                else:
                    reply_parts.append(await zh_word(token))

            if reply_parts:
                reply_text = "\n\n".join(reply_parts) + f"  {RESPONSE.ANCHOR_CJK}"
                cc_bot_disclaimer = RESPONSE.BOT_DISCLAIMER.replace(
                    "r/translator ", f"r/{comment.subreddit.display_name} "
                )  # Adapt the disclaimer to whatever subreddit the bot is posting on
                if len(reply_text) > 10000:
                    reply_text = reply_text[:9900]

                try:
                    reply = await comment.reply(reply_text + cc_bot_disclaimer)
                    logger.info(
                        f"[CC_REF]: Replied to lookup request for {tokenized_matches} "
                        f"on r/{comment.subreddit.display_name}. Comment ID: {reply.id}"
                    )
                except exceptions.RedditAPIException as ex:
                    logger.error(f"[CC_REF]: Reddit API exception: {ex}")
                except Exception as ex:
                    logger.error(f"[CC_REF]: Unexpected exception: {ex}")


async def _chinese_reference_login_async(credentials: dict[str, str]) -> "Reddit":
    """Async version of chinese_reference_login."""
    reddit = asyncpraw.Reddit(
        client_id=credentials["CHINESE_APP_ID"],
        client_secret=credentials["CHINESE_APP_SECRET"],
        username=credentials["CHINESE_USERNAME"],
        password=credentials["CHINESE_PASSWORD"],
        user_agent="Regular tasks on r/ChineseLanguage",
    )
    return reddit


async def cc_ref_main() -> None:
    """Initialize async PRAW and run the Chinese reference bot."""
    reddit = await _chinese_reference_login_async(credentials_source)
    try:
        await _cc_ref(reddit)
    finally:
        await reddit.close()


if __name__ == "__main__":
    msg.good("Launching Chinese Reference...")
    # noinspection PyBroadException
    try:
        asyncio.run(cc_ref_main())
    except Exception:
        error_entry = traceback.format_exc()
        error_log_extended(error_entry, "Chinese Reference")
    msg.info("Chinese Reference routine completed.")
