#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
A collection of database sets and language functions that all r/translator bots use.
"""
import copy
import csv
import random
import re

import orjson  # Using for faster performance
import pycountry
from rapidfuzz import fuzz

from config import Paths, load_settings

# Load the language module's settings and parse the file's content
language_module_settings = load_settings(Paths.SETTINGS['LANGUAGES_MODULE_SETTINGS'])


class Lingvo:
    def __init__(self, **kwargs):
        self.name = kwargs.get("name")
        self.name_alternates = kwargs.get("name_alternates", [])
        self.language_code_1 = kwargs.get("language_code_1")
        self.language_code_3 = kwargs.get("language_code_3")
        self.script_code = kwargs.get("script_code")  # For script entries
        self.country = kwargs.get("country")  # country code
        self.countries_default = kwargs.get("countries_default")
        self.family = kwargs.get("family")
        self.mistake_abbreviation = kwargs.get("mistake_abbreviation")
        self.population = kwargs.get("population")
        self.subreddit = kwargs.get("subreddit")
        self.supported = kwargs.get("supported", False)
        self.thanks = kwargs.get("thanks")
        self.link_ethnologue = kwargs.get("link_ethnologue")
        self.link_wikipedia = kwargs.get("link_wikipedia")

        # New statistics fields
        self.num_months = kwargs.get("num_months")
        self.rate_daily = kwargs.get("rate_daily")
        self.rate_monthly = kwargs.get("rate_monthly")
        self.rate_yearly = kwargs.get("rate_yearly")
        self.link_statistics = kwargs.get("permalink")  # Maps permalink → statistics_page

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
        return f"<Lingvo: {self.name} ({self.preferred_code})>"

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
            language_code_3=row.get("ISO 639-3") or None,
            country=None,
            countries_default=None,
            family=None,
            mistake_abbreviation=None,
            population=0,
            subreddit=None,
            supported=False,
            thanks=None,
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
            "language_code_3": self.language_code_3,
            "script_code": self.script_code,
            "country": self.country,
            "countries_default": self.countries_default,
            "family": self.family,
            "mistake_abbreviation": self.mistake_abbreviation,
            "population": self.population,
            "subreddit": self.subreddit,
            "supported": self.supported,
            "thanks": self.thanks,
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


def load_lingvo_dataset():
    """
    Loads the language dataset by combining raw language data and
    utility language data, then returns a dictionary of Lingvo instances.
    This also adds a limited amount of data regarding the language's
    statistical history on r/translator.

    :return: dict[str, Lingvo]
    """
    # Add statistics if present, but only include specific keys
    allowed_keys = {
        "num_months",
        "permalink",
        "rate_daily",
        "rate_monthly",
        "rate_yearly",
    }

    raw_data = load_settings(Paths.DATASETS["LANGUAGE_DATA"])
    utility_data = load_settings(Paths.DATASETS["UTILITY_LINGVO_DATA"])
    with open(Paths.LOGS["STATISTICS"], "rb") as f:  # Note 'rb' for binary mode
        statistics_data = orjson.loads(f.read())  # Need to read the file content first

    combined_data = {}

    # First process raw data
    for code, attrs in raw_data.items():
        combined_data[code] = attrs.copy()

    # Then overlay utility data (which may add new entries or override existing ones)
    for code, attrs in utility_data.items():
        if code in combined_data:
            combined_data[code].update(attrs)
        else:
            combined_data[code] = attrs.copy()

    # Add statistics if present
    for code, stats in statistics_data.items():
        filtered_stats = {k: v for k, v in stats.items() if k in allowed_keys}
        if not filtered_stats:
            continue  # Skip if nothing relevant

        if code in combined_data:
            combined_data[code].update(filtered_stats)
        else:
            combined_data[code] = filtered_stats.copy()

    return {code: Lingvo(**attrs) for code, attrs in combined_data.items()}


def define_language_lists():
    """
    Generate various language code and name mappings from a language dataset.

    :return: A dictionary with structured language metadata lists and mappings.
    """

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
            language_country_associated[code_1] = lingvo.countries_associated  # TODO check on this.

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
    text = text.lower()
    text = re.sub(r'[^\w\s]', '', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def fuzzy_text(word, supported_languages, threshold=75):
    exclude = language_module_settings['FUZZ_IGNORE_LANGUAGE_NAMES']
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


"""MAIN CONVERTER FUNCTIONS"""


def iso_codes_deep_search(search_term, script_search=False):
    """
    Searches for a language or script code from a CSV of ISO 639-3 or
    ISO 15924 codes.

    :param search_term: The term to search for (code or name).
    :param script_search: If True, search in script codes (ISO 15924, 4-letter codes).
    :return: Lingvo object if found, else None.
    """
    search_term = search_term.strip().lower()

    if script_search:
        dataset_path = Paths.DATASETS['ISO_SCRIPT_CODES']
        code_key = "Script Code"
        name_key = "Script Name"
        alt_key = "Alternate Names"
    else:
        dataset_path = Paths.DATASETS['ISO_CODES']
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
                alternates = [alt.strip().lower() for alt in alt_raw.split(";") if alt.strip()]

                if search_term in {code, name.lower()} or search_term in alternates:
                    if script_search:
                        return Lingvo(
                            name=name,
                            name_alternates=alternates,
                            language_code_1="unknown",
                            language_code_3="unknown",
                            script_code=row.get("Script Code"),
                            supported=True
                        )
                    else:
                        return Lingvo.from_csv_row(row)

    except FileNotFoundError:
        print(f"Dataset not found: {dataset_path}")
        return None

    return None


def converter(input_text: str, fuzzy: bool = True) -> Lingvo | None:
    """
    Convert an input string to a Lingvo object.
    Input can be a language code, name, or compound like zh-CN or
    unknown-CYRL.
    TODO test out with more country language combinations

    :param input_text: The input string to resolve.
    :param fuzzy: Whether to apply fuzzy name matching.
    :return: A Lingvo instance or None if not found.
    """
    input_text = input_text.strip()
    input_lower = input_text.lower()
    reference_lists = define_language_lists()

    # Handle compound codes like zh-CN or unknown-Cyrl first,
    # because that affects country assignment logic
    if "-" in input_text and "Anglo" not in input_text:
        broader, specific = input_text.split("-", 1)

        if broader.lower() == "unknown":
            try:
                result = iso_codes_deep_search(specific, script_search=True)
                script_name = getattr(result, "name", None)
                if not script_name:
                    return None
                return Lingvo(name=script_name, language_code_3=specific, supported=False)
            except (AttributeError, TypeError):
                return None

        # Language-region combo
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
            lingvo_copy.country = None
            return lingvo_copy
        if input_title in (alt.title() for alt in lingvo.name_alternates or []):
            lingvo_copy = copy.deepcopy(lingvo)
            lingvo_copy.country = None
            return lingvo_copy

    # Try to find a Lingvo by 2-letter code first
    if input_lower in reference_lists['ISO_639_1']:
        lingvo = lingvos.get(input_lower)
        if lingvo:
            lingvo_copy = copy.deepcopy(lingvo)
            # Clear country info for simple 2-letter code inputs
            lingvo_copy.country = None
            return lingvo_copy

    # If input is 3 letters, check if it maps to a 2-letter code, then prefer that Lingvo
    if len(input_lower) == 3:
        for code_1, lingvo in lingvos.items():
            if lingvo.language_code_3 == input_lower:
                if code_1 in lingvos:
                    lingvo_copy = copy.deepcopy(lingvos[code_1])
                    lingvo_copy.country = None
                    return lingvo_copy
                else:
                    lingvo_copy = copy.deepcopy(lingvo)
                    lingvo_copy.country = None
                    return lingvo_copy

        for lingvo in lingvos.values():
            if input_lower == lingvo.language_code_3:
                lingvo_copy = copy.deepcopy(lingvo)
                lingvo_copy.country = None
                return lingvo_copy

    # First try language codes.
    iso_search = iso_codes_deep_search(input_text)
    if not iso_search:
        iso_search = iso_codes_deep_search(input_text, script_search=True)

    if iso_search:
        # iso_codes_deep_search returns a Lingvo instance.
        # Copy it and clear country for simple inputs
        lingvo_copy = copy.deepcopy(iso_search)
        lingvo_copy.country = None
        return lingvo_copy

    # Special abbreviation fixes (like 'vn' meaning Vietnamese)
    if input_lower in reference_lists['MISTAKE_ABBREVIATIONS']:
        fixed = reference_lists['MISTAKE_ABBREVIATIONS'][input_lower]
        lingvo = lingvos.get(fixed)
        if lingvo:
            lingvo_copy = copy.deepcopy(lingvo)
            lingvo_copy.country = None
            return lingvo_copy

    # ISO 639-2B mapping (e.g., 'fre' -> 'fr')
    if input_lower in reference_lists['ISO_639_2B']:
        canonical_code = reference_lists['ISO_639_2B'][input_lower]
        lingvo = lingvos.get(canonical_code)
        if lingvo:
            lingvo_copy = copy.deepcopy(lingvo)
            lingvo_copy.country = None
            return lingvo_copy

    # Fuzzy match if nothing else worked
    if fuzzy and input_title not in language_module_settings['FUZZ_IGNORE_WORDS']:
        fuzzy_result = fuzzy_text(input_title, reference_lists['SUPPORTED_LANGUAGES'])
        if fuzzy_result:
            return converter(fuzzy_result, fuzzy=False)

    # Final fallback: maybe a script code
    if len(input_text) == 4:
        try:
            lingvo_script = iso_codes_deep_search(input_text, script_search=True)
            if lingvo_script:
                lingvo_copy = copy.deepcopy(lingvo_script)
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
    if 'LANGUAGES:' in list_string:
        list_string = list_string.rpartition('LANGUAGES:')[-1].strip()
    else:
        list_string = list_string.strip()

    # Normalize various delimiters to commas
    for delimiter in ['+', '\n', '/', ':', ';']:
        list_string = list_string.replace(delimiter, ',')

    # Handle space-delimited case specially
    if ',' not in list_string and ' ' in list_string:
        match = converter(list_string)
        items = [list_string] if match is None else [match]
    else:
        items = list_string.split(',')

    utility_codes = {'meta', 'community', 'all'}
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
                final_lingvos[lang.preferred_code] = lang  # Deduplicate by preferred code

    return sorted(final_lingvos.values(), key=lambda lingvo: lingvo.preferred_code.lower())


"""MANAGING COUNTRIES DATA"""


def get_country_emoji(country_name):
    """ Returns the emoji for a given country name in English.

    :param country_name: Name of a country in English.
    :return: Emoji if found, an empty string otherwise.
    """
    # Find the country using pycountry
    country = pycountry.countries.get(name=country_name)

    # If country not found, try matching common names (like UK
    # for the United Kingdom.)
    if not country:
        country = pycountry.countries.get(common_name=country_name)

    if country:
        # Convert the alpha_2 code (ISO 3166-1) to emoji
        code = country.alpha_2
        # Convert each character to its corresponding regional indicator symbol
        flag = chr(ord(code[0]) + 127397) + chr(ord(code[1]) + 127397)
        return flag
    else:
        return ''


def load_country_list():
    """
    Load countries from a CSV file. Returns a list of tuples.
    Expected CSV columns: CountryName, Alpha2, Alpha3, NumericCode,
                          Keywords (semicolon-separated)
    """
    country_list = []
    with open(Paths.DATASETS['COUNTRIES'], newline='', encoding='utf-8') as csvfile:
        reader = csv.reader(csvfile)
        for row in reader:
            name = row[0].strip()
            alpha2 = row[1].strip()
            alpha3 = row[2].strip()
            numeric = row[3].strip()
            keywords = row[4].strip().split(';') if len(row) > 4 and row[4].strip() else []
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
    country_list = load_country_list()

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
    Pick a random language code and name from a CSV file.

    Args:
        iso_639_1 (bool): If True, select ISO 639-1 codes (2-letter).
                          Otherwise, select ISO 639-3 codes (3-letter).

    Returns:
        tuple: (code, language name) or None if no match found.
    """
    pattern = r'^[a-z]{2}$' if iso_639_1 else r'^[a-z]{3}$'

    with open(Paths.DATASETS['ISO_CODES'], 'r', newline='', encoding='utf-8') as csvfile:
        reader = csv.reader(csvfile)
        next(reader, None)  # Skip header

        filtered = [
            row for row in reader
            if row and re.match(pattern, row[1] if iso_639_1 else row[0])
            and (iso_639_1 or not ('qaa' <= row[0].lower() <= 'qtz'))
        ]

    if not filtered:
        return None

    chosen = random.choice(filtered)
    code_index = 1 if iso_639_1 else 0
    return chosen[code_index], chosen[2]


# Load dataset for functions to use internally.
lingvos = load_lingvo_dataset()

if __name__ == "__main__":
    while True:
        my_test = input("Enter the string you wish to test with the converter: ")
        converter_result = converter(my_test)

        if converter_result:
            print(converter_result.preferred_code)
            print(vars(converter_result))
        else:
            print("Did not match anything.")
