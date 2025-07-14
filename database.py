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

from wasabi import msg

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


"""NON-SQLITE FILE WRITING"""


def record_activity_csv(data_tuple):
    """
    Append a tuple of data to a CSV file. The tuple should start with
    an activity type, followed by date and time, etc.

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
    ajo_cursor = db.cursor_ajo
    msg.info("DB path: {}".format(os.path.abspath(Paths.DATABASE['AJO'])))
    ajo_cursor.execute("SELECT * FROM ajo_database ORDER BY RANDOM() LIMIT 1")
    row = ajo_cursor.fetchone()
    msg.good(f"Row in DB: {dict(row)}")
