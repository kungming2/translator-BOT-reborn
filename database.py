#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
Handles database reading and writing. While the top-level stuff is
all in SQLite, there are also some plain text recording functions here.
"""
import csv
import datetime
import os
import sqlite3

from config import Paths, logger


"""SQLITE DATABASE ACCESS"""


class DatabaseManager:
    def __init__(self):
        self._conn_cache = None
        self._conn_main = None
        self._conn_ajo = None

    @staticmethod
    def _connect(file_path):
        conn = sqlite3.connect(file_path)
        conn.row_factory = sqlite3.Row  # Optional: allows dictionary-like row access
        return conn

    @property
    def conn_cache(self):
        if self._conn_cache is None:
            self._conn_cache = self._connect(Paths.DATABASE['CACHE'])
        return self._conn_cache

    @property
    def conn_main(self):
        if self._conn_main is None:
            self._conn_main = self._connect(Paths.DATABASE['MAIN'])
        return self._conn_main

    @property
    def conn_ajo(self):
        if self._conn_ajo is None:
            self._conn_ajo = self._connect(Paths.DATABASE['AJO'])
        return self._conn_ajo

    @property
    def cursor_cache(self):
        return self.conn_cache.cursor()

    @property
    def cursor_main(self):
        return self.conn_main.cursor()

    @property
    def cursor_ajo(self):
        return self.conn_ajo.cursor()

    def close_all(self):
        for conn in (self._conn_cache, self._conn_main, self._conn_ajo):
            if conn:
                conn.close()

    def fetch_ajo(self, query: str, params: tuple = (), used_database: str = "ajo"):
        """
        Execute a SELECT query and return a single row from the specified database.

        :param query: SQL SELECT statement
        :param params: Query parameters as a tuple
        :param used_database: One of 'ajo', 'main', or 'cache'
        :return: A single row (as a tuple or sqlite3.Row), or None
        """
        cursor = {
            "ajo": self.cursor_ajo,
            "main": self.cursor_main,
            "cache": self.cursor_cache
        }.get(used_database)

        if cursor is None:
            raise ValueError(f"Invalid database key '{used_database}'. Must be 'ajo', 'main', or 'cache'.")

        cursor.execute(query, params)
        return cursor.fetchone()

    def fetchall_ajo(self, query: str, params: tuple = ()):
        """
        Execute a SELECT query and return all matching rows from the AJO database.

        :param query: SQL SELECT statement
        :param params: Query parameters as a tuple
        :return: A list of rows (sqlite3.Row objects)
        """
        cursor = self.cursor_ajo
        cursor.execute(query, params)
        return cursor.fetchall()


"""CREATES DATABASES IF THEY DO NOT EXIST"""


def initialize_cache_db():

    db_path = Paths.DATABASE['CACHE']

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
        """
    ]

    _initialize_db(db_path, create_statements)


def initialize_ajo_db():

    db_path = Paths.DATABASE['AJO']

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


def initialize_main_db():

    db_path = Paths.DATABASE['MAIN']

    if os.path.exists(db_path):
        logger.debug(f"{db_path} already exists. Skipping main.db.")
        return

    logger.info(f"Creating main.db at {db_path}...")

    create_statements = [
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
            pid TEXT,
            username TEXT,
            points INTEGER,
            oid TEXT
        )
        """,
        """
        CREATE INDEX index_total_points_usernames ON total_points (username)
        """
    ]

    _initialize_db(db_path, create_statements)


def _initialize_db(db_path, statements):
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


def initialize_all_databases():
    initialize_cache_db()
    initialize_ajo_db()
    initialize_main_db()


"""NON-SQLITE FILE WRITING"""


def record_activity_csv(data_tuple):
    """
    Append a tuple of data to a CSV file. The tuple should start with
    an activity type, followed by date and time, etc. This CSV file is
    generally used to record parameters like memory used, notifications
    time sent, etc.

    :param data_tuple: Tuple of data to write as a CSV row.
    """
    with open(Paths.LOGS['ACTIVITY'], mode='a', newline='') as csv_file:
        writer = csv.writer(csv_file, quoting=csv.QUOTE_MINIMAL)
        writer.writerow(data_tuple)


def record_filter_log(filtered_title, created_timestamp, filter_type):
    """
    Append an entry to the filter log file as a Markdown table row.

    :param filtered_title: Title of the filtered post.
    :param created_timestamp: Unix timestamp of when the post was created.
    :param filter_type: Code of the violated filter rule.
    """
    timestamp_utc = datetime.datetime.fromtimestamp(created_timestamp).strftime("%Y-%m-%d")
    line = f"\n{timestamp_utc} | {filtered_title} | {filter_type}"

    with open(Paths.LOGS['FILTER'], 'a', encoding='utf-8') as f:
        f.write(line)


# Instantiate a global shared database manager (singleton-like)
db = DatabaseManager()


if __name__ == "__main__":
    initialize_all_databases()
