#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
Hermes database operations.

Extends the shared DatabaseManager (database.py) with the two tables
Hermes needs:

  hermes.db
  ├── entries    — one row per user: username, serialised user_data, posted_utc
  └── processed  — tracks post IDs already acted on

All Hermes DB work goes through HermesDatabaseManager, which is a thin
subclass of the shared DatabaseManager.  The database file itself lives
alongside the other bot databases under _data/Databases/.

Logger tag: [HM:DB]
"""

import os
import sqlite3
import time
from ast import literal_eval
from typing import Any

import orjson

from config import Paths, get_hermes_logger
from database import DatabaseManager

logger = get_hermes_logger("HM:DB")
HERMES_DB_PATH = Paths.HERMES["HERMES_DATABASE"]


# ─── Schema setup ─────────────────────────────────────────────────────────────


def initialize_hermes_db() -> None:
    """
    Create hermes.db with the required tables if it does not exist yet.
    Safe to call on every startup — it is a no-op when the file is present.
    """
    db_path = HERMES_DB_PATH

    if os.path.exists(db_path):
        logger.debug(f"{db_path} already exists. Skipping hermes.db.")
        return

    logger.info(f"Creating hermes.db at {db_path} ...")

    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn: sqlite3.Connection | None = None
    try:
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()

        cur.execute(
            """
            CREATE TABLE entries (
                username    TEXT PRIMARY KEY,
                user_data   TEXT NOT NULL,
                posted_utc  INTEGER NOT NULL
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE processed (
                post_id     TEXT PRIMARY KEY,
                created_utc INTEGER NOT NULL
            )
            """
        )
        conn.commit()
        logger.info("hermes.db initialised successfully.")
    except sqlite3.Error as exc:
        logger.error(f"Error initialising hermes.db: {exc}")
    finally:
        if conn:
            conn.close()


# ─── Private helpers ──────────────────────────────────────────────────────────


def _parse_user_data(raw: str) -> dict[str, Any] | None:
    """
    Deserialise a user_data string stored in the database.
    Accepts both JSON (new rows) and Python-literal strings (legacy rows).
    """
    if not raw:
        return None
    try:
        return orjson.loads(raw)
    except (orjson.JSONDecodeError, ValueError):
        pass
    try:
        return literal_eval(raw)
    except (ValueError, SyntaxError):
        pass
    return None


# ─── Database manager ─────────────────────────────────────────────────────────


class HermesDatabaseManager(DatabaseManager):
    """
    Extends the shared DatabaseManager with a connection to hermes.db
    and convenience methods for all Hermes-specific DB operations.
    """

    def __init__(self) -> None:
        super().__init__()
        self._conn_hermes: sqlite3.Connection | None = None

    # ── Connection properties ─────────────────────────────────────────────────

    @property
    def conn_hermes(self) -> sqlite3.Connection:
        if self._conn_hermes is None:
            self._conn_hermes = self._connect(HERMES_DB_PATH)
        return self._conn_hermes

    @property
    def cursor_hermes(self) -> sqlite3.Cursor:
        return self.conn_hermes.cursor()

    def close_all(self) -> None:
        super().close_all()
        if self._conn_hermes:
            self._conn_hermes.close()

    # ── processed table ───────────────────────────────────────────────────────

    def is_processed(self, post_id: str) -> bool:
        """Return True if post_id has already been handled."""
        cur = self.cursor_hermes
        cur.execute("SELECT 1 FROM processed WHERE post_id = ?", (post_id,))
        return cur.fetchone() is not None

    def mark_processed(self, post_id: str, created_utc: int) -> None:
        """Record a post as processed so it is never acted on again."""
        cur = self.cursor_hermes
        cur.execute(
            "INSERT OR IGNORE INTO processed VALUES (?, ?)",
            (post_id, created_utc),
        )
        self.conn_hermes.commit()

    # ── entries table — reads ─────────────────────────────────────────────────

    def get_entry(self, username: str) -> dict[str, Any] | None:
        """
        Return the stored user_data dict for *username*, or None if not present.
        """
        cur = self.cursor_hermes
        cur.execute("SELECT user_data FROM entries WHERE username = ?", (username,))
        row = cur.fetchone()
        if row is None:
            return None
        return _parse_user_data(row[0])

    def get_all_entries(self) -> list[tuple[str, dict[str, Any], int]]:
        """
        Return all entries as a list of (username, user_data_dict, posted_utc)
        triples.  Rows that cannot be deserialised are skipped with a warning.
        """
        cur = self.cursor_hermes
        cur.execute("SELECT username, user_data, posted_utc FROM entries")
        rows = cur.fetchall()

        results: list[tuple[str, dict[str, Any], int]] = []
        for username, raw, posted_utc in rows:
            data = _parse_user_data(raw)
            if data is None:
                logger.warning(f"Could not parse user_data for u/{username}. Skipped.")
                continue
            results.append((username, data, posted_utc))
        return results

    # ── entries table — writes ────────────────────────────────────────────────

    def upsert_entry(
        self, username: str, user_data: dict[str, Any], posted_utc: int
    ) -> None:
        """
        Insert or update the entry for *username*.
        If the user already exists their user_data is replaced; posted_utc is
        kept from the original insertion so the cutoff logic remains correct.
        """
        serialised = orjson.dumps(user_data).decode()
        cur = self.cursor_hermes
        # Use an explicit INSERT-or-UPDATE so this works regardless of whether
        # the live schema declared username as PRIMARY KEY or UNIQUE — the
        # ON CONFLICT(col) target syntax requires the constraint to be
        # present in the live DB, which may not be the case on older schemas.
        cur.execute("SELECT 1 FROM entries WHERE username = ?", (username,))
        if cur.fetchone() is None:
            cur.execute(
                "INSERT INTO entries (username, user_data, posted_utc) VALUES (?, ?, ?)",
                (username, serialised, posted_utc),
            )
        else:
            cur.execute(
                "UPDATE entries SET user_data = ? WHERE username = ?",
                (serialised, username),
            )
        self.conn_hermes.commit()
        logger.info(f"Upserted entry for u/{username}.")

    def delete_entry(self, username: str) -> None:
        """Remove a user's entry from the database."""
        cur = self.cursor_hermes
        cur.execute("DELETE FROM entries WHERE username = ?", (username,))
        self.conn_hermes.commit()
        logger.info(f"Deleted entry for u/{username}.")

    def delete_entry_by_utc(self, posted_utc: int) -> None:
        """Remove entries by their posted_utc timestamp (used during maintenance)."""
        cur = self.cursor_hermes
        cur.execute("DELETE FROM entries WHERE posted_utc = ?", (posted_utc,))
        self.conn_hermes.commit()

    # ── entries table — maintenance ───────────────────────────────────────────

    def prune_old_entries(self, cut_off_seconds: int) -> list[str]:
        """
        Delete all entries older than *cut_off_seconds* from now.

        Returns:
            List of post IDs that were pruned.
        """
        current_time = time.time()
        pruned: list[str] = []

        for username, data, posted_utc in self.get_all_entries():
            if current_time - posted_utc > cut_off_seconds:
                post_id = data.get("id", "unknown")
                self.delete_entry_by_utc(posted_utc)
                pruned.append(post_id)
                logger.info(f"Pruned expired entry: post {post_id} by u/{username}.")
        return pruned


# ─── Module-level singleton ───────────────────────────────────────────────────

hermes_db = HermesDatabaseManager()
