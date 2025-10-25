#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
A collection of database sets and language functions that all r/translator bots use.
"""

import copy
import csv
import random
import re
from pprint import pprint

import orjson  # Using for faster performance
import pycountry
from rapidfuzz import fuzz
import yaml

from config import Paths, load_settings, logger

# Load the language module's settings and parse the file's content
language_module_settings = load_settings(Paths.SETTINGS["LANGUAGES_MODULE_SETTINGS"])
_lingvos_cache = None  # for reloading purposes when the data changes


class Lingvo:
    def __init__(self, **kwargs):
        self.name = kwargs.get("name")
        self.name_alternates = kwargs.get("name_alternates", [])
        self.language_code_1 = kwargs.get("language_code_1")
        self.language_code_2b = kwargs.get("language_code_2b")
        self.language_code_3 = kwargs.get("language_code_3")
        self.script_code = kwargs.get("script_code")  # For script entries
        self.country = kwargs.get("country")  # country code
        self.countries_default = kwargs.get("countries_default")
        self.countries_associated = kwargs.get("countries_associated")
        self.family = kwargs.get("family")
        self.mistake_abbreviation = kwargs.get("mistake_abbreviation")
        self.population = kwargs.get("population")
        self.subreddit = kwargs.get("subreddit")
        self.supported = kwargs.get("supported", False)
        self.thanks = kwargs.get("thanks", "Thanks")
        self.greetings = kwargs.get("greetings", "Hello")
        self.link_ethnologue = kwargs.get("link_ethnologue")
        self.link_wikipedia = kwargs.get("link_wikipedia")

        # New statistics fields
        self.num_months = kwargs.get("num_months")
        self.rate_daily = kwargs.get("rate_daily")
        self.rate_monthly = kwargs.get("rate_monthly")
        self.rate_yearly = kwargs.get("rate_yearly")
        self.link_statistics = kwargs.get(
            "permalink"
        )  # Maps permalink → statistics_page

    # Define the preferred code to be used.
    @property
    def preferred_code(self):
        for code in (self.language_code_1, self.language_code_3):
            if code:
                lowered = code.lower()
                if lowered in {"multiple", "generic"}:
                    return lowered
                if lowered != "unknown":
                    return lowered
        return (self.script_code or "unknown").lower()

    def __repr__(self):
        code = self.preferred_code
        is_script = self.script_code is not None or len(code) == 4
        script_label = " | (script)" if is_script else ""  # Denote scripts
        return f"<Lingvo: {self.name} ({code}){script_label}>"

    def __str__(self):
        return self.preferred_code

    def __eq__(self, other):
        if not isinstance(other, Lingvo):
            return NotImplemented
        return self.preferred_code == other.preferred_code

    def __hash__(self):
        # hash should be consistent with __eq__
        return hash(self.preferred_code)

    @classmethod
    def from_csv_row(cls, row: dict):
        """
        Create a Lingvo object from a language CSV row in Datasets.
        Expected keys: 'ISO 639-3', 'ISO 639-1', 'Language Name', 'Alternate Names'
        """
        alt_names = row.get("Alternate Names", "")
        name_alternates = [alt.strip() for alt in alt_names.split(";") if alt.strip()]

        return cls(
            name=row.get("Language Name") or None,
            name_alternates=name_alternates,
            language_code_1=row.get("ISO 639-1") or None,
            language_code_2b=None,
            language_code_3=row.get("ISO 639-3") or None,
            country=None,
            countries_default=None,
            countries_associated=None,
            family=None,
            mistake_abbreviation=None,
            population=0,
            subreddit=None,
            supported=False,
            link_ethnologue=None,
            link_wikipedia=None,
            # Explicitly set statistics fields to None
            num_months=None,
            rate_daily=None,
            rate_monthly=None,
            rate_yearly=None,
            link_statistics=None,
        )

    def to_dict(self):
        return {
            "name": self.name,
            "name_alternates": self.name_alternates,
            "language_code_1": self.language_code_1,
            "language_code_2b": self.language_code_2b,
            "language_code_3": self.language_code_3,
            "script_code": self.script_code,
            "country": self.country,
            "countries_default": self.countries_default,
            "countries_associated": self.countries_associated,
            "family": self.family,
            "mistake_abbreviation": self.mistake_abbreviation,
            "population": self.population,
            "subreddit": self.subreddit,
            "supported": self.supported,
            "thanks": self.thanks,
            "greetings": self.greetings,
            "link_ethnologue": self.link_ethnologue,
            "link_wikipedia": self.link_wikipedia,
            "preferred_code": self.preferred_code,
            # Export statistics fields
            "num_months": self.num_months,
            "rate_daily": self.rate_daily,
            "rate_monthly": self.rate_monthly,
            "rate_yearly": self.rate_yearly,
            "link_statistics": self.link_statistics,
        }


"""MAIN LOADER"""


def _combine_language_data():
    """
    Helper function to combine raw language data, utility data, and statistics.

    :return: dict - Combined language data dictionary
    """
    allowed_keys = {
        "num_months",
        "permalink",
        "rate_daily",
        "rate_monthly",
        "rate_yearly",
    }

    raw_data = load_settings(Paths.DATASETS["LANGUAGE_DATA"])
    utility_data = load_settings(Paths.DATASETS["UTILITY_LINGVO_DATA"])
    with open(Paths.DATASETS["STATISTICS"], "rb") as f:
        statistics_data = orjson.loads(f.read())

    combined_data = {}

    # Process raw data
    for code, attrs in raw_data.items():
        combined_data[code] = attrs.copy()

    # Overlay utility data
    for code, attrs in utility_data.items():
        if code in combined_data:
            combined_data[code].update(attrs)
        else:
            combined_data[code] = attrs.copy()

    # Add statistics
    for code, stats in statistics_data.items():
        filtered_stats = {k: v for k, v in stats.items() if k in allowed_keys}
        if not filtered_stats:
            continue
        if code in combined_data:
            combined_data[code].update(filtered_stats)
        else:
            combined_data[code] = filtered_stats.copy()

    return combined_data


def validate_lingvo_dataset():
    """
    Validates the language dataset by checking for codes missing required fields.

    :return: list[str] - List of language codes missing required fields
                         (name or language_code)
    """
    combined_data = _combine_language_data()

    # Check for problematic codes
    problematic_codes = []
    for code, attrs in combined_data.items():
        name = attrs.get("name")
        lang_code = attrs.get("language_code", code)

        if not name or not lang_code:
            problematic_codes.append(code)
            logger.debug(f"Problematic code: `{code}`")

    return problematic_codes


def _load_lingvo_dataset(debug=False):
    """
    Loads the language dataset by combining raw language data and
    utility language data, then returns a dictionary of Lingvo instances.

    :return: dict[str, Lingvo]
    """
    combined_data = _combine_language_data()

    # Create Lingvo instances
    lingvo_dict = {}

    for code, attrs in combined_data.items():
        if debug:
            logger.debug(f"combined_data[{code}] = {attrs}")

        # Get values and remove from attrs so they are not passed twice
        name = attrs.pop("name", None)
        lang_code = attrs.pop("language_code", code)

        # Create Lingvo with cleaned attrs
        lingvo_dict[code] = Lingvo(
            language_code=lang_code, name=name or "unknown", **attrs
        )

    return lingvo_dict


def get_lingvos(force_refresh=False):
    """Get lingvos dataset, optionally forcing a refresh."""
    global _lingvos_cache
    if _lingvos_cache is None or force_refresh:
        _lingvos_cache = _load_lingvo_dataset()
    return _lingvos_cache


def define_language_lists():
    """
    Generate various language code and name mappings from a language dataset.

    :return: A dictionary with structured language metadata lists and mappings.
    """
    lingvos = get_lingvos()

    supported_codes = []
    supported_languages = []
    iso_default_associated = []
    iso_639_1 = []
    iso_639_2b = {}
    iso_639_3 = []
    iso_names = []
    mistake_abbreviations = {}
    language_country_associated = {}

    for code_1, lingvo in lingvos.items():
        if len(code_1) == 2:
            iso_639_1.append(code_1)

        if lingvo.language_code_3:
            iso_639_3.append(lingvo.language_code_3)

        # Handle 3-letter synonyms (if supported in the class)
        if hasattr(lingvo, "language_code_synonym") and lingvo.language_code_synonym:
            iso_639_3.append(lingvo.language_code_synonym)

        if lingvo.name:
            iso_names.append(lingvo.name)

        iso_names.extend(lingvo.name_alternates or [])

        if getattr(lingvo, "supported", False):
            supported_codes.append(code_1)
            supported_languages.append(lingvo.name)

        if lingvo.countries_default:
            iso_default_associated.append(f"{code_1}-{lingvo.countries_default}")

        if hasattr(lingvo, "countries_associated") and lingvo.countries_associated:
            language_country_associated[code_1] = lingvo.countries_associated

        if hasattr(lingvo, "mistake_abbreviation") and lingvo.mistake_abbreviation:
            mistake_abbreviations[lingvo.mistake_abbreviation] = code_1

        if hasattr(lingvo, "language_code_2b") and lingvo.language_code_2b:
            iso_639_2b[lingvo.language_code_2b] = code_1

    return {
        "SUPPORTED_CODES": supported_codes,
        "SUPPORTED_LANGUAGES": supported_languages,
        "ISO_DEFAULT_ASSOCIATED": iso_default_associated,
        "ISO_639_1": iso_639_1,
        "ISO_639_2B": iso_639_2b,
        "ISO_639_3": iso_639_3,
        "ISO_NAMES": iso_names,
        "MISTAKE_ABBREVIATIONS": mistake_abbreviations,
        "LANGUAGE_COUNTRY_ASSOCIATED": language_country_associated,
    }


def normalize(text):
    """Cleans the text for processing. Lowercases it, and then
    substitutes and strips whitespace."""
    text = text.lower()
    text = re.sub(r"[^\w\s]", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _fuzzy_text(word, supported_languages, threshold=75):
    """Attempts to fuzzy match the given word with language names,
    and ignores common mistaken matches."""
    exclude = language_module_settings["FUZZ_IGNORE_LANGUAGE_NAMES"]
    word_norm = normalize(word)

    best_match = None
    best_score = threshold

    for language in supported_languages:
        if language in exclude:
            continue
        lang_norm = normalize(language)
        score = fuzz.token_set_ratio(lang_norm, word_norm)
        if score > best_score:
            best_score = score
            best_match = language

    return best_match


"""EDITING FUNCTIONS"""


def add_alt_language_name(language_code: str, alt_name: str):
    """
    Adds an alternate name for a given language in the LANGUAGE_DATA YAML file.
    If the language doesn't have a 'name_alternates' field, it is created.
    If the alt_name already exists, nothing is changed.
    """
    try:
        language_data_path = Paths.DATASETS["LANGUAGE_DATA"]

        # Load the existing language data
        with open(language_data_path, "r", encoding="utf-8") as f:
            existing_data = yaml.safe_load(f) or {}

        # Check if the language entry exists
        if language_code not in existing_data:
            logger.warning(
                f"[AddAlt] Language code '{language_code}' not found in dataset."
            )
            return False

        lang_entry = existing_data[language_code]

        # Ensure 'name_alternates' exists and is a list
        if "name_alternates" not in lang_entry or not isinstance(
            lang_entry["name_alternates"], list
        ):
            lang_entry["name_alternates"] = []

        # Add new alternate name if not already present
        if alt_name not in lang_entry["name_alternates"]:
            lang_entry["name_alternates"].append(alt_name.title().strip())
            existing_data[language_code] = lang_entry

            # Write updated YAML back to file
            with open(language_data_path, "w", encoding="utf-8") as f:
                yaml.dump(existing_data, f, allow_unicode=True, sort_keys=True)

            logger.info(
                f"[AddAlt] Added alternate name '{alt_name}' to '{language_code}'."
            )
            return True
        else:
            logger.info(
                f"[AddAlt] Alternate name '{alt_name}' already exists for '{language_code}'."
            )
            return False

    except Exception as e:
        logger.error(f"[AddAlt] Error while adding alternate name: {e}")
        return False


"""MAIN CONVERTER FUNCTIONS"""


def _iso_codes_deep_search(search_term, script_search=False):
    """
    Searches for a language or script code from a CSV of ISO 639-3 or
    ISO 15924 codes.

    :param search_term: The term to search for (code or name).
    :param script_search: If True, search in script codes (ISO 15924, 4-letter codes).
    :return: Lingvo object if found, else None.
    """
    search_term = search_term.strip().lower()

    if script_search:
        dataset_path = Paths.DATASETS["ISO_SCRIPT_CODES"]
        code_key = "Script Code"
        name_key = "Script Name"
        alt_key = "Alternate Names"
    else:
        dataset_path = Paths.DATASETS["ISO_CODES"]
        code_key = "ISO 639-3"
        name_key = "Language Name"
        alt_key = "Alternate Names"

    try:
        with open(dataset_path, "rt", encoding="utf-8-sig") as file:
            reader = csv.DictReader(file)
            for row in reader:
                if not row.get(name_key):
                    continue  # Skip malformed/incomplete rows

                code = row.get(code_key, "").strip().lower()
                name = row.get(name_key, "").strip()
                alt_raw = row.get(alt_key) or ""
                alternates = [
                    alt.strip().lower() for alt in alt_raw.split(";") if alt.strip()
                ]

                if search_term in {code, name.lower()} or search_term in alternates:
                    if script_search:
                        return Lingvo(
                            name=name,
                            name_alternates=alternates,
                            language_code_1="unknown",
                            language_code_3="unknown",
                            script_code=row.get("Script Code"),
                            supported=True,
                        )
                    else:
                        return Lingvo.from_csv_row(row)

    except FileNotFoundError:
        print(f"Dataset not found: {dataset_path}")
        return None

    return None


def converter(
    input_text: str,
    fuzzy: bool = True,
    specific_mode: bool = False,
    preserve_country: bool = False,
) -> Lingvo | None:
    """
    Convert an input string to a Lingvo object.
    Input can be a language code, name, or compound like zh-MO or
    unknown-cyrl.

    :param input_text: The input string to resolve.
    :param fuzzy: Whether to apply fuzzy name matching.
    :param specific_mode: If True, use strict lookups (ISO_639_3 for 3-char,
                          ISO_15924 for 4-char).
    :param preserve_country: If True, keep the country field from YAML data.
                            If False (default), clear country for simple lookups.
    :return: A Lingvo instance or None if not found.
    """
    # Get the current (possibly refreshed) lingvos data
    lingvos = get_lingvos()

    input_text = input_text.strip()
    input_lower = input_text.lower()
    reference_lists = define_language_lists()

    # Too-short input.
    if len(input_text) <= 1:
        logger.debug(f"Skipping {input_text} as it's too short.")
        return None

    # Specific mode: strict lookups only
    if specific_mode:
        if len(input_text) == 2:
            # Only search in ISO 639-1
            if input_lower in reference_lists.get("ISO_639_1", {}):
                lingvo = lingvos.get(input_lower)
                if lingvo:
                    lingvo_copy = copy.deepcopy(lingvo)
                    if not preserve_country:
                        lingvo_copy.country = None
                    return lingvo_copy
            return None
        elif len(input_text) == 3:
            # Only search in ISO 639-3
            iso_search = _iso_codes_deep_search(input_text, script_search=False)
            if iso_search:
                lingvo_copy = copy.deepcopy(iso_search)
                if not preserve_country:
                    lingvo_copy.country = None
                return lingvo_copy
            return None
        elif len(input_text) == 4:
            # Only search in ISO 15924
            iso_search = _iso_codes_deep_search(input_text, script_search=True)
            if iso_search:
                lingvo_copy = copy.deepcopy(iso_search)
                if not preserve_country:
                    lingvo_copy.country = None
                return lingvo_copy
            return None
        else:
            # Invalid length for specific_mode
            return None

    # Normal mode: existing logic
    # Handle compound codes like zh-CN or unknown-Cyrl first,
    # because that affects country assignment logic
    if "-" in input_text and "Anglo" not in input_text:
        broader, specific = input_text.split("-", 1)
        combo = f"{broader.lower()}-{specific.upper()}"

        # Direct lookup in ISO_LANGUAGE_COUNTRY_ASSOCIATED
        # e.g. `de-CH` becomes `gsw`
        iso_map = language_module_settings["ISO_LANGUAGE_COUNTRY_ASSOCIATED"]
        if combo in iso_map:
            mapped_code = iso_map[combo]
            lingvo = lingvos.get(mapped_code)
            if lingvo:
                lingvo_copy = copy.deepcopy(lingvo)
                if not preserve_country:
                    lingvo_copy.country = None
                return lingvo_copy

        # Step 2: Prefixed script code ("unknown-Cyrl")
        if broader.lower() == "unknown":
            try:
                result = _iso_codes_deep_search(specific, script_search=True)
                script_name = getattr(result, "name", None)
                if not script_name:
                    return None
                return Lingvo(
                    name=script_name,
                    language_code_1="unknown",
                    language_code_3="unknown",
                    script_code=specific.lower(),
                    supported=True,
                )
            except (AttributeError, TypeError):
                return None

        # Step 3: Language-region combo (fallback, less strict)
        country_info = country_converter(specific, abbreviations_okay=True)
        if country_info:
            country_code = country_info[0].upper()
            language_code = broader.lower()
            if language_code in lingvos:
                lingvo = copy.deepcopy(lingvos[language_code])
                lingvo.name += f" {{{country_info[1]}}}"  # e.g., "Chinese {China}"
                lingvo.country = country_code  # e.g. 'IN'
                return lingvo

    # Search by name or alternate name
    input_title = input_text.title()
    for code, lingvo in lingvos.items():
        if input_title == lingvo.name:
            # Return a copy with no country info since input has no region
            lingvo_copy = copy.deepcopy(lingvo)
            if not preserve_country:
                lingvo_copy.country = None
            return lingvo_copy
        if input_title in (alt.title() for alt in lingvo.name_alternates or []):
            lingvo_copy = copy.deepcopy(lingvo)
            if not preserve_country:
                lingvo_copy.country = None
            return lingvo_copy

    # Try to find a Lingvo by 2-letter code first
    if input_lower in reference_lists["ISO_639_1"]:
        lingvo = lingvos.get(input_lower)
        if lingvo:
            lingvo_copy = copy.deepcopy(lingvo)
            # Clear country info for simple 2-letter code inputs
            if not preserve_country:
                lingvo_copy.country = None
            return lingvo_copy

    # If input is 3 letters, check if it maps to a 2-letter code, then prefer that Lingvo
    if len(input_lower) == 3:
        for code_1, lingvo in lingvos.items():
            if lingvo.language_code_3 == input_lower:
                if code_1 in lingvos:
                    lingvo_copy = copy.deepcopy(lingvos[code_1])
                    if not preserve_country:
                        lingvo_copy.country = None
                    return lingvo_copy
                else:
                    lingvo_copy = copy.deepcopy(lingvo)
                    if not preserve_country:
                        lingvo_copy.country = None
                    return lingvo_copy

        for lingvo in lingvos.values():
            if input_lower == lingvo.language_code_3:
                lingvo_copy = copy.deepcopy(lingvo)
                if not preserve_country:
                    lingvo_copy.country = None
                return lingvo_copy

    # First try language codes.
    iso_search = _iso_codes_deep_search(input_text)
    if not iso_search:
        iso_search = _iso_codes_deep_search(input_text, script_search=True)

    if iso_search:
        # _iso_codes_deep_search returns a Lingvo instance.
        # Copy it and clear country for simple inputs
        lingvo_copy = copy.deepcopy(iso_search)
        if not preserve_country:
            lingvo_copy.country = None
        return lingvo_copy

    # Special abbreviation fixes (like 'vn' meaning Vietnamese)
    if input_lower in reference_lists["MISTAKE_ABBREVIATIONS"]:
        fixed = reference_lists["MISTAKE_ABBREVIATIONS"][input_lower]
        lingvo = lingvos.get(fixed)
        if lingvo:
            lingvo_copy = copy.deepcopy(lingvo)
            if not preserve_country:
                lingvo_copy.country = None
            return lingvo_copy

    # ISO 639-2B mapping (e.g., 'fre' -> 'fr')
    if input_lower in reference_lists["ISO_639_2B"]:
        canonical_code = reference_lists["ISO_639_2B"][input_lower]
        lingvo = lingvos.get(canonical_code)
        if lingvo:
            lingvo_copy = copy.deepcopy(lingvo)
            if not preserve_country:
                lingvo_copy.country = None
            return lingvo_copy

    # Fuzzy match if nothing else worked
    if fuzzy and input_title not in language_module_settings["FUZZ_IGNORE_WORDS"]:
        fuzzy_result = _fuzzy_text(input_title, reference_lists["SUPPORTED_LANGUAGES"])
        if fuzzy_result:
            return converter(
                fuzzy_result, fuzzy=False, preserve_country=preserve_country
            )

    # Final fallback: maybe a script code
    if len(input_text) == 4:
        try:
            lingvo_script = _iso_codes_deep_search(input_text, script_search=True)
            if lingvo_script:
                lingvo_copy = copy.deepcopy(lingvo_script)
                if not preserve_country:
                    lingvo_copy.country = None
                return lingvo_copy
            else:
                return None
        except TypeError:
            pass

    return None


def parse_language_list(list_string):
    """
    Splits a string of language codes or names using flexible delimiters.
    Examples: "ar, latin, yi", "ko+lo", etc.

    :param list_string: A possible list of languages as a string.
    :return: A sorted list of Lingvo objects, or an empty list if none found.
    """
    if not list_string:
        return []

    # Strip 'LANGUAGES:' prefix if present
    if "LANGUAGES:" in list_string:
        list_string = list_string.rpartition("LANGUAGES:")[-1].strip()
    else:
        list_string = list_string.strip()

    # Normalize various delimiters to commas
    for delimiter in ["+", "\n", "/", ":", ";"]:
        list_string = list_string.replace(delimiter, ",")

    # Handle space-delimited case specially
    if "," not in list_string and " " in list_string:
        match = converter(list_string)
        items = [list_string] if match is None else [match]
    else:
        items = list_string.split(",")

    utility_codes = {"meta", "community", "all"}
    final_lingvos = {}

    for item in items:
        item = item.strip().lower()
        if not item:
            continue

        if item in utility_codes:
            # Optionally wrap utility codes as special Lingvo objects if needed
            continue  # or handle separately
        else:
            lang = converter(item)
            if lang:
                final_lingvos[lang.preferred_code] = (
                    lang  # Deduplicate by preferred code
                )

    return sorted(
        final_lingvos.values(), key=lambda lingvo: lingvo.preferred_code.lower()
    )


"""MANAGING COUNTRIES DATA"""


def get_country_emoji(country_name):
    """Return the flag emoji for a given country name."""
    if not country_name:
        return ""

    try:
        # Try direct name match first
        country = pycountry.countries.get(name=country_name)
    except LookupError:
        country = None

    if not country:
        # Try using common_name (like "UK" or "South Korea")
        try:
            country = pycountry.countries.get(common_name=country_name)
        except LookupError:
            country = None

    if not country:
        # Try fuzzy lookup (partial match)
        try:
            matches = pycountry.countries.search_fuzzy(country_name)
            if matches:
                country = matches[0]
        except LookupError:
            country = None

    if country:
        code = country.alpha_2
        return chr(ord(code[0]) + 127397) + chr(ord(code[1]) + 127397)
    else:
        return ""


def _load_country_list():
    """
    Load countries from a CSV file. Returns a list of tuples.
    Expected CSV columns: CountryName, Alpha2, Alpha3, NumericCode,
                          Keywords (semicolon-separated)
    """
    country_list = []
    with open(Paths.DATASETS["COUNTRIES"], newline="", encoding="utf-8") as csvfile:
        reader = csv.reader(csvfile)
        for row in reader:
            name = row[0].strip()
            alpha2 = row[1].strip()
            alpha3 = row[2].strip()
            numeric = row[3].strip()
            keywords = (
                row[4].strip().split(";") if len(row) > 4 and row[4].strip() else []
            )
            country_list.append((name, alpha2, alpha3, numeric, keywords))
    return country_list


def country_converter(text_input, abbreviations_okay=True):
    """
    Detects a country based on input. Supports full names, 2-letter
    and 3-letter codes, or associated keywords.

    :param text_input: The input text to match.
    :param abbreviations_okay: If True, allow matching by abbreviations,
                               like 'CN' or 'MX'. Default is True.
    :return: (country_code, country_name)
    """
    country_list = _load_country_list()

    text = text_input.strip()
    if len(text) <= 1:
        return "", ""

    text_upper = text.upper()
    text_title = text.title()

    # Match 2-letter code
    if len(text) == 2 and abbreviations_okay:
        for name, alpha2, _, _, _ in country_list:
            if text_upper == alpha2:
                return alpha2, name

    # Match 3-letter code
    if len(text) == 3 and abbreviations_okay:
        for name, alpha2, alpha3, _, _ in country_list:
            if text_upper == alpha3:
                return alpha2, name

    # Initialize fallback match variables
    possible_code = ""
    possible_name = ""

    # Match exact or partial name
    for name, alpha2, _, _, _ in country_list:
        if text_title == name:
            return alpha2, name
        elif text_title in name and len(text_title) >= 3:
            possible_code = alpha2
            possible_name = name

    # Match keyword
    for name, alpha2, _, _, keywords in country_list:
        if any(text_title == kw for kw in keywords):
            return alpha2, name

    # Fallback to partial name match
    if possible_code and possible_name:
        return possible_code, possible_name

    return "", ""


def select_random_language(iso_639_1=False):
    """
    Pick a random language code and name from our CSV file.

    Args:
        iso_639_1 (bool): If True, select ISO 639-1 codes (2-letter).
                          Otherwise, select ISO 639-3 codes (3-letter).

    Returns:
        Lingvo or None if no match found.
    """
    pattern = r"^[a-z]{2}$" if iso_639_1 else r"^[a-z]{3}$"

    with open(
        Paths.DATASETS["ISO_CODES"], "r", newline="", encoding="utf-8"
    ) as csvfile:
        reader = csv.reader(csvfile)
        next(reader, None)  # Skip header

        filtered = [
            row
            for row in reader
            if row
            and re.match(pattern, row[1] if iso_639_1 else row[0])
            and (iso_639_1 or not ("qaa" <= row[0].lower() <= "qtz"))
        ]

    if not filtered:
        return None

    chosen = random.choice(filtered)
    code_index = 1 if iso_639_1 else 0
    selected_language = converter(chosen[code_index])

    return selected_language


def show_menu():
    print("\nSelect a test to run:")
    print("1. Converter test (enter a string to test with the converter)")
    print("2. Parse language list (enter a language list string to parse)")
    print("x. Exit")


if __name__ == "__main__":
    while True:
        show_menu()
        choice = input("Enter your choice (1-2 or x): ")

        if choice == "x":
            print("Exiting...")
            break

        if choice not in ["1", "2"]:
            print("Invalid choice, please try again.")
            continue

        if choice == "1":
            my_test = input("Enter the string you wish to test with the converter: ")
            converter_result = converter(my_test)

            if converter_result:
                print(
                    f"Your Input: `{my_test}` → Preferred Code: `{converter_result.preferred_code}`"
                )
                pprint(vars(converter_result))
            else:
                print("Did not match anything.")

        elif choice == "2":
            language_list_input = input(
                "Enter the language list from a subscription message to parse: "
            )
            parse_result = parse_language_list(language_list_input)
            pprint(parse_result)
