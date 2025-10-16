#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
This Diskuto class covers posts that are *not* requests - e.g.
Meta or Community posts. This is intended to make creating more granular
types easier in the future.
"""

import re

import orjson

from config import logger
from connection import REDDIT_HELPER
from database import db


class Diskuto:
    def __init__(
        self,
        title_original=None,
        post_type=None,
        _id=None,
        created_utc=None,
        processed=False,
    ):
        self.title_original = title_original
        self.post_type = post_type
        self.id = _id
        self.created_utc = created_utc
        self.processed = processed

    def __repr__(self):
        return (
            f"<Diskuto: id={self.id}, type={self.post_type}, "
            f"processed={self.processed} | {self.title_original}>"
        )

    def to_dict(self):
        """
        Convert Diskuto instance to a dictionary representation.

        Returns:
            dict: Dictionary with all Diskuto attributes
        """
        return {
            "id": self.id,
            "created_utc": self.created_utc,
            "title_original": self.title_original,
            "post_type": self.post_type,
            "processed": self.processed,
        }

    def __str__(self):
        return (
            f"Diskuto(\n"
            f"  id='{self.id}',\n"
            f"  created_utc={self.created_utc},\n"
            f"  title_original='{self.title_original}',\n"
            f"  post_type='{self.post_type}',\n"
            f"  processed={self.processed}\n"
            f")"
        )

    @classmethod
    def process_post(cls, praw_submission):
        """
        Build a Diskuto directly from a PRAW submission:
        - id: praw_submission.id
        - created_utc: integer version of praw_submission.created_utc
        - title_original: the full title string
        - post_type: the lowercase text inside the first [TAG] if present
        - processed: defaults to False
        """
        if not hasattr(praw_submission, "title") or not hasattr(praw_submission, "id"):
            raise TypeError("process_title requires a valid PRAW submission object.")

        title = praw_submission.title
        m = re.match(r"^\s*\[([^]]+)]", title)
        post_type = m.group(1).strip().lower() if m else None

        return cls(
            title_original=title,
            post_type=post_type,
            _id=praw_submission.id,
            created_utc=int(praw_submission.created_utc),
            processed=False,
        )

    def toggle_processed(self):
        """
        Flip the processed flag (True -> False or False -> True).
        """
        self.processed = not self.processed


def diskuto_exists(post_id):
    """
    Check if a Diskuto post exists in the internal_posts table.

    :param post_id: The ID of the Diskuto post to check
    :return: True if exists, False otherwise
    """
    cursor = db.cursor_main
    cursor.execute("SELECT 1 FROM internal_posts WHERE id = ? LIMIT 1", (post_id,))
    return cursor.fetchone() is not None


def diskuto_writer(diskuto_obj):
    """
    Takes a Diskuto object and saves it to the main database
    (the internal_posts table).

    :param diskuto_obj: Diskuto object to save
    """
    if not hasattr(diskuto_obj, "id") or not hasattr(diskuto_obj, "created_utc"):
        raise TypeError("diskuto_writer requires a valid Diskuto object.")

    post_id = str(diskuto_obj.id)
    created_time = diskuto_obj.created_utc
    content_json = orjson.dumps(diskuto_obj.__dict__).decode("utf-8")

    cursor = db.cursor_main
    conn = db.conn_main

    # Ensure table exists
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS internal_posts (
            id TEXT PRIMARY KEY,
            created_utc INTEGER,
            content TEXT
        )
    """)

    # Check if the post already exists
    cursor.execute("SELECT content FROM internal_posts WHERE id = ?", (post_id,))
    row = cursor.fetchone()

    if row:
        existing_content = row["content"]
        if existing_content != content_json:
            cursor.execute(
                "UPDATE internal_posts SET created_utc = ?, content = ? WHERE id = ?",
                (created_time, content_json, post_id),
            )
            conn.commit()
            logger.info(f"[Diskuto Writer] Diskuto {post_id} exists, data updated.")
        else:
            logger.info(f"[Diskuto Writer] Diskuto {post_id} exists, no change.")
    else:
        cursor.execute(
            "INSERT OR REPLACE INTO internal_posts (id, created_utc, content) VALUES (?, ?, ?)",
            (post_id, created_time, content_json),
        )
        conn.commit()
        logger.info(f"[Diskuto Writer] New Diskuto {post_id} written to database.")


def diskuto_loader(post_id):
    """
    Load a Diskuto object from the internal_posts table by its post_id.

    :param post_id: The ID of the Diskuto to load
    :return: Diskuto object if found, else None
    """
    result = db.fetch_main(
        "SELECT content FROM internal_posts WHERE id = ?", (post_id,)
    )

    if result is None:
        logger.debug(f"[Diskuto Loader] No Diskuto found for id {post_id}.")
        return None

    try:
        diskuto_dict = orjson.loads(result["content"])
    except orjson.JSONDecodeError:
        logger.error(
            f"[Diskuto Loader] Failed to decode Diskuto JSON for id {post_id}."
        )
        return None

    # Rebuild Diskuto object
    return Diskuto(
        title_original=diskuto_dict.get("title_original"),
        post_type=diskuto_dict.get("post_type"),
        _id=diskuto_dict.get("id"),
        created_utc=diskuto_dict.get("created_utc"),
        processed=diskuto_dict.get("processed", False),
    )


if __name__ == "__main__":
    url_input = input("Please enter a non-request Reddit URL to test: ")
    reddit_submission = REDDIT_HELPER.submission(url=url_input)

    # Process into a Diskuto
    diskuto_test = Diskuto.process_post(reddit_submission)

    # Print Diskuto info
    print("Diskuto object:")
    print(diskuto_test)

    # Write to the database
    try:
        diskuto_writer(diskuto_test)
        print(f"> Diskuto `{diskuto_test.id}` written to database successfully.")
    except Exception as e:
        print(f"> Failed to write Diskuto: {e}")
