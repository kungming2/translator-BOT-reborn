#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
Defines the Ajo class and related helpers for managing translation request posts.

An Ajo is the canonical in-memory representation of a Reddit submission on
r/translator. It tracks language identification, translation status, flair,
translator credits, and notification history. Ajos are persisted to and
loaded from a local SQLite database, and their flair is synced back to Reddit
via PRAW.

Key components:
    Ajo                          -- Primary model class for a translation request post.
    Ajo.from_titolo              -- Construct a new Ajo from a parsed Titolo instance.
    Ajo.from_dict                -- Reconstruct an Ajo from a serialized dictionary.
    ajo_writer                   -- Persist an Ajo to the local database (insert or update).
    ajo_loader                   -- Load an Ajo from the local database by post ID.
    ajo_delete                   -- Permanently remove an Ajo record from the database.
    determine_flair_and_update   -- Compute and apply the correct Reddit flair for an Ajo.
...

Logger tag: [M:AJO]
"""

import ast
import logging
from typing import Any, cast

import orjson

from config import SETTINGS
from config import logger as _base_logger
from database import db
from lang.languages import converter
from models.lingvo import Lingvo
from models.titolo import Titolo
from reddit.connection import REDDIT, REDDIT_HELPER
from testing import log_testing_mode
from title.title_handling import process_title
from utility import check_url_extension, generate_image_hash

logger = logging.LoggerAdapter(_base_logger, {"tag": "M:AJO"})


# ─── Internal helpers ─────────────────────────────────────────────────────────


def _normalize_lang_field(value: "list | str | None") -> list[Lingvo]:
    """
    Normalize the original_[source|target]_language_name field to
    always be a list of Lingvo objects.

    Supports:
      - [<Lingvo: ...>] (already normalized)
      - ['Dari', 'Pashto'] (list of strings)
      - 'English' (single string)
      - None or other types -> empty list
    """
    if isinstance(value, list):
        normalized = []
        for i, x in enumerate(value):
            if isinstance(x, Lingvo):
                normalized.append(x)
            elif isinstance(x, str) and x.strip():
                lingvo_obj = converter(x.strip())
                if lingvo_obj is not None:
                    normalized.append(lingvo_obj)
            else:
                logger.debug(f"Skipping element {i}: {x}")
        logger.debug(f"Normalized lang list: {normalized}")
        return normalized

    elif isinstance(value, str) and value.strip():
        lingvo_obj = converter(value.strip())
        if lingvo_obj is None:
            logger.debug(
                "String could not be converted to Lingvo, returning empty list."
            )
            return []
        return [lingvo_obj]

    else:
        logger.debug("Lang field is None or invalid, returning empty list.")
        return []


def _fetch_submission(post_id: str) -> Any:
    """
    Fetch a PRAW submission by ID.

    :param post_id: The Reddit submission ID
    :return: PRAW submission object or None if fetch fails
    """
    try:
        return REDDIT.submission(id=post_id)
    except Exception as e:
        logger.error(f"Failed to fetch submission {post_id}: {e}")
        return None


def _convert_to_dict(input_string: str) -> dict:
    """
    Converts a Python dictionary string or JSON string to a Python dictionary.

    Args:
        input_string (str): A string containing either a Python dict or JSON

    Returns:
        dict: The converted Python dictionary

    Raises:
        ValueError: If the input cannot be parsed as either a Python dict or JSON
    """
    input_string = input_string.strip()

    try:
        result = ast.literal_eval(input_string)
        if isinstance(result, dict):
            return result
    except (ValueError, SyntaxError):
        pass

    try:
        result = orjson.loads(input_string.encode("utf-8"))
        if isinstance(result, dict):
            return result
    except orjson.JSONDecodeError:
        pass

    raise ValueError("Input could not be parsed as a Python dictionary or JSON")


def _preferred_code_from_titolo(titolo: "Titolo") -> "str | None":
    """
    Derive the preferred language code from a Titolo instance.
    Prefers final_text (resolved through the converter) over the raw
    final_code, mirroring the logic used in Ajo.from_titolo.
    """
    if titolo.final_text:
        lingvo = converter(titolo.final_text)
        return lingvo.preferred_code if lingvo is not None else titolo.final_code
    return titolo.final_code


# ─── Main Ajo class ───────────────────────────────────────────────────────────


class Ajo:
    """
    The primary class we work with that represents translation requests.
    """

    # ── Construction ──────────────────────────────────────────────────────────

    def __init__(self) -> None:
        """Initialize an Ajo with all fields set to their default values."""
        self._id: str | None = None
        self._created_utc: int | None = None
        self._author: str | None = None
        self.title_original: str | None = None
        self.title: str | None = None
        self.direction: str | None = None

        self.preferred_code: str | None = None  # store this in the DB
        self.language_history: list[str | list[str]] = []

        self.status: str | dict[str, str] = "untranslated"
        self.output_post_flair_css: str | None = None
        self.output_post_flair_text: str | None = None
        self.original_source_language_name: list[Lingvo] | None = None
        self.original_target_language_name: list[Lingvo] | None = None

        self.is_identified = False
        self.is_long = False

        self.recorded_translators: list[str] = []
        self.notified: list[str] = []
        self.time_delta: dict[str, int] = {}
        self.author_messaged = False
        self.type = "single"
        self.image_hash: str | None = None
        self.is_defined_multiple = False
        self.closed_out = False

        self._lingvo: Lingvo | None = None  # initialized lazily from preferred_code
        self._submission: Any = None  # cached PRAW submission

    def __repr__(self) -> str:
        main_fields = {
            "id": self.id,
            "direction": self.direction,
            "language_name": self.language_name,
            "status": self.status,
        }
        return f"<Ajo: ({main_fields})>"

    def __eq__(self, other: object) -> bool:
        """
        Two Ajos are defined as the same if the dictionary
        representation of their contents match.

        :param other: The other Ajo we are comparing against.
        :return: A boolean. True if their dictionary contents match,
                 False otherwise.
        """
        return self.__dict__ == other.__dict__

    @classmethod
    def from_titolo(cls, titolo: Titolo, submission: Any = None) -> "Ajo":
        """
        Construct an Ajo object from a Titolo instance and an optional PRAW submission.
        This is the primary way to construct an Ajo, as simple as:
        Ajo.from_titolo(process_title(submission.title))

        :param titolo: A Titolo instance containing parsed title information.
        :param submission: (Optional) A PRAW submission object to populate Ajo fields.
        :return: A fully constructed Ajo object.
        """
        ajo = cls()

        # Basic info
        ajo.title_original = titolo.title_original or (
            submission.title if submission else None
        )
        ajo.title = titolo.title_actual
        ajo.direction = titolo.direction

        # Set the language via preferred code
        # Use final_text to get the actual language, not final_code which is for CSS
        ajo.preferred_code = _preferred_code_from_titolo(titolo)
        ajo.initialize_lingvo()

        # Additional info
        ajo.original_source_language_name = titolo.source
        ajo.original_target_language_name = titolo.target

        # Populate language_history with actual language codes from target languages
        if titolo.target:
            # Filter out English from targets for classification purposes
            non_english_targets = [
                lang for lang in titolo.target if lang.preferred_code != "en"
            ]

            # If multiple languages (defined multiple), wrap in a list
            if len(non_english_targets) > 1:
                ajo.language_history = [
                    [lang.preferred_code for lang in non_english_targets]
                ]
                # Create status dictionary with 'untranslated' for each language code (excluding English)
                ajo.status = {
                    lang.preferred_code: "untranslated" for lang in non_english_targets
                }
                ajo.is_defined_multiple = True
                ajo.type = "multiple"
            # Check if this is a non-defined multiple (a standard "Multiple Languages" request)
            elif (
                titolo.final_code == "multiple"
                or titolo.final_text == "Multiple Languages"
            ):
                ajo.language_history = [titolo.final_code] if titolo.final_code else []
                ajo.status = "untranslated"
                ajo.is_defined_multiple = False
                ajo.type = "multiple"
            else:
                # Single language, keep as flat list
                ajo.language_history = [titolo.final_code] if titolo.final_code else []
                ajo.status = "untranslated"  # Default
        else:
            ajo.language_history = []
            ajo.status = "untranslated"

        # Populate fields from Reddit submission if available
        if submission:
            ajo.id = submission.id
            ajo.created_utc = int(submission.created_utc)
            ajo.author = str(submission.author) if submission.author else "[deleted]"

            # If the submission is a link to an image, set the image hash
            ajo.set_image_hash(submission)

        logger.debug(
            f"from_titolo: created Ajo `{ajo.id}` — "
            f"type={ajo.type}, preferred_code={ajo.preferred_code!r}, status={ajo.status!r}"
        )
        return ajo

    @classmethod
    def from_dict(cls, data: dict) -> "Ajo":
        """Reconstruct an Ajo from a serialized dictionary,
        handling legacy (Python-syntax) formats."""
        ajo = cls()

        # Determine preferred_code early
        preferred_code = data.get("preferred_code")

        language_codes_3 = data.get("language_code_3", [])
        language_codes_1 = data.get("language_code_1", [])

        # Handle defined multiple posts (lists of specific language codes)
        if isinstance(language_codes_3, list) and len(language_codes_3) > 1:
            preferred_code = "multiple"
            ajo.is_defined_multiple = True
            ajo.type = "multiple"
        # Handle legacy non-defined multiple (just code 'multiple')
        elif language_codes_3 == "multiple" or language_codes_1 == "multiple":
            preferred_code = "multiple"
            ajo.is_defined_multiple = False  # Not a defined multiple
            ajo.type = "multiple"
        # Handle legacy 'generic' code
        elif language_codes_3 == "generic":
            preferred_code = "generic"
        elif not preferred_code:
            # Try language_code_1 first (2-letter codes like 'ja' are preferred)
            code1 = data.get("language_code_1")
            if isinstance(code1, list):
                valid_codes = [c for c in code1 if isinstance(c, str) and c.strip()]
                preferred_code = valid_codes[0] if valid_codes else None
            elif isinstance(code1, str) and code1.strip():
                preferred_code = code1.strip().lower()
            else:
                # Fallback to language_code_3 (handles 'unknown', macrolanguages, etc.)
                code3 = data.get("language_code_3")
                if isinstance(code3, str) and code3.strip():
                    preferred_code = code3.strip().lower()
                else:
                    preferred_code = None

        ajo.preferred_code = preferred_code

        # Initialize Lingvo only if not multiple
        if ajo.preferred_code and ajo.preferred_code != "multiple":
            ajo.initialize_lingvo()

        read_only_properties = {"is_script", "script_code", "script_name"}

        # Set other fields
        for key, value in data.items():
            if (
                key
                in {
                    "_lingvo",
                    "language_code_1",
                    "language_code_3",
                    "language_name",
                    "country_code",
                    "is_supported",
                    "preferred_code",
                }
                | read_only_properties
            ):
                continue
            if hasattr(ajo, key):
                setattr(ajo, key, value)

        # Compatibility defaults - ensure all tracking fields are initialized
        ajo.language_history = data.get("language_history", [])
        ajo.status = data.get("status", "untranslated")
        ajo.is_identified = data.get("is_identified", False)
        ajo.is_long = data.get("is_long", False)
        ajo.closed_out = data.get("closed_out", False)

        # Initialize tracking fields with proper defaults
        ajo.recorded_translators = data.get("recorded_translators", [])
        ajo.notified = data.get("notified", [])
        ajo.time_delta = data.get("time_delta", {})
        ajo.author_messaged = data.get("author_messaged", False)

        # Normalize language name fields
        ajo.original_source_language_name = _normalize_lang_field(
            data.get("original_source_language_name")
        )
        ajo.original_target_language_name = _normalize_lang_field(
            data.get("original_target_language_name")
        )

        logger.debug(
            f"from_dict: loaded Ajo `{ajo.id}` — "
            f"type={ajo.type}, preferred_code={ajo.preferred_code!r}, status={ajo.status!r}"
        )
        return ajo

    # ── Immutable core properties ──────────────────────────────────────────────

    @property
    def id(self) -> "str | None":
        """The Reddit post ID; immutable once set."""
        return self._id

    @id.setter
    def id(self, value: str) -> None:
        if self._id is not None:
            raise AttributeError("Ajo.id is immutable once set.")
        self._id = value

    @property
    def created_utc(self) -> "int | None":
        """The Unix timestamp of post creation; immutable once set."""
        return self._created_utc

    @created_utc.setter
    def created_utc(self, value: int) -> None:
        if self._created_utc is not None:
            raise AttributeError("Ajo.created_utc is immutable once set.")
        self._created_utc = value

    @property
    def author(self) -> "str | None":
        """The Reddit username of the post author; immutable once set."""
        return self._author

    @author.setter
    def author(self, value: str) -> None:
        if self._author is not None:
            raise AttributeError("Ajo.author is immutable once set.")
        self._author = value

    # ── Lingvo / language properties ──────────────────────────────────────────

    @property
    def lingvo(self) -> "Lingvo | None":
        """The Lingvo object for this post's language; initialized
        lazily from preferred_code."""
        if not self._lingvo:
            self.initialize_lingvo()
        return self._lingvo

    @property
    def _lingvo_safe(self) -> "Lingvo":
        """Internal: returns lingvo, raising if None.
        Used by delegating properties."""
        if self._lingvo is None:
            raise AttributeError(f"Ajo `{self._id}` has no lingvo initialized.")
        return self._lingvo

    @property
    def language_code_1(self) -> str | None:
        """ISO 639-1 code delegated from the Lingvo object."""
        return self._lingvo_safe.language_code_1

    @property
    def language_code_3(self) -> str | None:
        """ISO 639-3 code delegated from the Lingvo object."""
        return self._lingvo_safe.language_code_3

    @property
    def language_name(self) -> str | None:
        """Language name delegated from the Lingvo object."""
        return self._lingvo_safe.name

    @property
    def country_code(self) -> str | None:
        """Country code delegated from the Lingvo object."""
        return self._lingvo_safe.country

    @property
    def is_supported(self) -> bool:
        """Whether the language is supported with the subreddit's flairs,
        delegated from the Lingvo object."""
        return self._lingvo_safe.supported

    @property
    def script_code(self) -> str | None:
        """Script code delegated from the Lingvo object."""
        return self._lingvo_safe.script_code

    @property
    def script_name(self) -> str | None:
        """Human-readable script name (e.g. Han Characters) resolved
        from script_code, or None."""
        if not self.script_code:
            return None
        _sc = converter(self.script_code)
        return _sc.name if _sc is not None else None

    @property
    def is_script(self) -> bool:
        """True if this is a script Lingvo."""
        return self.script_code is not None

    # ── PRAW submission cache ──────────────────────────────────────────────────

    @property
    def submission(self) -> Any:
        """
        Lazily load and cache the PRAW submission object.
        Returns None if no ID is set.
        """
        if self._submission is None and self._id is not None:
            self._submission = _fetch_submission(self._id)
        return self._submission

    def clear_submission_cache(self) -> Any:
        """
        Clear the cached PRAW submission object.
        Useful before serialization to avoid storing large objects.

        :return: The cached submission object (if any) before clearing.
        """
        cached = self._submission
        self._submission = None
        return cached

    def restore_submission_cache(self, submission: Any) -> None:
        """
        Restore a previously cached PRAW submission object.

        :param submission: The PRAW submission object to cache.
        """
        self._submission = submission

    # ── Serialization ─────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        """
        Serialize only JSON-safe fields of this Ajo object.
        Excludes internal and derived attributes like `_lingvo`, `_submission`,
        and computed properties like `language_name`, `is_supported`, etc.
        """

        def lingvo_list_to_names(lingvo_list: "list[Lingvo] | None") -> list[str]:
            if not lingvo_list:
                return []
            return [
                lv.name if hasattr(lv, "name") and lv.name is not None else str(lv)
                for lv in lingvo_list
            ]

        return {
            # Immutable core fields
            "id": self.id,
            "created_utc": self.created_utc,
            "author": self.author,
            # Title and direction info
            "title_original": self.title_original,
            "title": self.title,
            "direction": self.direction,
            # Language identification
            "preferred_code": self.preferred_code,
            "language_history": self.language_history or [],
            "original_source_language_name": lingvo_list_to_names(
                self.original_source_language_name
            ),
            "original_target_language_name": lingvo_list_to_names(
                self.original_target_language_name
            ),
            # Status tracking
            "status": self.status or "untranslated",
            "output_post_flair_css": self.output_post_flair_css,
            "output_post_flair_text": self.output_post_flair_text,
            # Boolean flags
            "is_identified": bool(self.is_identified),
            "is_long": bool(self.is_long),
            "is_defined_multiple": bool(self.is_defined_multiple),
            "closed_out": bool(self.closed_out),
            # Type classification
            "type": self.type or "single",
            # Media
            "image_hash": self.image_hash,
            # Tracking lists and timestamps
            "recorded_translators": self.recorded_translators or [],
            "notified": self.notified or [],
            "time_delta": self.time_delta or {},
            "author_messaged": bool(self.author_messaged),
        }

    # ── Lingvo initialization ──────────────────────────────────────────────────

    def initialize_lingvo(self) -> None:
        """
        Initialize self._lingvo from the preferred_code.
        """
        if self.preferred_code:
            self._lingvo = converter(self.preferred_code)

    def _reset_to_titolo(self, titolo: Titolo) -> None:
        """
        Update this Ajo instance in-place based on a Titolo instance.
        This is used by reset() to restore an Ajo to its original state.
        """
        self.title_original = titolo.title_original
        self.title = titolo.title_actual
        self.direction = titolo.direction

        # Mirror from_titolo: prefer final_text -> Lingvo -> preferred_code over raw final_code.
        self.preferred_code = _preferred_code_from_titolo(titolo)
        self.initialize_lingvo()

        self.original_source_language_name = titolo.source
        self.original_target_language_name = titolo.target

        # Reset all state fields unconditionally — a reset must wipe these
        # regardless of post type.
        self.status = "untranslated"
        self.closed_out = False
        self.time_delta = {}
        self.recorded_translators = []
        self.author_messaged = False
        self.is_identified = False

        # Determine if this should be a multiple or single post based on targets
        if titolo.target and len(titolo.target) > 1:
            # Multiple languages detected
            non_english_targets = [
                lang for lang in titolo.target if lang.preferred_code != "en"
            ]

            if len(non_english_targets) > 1:
                self.type = "multiple"
                self.is_defined_multiple = True
                self.status = {
                    lang.preferred_code: "untranslated" for lang in non_english_targets
                }
                self.language_history = [
                    [lang.preferred_code for lang in non_english_targets]
                ]
            else:
                # Only one non-English language or all English
                self.type = "single"
                self.is_defined_multiple = False
                self.status = "untranslated"
                self.language_history = [titolo.final_code] if titolo.final_code else []
        else:
            # Single language or no target
            self.type = "single"
            self.is_defined_multiple = False
            self.status = "untranslated"
            self.language_history = [titolo.final_code] if titolo.final_code else []

        logger.info(
            f"Reset to type='{self.type}', is_defined_multiple={self.is_defined_multiple}"
        )

    # ── State mutation methods ─────────────────────────────────────────────────

    def set_language(
        self, code_or_lingvo: "str | Lingvo | list", is_identified: bool = True
    ) -> None:
        """
        Change the Lingvo for this Ajo and update relevant fields.

        Parameters:
            code_or_lingvo (str, Lingvo, or list): An ISO 639-1 or 639-3 language code,
            a Lingvo object, or a list of codes/Lingvo objects for defined multiple posts.
            is_identified (bool): Whether this update was due to manual language correction.
                                  Defaults to True.
        """
        # Check if we received a list (for defined multiples)
        if isinstance(code_or_lingvo, list):
            # Convert all items to language codes
            lang_codes = []
            for item in code_or_lingvo:
                if isinstance(item, str):
                    lang_codes.append(item.lower())
                else:
                    # Assume it's a Lingvo object
                    lang_codes.append(item.preferred_code)

            # Set up as a defined multiple
            self.preferred_code = "multiple"
            self.initialize_lingvo()
            self.type = "multiple"
            self.is_defined_multiple = True

            # Initialize status as dictionary with all languages set to 'untranslated'
            self.status = {code: "untranslated" for code in lang_codes}

            # Append the list of codes to language_history only if it's not the last entry
            if not self.language_history or self.language_history[-1] != lang_codes:
                self.language_history.append(lang_codes)

            logger.debug(f"Language set to defined multiple: {lang_codes}")
        else:
            # Single language (default behavior)
            if isinstance(code_or_lingvo, str):
                self.preferred_code = code_or_lingvo.lower()
                self.initialize_lingvo()
            else:
                # Assume it's a Lingvo object
                self._lingvo = code_or_lingvo
                self.preferred_code = self._lingvo.preferred_code

            # Check if this is the "multiple" language code (non-defined multiple post)
            if self.preferred_code == "multiple":
                self.type = "multiple"
                self.is_defined_multiple = False
                logger.info("Set to non-defined multiple language post")
            else:
                # Reset multiple post flags when setting to single language
                self.type = "single"
                self.is_defined_multiple = False
                logger.info(f"Single language post: {self.language_name}")

            # Reset status to string format for single posts
            if isinstance(self.status, dict):
                # Preserve 'translated' or 'doublecheck' if any language had it
                if any(
                    s in ["translated", "doublecheck"] for s in self.status.values()
                ):
                    # Keep the most "complete" status
                    if "translated" in self.status.values():
                        self.status = "translated"
                    else:
                        self.status = "doublecheck"
                else:
                    self.status = "untranslated"

            # Update tracking fields - only append if the last entry is different
            if self.preferred_code and (
                not self.language_history
                or self.language_history[-1] != self.preferred_code
            ):
                self.language_history.append(self.preferred_code)

        # Set is_identified for both cases
        self.is_identified = is_identified

    def set_status(self, value: str) -> None:
        """
        Set the status of the post.
        Allowed values: 'translated', 'doublecheck', 'inprogress', 'missing', 'untranslated'

        Status transition rules:
        - Once marked as 'doublecheck', can only transition to 'translated'
        - Once marked as 'translated', status is final and cannot be changed

        This method is for single language posts or non-defined multiple posts only.
        For defined multiple posts, use set_defined_multiple_status() instead.
        """
        if self.is_defined_multiple:
            logger.warning(
                "Cannot use set_status() on a defined multiple post. "
                "Use set_defined_multiple_status() instead."
            )
            return

        allowed = {"translated", "doublecheck", "inprogress", "missing", "untranslated"}
        if value not in allowed:
            logger.warning(
                f"Ignoring invalid status '{value}'. Must be one of {allowed}."
            )
            return

        # Check if current status is 'translated' - cannot change from this state.
        # NOTE: This guard means set_status() must never be used to implement a reset.
        # Resetting status must go through _reset_to_titolo(), which sets self.status
        # directly and bypasses this lock.
        if hasattr(self, "status") and self.status == "translated":
            logger.warning(
                "Attempted to change status after 'translated' (final). Ignoring."
            )
            return

        # Check if current status is 'doublecheck' - can only transition to 'translated'
        if (
            hasattr(self, "status")
            and self.status == "doublecheck"
            and value != "translated"
        ):
            logger.warning(
                f"Invalid transition from 'doublecheck' to '{value}'. "
                "Only 'translated' is allowed."
            )
            return

        self.status = value
        logger.info(f"Status set to '{value}'.")

        # Automatically set closed_out to True when status is 'translated' or 'doublecheck'
        if value in {"translated", "doublecheck"}:
            self.closed_out = True

    def set_defined_multiple_status(
        self, language_code: str, status_value: str
    ) -> None:
        """
        Set the status for a specific language in a defined multiple post.
        Allowed status values: 'translated', 'doublecheck', 'inprogress', 'missing', 'untranslated'

        This method is for defined multiple posts only.
        For regular posts, use set_status() instead.

        :param language_code: The ISO language code (e.g., 'ja', 'ko', 'es')
        :param status_value: The status to set for that language
        :raises ValueError: If called on a non-defined multiple or if status value is not allowed.
        """
        if not self.is_defined_multiple:
            raise ValueError(
                "Cannot use set_defined_multiple_status() on a non-defined multiple post. Use set_status() instead."
            )

        allowed = {"translated", "doublecheck", "inprogress", "missing", "untranslated"}
        if status_value not in allowed:
            raise ValueError(f"Status must be one of {allowed}.")

        # Initialize status as a dict if it's not already
        if not isinstance(self.status, dict):
            self.status = cast(dict[str, str], {})

        # Set the status for the specific language
        self.status[language_code] = status_value

    def set_type(self, value: str) -> None:
        """
        Set the type of the post.
        Must be either 'single' or 'multiple'.
        If changing from 'multiple' to 'single', reset
        is_defined_multiple to False.
        """
        if value not in ["single", "multiple"]:
            raise ValueError("Post type must be 'single' or 'multiple'.")
        self.type = value

        # Reset is_defined_multiple if type is changed to 'single'
        if value == "single":
            self.is_defined_multiple = False

    def set_is_long(self, value: bool) -> None:
        """
        Set whether the post is marked as long.
        """
        self.is_long = bool(value)

    def set_is_defined_multiple(self, value: bool) -> None:
        """
        Set whether the post is marked as a defined multiple post.
        This should only be meaningful when type is 'multiple'.

        :param value: Boolean indicating if this is a defined multiple.
        """
        self.is_defined_multiple = bool(value)

    def toggle_is_defined_multiple(self) -> bool:
        """
        Toggle the is_defined_multiple attribute between True and False.
        Returns the new value after toggling.

        :return: The new value of is_defined_multiple after toggling.
        """
        self.is_defined_multiple = not self.is_defined_multiple
        return self.is_defined_multiple

    def set_closed_out(self, value: bool) -> None:
        """
        Set the closed_out flag indicating whether the post has been closed out.

        :param value: Boolean indicating if the post is closed out.
        """
        self.closed_out = bool(value)

    def set_time(self, status: str, moment: int) -> None:
        """
        Create or update a dictionary marking times when the status/state of the Ajo changed.
        The dictionary is keyed by status and contains Unix times of the changes.
        Note that this is shared between single and defined multiple posts;
        that is, if a defined multiple post is claimed, the timestamp will
        not be disambiguated by language.

        :param status: The status that it was changed to. Example: 'translated'.
        :param moment: The Unix UTC time when the action was taken (integer).
        """
        if not hasattr(self, "time_delta") or self.time_delta is None:
            self.time_delta = {}

        # Record the moment for this status only if it hasn't been recorded before.
        self.time_delta.setdefault(status, int(moment))

    def set_author_messaged(self, is_messaged: bool) -> None:
        """
        Set the `author_messaged` flag indicating whether the post's author has been notified of the translation.

        :param is_messaged: True if the author has been messaged, False otherwise.
        """
        self.author_messaged = is_messaged

    # ── Tracking / accumulator methods ────────────────────────────────────────

    def add_translators(self, translator_name: str) -> None:
        """
        Add the username of who translated what to the Ajo of a post
        by appending their name to the list. This allows Ziwen to track translators.

        :param translator_name: The name of the individual who made the translation.
        """
        if (
            not hasattr(self, "recorded_translators")
            or self.recorded_translators is None
        ):
            self.recorded_translators = []

        if translator_name not in self.recorded_translators:
            self.recorded_translators.append(translator_name)
            logger.debug(
                f"Added translator to recorded translators: u/{translator_name}."
            )

    def add_notified(self, notified_list: list[str]) -> None:
        """
        Add usernames who have been notified by the bot for this post.
        Ensures the same user is not contacted multiple times.

        :param notified_list: List of usernames who have been contacted regarding the post.
        """
        if not hasattr(self, "notified") or self.notified is None:
            self.notified = []

        for name in notified_list:
            if name not in self.notified:
                self.notified.append(name)
                logger.debug(f"Added notified name u/{name}.")

    def set_image_hash(self, reddit_submission: Any) -> None:
        """
        If the submission is a link post and links to an image, generate an image hash.
        """
        if not reddit_submission.is_self and check_url_extension(reddit_submission.url):
            self.image_hash = generate_image_hash(reddit_submission.url)

    # ── Reddit actions ────────────────────────────────────────────────────────

    def reset(self) -> None:
        """
        Reset this Ajo to its original state based on its Reddit post title.
        Re-fetches the submission via PRAW, re-processes the title, and re-applies
        initial parsing via from_titolo.
        """
        submission = REDDIT_HELPER.submission(id=self.id)
        titolo = process_title(submission)
        self._reset_to_titolo(titolo)

    def update_reddit(
        self, initial_update: bool = False, moderator_set: bool = False
    ) -> None:
        """
        Thin wrapper that calls the external flair update function.
        It also writes changes to the database.

        Args:
            initial_update: If True, sets flair even if unchanged
                            (default: False). This is used in initial
                            processing of posts.
            moderator_set: If True, indicates the language was set by a moderator
                           and skips adding "(Identified)" to the flair text
                           (default: False).
        """
        ajo_writer(self)
        determine_flair_and_update(
            self, initial_update=initial_update, moderator_set=moderator_set
        )


# ─── Database persistence ─────────────────────────────────────────────────────


def parse_ajo_data(data_str: str) -> dict:
    """For backwards compatibility, since older Ajos are saved as
    dictionary literals. This allows Ajo data to be passed in as a
    regular dictionary string (old behavior) or JSON (new)."""
    try:
        # Try JSON first (orjson or json)
        return orjson.loads(data_str)
    except orjson.JSONDecodeError:
        # Fallback: try Python literal parsing
        try:
            return ast.literal_eval(data_str)
        except Exception as e:
            raise ValueError(f"Failed to parse data string: {e}") from e


def ajo_writer(new_ajo: "Ajo") -> None:
    """
    Takes an Ajo object and saves it to the local Ajo database.
    Note that if a PRAW submission is attached, it will discard it
    before saving it.

    :param new_ajo: An Ajo object that should be saved.
    :return: Nothing.
    """
    ajo_id = str(new_ajo.id)
    created_time = new_ajo.created_utc

    # Temporarily clear the submission cache to avoid saving it
    cached_submission = new_ajo.clear_submission_cache()

    try:
        current_dict = new_ajo.to_dict()
        representation = orjson.dumps(current_dict).decode("utf-8")

        cursor = db.cursor_ajo
        conn = db.conn_ajo

        cursor.execute("SELECT ajo FROM ajo_database WHERE id = ?", (ajo_id,))
        row = cursor.fetchone()

        if row:
            try:
                stored_ajo_dict = orjson.loads(row["ajo"])
            except orjson.JSONDecodeError:  # Stored in an old format.
                logger.warning(
                    f"Old Ajo format detected for `{ajo_id}`; "
                    f"trying literal_eval fallback."
                )
                try:
                    stored_ajo_dict = ast.literal_eval(row["ajo"])
                    if not isinstance(stored_ajo_dict, dict):
                        raise ValueError("Fallback eval didn't yield a dict.")
                except Exception as e:
                    logger.error("Failed to decode legacy Ajo format.")
                    raise e
            if current_dict != stored_ajo_dict:
                cursor.execute(
                    "UPDATE ajo_database SET ajo = ? WHERE id = ?",
                    (representation, ajo_id),
                )
                conn.commit()
                logger.info(f"Ajo `{ajo_id}` exists, data updated.")
            else:
                logger.debug(f"Ajo `{ajo_id}` exists, but no change in data.")
        else:
            cursor.execute(
                "INSERT OR REPLACE INTO ajo_database (id, created_utc, ajo) VALUES (?, ?, ?)",
                (ajo_id, created_time, representation),
            )
            conn.commit()
            logger.info(f"Ajo `{ajo_id}` not found in database. Created new record.")
    finally:
        # Restore the cached submission after writing
        new_ajo.restore_submission_cache(cached_submission)


def ajo_loader(ajo_id: str) -> "Ajo | None":
    """Loads Ajos from the local database."""
    result = db.fetch_ajo("SELECT * FROM ajo_database WHERE id = ?", (ajo_id,))
    if result is None:
        logger.debug("No local Ajo stored.")
        return None

    try:
        data = parse_ajo_data(result["ajo"])

        # Legacy compatibility patch
        if "output_oflair_css" in data and "output_post_flair_css" not in data:
            data["output_post_flair_css"] = data.pop("output_oflair_css")

        if "output_oflair_text" in data and "output_post_flair_text" not in data:
            data["output_post_flair_text"] = data.pop("output_oflair_text")

        # Initialize the Ajo object
        ajo = Ajo.from_dict(data)

        # Re-serialize _lingvo from preferred_code if available
        if hasattr(ajo, "preferred_code") and ajo.preferred_code:
            ajo._lingvo = converter(ajo.preferred_code)

        logger.debug(f"Loaded Ajo `{ajo_id}` from local database.")
        return ajo
    except Exception as e:
        logger.error(f"Failed to load or initialize Ajo `{ajo_id}`: {e}")
        return None


def ajo_delete(ajo_id: str) -> bool:
    """
    Permanently removes an Ajo record from the ajo_database table.
    This is intentionally irreversible and should only be called when
    reclassifying a post as a Diskuto (internal/non-request post).

    :param ajo_id: The Reddit submission ID of the Ajo to remove.
    :return: True if a row was deleted, False if no matching record existed.
    """
    cursor = db.cursor_ajo
    conn = db.conn_ajo

    cursor.execute("DELETE FROM ajo_database WHERE id = ?", (str(ajo_id),))
    conn.commit()

    deleted = cursor.rowcount > 0
    if deleted:
        logger.info(f"Ajo `{ajo_id}` permanently removed from database.")
    else:
        logger.warning(f"No Ajo found with id `{ajo_id}` to delete.")
    return deleted


# ─── Reddit flair helpers ─────────────────────────────────────────────────────


def ajo_defined_multiple_flair_former(flair_dict: dict) -> str:
    """
    Takes a dictionary of defined multiple statuses and returns a formatted string
    for flair text. Example output:
    'Multiple Languages [CS, DE✔, HU✓, IT, NL✔]'

    :param flair_dict: Dict keyed by language code (ISO 639-3) with their respective states.
    :return: Formatted flair string.
    """
    formatted_entries = []

    for lang_code, status in flair_dict.items():
        lingvo_obj = converter(lang_code)

        # Convert ISO 639-3 to ISO 639-1 if possible
        used_code = (
            lingvo_obj.language_code_1 if lingvo_obj is not None else None
        ) or lang_code

        # Find the symbol corresponding to the status in the legend, default to empty string
        symbol = next(
            (
                sym
                for sym, val in SETTINGS["defined_multiple_legend"].items()
                if val == status
            ),
            "",
        )

        # Format language code + symbol, e.g. "DE✔"
        formatted_entries.append(f"{used_code.upper()}{symbol}")

    # Sort alphabetically and join with commas, then wrap in brackets
    joined = ", ".join(sorted(formatted_entries))
    return f"[{joined}]"


def determine_flair_and_update(
    ajo: Ajo, initial_update: bool = False, moderator_set: bool = False
) -> None:
    """
    Determine the correct flair CSS and text based on ajo attributes
    and update the Reddit submission flair.

    Args:
        ajo: The Ajo object containing post information
        initial_update: If True, always sets flair even if unchanged
                        (default: False). Used when processing a post
                        for the very first time.
        moderator_set: If True, indicates the language was set by a moderator
                       and skips adding "(Identified)" to the flair text
                       (default: False).
    """
    from reddit.startup import STATE

    testing_mode = SETTINGS["testing_mode"]
    post_templates = STATE.post_templates
    submission = REDDIT.submission(id=ajo.id)

    # Special language name values that bypass standard code-based flair
    unq_types = {"Unknown", "Multiple Languages", "Generic", ""}

    output_flair_css: str = "generic"
    output_flair_text: str = "Generic"
    code_tag: str | None = None

    if ajo.lingvo is None:
        # Fallback flair when no lingvo is available
        if not testing_mode:
            if output_flair_css in post_templates:
                template_id = post_templates[output_flair_css]
                submission.flair.select(
                    flair_template_id=template_id, text=output_flair_text
                )
        else:
            log_testing_mode(
                output_text=output_flair_text,
                title=f"Flair Update Dry Run for Submission {ajo.id}",
                metadata={
                    "Submission ID": ajo.id,
                    "Flair CSS": output_flair_css,
                    "Flair Template ID": post_templates.get(output_flair_css, "N/A"),
                    "Submission Title": getattr(ajo, "title_original", "N/A"),
                    "Post Type": ajo.type,
                    "Note": "No lingvo object available",
                },
            )
        logger.warning(
            f"Set post `{ajo.id}` to CSS `{output_flair_css}` "
            f"and text `{output_flair_text}` (no lingvo)."
        )

        # Sync flair output back to Ajo instance
        ajo.output_post_flair_css = output_flair_css
        ajo.output_post_flair_text = output_flair_text
        return  # Early return to prevent AttributeError

    language_name = ajo.lingvo.name or ""
    language_code_1 = (
        ajo.lingvo.language_code_1
        if isinstance(ajo.lingvo.language_code_1, str)
        else None
    )
    language_code_3 = (
        ajo.lingvo.language_code_3
        if isinstance(ajo.lingvo.language_code_3, str)
        else None
    )

    # Helper to set code_tag and css for a given code and css
    def set_code_and_css(code: str, css: str) -> None:
        nonlocal code_tag, output_flair_css
        code_tag = f"[{code.upper()}]"
        output_flair_css = css

    if ajo.type == "single":
        # FIX: Check if this is a script (used for Unknown posts that were identified)
        # Scripts should always display as [?], not as their script code
        is_script = getattr(ajo, "is_script", False)

        if is_script:
            # Scripts always use [?] display, regardless of the script code
            code_tag = "[?]"
            output_flair_css = "unknown"
            logger.debug(
                f">>> Update Reddit: Script detected for post `{ajo.id}`, using [?]."
            )
        elif language_name not in unq_types:
            if ajo.is_supported:
                if language_code_1:
                    set_code_and_css(language_code_1, language_code_1)
                elif language_code_3:
                    set_code_and_css(language_code_3, language_code_3)
            else:
                if language_code_1:
                    set_code_and_css(language_code_1, "generic")
                elif language_code_3:
                    set_code_and_css(language_code_3, "generic")
        else:
            # Handle special names
            if language_name == "Unknown":
                code_tag = "[?]"
                output_flair_css = "unknown"
                logger.debug(f">>> Update Reddit: Unknown post `{ajo.id}`.")
            else:  # None, Generic, or empty
                code_tag = "[--]"
                output_flair_css = "generic"
    else:  # multiple posts
        output_flair_css = "multiple"

        if not hasattr(ajo, "status"):
            ajo.status = {}
        if isinstance(ajo.status, dict):
            code_tag = ajo_defined_multiple_flair_former(ajo.status)
        else:
            code_tag = None

    # Determine flair text
    if ajo.type == "single":
        status_map = {
            "translated": ("translated", f"Translated {code_tag}"),
            "doublecheck": ("doublecheck", f"Needs Review {code_tag}"),
            "inprogress": ("inprogress", f"In Progress {code_tag}"),
            "missing": ("missing", f"Missing Assets {code_tag}"),
        }
        if isinstance(ajo.status, str) and ajo.status in status_map:
            output_flair_css, output_flair_text = status_map[ajo.status]
        else:
            # Default untranslated flair text
            output_flair_text = language_name
            if ajo.country_code:
                output_flair_text += f" {{{ajo.country_code}}}"
            if language_name != "Unknown":
                # Only add "(Identified)" if NOT moderator_set
                if getattr(ajo, "is_identified", False) and not moderator_set:
                    output_flair_text += " (Identified)"
                if getattr(ajo, "is_long", False):
                    output_flair_text += " (Long)"
            else:
                # Unknown post script flair
                if getattr(ajo, "is_script", False):
                    output_flair_text = getattr(ajo, "script_name", "") + " (Script)"
    else:  # This is a multiple post.
        # Multiple post flair text
        if code_tag is None:  # Not defined
            output_flair_text = "Multiple Languages"
        else:  # Defined
            output_flair_text = f"Multiple Languages {code_tag}"

    # Update flair on Reddit if template exists
    if output_flair_css in post_templates:
        template_id = post_templates[output_flair_css]
        logger.debug(f"Template for CSS `{output_flair_css}` is `{template_id}`.")

        # Get current flair info
        current_flair: str | None = getattr(submission, "link_flair_text", None)
        current_flair_template_id: str | None = getattr(
            submission, "link_flair_template_id", None
        )

        # Only update flair if something actually changed
        flair_changed: bool = (
            current_flair != output_flair_text
            or current_flair_template_id != template_id
        )

        if not testing_mode:
            if flair_changed:
                submission.flair.select(
                    flair_template_id=template_id, text=output_flair_text
                )
                logger.debug(
                    f"Updated post `{ajo.id}` flair to `{output_flair_text}` "
                    f"(template `{template_id}`)."
                )
            elif initial_update:
                submission.flair.select(
                    flair_template_id=template_id, text=output_flair_text
                )
                logger.info(
                    f"Initial flair set for post `{ajo.id}` to `{output_flair_text}` "
                    f"(template `{template_id}`)."
                )
            else:
                logger.debug(
                    f"Skipped flair update for `{ajo.id}` "
                    f"(already `{output_flair_text}` / `{template_id}`)."
                )
        else:
            log_testing_mode(
                output_text=output_flair_text,
                title=f"Flair Update Dry Run for Submission {ajo.id}",
                metadata={
                    "Submission ID": ajo.id,
                    "Flair CSS": output_flair_css,
                    "Flair Template ID": template_id,
                    "Submission Title": getattr(ajo, "title_original", "N/A"),
                    "Post Type": ajo.type,
                },
            )
        logger.debug(
            f"Set post `{ajo.id}` to CSS `{output_flair_css}` and text `{output_flair_text}`."
        )

    # Sync flair output back to Ajo instance
    ajo.output_post_flair_css = output_flair_css
    ajo.output_post_flair_text = output_flair_text
