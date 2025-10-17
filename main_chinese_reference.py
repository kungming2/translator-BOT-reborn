#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
import asyncio
import re
import traceback

import asyncpraw
from asyncpraw import exceptions
from wasabi import msg

from config import SETTINGS, logger
from connection import credentials_source
from error import error_log_extended
from lookup.other import lookup_zh_ja_tokenizer
from lookup.zh import zh_character, zh_word
from responses import RESPONSE


async def cc_ref(reddit):
    """
    Runtime for Chinese language subreddits. The bot monitors a
    multireddit called 'chinese' and provides character and word lookups
    for requests marked by backticks, just like on r/translator.
    """
    multireddit = await reddit.multireddit(redditor="translator-BOT", name="chinese")
    comments = []

    async for comment in multireddit.comments(limit=SETTINGS["max_posts"]):
        comments.append(comment)

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
                reply_text = "\n\n".join(reply_parts)
                cc_bot_disclaimer = RESPONSE.BOT_DISCLAIMER.replace(
                    "translator", comment.subreddit.display_name
                )
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


async def chinese_reference_login_async(credentials):
    """Async version of chinese_reference_login."""
    reddit = asyncpraw.Reddit(
        client_id=credentials["CHINESE_APP_ID"],
        client_secret=credentials["CHINESE_APP_SECRET"],
        username=credentials["CHINESE_USERNAME"],
        password=credentials["CHINESE_PASSWORD"],
        user_agent="Regular tasks on r/ChineseLanguage",
    )
    return reddit


async def main():
    """Initialize async PRAW and run the Chinese reference bot."""
    reddit = await chinese_reference_login_async(credentials_source)
    try:
        await cc_ref(reddit)
    finally:
        await reddit.close()


if __name__ == "__main__":
    msg.good("Launching Chinese Reference...")
    # noinspection PyBroadException
    try:
        asyncio.run(main())
    except Exception:
        error_entry = traceback.format_exc()
        error_log_extended(error_entry, "Chinese Reference")
    msg.info("Chinese Reference routine completed.")
