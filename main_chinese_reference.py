#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
Chinese Reference Bot for Chinese language learning subreddits.
Often referred to as CR for short.

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
...

Logger tag: [CR]
"""

import asyncio
import re
import sys
import traceback
from typing import TYPE_CHECKING

import asyncpraw
from asyncpraw import exceptions
from asyncprawcore import exceptions as asyncprawcore_exceptions

from config import SETTINGS, TRANSIENT_ERRORS, Paths, get_specific_logger
from error import error_log_basic
from reddit.connection import USERNAME, credentials_source
from responses import RESPONSE
from ziwen_lookup.match_helpers import lookup_zh_ja_tokenizer
from ziwen_lookup.zh import zh_character, zh_word

if TYPE_CHECKING:
    from asyncpraw import Reddit

logger = get_specific_logger("CR", log_path=Paths.CR["CR_EVENTS"])


# ─── Auth ─────────────────────────────────────────────────────────────────────


async def _chinese_reference_login_async(credentials: dict[str, str]) -> "Reddit":
    """Async login using CHINESE_* credentials."""
    return asyncpraw.Reddit(
        client_id=credentials["CHINESE_APP_ID"],
        client_secret=credentials["CHINESE_APP_SECRET"],
        username=credentials["CHINESE_USERNAME"],
        password=credentials["CHINESE_PASSWORD"],
        user_agent="Regular tasks on r/ChineseLanguage",
    )


# ─── Comment processing ───────────────────────────────────────────────────────


async def _fetch_and_reply_chinese_comments(reddit: "Reddit") -> None:
    """Fetch comments from the Chinese multireddit and reply to lookup requests."""
    try:
        multireddit = await reddit.multireddit(redditor=USERNAME, name="chinese")
    except asyncprawcore_exceptions.RequestException as e:
        logger.warning(f"Failed to fetch multireddit - network/auth error: {e}")
        return
    except Exception as e:
        logger.error(f"Unexpected error fetching multireddit: {e}")
        return

    comments = []
    try:
        async for comment in multireddit.comments(limit=SETTINGS["max_posts"]):
            comments.append(comment)
    except asyncprawcore_exceptions.RequestException as e:
        logger.error(f"Failed to fetch comments - network/auth error: {e}")
        return
    except Exception as e:
        logger.error(f"Unexpected error fetching comments: {e}")
        return

    for comment in comments:
        body = comment.body

        if comment.saved:  # Already processed
            continue

        if "`" not in body:
            continue

        matches = re.findall(r"`([\u2E80-\u9FFF]+)`", body)
        await comment.save()  # Mark as processed before any reply attempt

        if not matches:
            continue

        # Tokenize multi-character matches into meaningful segments
        tokenized_matches = []
        for item in matches:
            if len(item) >= 2:
                tokenized_matches.extend(
                    lookup_zh_ja_tokenizer(item, language_code="zh")
                )
            else:
                tokenized_matches.append(item)

        # Build reply from per-token lookups
        reply_parts = []
        for token in tokenized_matches:
            if len(token) == 1:
                reply_parts.append(await zh_character(token))
            else:
                reply_parts.append(await zh_word(token))

        if not reply_parts:
            continue

        reply_body = "\n\n".join(reply_parts)

        if len(reply_body) > 10000:
            reply_body = (
                reply_body[:9000]
                + "\n\n"
                + RESPONSE.SNIPPET_LOOKUP_TRUNCATED.format(content_type="Reference")
            )

        # Adapt disclaimer to the subreddit the bot is posting on
        cc_bot_disclaimer = RESPONSE.BOT_DISCLAIMER.replace(
            "r/translator ", f"r/{comment.subreddit.display_name} "
        )

        reply_text = reply_body + f"  {RESPONSE.ANCHOR_CJK}" + cc_bot_disclaimer

        try:
            reply = await comment.reply(reply_text)
            logger.info(
                f"Replied to lookup request for {tokenized_matches} "
                f"on r/{comment.subreddit.display_name}. Comment ID: {reply.id}"
            )
        except exceptions.RedditAPIException as ex:
            logger.error(f"Reddit API exception: {ex}")
        except Exception as ex:
            logger.error(f"Unexpected exception: {ex}")


# ─── Entry point ──────────────────────────────────────────────────────────────


async def chinese_reference_main() -> None:
    """Initialize async PRAW and run the Chinese reference bot."""
    reddit = await _chinese_reference_login_async(credentials_source)
    try:
        await _fetch_and_reply_chinese_comments(reddit)
    finally:
        await reddit.close()


if __name__ == "__main__":
    logger.info("Launching Chinese Reference routine.")
    # noinspection PyBroadException
    try:
        asyncio.run(chinese_reference_main())

    except KeyboardInterrupt:
        logger.info("Chinese Reference routine stopped by user (KeyboardInterrupt).")
        sys.exit(0)

    except TRANSIENT_ERRORS as exc:
        logger.warning(f"Transient error encountered: {type(exc).__name__}: {exc}")
        logger.info("Will retry on next cycle.")

    except Exception as exc:
        error_entry = f"### {exc}\n\n{traceback.format_exc()}"
        logger.critical(error_entry)
        error_log_basic(error_entry, "Chinese Reference")

    else:
        logger.debug("Chinese Reference routine completed.")
