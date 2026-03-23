#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
Handles database reading and writing. While the top-level stuff is
all in SQLite, there are also some plain text recording functions here.

This module provides a unified interface for all database operations across
the bot's three SQLite databases:

1. cache.db - Temporary data and caching:
   - comment_cache: Stores comment content (including commands)
     and creation time for edit detection
   - multiplier_cache: Caches language point multipliers by month

2. main.db - Core operational data:
   - internal_posts: Subreddit internal announcements
   - notify_*: User notification preferences and tracking
   - old_comments/old_posts: Processed item tracking
   - total_commands: User command usage statistics
   - total_points: Monthly point accumulation records

3. ajo.db - Post/translation request data:
   - ajo_database: Serialized Ajo objects with metadata

The DatabaseManager class provides lazy-loaded connections and cursor access
with convenient query methods. Additional functions handle CSV/text logging
and complex search operations across the databases.
...

Logger tag: [DATA]
"""

# ─── Imports ──────────────────────────────────────────────────────────────────

import csv
import json
import logging
import os
import sqlite3
from ast import literal_eval
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Optional, Tuple

from config import Paths
from config import logger as _base_logger
from time_handling import convert_to_day

if TYPE_CHECKING:
    from models.ajo import Ajo

# ─── Module-level constants ───────────────────────────────────────────────────

logger = logging.LoggerAdapter(_base_logger, {"tag": "DATA"})


# ─── Database manager ─────────────────────────────────────────────────────────


class DatabaseManager:
    """
    Unified class to handle writes and reads to the three databases.
    """

    def __init__(self) -> None:
        """Initialize the manager with deferred connections to all three databases."""
        self._conn_cache: sqlite3.Connection | None = None
        self._conn_main: sqlite3.Connection | None = None
        self._conn_ajo: sqlite3.Connection | None = None

    # ── Connection management ─────────────────────────────────────────────────

    @staticmethod
    def _connect(file_path: str) -> sqlite3.Connection:
        """Open a SQLite connection to *file_path* with row_factory set to sqlite3.Row."""
        conn = sqlite3.connect(file_path)
        conn.row_factory = sqlite3.Row
        return conn

    @property
    def conn_cache(self) -> sqlite3.Connection:
        """Lazy connection to the cache database; opens on first access."""
        if self._conn_cache is None:
            self._conn_cache = self._connect(Paths.DATABASE["CACHE"])
        return self._conn_cache

    @property
    def conn_main(self) -> sqlite3.Connection:
        """Lazy connection to the main database; opens on first access."""
        if self._conn_main is None:
            self._conn_main = self._connect(Paths.DATABASE["MAIN"])
        return self._conn_main

    @property
    def conn_ajo(self) -> sqlite3.Connection:
        """Lazy connection to the Ajo database; opens on first access."""
        if self._conn_ajo is None:
            self._conn_ajo = self._connect(Paths.DATABASE["AJO"])
        return self._conn_ajo

    @property
    def cursor_cache(self) -> sqlite3.Cursor:
        """Return a fresh cursor on the cache database connection."""
        return self.conn_cache.cursor()

    @property
    def cursor_main(self) -> sqlite3.Cursor:
        """Return a fresh cursor on the main database connection."""
        return self.conn_main.cursor()

    @property
    def cursor_ajo(self) -> sqlite3.Cursor:
        """Return a fresh cursor on the Ajo database connection."""
        return self.conn_ajo.cursor()

    def close_all(self) -> None:
        """Close all open database connections."""
        for conn in (self._conn_cache, self._conn_main, self._conn_ajo):
            if conn:
                conn.close()

    # ── Query helpers ─────────────────────────────────────────────────────────

    def fetch_ajo(self, query: str, params: tuple = ()) -> sqlite3.Row | None:
        """
        Execute a SELECT query and return a single row from the AJO database.

        :param query: SQL SELECT statement
        :param params: Query parameters as a tuple
        :return: A single row (as a tuple or sqlite3.Row), or None
        """
        cursor = self.cursor_ajo
        cursor.execute(query, params)
        return cursor.fetchone()

    def fetchall_ajo(self, query: str, params: tuple = ()) -> list[sqlite3.Row]:
        """
        Execute a SELECT query and return all matching rows from the AJO database.

        :param query: SQL SELECT statement
        :param params: Query parameters as a tuple
        :return: A list of rows (sqlite3.Row objects)
        """
        cursor = self.cursor_ajo
        cursor.execute(query, params)
        return cursor.fetchall()

    def fetch_main(self, query: str, params: tuple = ()) -> sqlite3.Row | None:
        """Return a single row from the MAIN database."""
        cursor = self.cursor_main
        cursor.execute(query, params)
        return cursor.fetchone()

    def fetchall_main(self, query: str, params: tuple = ()) -> list[sqlite3.Row]:
        """Return all rows from the MAIN database."""
        cursor = self.cursor_main
        cursor.execute(query, params)
        return cursor.fetchall()


# ─── Schema setup ─────────────────────────────────────────────────────────────


def _initialize_db(db_path: str, statements: list[str]) -> None:
    """Run a list of DDL statements against a freshly created database file."""
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = None
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        for statement in statements:
            cursor.execute(statement)
        conn.commit()
        logger.info(f"{os.path.basename(db_path)} initialized successfully.")
    except sqlite3.Error as e:
        logger.error(f"Error initializing {db_path}: {e}")
    finally:
        if conn:
            conn.close()


def _initialize_cache_db() -> None:
    """Initialize the cache database if it does not exist."""
    db_path = Paths.DATABASE["CACHE"]

    if os.path.exists(db_path):
        logger.debug(f"{db_path} already exists. Skipping cache.db.")
        return

    logger.info(f"Creating cache.db at {db_path}...")

    create_statements = [
        """
        CREATE TABLE comment_cache (
            id TEXT PRIMARY KEY,
            content TEXT,
            created_utc INTEGER,
            komandos TEXT
        )
        """,
        """
        CREATE TABLE multiplier_cache (
            month_year TEXT,
            language_code TEXT,
            language_multiplier INTEGER
        )
        """,
        """
        CREATE TABLE lookup_cjk_cache (
            term TEXT NOT NULL,
            language_code TEXT NOT NULL,
            retrieved_utc INTEGER NOT NULL,
            type TEXT NOT NULL,
            data TEXT NOT NULL,
            PRIMARY KEY(term, language_code, type)
        )
        """,
    ]

    _initialize_db(db_path, create_statements)


def _initialize_ajo_db() -> None:
    """Initialize the Ajo database if it does not exist."""
    db_path = Paths.DATABASE["AJO"]

    if os.path.exists(db_path):
        logger.debug(f"{db_path} already exists. Skipping ajo.db.")
        return

    logger.info(f"Creating ajo.db at {db_path}...")

    create_statement = [
        """
        CREATE TABLE ajo_database (
            id TEXT,
            created_utc INTEGER,
            ajo TEXT,
            PRIMARY KEY(id)
        )
        """
    ]

    _initialize_db(db_path, create_statement)


def _initialize_main_db() -> None:
    """Initialize the main database if it does not exist."""
    db_path = Paths.DATABASE["MAIN"]

    if os.path.exists(db_path):
        logger.debug(f"{db_path} already exists. Skipping main.db.")
        return

    logger.info(f"Creating main.db at {db_path}...")

    create_statements = [
        """
        CREATE TABLE internal_posts (
            id TEXT,
            created_utc INTEGER,
            content TEXT,
            PRIMARY KEY(id)
        )
        """,
        """
        CREATE TABLE acted_comments (
            comment_id TEXT PRIMARY KEY,
            created_utc INTEGER,
            comment_author_username TEXT,
            action_type TEXT
        )
        """,
        """
        CREATE TABLE notify_cumulative (
            username TEXT,
            received TEXT,
            PRIMARY KEY(username)
        )
        """,
        """
        CREATE TABLE notify_internal (
            post_type TEXT,
            username TEXT
        )
        """,
        """
        CREATE TABLE notify_users (
            language_code TEXT,
            username TEXT
        )
        """,
        """
        CREATE TABLE old_comments (
            id TEXT,
            created_utc INTEGER
        )
        """,
        """
        CREATE TABLE old_posts (
            id TEXT PRIMARY KEY,
            created_utc INTEGER,
            filtered BOOLEAN DEFAULT 0
        )
        """,
        """
        CREATE TABLE total_commands (
            username TEXT PRIMARY KEY,
            commands TEXT
        )
        """,
        """
        CREATE TABLE total_points (
            year_month TEXT,
            comment_id TEXT,
            username TEXT,
            points INTEGER,
            post_id TEXT
        )
        """,
        """
        CREATE TABLE verification_database (
            verification_comment_id TEXT PRIMARY KEY,
            post_id TEXT,
            created_utc INTEGER,
            username TEXT,
            language_code TEXT
        )
        """,
        """
        CREATE INDEX index_total_points_usernames ON total_points (username)
        """,
        """
        CREATE INDEX idx_notify_cumulative_username ON notify_cumulative (
            username
        )
        """,
        """
        CREATE INDEX idx_notify_internal_username ON notify_internal (
            username
        )
        """,
        """
        CREATE INDEX idx_notify_users_language ON notify_users (
            language_code
        )
        """,
        """
        CREATE UNIQUE INDEX idx_notify_users_username_lang ON notify_users (
            username,
            language_code
        )
        """,
        """
        CREATE INDEX idx_old_comments_created ON old_comments (
            created_utc
        )
        """,
        """
        CREATE INDEX idx_total_points_comment_id ON total_points (
            comment_id
        )
        """,
        """
        CREATE INDEX idx_total_points_post_id ON total_points (
            post_id
        )
        """,
        """
        CREATE INDEX idx_total_points_username_year_month ON total_points (
            username,
            year_month
        )
        """,
        """
        CREATE INDEX idx_verification_database_username ON verification_database (
            username
        )
        """,
    ]

    _initialize_db(db_path, create_statements)


def initialize_all_databases() -> None:
    """
    Create all three required databases if they do not exist.
    This is unlikely to be often used as the databases should transfer over.
    """
    _initialize_cache_db()
    _initialize_ajo_db()
    _initialize_main_db()


# ─── File logging ─────────────────────────────────────────────────────────────


def record_activity_csv(run_type: str, data_tuple: tuple) -> None:
    """
    Append a row of activity data to the appropriate CSV log file.

    Two run types are supported, each writing to its own file:

    - ``"cycle"``: Records a cycle run. Columns are:
      Date, Activity Type, Used Calls, Memory Usage, Duration (Minutes), PID

    - ``"messaging"``: Records a messaging run. Columns are:
      Date, Activity Type, Notifications Sent, Language,
      Duration (Minutes), Time Per Notification (Seconds)

    The CSV file is created with a header row if it does not yet exist.

    :param run_type: Either ``"cycle"`` or ``"messaging"``.
    :param data_tuple: Tuple of values matching the columns for the given run type.
    :raises ValueError: If ``run_type`` is not ``"cycle"`` or ``"messaging"``.
    """
    if run_type == "cycle":
        log_path = Paths.LOGS["ACTIVITY"]
        header = [
            "Date",
            "Activity Type",
            "Used Calls",
            "Memory Usage",
            "Duration (Minutes)",
            "PID",
        ]
    elif run_type == "messaging":
        log_path = Paths.LOGS["MESSAGING"]
        header = [
            "Date",
            "Activity Type",
            "Notifications Sent",
            "Language",
            "Duration (Minutes)",
            "Time Per Notification (Seconds)",
        ]
    else:
        raise ValueError(
            f"Invalid run_type '{run_type}': must be 'cycle' or 'messaging'."
        )

    file_exists = os.path.exists(log_path)

    with open(log_path, mode="a", newline="") as csv_file:
        writer = csv.writer(csv_file, quoting=0)  # 0 == csv.QUOTE_MINIMAL
        if not file_exists:
            writer.writerow(header)
        writer.writerow(data_tuple)


def record_filter_log(
    filtered_title: str, created_timestamp: int | float, filter_type: str
) -> None:
    """
    Append an entry to the filter log file as a Markdown table row.

    :param filtered_title: Title of the filtered post.
    :param created_timestamp: Unix timestamp of when the post was created.
    :param filter_type: Code of the violated filter rule.
    """
    timestamp_utc = convert_to_day(created_timestamp)

    # Clean the title: remove tabs, newlines, and normalize whitespace
    cleaned_title = " ".join(filtered_title.split())

    line = f"\n| {timestamp_utc} | {cleaned_title} | {filter_type} |"

    with open(Paths.LOGS["FILTER"], "a", encoding="utf-8") as f:
        f.write(line)


# ─── Ajo database search ──────────────────────────────────────────────────────


def _parse_ajo_row(
    result: sqlite3.Row | tuple, start_utc: int | None = None
) -> tuple[str, int, dict[str, Any]] | None:
    """
    Parse a row from the AJO database.

    Args:
        result: Database row (sqlite3.Row or tuple)
        start_utc: Optional UNIX timestamp filter. Only return if created_utc >= start_utc

    Returns:
        Tuple of (post_id, created_utc, data_dict) or None if parsing fails or filtered out
    """
    try:
        post_id = result["id"] if isinstance(result, sqlite3.Row) else result[0]
        created_utc = (
            result["created_utc"] if isinstance(result, sqlite3.Row) else result[1]
        )

        if start_utc is not None and created_utc < start_utc:
            return None

        data_json = result["ajo"] if isinstance(result, sqlite3.Row) else result[2]

        if isinstance(data_json, dict):
            data = data_json
        elif isinstance(data_json, str):
            # Try JSON first (proper JSON with double quotes)
            try:
                data = json.loads(data_json)
            except json.JSONDecodeError:
                # Fall back to ast.literal_eval for Python dict strings (single quotes)
                try:
                    data = literal_eval(data_json)
                except (ValueError, SyntaxError) as e:
                    logger.debug(f"Failed to parse string data for ID {post_id}: {e}")
                    logger.debug(f"Data preview: {repr(data_json[:100])}")
                    return None
        else:
            # Handle other types (bytes, etc.)
            try:
                data = json.loads(str(data_json))
            except json.JSONDecodeError:
                data = literal_eval(str(data_json))

        return post_id, created_utc, data

    except (TypeError, KeyError, IndexError) as e:
        try:
            row_id = result["id"] if isinstance(result, sqlite3.Row) else result[0]
        except (KeyError, IndexError):
            row_id = "unknown"
        logger.debug(f"Error parsing row for ID {row_id}: {e}")
        return None


def search_database(
    search_term: str, search_type: str, start_utc: int | None = None
) -> list["Ajo"]:
    """
    Search the AJO database for matching records. Note that this can
    take a while for username searches.

    Args:
        search_term: The term to search for (username or post_id)
        search_type: Type of search ('user' or 'post')
        start_utc: Optional UNIX timestamp to filter results from this time onward

    Returns:
        List of Ajo objects (empty list if none found)
    """
    # Import here to avoid circular import
    from models.ajo import Ajo

    try:
        if search_type == "post":
            query = "SELECT id, created_utc, ajo FROM ajo_database WHERE id = ?"
            result = db.fetch_ajo(query, (search_term,))

            if result:
                parsed = _parse_ajo_row(result, start_utc=start_utc)
                if parsed is None:
                    logger.debug(f"Could not parse data for post {search_term}")
                    return []

                post_id, created_utc, data = parsed
                return [Ajo.from_dict(data)]
            else:
                return []

        elif search_type == "user":
            logger.warning("Searching for user in database... This can take a while.")
            query = "SELECT id, created_utc, ajo FROM ajo_database"
            results = db.fetchall_ajo(query)

            matching_ajos = []
            parse_errors = 0

            for result in results:
                parsed = _parse_ajo_row(result, start_utc=start_utc)
                if parsed is None:
                    parse_errors += 1
                    continue

                post_id, created_utc, data = parsed

                if (
                    data.get("author") == search_term
                    or data.get("username") == search_term
                ):
                    matching_ajos.append(Ajo.from_dict(data))

            if parse_errors > 0:
                logger.warning(f"Warning: {parse_errors} rows could not be parsed")

            return matching_ajos

        else:
            return []

    except Exception as db_error:
        import traceback

        logger.error(f"Error querying database: {traceback.format_exc()} {db_error}")
        return []


# ─── Log search & event log utilities ────────────────────────────────────────


def get_recent_event_log_lines(
    num_lines: int = 5, tag: Optional[str] = None
) -> Tuple[str, str]:
    """
    Extract the last N lines from the events log and find the last event
    with a specific tag.

    Args:
        num_lines: Number of lines to extract from the end of the file (default: 5)
        tag: Tag to search for in brackets, e.g. 'ZW' to find '[ZW]' (default: None)

    Returns:
        A tuple of (log_content, time_ago) where:
        - log_content: String containing the last N lines formatted in a code block
        - time_ago: String describing how long ago the last tagged event occurred

    Raises:
        FileNotFoundError: If the log file doesn't exist
        Exception: For other errors during file reading or parsing
    """
    with open(Paths.LOGS["EVENTS"], "r", encoding="utf-8") as f:
        lines = f.readlines()
        last_n = lines[-num_lines:] if len(lines) >= num_lines else lines

    if not last_n:
        raise ValueError("Log file is empty")

    log_content = "```\n" + "".join(last_n) + "```"

    if tag is None:
        return log_content, "no tag specified"

    tag_pattern = f"[{tag.upper()}]"
    tagged_lines = [line for line in last_n if tag_pattern in line]

    if not tagged_lines:
        time_ago = f"no {tag} events found"
    else:
        last_tagged_line = tagged_lines[-1].strip()
        try:
            # Extract timestamp from format: INFO: 2026-01-07T19:45:59Z - ...
            timestamp_str = last_tagged_line.split(" - ")[0].split(": ")[1]
            last_event_time = datetime.fromisoformat(
                timestamp_str.replace("Z", "+00:00")
            )
            current_time = datetime.now(timezone.utc)

            delta = current_time - last_event_time
            delta_seconds = delta.total_seconds()

            if delta_seconds < 60:
                seconds = int(delta_seconds)
                time_ago = f"{seconds} second{'s' if seconds != 1 else ''} ago"
            elif delta_seconds < 3600:
                minutes = int(delta_seconds / 60)
                time_ago = f"{minutes} minute{'s' if minutes != 1 else ''} ago"
            else:
                hours = delta_seconds / 3600
                if hours < 48:
                    hours_int = int(hours)
                    time_ago = f"{hours_int} hour{'s' if hours_int != 1 else ''} ago"
                else:
                    days = int(hours / 24)
                    time_ago = f"{days} day{'s' if days != 1 else ''} ago"
        except (IndexError, ValueError):
            time_ago = "unknown"

    return log_content, time_ago


# ─── Module-level singleton ───────────────────────────────────────────────────

db = DatabaseManager()
