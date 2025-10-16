#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
import asyncio
import re
import traceback

from praw import exceptions
from wasabi import msg

from config import SETTINGS, logger
from connection import chinese_reference_login, credentials_source
from error import error_log_extended
from lookup.other import lookup_zh_ja_tokenizer
from lookup.zh import zh_character, zh_word
from reddit_sender import comment_reply
from responses import RESPONSE


def cc_ref():
    """
    Runtime for Chinese language subreddits. The bot monitors a
    multireddit called 'chinese' and provides character and word lookups
    for requests marked by backticks, just like on r/translator.
    """
    multireddit = REDDIT_CHINESE.multireddit(redditor='translator-BOT',
                                             name='chinese')
    comments = list(multireddit.comments(limit=SETTINGS['max_posts']))

    for comment in comments:
        body = comment.body

        # Skip already processed comments.
        if comment.saved:
            continue

        # Detected a possible match.
        if '`' in body:
            matches = re.findall(r'`([\u2E80-\u9FFF]+)`', body)
            comment.save()  # To mark as processed
            if not matches:
                continue

            tokenized_matches = []
            for item in matches:
                if len(item) >= 2:
                    tokenized_matches.extend(lookup_zh_ja_tokenizer(item,
                                                                    language_code="zh"))
                else:
                    tokenized_matches.append(item)

            reply_parts = []
            for token in tokenized_matches:
                if len(token) == 1:
                    reply_parts.append(zh_character(token))
                else:
                    reply_parts.append(asyncio.run(zh_word(token)))

            if reply_parts:
                reply_text = '\n\n'.join(reply_parts)
                if len(reply_text) > 10000:
                    reply_text = reply_text[:9900]  # shorten to Reddit max comment length

                try:
                    comment_reply(comment, reply_text + RESPONSE.BOT_DISCLAIMER)
                    logger.info(f"[CC_REF]: Replied to lookup request for {tokenized_matches} "
                                f"on a Chinese subreddit.")
                except exceptions.RedditAPIException as ex:
                    logger.error(f"Encountered an API exception. `{ex}`")


REDDIT_CHINESE = chinese_reference_login(credentials_source)


if __name__ == '__main__':
    msg.good("Launching Chinese Reference...")
    # noinspection PyBroadException
    try:
        cc_ref()
    except Exception:  # intentionally broad: catch all exceptions for logging
        error_entry = traceback.format_exc()
        error_log_extended(error_entry, "Chinese Reference")
    msg.info("Chinese Reference routine completed.")
