#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
Defines the Ajo post structure and class, along with related functions.
"""
import ast
from typing import List

import orjson
import pprint

from config import logger, SETTINGS
from connection import REDDIT, REDDIT_HELPER
from database import db
from languages import Lingvo, converter
from testing import log_testing_mode
from title_handling import Titolo, process_title
from utility import check_url_extension, generate_image_hash


def ajo_writer(new_ajo):
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
        representation = orjson.dumps(new_ajo.to_dict()).decode("utf-8")

        cursor = db.cursor_ajo
        conn = db.conn_ajo

        cursor.execute("SELECT ajo FROM ajo_database WHERE id = ?", (ajo_id,))
        row = cursor.fetchone()

        if row:
            try:
                stored_ajo_dict = orjson.loads(row["ajo"])
            except orjson.JSONDecodeError:  # Stored in an old format.
                logger.warning("[ZW] ajo_writer: Old Ajo format detected; trying literal_eval fallback.")
                try:
                    stored_ajo_dict = ast.literal_eval(row["ajo"])
                    if not isinstance(stored_ajo_dict, dict):
                        raise ValueError("Fallback eval didn't yield a dict.")
                except Exception as e:
                    logger.exception("[ZW] ajo_writer: Failed to decode legacy Ajo format.")
                    raise e
            if new_ajo.to_dict() != stored_ajo_dict:
                cursor.execute(
                    "UPDATE ajo_database SET ajo = ? WHERE id = ?", (representation, ajo_id)
                )
                conn.commit()
                logger.info("[ZW] ajo_writer: Ajo exists, data updated.")
            else:
                logger.info("[ZW] ajo_writer: Ajo exists, but no change in data.")
        else:
            cursor.execute(
                "INSERT OR REPLACE INTO ajo_database (id, created_utc, ajo) VALUES (?, ?, ?)",
                (ajo_id, created_time, representation)
            )
            conn.commit()
            logger.info("[ZW] ajo_writer: New Ajo not found in the database.")
            logger.info("[ZW] ajo_writer: Wrote Ajo to local database.")
    finally:
        # Restore the cached submission after writing
        new_ajo.restore_submission_cache(cached_submission)


def parse_ajo_data(data_str):
    """For backwards compatability, since older Ajos are saved as
    dictionary literals."""
    try:
        # Try JSON first (orjson or json)
        return orjson.loads(data_str)
    except orjson.JSONDecodeError:
        # Fallback: try Python literal parsing
        try:
            return ast.literal_eval(data_str)
        except Exception as e:
            raise ValueError(f"Failed to parse data string: {e}")


def ajo_loader(ajo_id):
    result = db.fetch_ajo("SELECT * FROM ajo_database WHERE id = ?", (ajo_id,))
    if result is None:
        logger.debug("[ZW] ajo_loader: No local Ajo stored.")
        return None

    try:
        data = parse_ajo_data(result["ajo"])

        # Normalize language name fields to lists of Lingvo objects
        if "original_source_language_name" in data:
            data["original_source_language_name"] = _normalize_lang_field(data["original_source_language_name"])

        if "original_target_language_name" in data:
            data["original_target_language_name"] = _normalize_lang_field(data["original_target_language_name"])

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

        logger.debug("[ZW] ajo_loader: Loaded Ajo from local database.")
        return ajo
    except Exception as e:
        logger.exception(f"[ZW] ajo_loader: Failed to load or initialize Ajo: {e}")
        return None


def _normalize_lang_field(value):
    """
    Normalize the original_[source|target]_language_name field to
    always be a list of Lingvo objects.
    Supports:
      - [<Lingvo: ...>] (already normalized)
      - 'Japanese' (single string)
      - None or other types -> empty list
    """
    if isinstance(value, list):
        # Check if already a list of Lingvo or empty list
        if all(isinstance(x, Lingvo) for x in value):
            return value
        # If list of strings, convert each to Lingvo
        if all(isinstance(x, str) for x in value):
            return [Lingvo(name=x) for x in value]
        # Mixed or unknown types - fallback empty list or raise
        return []
    if isinstance(value, str):
        return [Lingvo(name=value)]
    return []


"""MAIN AJO CLASS"""


class Ajo:
    """
    The main class we work with that represents translation requests.
    """

    def __init__(self):
        self._id = None
        self._created_utc = None
        self._author = None
        self.title_original = None
        self.title = None
        self.direction = None

        self.preferred_code = None  # store this in the DB
        self.language_history = []

        self.status = "untranslated"
        self.output_post_flair_css = None
        self.output_post_flair_text = None
        self.original_source_language_name = None
        self.original_target_language_name = None

        self.is_identified = False
        self.is_long = False

        # New additions
        self.recorded_translators = []
        self.notified = []
        self.time_delta = {}
        self.author_messaged = False
        self.type = "single"
        self.image_hash = None
        self.is_defined_multiple = False  # New attribute

        self._lingvo = None  # initialized lazily from preferred_code
        self._submission = None  # cached PRAW submission

    def initialize_lingvo(self):
        """
        Initialize self._lingvo from the preferred_code.
        """
        if self.preferred_code:
            self._lingvo = converter(self.preferred_code)

    def __repr__(self):
        main_fields = {
            "id": self.id,  # Include the ID
            "direction": self.direction,  # Already included
            "language_name": self.language_name,
            "status": self.status,
        }
        return f"<Ajo: ({main_fields})>"

    def __eq__(self, other):
        """
        Two Ajos are defined as the same if the dictionary
        representation of their contents match.

        :param other: The other Ajo we are comparing against.
        :return: A boolean. True if their dictionary contents match,
                 False otherwise.
        """

        return self.__dict__ == other.__dict__

    @property
    def id(self):
        return self._id

    @id.setter
    def id(self, value):
        if self._id is not None:
            raise AttributeError("Ajo.id is immutable once set.")
        self._id = value

    @property
    def created_utc(self):
        return self._created_utc

    @created_utc.setter
    def created_utc(self, value):
        if self._created_utc is not None:
            raise AttributeError("Ajo.created_utc is immutable once set.")
        self._created_utc = value

    @property
    def author(self):
        return self._author

    @author.setter
    def author(self, value):
        if self._author is not None:
            raise AttributeError("Ajo.author is immutable once set.")
        self._author = value

    @property
    def lingvo(self):
        if not self._lingvo:
            self.initialize_lingvo()
        return self._lingvo

    @property
    def submission(self):
        """
        Lazily load and cache the PRAW submission object.
        Returns None if no ID is set.
        """
        if self._submission is None and self._id is not None:
            self._submission = _fetch_submission(self._id)
        return self._submission

    @property
    def language_code_1(self):
        return self.lingvo.language_code_1

    @property
    def language_code_3(self):
        return self.lingvo.language_code_3

    @property
    def language_name(self):
        return self.lingvo.name

    @property
    def country_code(self):
        return self.lingvo.country

    @property
    def is_supported(self):
        return self.lingvo.supported

    @property
    def script_code(self):
        return self.lingvo.script_code

    @property
    def script_name(self):
        return converter(self.script_code).name if self.script_code else None

    @property
    def is_script(self):
        return self.script_code is not None

    @classmethod
    def from_titolo(cls, titolo: "Titolo", submission=None):
        """
        Construct an Ajo object from a Titolo instance and an optional PRAW submission.
        This is the main way to construct an Ajo, as simple as:
        Ajo.from_titolo(Titolo.process_title(submission.title))

        :param titolo: A Titolo instance containing parsed title information.
        :param submission: (Optional) A PRAW submission object to populate Ajo fields.
        :return: A fully constructed Ajo object.
        """
        ajo = cls()

        # Basic info
        ajo.title_original = titolo.title_original or (submission.title if submission else None)
        ajo.title = titolo.title_actual
        ajo.direction = titolo.direction

        # Set the language via preferred code
        ajo.preferred_code = titolo.final_code
        ajo.initialize_lingvo()  # Build the Lingvo object

        # Additional info
        ajo.original_source_language_name = titolo.source
        ajo.original_target_language_name = titolo.target

        # Ajo extras
        # Populate language_history with actual language codes from target languages
        if titolo.target:
            # If multiple languages (defined multiple), wrap in a list
            if len(titolo.target) > 1:
                ajo.language_history = [[lang.preferred_code for lang in titolo.target]]
                # Create status dictionary with 'untranslated' for each language code
                ajo.status = {lang.preferred_code: 'untranslated' for lang in titolo.target}
            else:
                # Single language, keep as flat list
                ajo.language_history = [titolo.final_code]
                ajo.status = "untranslated"  # Default
        else:
            ajo.language_history = []
            ajo.status = "untranslated"

        # Set is_defined_multiple if there are multiple target languages
        if titolo.target and len(titolo.target) > 1:
            ajo.is_defined_multiple = True
            ajo.type = 'multiple'

        # Populate fields from Reddit submission if available
        if submission:
            ajo.id = submission.id
            ajo.created_utc = int(submission.created_utc)
            ajo.author = str(submission.author) if submission.author else None

            # If the submission is a link to an image, set the image hash
            ajo.set_image_hash(submission)

        return ajo

    def update_from_titolo(self, titolo: "Titolo"):
        """
        Update this Ajo instance in-place based on a Titolo instance and
        optional Reddit submission.
        """
        self.title_original = titolo.title_original
        self.title = titolo.title_actual
        self.direction = titolo.direction

        self.preferred_code = titolo.final_code
        self.initialize_lingvo()

        self.original_source_language_name = titolo.source
        self.original_target_language_name = titolo.target

        self.status = "untranslated"

    def to_dict(self):
        """
        Serialize only JSON-safe fields of this Ajo object.
        Excludes internal and derived attributes like `_lingvo`, `language_name`, `is_supported`, etc.
        """

        def lingvo_list_to_names(lingvo_list):
            if not lingvo_list:
                return []
            return [lv.name if hasattr(lv, "name") else str(lv) for lv in lingvo_list]

        return {
            "id": self.id,
            "created_utc": self.created_utc,
            "author": self.author,
            "title_original": self.title_original,
            "title": self.title,
            "direction": self.direction,
            "preferred_code": self.preferred_code,
            "language_history": self.language_history or [],
            "status": self.status or "untranslated",
            "output_post_flair_css": self.output_post_flair_css,  # solely for backwards compatability
            "output_post_flair_text": self.output_post_flair_text,  # solely for backwards compatability
            "original_source_language_name": lingvo_list_to_names(self.original_source_language_name),
            "original_target_language_name": lingvo_list_to_names(self.original_target_language_name),
            "is_identified": bool(self.is_identified),
            "is_long": bool(self.is_long),
            "image_hash": self.image_hash,
            "type": self.type or "single",  # default fallback
            "is_defined_multiple": bool(self.is_defined_multiple)
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Ajo":
        ajo = cls()

        # Determine preferred_code early
        preferred_code = data.get("preferred_code") or data.get("language_code_1") or data.get("language_code_3")
        ajo.preferred_code = preferred_code

        # Initialize Lingvo before setting other fields to avoid property setter issues
        if ajo.preferred_code:
            ajo.initialize_lingvo()

        read_only_properties = {"is_script", "script_code", "script_name"}

        for key, value in data.items():
            if key in {"_lingvo", "language_code_1", "language_code_3", "language_name",
                       "country_code", "is_supported", "preferred_code"} | read_only_properties:
                continue
            if hasattr(ajo, key):
                setattr(ajo, key, value)

        # Apply compatibility defaults if not already set
        ajo.language_history = data.get("language_history", [])
        ajo.status = data.get("status", "untranslated")
        ajo.is_identified = data.get("is_identified", False)
        ajo.is_long = data.get("is_long", False)
        ajo.is_defined_multiple = data.get("is_defined_multiple", False)

        # Normalize language name fields
        ajo.original_source_language_name = _normalize_lang_field(data.get("original_source_language_name"))
        ajo.original_target_language_name = _normalize_lang_field(data.get("original_target_language_name"))

        return ajo

    """FUNCTIONS THAT CHANGE STATES"""

    def set_language(self, code_or_lingvo, is_identified: bool = True):
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
            self.preferred_code = 'multiple'
            self.initialize_lingvo()
            self.type = 'multiple'
            self.is_defined_multiple = True

            # Initialize status as dictionary with all languages set to 'untranslated'
            self.status = {code: 'untranslated' for code in lang_codes}

            # Append the list of codes to language_history
            self.language_history.append(lang_codes)
        else:
            # Single language (default behavior)
            if isinstance(code_or_lingvo, str):
                self.preferred_code = code_or_lingvo.lower()
                self.initialize_lingvo()
            else:
                # Assume it's a Lingvo object
                self._lingvo = code_or_lingvo
                self.preferred_code = self._lingvo.preferred_code

            # Update tracking fields
            self.language_history.append(self.language_name)

        # Set is_identified for both cases
        self.is_identified = is_identified

    def set_is_long(self, value: bool):
        """
        Set whether the post is marked as long.
        """
        self.is_long = bool(value)

    def set_type(self, value: str):
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

    def set_status(self, value: str):
        """
        Set the status of the post.
        Allowed values: 'translated', 'doublecheck', 'inprogress', 'missing', 'untranslated'

        Status transition rules:
        - Once marked as 'doublecheck', can only transition to 'translated'
        - Once marked as 'translated', status is final and cannot be changed

        This method is for single language posts or non-defined multiple posts only.
        For defined multiple posts, use set_defined_multiple_status() instead.

        :raises ValueError: If the status value is not allowed, if called on a defined multiple,
                           or if the status transition is not permitted.
        """
        if self.is_defined_multiple:
            raise ValueError(
                "Cannot use set_status() on a defined multiple post. Use set_defined_multiple_status() instead.")

        allowed = {"translated", "doublecheck", "inprogress", "missing", "untranslated"}
        if value not in allowed:
            raise ValueError(f"Status must be one of {allowed}.")

        # Check if current status is 'translated' - cannot change from this state
        if hasattr(self, 'status') and self.status == 'translated':
            raise ValueError("Cannot change status once marked as 'translated'. Status is final.")

        # Check if current status is 'doublecheck' - can only transition to 'translated'
        if hasattr(self, 'status') and self.status == 'doublecheck' and value != 'translated':
            raise ValueError(
                "Once marked as 'doublecheck', status can only be changed to 'translated'.")

        self.status = value

    def set_defined_multiple_status(self, language_code: str, status_value: str):
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
                "Cannot use set_defined_multiple_status() on a non-defined multiple post. Use set_status() instead.")

        allowed = {"translated", "doublecheck", "inprogress", "missing", "untranslated"}
        if status_value not in allowed:
            raise ValueError(f"Status must be one of {allowed}.")

        # Initialize status as a dict if it's not already
        if not isinstance(self.status, dict):
            self.status = {}

        # Set the status for the specific language
        self.status[language_code] = status_value

    def set_is_defined_multiple(self, value: bool):
        """
        Set whether the post is marked as a defined multiple post.
        This should only be meaningful when type is 'multiple'.

        :param value: Boolean indicating if this is a defined multiple.
        """
        self.is_defined_multiple = bool(value)

    def toggle_is_defined_multiple(self):
        """
        Toggle the is_defined_multiple attribute between True and False.
        Returns the new value after toggling.

        :return: The new value of is_defined_multiple after toggling.
        """
        self.is_defined_multiple = not self.is_defined_multiple
        return self.is_defined_multiple

    def set_time(self, status, moment):
        """
        Create or update a dictionary marking times when the status/state of the Ajo changed.
        The dictionary is keyed by status and contains Unix times of the changes.
        Note that this is shared between single and defined multiple posts;
        that is, if a defined multiple post is claimed, the timestamp will
        not be disambiguated by language.

        :param status: The status that it was changed to. Example: 'translated'.
        :param moment: The Unix UTC time when the action was taken (integer).
        """

        if not hasattr(self, 'time_delta') or self.time_delta is None:
            self.time_delta = {}

        # Record the moment for this status only if it hasn't been recorded before.
        self.time_delta.setdefault(status, int(moment))

    def set_author_messaged(self, is_messaged: bool) -> None:
        """
        Set the `author_messaged` flag indicating whether the post's author has been notified of the translation.

        :param is_messaged: True if the author has been messaged, False otherwise.
        """
        self.author_messaged = is_messaged

    def add_translators(self, translator_name):
        """
        Add the username of who translated what to the Ajo of a post
        by appending their name to the list. This allows Ziwen to track translators.

        :param translator_name: The name of the individual who made the translation.
        """

        if not hasattr(self, 'recorded_translators') or self.recorded_translators is None:
            self.recorded_translators = []

        if translator_name not in self.recorded_translators:
            self.recorded_translators.append(translator_name)
            logger.debug(f"[ZW] Ajo: Added translator name u/{translator_name}.")

    def add_notified(self, notified_list: List[str]) -> None:
        """
        Add usernames who have been notified by the bot for this post.
        Ensures the same user is not contacted multiple times.

        :param notified_list: List of usernames who have been contacted regarding the post.
        """

        if not hasattr(self, 'notified') or self.notified is None:
            self.notified = []

        for name in notified_list:
            if name not in self.notified:
                self.notified.append(name)
                logger.debug(f"[ZW] Ajo: Added notified name u/{name}.")

    def set_image_hash(self, reddit_submission):
        """
        If the submission is a link post and links to an image, generate an image hash.
        """
        if not reddit_submission.is_self:
            if check_url_extension(reddit_submission.url):
                self.image_hash = generate_image_hash(reddit_submission.url)

    def clear_submission_cache(self):
        """
        Clear the cached PRAW submission object.
        Useful before serialization to avoid storing large objects.

        :return: The cached submission object (if any) before clearing.
        """
        cached = self._submission
        self._submission = None
        return cached

    def restore_submission_cache(self, submission):
        """
        Restore a previously cached PRAW submission object.

        :param submission: The PRAW submission object to cache.
        """
        self._submission = submission

    """ACTING FUNCTIONS"""

    def reset(self) -> None:
        """
        Reset this Ajo to its original state based on its Reddit post title.
        Re-fetches the submission via PRAW, re-processes the title, and re-applies
        initial parsing via from_titolo.
        """
        submission = REDDIT_HELPER.submission(id=self.id)
        titolo = process_title(submission.title)
        self.update_from_titolo(titolo)

    def update_reddit(self):
        """
        Thin wrapper that calls the external flair update function.
        It also writes changes to the database.
        """
        determine_flair_and_update(self)
        ajo_writer(self)


# Module-level utility function
def _fetch_submission(post_id: str):
    """
    Fetch a PRAW submission by ID.

    :param post_id: The Reddit submission ID
    :return: PRAW submission object or None if fetch fails
    """
    try:
        return REDDIT.submission(id=post_id)
    except Exception as e:
        logger.error(f"[ZW] Failed to fetch submission {post_id}: {e}")
        return None


"""EXTERNAL FUNCTIONS"""


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
        used_code = lingvo_obj.language_code_1 or lang_code

        # Find the symbol corresponding to the status in the legend, default to empty string
        symbol = next((sym for sym, val in SETTINGS['defined_multiple_legend'].items() if val == status), "")

        # Format language code + symbol, e.g. "DE✔"
        formatted_entries.append(f"{used_code.upper()}{symbol}")

    # Sort alphabetically and join with commas, then wrap in brackets
    joined = ", ".join(sorted(formatted_entries))
    return f"[{joined}]"


def determine_flair_and_update(ajo: Ajo) -> None:
    """
    Determine the correct flair CSS and text based on ajo attributes
    and update the Reddit submission flair.
    """
    from maintenance import STATE
    testing_mode = SETTINGS['testing_mode']
    post_templates = STATE.post_templates
    submission = REDDIT.submission(id=ajo.id)

    # Initialize flair defaults
    code_tag = "[--]"
    output_flair_css = "generic"

    unq_types = {"Unknown", "Generic"}
    language_name = ajo.language_name or ""
    language_code_1 = ajo.language_code_1 if isinstance(ajo.language_code_1, str) else None
    language_code_3 = ajo.language_code_3 if isinstance(ajo.language_code_3, str) else None

    # Helper to set code_tag and css for a given code and css
    def set_code_and_css(code, css):
        nonlocal code_tag, output_flair_css
        code_tag = f"[{code.upper()}]"
        output_flair_css = css

    if ajo.type == "single":
        if language_name not in unq_types:
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
                print(f">>> Update Reddit: Unknown post `{ajo.id}`.")
            else:  # None, Generic, or empty
                code_tag = "[--]"
                output_flair_css = "generic"
    else:  # multiple posts
        if language_code_3 == "multiple":
            output_flair_css = "multiple"
            code_tag = None
        else:
            output_flair_css = "multiple"

            if not hasattr(ajo, 'status'):
                ajo.status = {}
            if isinstance(ajo.status, dict):
                code_tag = ajo_defined_multiple_flair_former(ajo.status)

    # Determine flair text
    if ajo.type == "single":
        status_map = {
            "translated": ("translated", f"Translated {code_tag}"),
            "doublecheck": ("doublecheck", f"Needs Review {code_tag}"),
            "inprogress": ("inprogress", f"In Progress {code_tag}"),
            "missing": ("missing", f"Missing Assets {code_tag}")
        }
        if isinstance(ajo.status, str) and ajo.status in status_map:
            output_flair_css, output_flair_text = status_map[ajo.status]
        else:
            # Default untranslated flair text
            output_flair_text = language_name
            if ajo.country_code:
                output_flair_text += f" {{{ajo.country_code}}}"
            if language_name != "Unknown":
                if getattr(ajo, "is_identified", False):
                    output_flair_text += " (Identified)"
                if getattr(ajo, "is_long", False):
                    output_flair_text += " (Long)"
            else:
                # Unknown post script flair
                if getattr(ajo, "is_script", False):
                    output_flair_text = getattr(ajo, "script_name", "") + " (Script)"
    else:  # This is a multiple post.
        # Multiple post flair text
        if code_tag is None:
            output_flair_text = converter(output_flair_css).preferred_code
        else:
            output_flair_text = f"Multiple Languages {code_tag}"

    # Update flair on Reddit if template exists
    if output_flair_css in post_templates:
        template_id = post_templates[output_flair_css]
        logger.debug(f"[ZW] Update Reddit: Template for CSS `{output_flair_css}` is `{template_id}`.")
        if not testing_mode:  # Regular mode.
            submission.flair.select(flair_template_id=template_id, text=output_flair_text)
        else:
            log_testing_mode(
                output_text=output_flair_text,
                title=f"Flair Update Dry Run for Submission {ajo.id}",
                metadata={
                    "Submission ID": ajo.id,
                    "Flair CSS": output_flair_css,
                    "Flair Template ID": template_id,
                    "Submission Title": getattr(ajo, 'title_original', 'N/A'),
                    "Post Type": ajo.type,
                }
            )
        logger.info(f"[ZW] Set post `{ajo.id}` to CSS `{output_flair_css}` and text `{output_flair_text}`.")

    # Sync flair output back to Ajo instance
    ajo.output_flair_css = output_flair_css
    ajo.output_flair_text = output_flair_text


"""INTERNAL USE"""


def _convert_to_dict(input_string):
    """
    Converts a Python dictionary string or JSON string to a Python dictionary.

    Args:
        input_string (str): A string containing either a Python dict or JSON

    Returns:
        dict: The converted Python dictionary

    Raises:
        ValueError: If the input cannot be parsed as either a Python dict or JSON
    """
    # Remove any leading/trailing whitespace
    input_string = input_string.strip()

    # Try parsing as Python dictionary first
    try:
        result = ast.literal_eval(input_string)
        if isinstance(result, dict):
            return result
    except (ValueError, SyntaxError):
        pass

    # Try parsing as JSON using orjson
    try:
        # orjson.loads expects bytes, so encode the string
        result = orjson.loads(input_string.encode('utf-8'))
        if isinstance(result, dict):
            return result
    except orjson.JSONDecodeError:
        pass

    # If both methods fail, raise an error
    raise ValueError("Input could not be parsed as a Python dictionary or JSON")


"""INQUIRY SECTION"""


def show_menu():
    print("\nSelect a search to run:")
    print("1. Ajo testing (enter a URL of a Reddit post to test)")
    print("2. Reddit posts (retrieve the last few Reddit posts to test against)")
    print("3. Text testing (paste a dictionary of an Ajo to test)")
    print("x. Exit")


if __name__ == "__main__":

    while True:
        show_menu()
        choice = input("Enter your choice (1-3): ")

        if choice == "x":
            print("Exiting...")
            break

        if choice not in ["1", "2", "3"]:
            print("Invalid choice, please try again.")
            continue

        if choice == "1":
            test_url = input("Enter the URL of the Reddit post to test: ")
            submission_id = test_url.split("comments/")[1].split("/")[0]
            test_post = REDDIT_HELPER.submission(id=submission_id)

            test_titolo = Titolo.process_title(test_post)
            pprint.pprint(vars(test_titolo))

            post_ajo = Ajo.from_titolo(test_titolo, test_post)
            pprint.pprint(vars(post_ajo))

        elif choice == "2":
            for submission_new in REDDIT_HELPER.subreddit('translator').new(limit=3):
                print(f"Title: {submission_new.title}")
                ajo_new = Ajo.from_titolo(Titolo.process_title(submission_new),
                                          submission_new)
                pprint.pprint(vars(ajo_new))
                print('------------------')

        elif choice == "3":
            test_dict = input("Paste an Ajo as a Python dictionary or JSON: ")
            test_dict = _convert_to_dict(test_dict)
            pprint.pp(vars(Ajo.from_dict(test_dict)))
