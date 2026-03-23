#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
This Diskuto class covers internal posts that are *not* requests - e.g.
Meta or Community posts. This is intended to make making creating more granular
types easier in the future.
...

Logger tag: [M:DISKUTO]
"""

import logging
import re
from typing import Any

import orjson

from config import SETTINGS
from config import logger as _base_logger
from database import db
from reddit.connection import REDDIT
from testing import log_testing_mode

logger = logging.LoggerAdapter(_base_logger, {"tag": "M:DISKUTO"})


# ─── Main Diskuto class ───────────────────────────────────────────────────────


class Diskuto:
    """Represents an internal (non-request) subreddit post such as a
    Meta or Community post."""

    # ── Construction ──────────────────────────────────────────────────────────

    def __init__(
        self,
        title_original: str | None = None,
        post_type: str | None = None,
        _id: str | None = None,
        created_utc: int | None = None,
        processed: bool = False,
    ) -> None:
        """Initialize a Diskuto with title, post type, ID, timestamp,
        and processed flag."""
        self.title_original = title_original
        self.post_type = post_type
        self.id = _id
        self.created_utc = created_utc
        self.processed = processed

    def __repr__(self) -> str:
        return (
            f"<Diskuto: id={self.id}, type={self.post_type}, "
            f"processed={self.processed} | {self.title_original}>"
        )

    def __str__(self) -> str:
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
    def process_post(cls, praw_submission: Any) -> "Diskuto":
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

    # ── Serialization ─────────────────────────────────────────────────────────

    def to_dict(self) -> dict[str, Any]:
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

    # ── State mutation methods ─────────────────────────────────────────────────

    def toggle_processed(self) -> None:
        """
        Flip the processed flag (True -> False or False -> True).
        """
        self.processed = not self.processed

    # ── Reddit actions ────────────────────────────────────────────────────────

    def update_reddit(self) -> None:
        """
        Set the Reddit post flair to match this Diskuto's post_type
        (e.g. 'meta' or 'community') and write the updated record to
        the database.

        The flair CSS class and text are both derived directly from
        post_type, which must be a key in STATE.post_templates. If no
        matching template is found, the flair is left unchanged.
        """
        from reddit.startup import STATE

        testing_mode = SETTINGS["testing_mode"]
        post_templates = STATE.post_templates

        if not self.post_type:
            logger.warning(f"No post_type set for `{self.id}`. Skipping flair update.")
            return

        if self.post_type not in post_templates:
            logger.warning(
                f"No flair template found for post_type "
                f"'{self.post_type}' on `{self.id}`. Skipping flair update."
            )
            return

        template_id = post_templates[self.post_type]
        flair_text = self.post_type.capitalize()
        submission = REDDIT.submission(id=self.id)

        if not testing_mode:
            submission.flair.select(flair_template_id=template_id, text=flair_text)
            logger.info(
                f"Set flair for `{self.id}` to "
                f"'{flair_text}' (template `{template_id}`)."
            )
        else:
            log_testing_mode(
                output_text=flair_text,
                title=f"Flair Update Dry Run for Diskuto {self.id}",
                metadata={
                    "Submission ID": self.id,
                    "Flair CSS": self.post_type,
                    "Flair Template ID": template_id,
                    "Post Type": self.post_type,
                },
            )

        diskuto_writer(self)


# ─── Database persistence ─────────────────────────────────────────────────────


def diskuto_exists(post_id: str) -> bool:
    """
    Check if a Diskuto post exists in the internal_posts table.

    :param post_id: The ID of the Diskuto post to check
    :return: True if exists, False otherwise
    """
    cursor = db.cursor_main
    cursor.execute("SELECT 1 FROM internal_posts WHERE id = ? LIMIT 1", (post_id,))
    return cursor.fetchone() is not None


def diskuto_writer(diskuto_obj: Diskuto) -> None:
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
            logger.info(f"Diskuto `{post_id}` exists, data updated.")
        else:
            logger.info(f"Diskuto `{post_id}` exists, no change.")
    else:
        cursor.execute(
            "INSERT OR REPLACE INTO internal_posts (id, created_utc, content) VALUES (?, ?, ?)",
            (post_id, created_time, content_json),
        )
        conn.commit()
        logger.info(f"New Diskuto `{post_id}` written to database.")


def diskuto_loader(post_id: str) -> Diskuto | None:
    """
    Load a Diskuto object from the internal_posts table by its post_id.

    :param post_id: The ID of the Diskuto to load
    :return: Diskuto object if found, else None
    """
    result = db.fetch_main(
        "SELECT content FROM internal_posts WHERE id = ?", (post_id,)
    )

    if result is None:
        logger.debug(f"No Diskuto found for id `{post_id}`.")
        return None

    try:
        diskuto_dict = orjson.loads(result["content"])
    except orjson.JSONDecodeError:
        logger.error(f"Failed to decode Diskuto JSON for id `{post_id}`.")
        return None

    # Rebuild Diskuto object
    return Diskuto(
        title_original=diskuto_dict.get("title_original"),
        post_type=diskuto_dict.get("post_type"),
        _id=diskuto_dict.get("id"),
        created_utc=diskuto_dict.get("created_utc"),
        processed=diskuto_dict.get("processed", False),
    )
