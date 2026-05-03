#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
Utilities for infrequent ISO 639-3 dataset maintenance.
...

Logger tag: [WY:CODE]
"""

import csv
import logging
import re
from pathlib import Path

from config import Paths
from config import logger as _base_logger

logger = logging.LoggerAdapter(_base_logger, {"tag": "WY:CODE"})


# ─── Configuration ────────────────────────────────────────────────────────────

# Location of our primary ISO dataset for codes
CSV_PATH = Path(Paths.DATASETS["ISO_CODES"])
CSV_FIELDS = ["ISO 639-3", "ISO 639-1", "Language Name", "Alternate Names"]
ISO_639_3_RE = re.compile(r"^[a-z]{3}$")
ISO_639_1_RE = re.compile(r"^[a-z]{2}$")


# ─── I/O helpers ──────────────────────────────────────────────────────────────


def _normalize_iso_639_3(value: str) -> str | None:
    """Return a normalized ISO 639-3 code, or None if invalid."""
    code = value.strip().lower()
    if not ISO_639_3_RE.fullmatch(code):
        print("ISO 639-3 code must be exactly three ASCII letters.")
        return None
    return code


def _normalize_iso_639_1(value: str) -> str | None:
    """Return a normalized optional ISO 639-1 code, or None if invalid."""
    code = value.strip().lower()
    if not code:
        return ""
    if not ISO_639_1_RE.fullmatch(code):
        print("ISO 639-1 code must be blank or exactly two ASCII letters.")
        return None
    return code


def _row_for_code(rows: list[dict[str, str]], iso_639_3: str) -> dict[str, str] | None:
    """Return the dataset row matching an ISO 639-3 code."""
    for row in rows:
        if row["ISO 639-3"] == iso_639_3:
            return row
    return None


def load_csv() -> list[dict[str, str]] | None:
    """Load the ISO dataset CSV."""
    try:
        encodings = ["utf-8", "latin-1", "iso-8859-1", "cp1252"]
        for encoding in encodings:
            try:
                with open(CSV_PATH, newline="", encoding=encoding) as file:
                    reader = csv.DictReader(file)
                    if reader.fieldnames != CSV_FIELDS:
                        logger.error(
                            "Unexpected ISO CSV columns: "
                            f"{reader.fieldnames}. Expected {CSV_FIELDS}."
                        )
                        return None
                    rows = [dict(row) for row in reader]
                logger.debug(f"Loaded CSV with encoding {encoding!r}")
                return rows
            except (UnicodeDecodeError, UnicodeError):
                continue

        logger.error("Could not decode file with any standard encoding")
        return None
    except FileNotFoundError:
        logger.error(f"File not found at `{CSV_PATH}`")
        return None


def save_csv(rows: list[dict[str, str]]) -> None:
    """Save rows back to the ISO dataset CSV."""
    try:
        with open(CSV_PATH, "w", newline="", encoding="utf-8") as file:
            writer = csv.DictWriter(file, fieldnames=CSV_FIELDS, lineterminator="\r\n")
            writer.writeheader()
            writer.writerows(rows)
        logger.info("File saved successfully")
    except Exception as e:
        logger.error(f"Failed to save file: {e}")


# ─── CRUD operations ──────────────────────────────────────────────────────────


def create_entry() -> None:
    """Create a new ISO 639-3 entry."""
    rows = load_csv()
    if rows is None:
        return

    iso_639_3 = _normalize_iso_639_3(input("Enter ISO 639-3 code: "))
    if iso_639_3 is None:
        return

    if _row_for_code(rows, iso_639_3):
        print(f"ISO 639-3 code '{iso_639_3}' already exists.")
        return

    language_name = input("Enter Language Name: ").strip()
    iso_639_1 = _normalize_iso_639_1(input("Enter ISO 639-1 code (blank if none): "))
    if iso_639_1 is None:
        return
    alternate_names = input(
        "Enter Alternate Names (semicolon-separated, blank if none): "
    ).strip()

    if not iso_639_3 or not language_name:
        print("ISO 639-3 and Language Name cannot be empty.")
        return

    new_row = {
        "ISO 639-3": iso_639_3,
        "ISO 639-1": iso_639_1,
        "Language Name": language_name,
        "Alternate Names": alternate_names,
    }

    rows.append(new_row)
    save_csv(rows)
    print(f"✓ Created new entry: {iso_639_3} - {language_name}")


def update_entry() -> None:
    """Update fields for an existing ISO 639-3 entry."""
    rows = load_csv()
    if rows is None:
        return

    iso_639_3 = _normalize_iso_639_3(input("Enter ISO 639-3 code to update: "))
    if iso_639_3 is None:
        return

    row = _row_for_code(rows, iso_639_3)
    if row is None:
        print(f"ISO 639-3 code '{iso_639_3}' not found.")
        return

    print(f"Current Language Name: {row['Language Name']}")
    print(f"Current ISO 639-1: {row['ISO 639-1'] or '(none)'}")
    print(f"Current Alternate Names: {row['Alternate Names'] or '(none)'}")

    new_name = input("Enter updated Language Name (blank to keep current): ").strip()
    new_iso_639_1 = input(
        "Enter updated ISO 639-1 code (blank to keep current, '-' to clear): "
    )
    new_alternate_names = input(
        "Enter updated Alternate Names (blank to keep current, '-' to clear): "
    ).strip()

    updates: dict[str, str] = {}
    if new_name:
        updates["Language Name"] = new_name
    if new_iso_639_1.strip():
        if new_iso_639_1.strip() == "-":
            updates["ISO 639-1"] = ""
        else:
            normalized_iso_639_1 = _normalize_iso_639_1(new_iso_639_1)
            if normalized_iso_639_1 is None:
                return
            updates["ISO 639-1"] = normalized_iso_639_1
    if new_alternate_names:
        updates["Alternate Names"] = (
            "" if new_alternate_names == "-" else new_alternate_names
        )

    if not updates:
        print("No changes made.")
        return

    row.update(updates)
    save_csv(rows)
    print(f"✓ Updated {iso_639_3}: {', '.join(updates.keys())}")


def deprecate_entry() -> None:
    """Remove a row with the specified ISO 639-3 code."""
    rows = load_csv()
    if rows is None:
        return

    iso_639_3 = _normalize_iso_639_3(input("Enter ISO 639-3 code to deprecate: "))
    if iso_639_3 is None:
        return

    row = _row_for_code(rows, iso_639_3)
    if row is None:
        print(f"ISO 639-3 code '{iso_639_3}' not found.")
        return

    language_name = row["Language Name"]
    confirm = (
        input(
            f"Are you sure you want to delete '{iso_639_3} - {language_name}'? (yes/no): "
        )
        .strip()
        .lower()
    )

    if confirm != "yes":
        print("Cancelled.")
        return

    save_csv([row for row in rows if row["ISO 639-3"] != iso_639_3])
    print(f"✓ Deprecated {iso_639_3} - {language_name}")
