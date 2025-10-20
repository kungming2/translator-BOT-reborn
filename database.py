#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
Handles database reading and writing. While the top-level stuff is
all in SQLite, there are also some plain text recording functions here.

This module provides a unified interface for all database operations across
the bot's three SQLite databases:

1. cache.db - Temporary data and caching:
   - comment_cache: Stores comment content for edit detection
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
"""

import csv
import json
import os
import pprint
import sqlite3
import time
from ast import literal_eval
from typing import TYPE_CHECKING, Any

from config import SETTINGS, Paths, logger
from time_handling import convert_to_day

if TYPE_CHECKING:
    from discord.ext.commands import Context

    from models.ajo import Ajo

"""SQLITE DATABASE ACCESS"""


class DatabaseManager:
    """
    Unified class to handle writes and reads to the three databases.
    """

    def __init__(self) -> None:
        self._conn_cache: sqlite3.Connection | None = None
        self._conn_main: sqlite3.Connection | None = None
        self._conn_ajo: sqlite3.Connection | None = None

    @staticmethod
    def _connect(file_path: str) -> sqlite3.Connection:
        conn = sqlite3.connect(file_path)
        conn.row_factory = sqlite3.Row  # Optional: allows dictionary-like row access
        return conn

    @property
    def conn_cache(self) -> sqlite3.Connection:
        if self._conn_cache is None:
            self._conn_cache = self._connect(Paths.DATABASE["CACHE"])
        return self._conn_cache

    @property
    def conn_main(self) -> sqlite3.Connection:
        if self._conn_main is None:
            self._conn_main = self._connect(Paths.DATABASE["MAIN"])
        return self._conn_main

    @property
    def conn_ajo(self) -> sqlite3.Connection:
        if self._conn_ajo is None:
            self._conn_ajo = self._connect(Paths.DATABASE["AJO"])
        return self._conn_ajo

    @property
    def cursor_cache(self) -> sqlite3.Cursor:
        return self.conn_cache.cursor()

    @property
    def cursor_main(self) -> sqlite3.Cursor:
        return self.conn_main.cursor()

    @property
    def cursor_ajo(self) -> sqlite3.Cursor:
        return self.conn_ajo.cursor()

    def close_all(self) -> None:
        for conn in (self._conn_cache, self._conn_main, self._conn_ajo):
            if conn:
                conn.close()

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


"""CREATES DATABASES IF THEY DO NOT EXIST"""


def _initialize_cache_db() -> None:
    """Internal function to initialize the cache database if it
    does not exist."""
    db_path = Paths.DATABASE["CACHE"]

    if os.path.exists(db_path):
        logger.debug(f"{db_path} already exists. Skipping cache.db.")
        return

    logger.info(f"Creating cache.db at {db_path}...")

    create_statements = [
        """
        CREATE TABLE comment_cache (
            id TEXT PRIMARY KEY,
            content TEXT
        )
        """,
        """
        CREATE TABLE multiplier_cache (
            month_year TEXT,
            language_code TEXT,
            language_multiplier INTEGER
        )
        """,
    ]

    _initialize_db(db_path, create_statements)


def _initialize_ajo_db() -> None:
    """Internal function to initialize the Ajo database if it
    does not exist."""
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
    """Internal function to initialize the main database if it
    does not exist."""
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
            id TEXT
        )
        """,
        """
        CREATE TABLE old_posts (
            id TEXT PRIMARY KEY
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
            month_year TEXT,
            comment_id TEXT,
            username TEXT,
            points INTEGER,
            post_id TEXT
        )
        """,
        """
        CREATE INDEX index_total_points_usernames ON total_points (username)
        """,
    ]

    _initialize_db(db_path, create_statements)


def _initialize_db(db_path: str, statements: list[str]) -> None:
    """Internal function to run the table creation commands."""
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
        logger.info(f"Error initializing {db_path}: {e}")
    finally:
        if conn:
            conn.close()


def initialize_all_databases() -> None:
    """
    Creates all three required databases if they do not exist.
    This is unlikely to be often used as the databases should transfer over.
    """
    _initialize_cache_db()
    _initialize_ajo_db()
    _initialize_main_db()


"""NON-SQLITE FILE WRITING"""


def record_activity_csv(data_tuple: tuple) -> None:
    """
    Append a tuple of data to a CSV file. The tuple should start with
    an activity type, followed by date and time, etc. This CSV file is
    generally used to record parameters like memory used, notifications
    time sent, etc.

    :param data_tuple: Tuple of data to write as a CSV row.
    """
    with open(Paths.LOGS["ACTIVITY"], mode="a", newline="") as csv_file:
        writer = csv.writer(csv_file, quoting=csv.QUOTE_MINIMAL)
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
    line = f"\n| {timestamp_utc} | {filtered_title} | {filter_type} |"

    with open(Paths.LOGS["FILTER"], "a", encoding="utf-8") as f:
        f.write(line)


"""SPECIFIC SEARCH/RETRIEVAL FUNCTIONS"""


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

        # Filter by time if start_utc is provided
        if start_utc is not None and created_utc < start_utc:
            return None

        data_json = result["ajo"] if isinstance(result, sqlite3.Row) else result[2]

        # Parse the JSON/dict data
        if isinstance(data_json, dict):
            # Already a dict, use as-is
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
        # Fixed: Handle both Row and tuple objects properly
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

                # Check if this post matches the username
                if (
                    data.get("author") == search_term
                    or data.get("username") == search_term
                ):
                    matching_ajos.append(Ajo.from_dict(data))

            if parse_errors > 0:
                logger.debug(f"Warning: {parse_errors} rows could not be parsed")

            return matching_ajos

        else:
            # Unknown search type, return empty list
            return []

    except Exception as db_error:
        logger.debug(f"Error querying database: {str(db_error)}")
        import traceback

        traceback.print_exc()
        return []


async def search_logs(ctx: "Context", search_term: str, term_type: str) -> None:
    """
    Internal helper function to search through log files and the
    Ajo database for a given term, which can be a username or a post ID.

    Args:
        ctx: Discord context
        search_term: The term to search for (username or post_id)
        term_type: Type of search ('user' or 'post') for display purposes
    """
    days_back = SETTINGS["log_search_days"]  # How many days back to search
    log_files = {
        "FILTER": Paths.LOGS["FILTER"],
        "EVENTS": Paths.LOGS["EVENTS"],
        "ERROR": Paths.LOGS["ERROR"],
    }

    # Calculate the cutoff time in UNIX seconds
    cutoff_utc = int(time.time()) - (days_back * 86400)

    try:
        log_lines = []

        # Search through log files
        for log_name, log_path in log_files.items():
            try:
                with open(
                    log_path, "r", encoding="utf-8", errors="replace"
                ) as log_file:
                    for line in log_file:
                        if search_term in line:
                            log_lines.append(f"[{log_name}] {line.strip()}")
            except FileNotFoundError:
                await ctx.send(
                    f"Warning: {log_name} log file not found at `{log_path}`"
                )
                continue

        # Search database for historical information (with time filter)
        db_results = search_database(search_term, term_type, start_utc=cutoff_utc)

        # Check if we have any results at all
        if not log_lines and not db_results:
            await ctx.send(
                f"No entries found for {term_type} `{search_term}` in the last {days_back} days."
            )
            return

        # Build response with sections
        response = f"Search results for {term_type} `{search_term}` (last {days_back} days):\n```\n"

        # Add log file results
        if log_lines:
            response += f"=== LOG FILES ({len(log_lines)} matches) ===\n"
            for line in log_lines:
                # Check if adding this line would exceed Discord's limit
                if len(response) + len(line) + 10 > 1900:
                    response += "```"
                    await ctx.send(response)
                    response = "```\n"

                response += line + "\n"

            response += "\n"  # Extra spacing between sections

        # Add database results
        if db_results:
            response += f"=== DATABASE ({len(db_results)} records) ===\n"
            for ajo in db_results:
                # Format the Ajo object as a string
                ajo_str = (
                    f"Post ID: {ajo.id}\n"
                    f"  Author: u/{ajo.author}\n"
                    f"  Status: {ajo.status}\n"
                    f"  Language: {ajo.language_name} ({ajo.preferred_code})\n"
                    f"  Title: {ajo.title}\n"
                    f"  Direction: {ajo.direction}\n"
                    f"---"
                )

                # Check if adding this entry would exceed Discord's limit
                if len(response) + len(ajo_str) + 10 > 1900:
                    response += "```"
                    await ctx.send(response)
                    response = "```\n"

                response += ajo_str + "\n"

        response += "```"
        print(response)
        await ctx.send(response)

    except Exception as e:
        await ctx.send(f"An error occurred: {str(e)}")
        import traceback

        traceback.print_exc()


def _show_menu() -> None:
    print("\nSelect a search to run:")
    print("1. Database search (enter a query to test)")
    print("2. Initialize databases if they do not already exist")


# Instantiate a global shared database manager (singleton-like)
db = DatabaseManager()


if __name__ == "__main__":
    while True:
        _show_menu()
        choice = input("Enter your choice (1-2): ")

        if choice == "x":
            print("Exiting...")
            break

        if choice not in ["1", "2"]:
            print("Invalid choice, please try again.")
            continue

        if choice == "1":
            term_to_search = input("Enter the search term (username or post_id): ")
            type_to_search = input("Enter the search type (user/post): ")
            derived_ajos = search_database(term_to_search, type_to_search)
            for item in derived_ajos:
                pprint.pprint(vars(item))
                print("\n\n")

        elif choice == "2":
            initialize_all_databases()
