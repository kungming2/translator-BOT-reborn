#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
import asyncio
import re

from praw import exceptions

from config import logger, SETTINGS
from connection import reddit_login  # TODO Likely will want to change accounts for this one.
from database import db
from lookup.other import lookup_zh_ja_tokenizer
from lookup.zh import zh_word, zh_character
from responses import RESPONSE


def cc_ref():
    """
    Runtime for Chinese language subreddits. The bot monitors a
    multireddit called 'chinese' and provides character and word lookups
    for requests marked by backticks, similar to r/translator.
    """
    multireddit = REDDIT_CHINESE.multireddit(redditor='translator-BOT', name='chinese')
    comments = list(multireddit.comments(limit=SETTINGS['max_posts']))
    cursor = db.cursor_main
    conn = db.conn_main

    for comment in comments:
        comment_id = comment.id

        # Skip already processed comments
        cursor.execute("SELECT 1 FROM old_comments WHERE ID = ?", (comment_id,))
        if cursor.fetchone():
            continue

        body = comment.body.lower()
        cursor.execute("INSERT INTO old_comments (ID) VALUES (?)", (comment_id,))
        conn.commit()

        if '`' in body:
            matches = re.findall(r'`([\u2E80-\u9FFF]+)`', body)
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
                    reply_text = reply_text[:9900]  # Reddit max comment length

                try:
                    print(reply_text + RESPONSE.BOT_DISCLAIMER)  # TODO change back to reply when deployed
                    logger.info(f"[ZW] CC_REF: Replied to lookup request for {tokenized_matches} "
                                f"on a Chinese subreddit.")
                except exceptions.RedditAPIException:
                    print("Sorry, but the character data you've requested exceeds "
                          "the amount Reddit allows for a comment.")  # TODO change back to reply when deployed


if __name__ == '__main__':
    cc_ref()
