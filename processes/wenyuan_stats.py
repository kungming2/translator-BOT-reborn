#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
Lumo - Translation Statistics Analyzer

A high-performance analyzer for translation request statistics from r/translator.
Provides time-based filtering, language-specific analytics, and aggregated metrics
for translation posts stored in the Ajo database.

Key features:
- Flexible time range queries (days, months, all-time)
- Language-specific filtering with fuzzy matching support
- Performance-optimized with LRU caching
- Handles both single-language and multi-language posts
- Direction analysis (to/from/non-English translations)

REFACTORED VERSION - Optimized for efficiency and consistency with stable modules.
"""

import calendar
import time
from collections import Counter, defaultdict
from collections.abc import Iterator
from datetime import datetime
from functools import lru_cache
from typing import Any

from database import db, search_database
from languages import converter, parse_language_list, Lingvo
from models.ajo import Ajo, ajo_loader
from time_handling import time_convert_to_string

# Type aliases for clarity
TimeRange = tuple[int, int]  # (start_timestamp, end_timestamp)
LanguageStats = dict[str, Any]  # Statistics dictionary for a language
FastestStats = dict[str, dict[str, float | None | str] | float]  # Nested timing stats


def get_effective_status(ajo: Ajo) -> str:
    """
    Get effective status string for any Ajo type.
    Handles both single posts and defined multiples consistently.

    For defined multiples, returns the "dominant" status:
    - "translated" if all languages are translated
    - "partial" if some are translated
    - "untranslated" otherwise

    Args:
        ajo: The Ajo object to get status from

    Returns:
        Status string
    """
    if isinstance(ajo.status, str):
        return ajo.status
    elif isinstance(ajo.status, dict):
        statuses = list(ajo.status.values())
        if all(s == "translated" for s in statuses):
            return "translated"
        elif any(s == "translated" for s in statuses):
            return "partial"
        elif all(s == "doublecheck" for s in statuses):
            return "doublecheck"
        elif any(s == "inprogress" for s in statuses):
            return "inprogress"
        return "untranslated"
    return "untranslated"


class Lumo:
    """Analyzes translation request statistics from a database of Ajos (request objects)."""

    def __init__(
        self, start_time: int | None = None, end_time: int | None = None
    ) -> None:
        """
        Initialize Lumo analyzer.

        Args:
            start_time: Unix timestamp for default start time
            end_time: Unix timestamp for default end time
        """
        self.ajos: list[Ajo] = []
        self._cache: dict[str, Any] = {}
        self.start_time = start_time
        self.end_time = end_time

        # Earliest possible post date: January 1, 2015
        self.EARLIEST_POST = self.date_to_unix(2015, 1, 1)

    def __iter__(self) -> Iterator[Ajo]:
        """Allow direct iteration over Lumo instance."""
        return iter(self.ajos)

    def __len__(self) -> int:
        """Return the number of loaded Ajos."""
        return len(self.ajos)

    def __getitem__(self, index: int) -> Ajo:
        """Allow indexing into Lumo instance."""
        return self.ajos[index]

    def __repr__(self) -> str:
        """Return a string representation of the Lumo instance."""
        return f"<Lumo: {len(self.ajos)} Ajos loaded>"

    # ==================== Time Helper Methods ====================

    @staticmethod
    def date_to_unix(
        year: int,
        month: int,
        day: int = 1,
        hour: int = 0,
        minute: int = 0,
        second: int = 0,
    ) -> int:
        """
        Convert a date to Unix timestamp.

        Args:
            year: Year (e.g., 2023)
            month: Month (1-12)
            day: Day of month (default: 1)
            hour: Hour (default: 0)
            minute: Minute (default: 0)
            second: Second (default: 0)

        Returns:
            Unix timestamp as integer
        """
        dt = datetime(year, month, day, hour, minute, second)
        return int(calendar.timegm(dt.timetuple()))

    @staticmethod
    def month_to_unix_range(year: int, month: int) -> TimeRange:
        """
        Get Unix timestamp range for an entire month.

        Returns:
            Tuple of (start_timestamp, end_timestamp)
        """
        # First day of month at 00:00:00
        start = Lumo.date_to_unix(year, month, 1, 0, 0, 0)

        # Last day of month at 23:59:59
        last_day = calendar.monthrange(year, month)[1]
        end = Lumo.date_to_unix(year, month, last_day, 23, 59, 59)

        return start, end

    @staticmethod
    def last_n_days(days: int = 30) -> TimeRange:
        """
        Get Unix timestamp range for the last N days.

        Returns:
            Tuple of (start_timestamp, end_timestamp)
        """
        end = int(time.time())
        start = end - (days * 86400)  # 86400 seconds in a day
        return start, end

    @staticmethod
    def all_time_range() -> TimeRange:
        """
        Get Unix timestamp range for all time (from Jan 1, 2015 to now).

        Returns:
            Tuple of (start_timestamp, end_timestamp)
        """
        start = Lumo.date_to_unix(2015, 1, 1)
        end = int(time.time())
        return start, end

    # ==================== Data Loading ====================

    def load_ajos(
        self,
        start_time: int | None = None,
        end_time: int | None = None,
        all_time: bool = False,
    ) -> list[Ajo]:
        """
        Load Ajos from database within time range using stable ajo_loader().

        Args:
            start_time: Unix timestamp for start (uses instance default if not provided)
            end_time: Unix timestamp for end (uses instance default if not provided)
            all_time: If True, load all posts from Jan 1, 2015 to now

        Returns:
            List of loaded Ajo objects

        Raises:
            ValueError: If time parameters are not provided and no defaults exist
        """
        # Handle all_time flag
        if all_time:
            start, end = self.all_time_range()
        else:
            # Use provided times or fall back to instance defaults
            start = start_time if start_time is not None else self.start_time
            end = end_time if end_time is not None else self.end_time

        if start is None or end is None:
            raise ValueError(
                "start_time and end_time must be provided either "
                "during init, when calling load_ajos, or use all_time=True"
            )

        # Update instance times
        self.start_time = start
        self.end_time = end
        self.ajos = []

        # Query database for Ajo IDs in time range
        query = (
            "SELECT id FROM ajo_database WHERE created_utc >= ? AND created_utc <= ?"
        )
        results = db.fetchall_ajo(query, (start, end))

        # Load Ajos using stable ajo_loader function
        for row in results:
            ajo = ajo_loader(row["id"])
            if ajo:
                self.ajos.append(ajo)

        # Expand defined multiple language posts
        self.ajos = self._expand_multiple_language_posts(self.ajos)

        # Clear any cached results since data changed
        self._clear_cache()

        return self.ajos

    def load_month(self, year: int, month: int) -> list[Ajo]:
        """Convenience method to load all Ajos from a specific month."""
        start, end = self.month_to_unix_range(year, month)
        return self.load_ajos(start, end)

    def load_last_days(self, days: int = 30) -> list[Ajo]:
        """Convenience method to load Ajos from the last N days."""
        start, end = self.last_n_days(days)
        return self.load_ajos(start, end)

    def load_all_time(self) -> list[Ajo]:
        """Convenience method to load ALL Ajos from Jan 1, 2015 to now."""
        return self.load_ajos(all_time=True)

    def load_from_list(self, ajos: list[Ajo]) -> None:
        """Load Ajos directly from a list (useful for testing)."""
        self.ajos = self._expand_multiple_language_posts(ajos)
        self._clear_cache()

    def load_for_user(
        self,
        username: str,
        start_time: int | None = None,
        end_time: int | None = None,
    ) -> list[Ajo]:
        """
        Load all Ajos by a specific user using stable search_database().

        Args:
            username: Reddit username (without 'u/' prefix)
            start_time: Optional Unix timestamp for start
            end_time: Optional Unix timestamp for end

        Returns:
            List of user's Ajo objects
        """
        # Use search_database function from database.py
        start_utc = start_time or self.start_time
        self.ajos = search_database(username, "user", start_utc=start_utc)

        # Apply end_time filter if provided
        if end_time:
            self.ajos = [ajo for ajo in self.ajos if ajo.created_utc <= end_time]

        # Expand multiple language posts
        self.ajos = self._expand_multiple_language_posts(self.ajos)
        self._clear_cache()

        return self.ajos

    def load_single_post(self, post_id: str) -> Ajo | None:
        """
        Load a single Ajo by post ID using stable search_database().

        Returns:
            Ajo object or None if not found
        """
        results = search_database(post_id, "post")
        if results:
            self.ajos = results
            self._clear_cache()
            return results[0]
        return None

    # ==================== Search & Filter ====================

    def filter_by_time_range(self, start_time: int, end_time: int) -> list[Ajo]:
        """Filter currently loaded Ajos by a different time range."""
        return [ajo for ajo in self.ajos if start_time <= ajo.created_utc <= end_time]

    def filter_by_language(self, language: str | Lingvo) -> list[Ajo]:
        """
        Get all requests for a specific language.
        Uses converter() for flexible matching - accepts names, codes, or alternates.

        Args:
            language: Language name, code, or Lingvo object

        Returns:
            Filtered list of Ajos
        """
        # Convert to Lingvo if needed
        if isinstance(language, str):
            target_lingvo = converter(language)
            if not target_lingvo:
                return []
        else:
            target_lingvo = language

        return [
            ajo
            for ajo in self.ajos
            if ajo.lingvo and ajo.lingvo.preferred_code == target_lingvo.preferred_code
        ]

    def filter_by_status(self, status: str) -> list[Ajo]:
        """
        Get all requests with a specific status.
        Handles both single posts and defined multiples.
        """
        results = []
        for ajo in self.ajos:
            effective_status = get_effective_status(ajo)
            if effective_status == status:
                results.append(ajo)
        return results

    def filter_by_type(self, req_type: str) -> list[Ajo]:
        """Get all requests of a specific type (single/multiple)."""
        return [ajo for ajo in self.ajos if ajo.type == req_type]

    def filter_by_direction(self, direction: str) -> list[Ajo]:
        """Get all requests with a specific translation direction."""
        return [ajo for ajo in self.ajos if ajo.direction == direction]

    def search(self, **kwargs: Any) -> list[Ajo]:
        """
        Flexible search across multiple criteria using converter() for language matching.

        Kwargs:
            language: Filter by language name/code (uses converter for flexible matching)
            status: Filter by status (translated, untranslated, etc.)
            type: Filter by type (single, multiple)
            direction: Filter by direction (english_to, english_from, etc.)
            author: Filter by post author username

        Returns:
            Filtered list of Ajos
        """
        results = self.ajos

        for key, value in kwargs.items():
            if key == "language":
                # Use the optimized filter_by_language method
                results = [
                    ajo for ajo in results if ajo in self.filter_by_language(value)
                ]
            elif key == "status":
                results = [ajo for ajo in results if get_effective_status(ajo) == value]
            elif key == "type":
                results = [ajo for ajo in results if ajo.type == value]
            elif key == "direction":
                results = [ajo for ajo in results if ajo.direction == value]
            elif key == "author":
                results = [ajo for ajo in results if ajo.author == value]

        return results

    # ==================== Language Statistics ====================

    @lru_cache(maxsize=128)
    def get_language_stats(self, language: str) -> LanguageStats | None:
        """
        Get comprehensive statistics for a specific language.
        Cached for performance on frequently accessed languages.

        Args:
            language: Language name or code

        Returns:
            Dictionary with language statistics or None if no data
        """
        # Convert to ensure we have a valid language
        lingvo = converter(language)
        if not lingvo:
            return None

        language_ajos = self.filter_by_language(lingvo)

        if not language_ajos:
            return None

        # Collect statuses using the helper method
        statuses = [get_effective_status(ajo) for ajo in language_ajos]

        if not statuses:
            return None

        total = len(statuses)

        translated = statuses.count("translated")
        doublecheck = statuses.count("doublecheck")
        untranslated = (
            statuses.count("untranslated")
            + statuses.count("missing")
            + statuses.count("inprogress")
        )

        # Calculate translation percentage
        translation_pct = (
            int(((translated + doublecheck) / total) * 100) if total > 0 else 0
        )

        # Calculate percentage of all requests
        percent_of_all = round((total / len(self.ajos)) * 100, 2) if self.ajos else 0

        # Calculate direction ratios using Counter
        directions = self._calculate_directions(language_ajos)

        return {
            "language": lingvo.name,
            "total_requests": total,
            "translated": translated,
            "needs_review": doublecheck,
            "untranslated": untranslated,
            "translation_percentage": translation_pct,
            "percent_of_all_requests": percent_of_all,
            "directions": directions,
        }

    def get_stats_for_languages(
        self, language_string: str
    ) -> dict[str, LanguageStats | None]:
        """
        Get stats for multiple languages at once using parse_language_list.
        Accepts: "German, French, Spanish" or "de+fr+es" etc.

        Args:
            language_string: String with multiple languages in various formats

        Returns:
            Dictionary mapping language names to their stats
        """
        lingvos = parse_language_list(language_string)
        return {lingvo.name: self.get_language_stats(lingvo.name) for lingvo in lingvos}

    def get_all_languages(self) -> list[str]:
        """Get list of all unique languages in the dataset."""
        languages = set()
        for ajo in self.ajos:
            if ajo.lingvo and ajo.lingvo.name:
                languages.add(ajo.lingvo.name)
        return sorted(list(languages))

    def get_language_rankings(self, by: str = "total") -> list[tuple[str, int]]:
        """
        Get languages ranked by various metrics using Counter for efficiency.

        Args:
            by: Metric to rank by ('total', 'translated', 'untranslated')

        Returns:
            List of (language, count) tuples, sorted descending
        """
        if by == "total":
            # Count all occurrences
            language_counts = Counter(
                ajo.language_name
                for ajo in self.ajos
                if ajo.lingvo and ajo.language_name
            )
        elif by == "translated":
            # Count only translated
            language_counts = Counter(
                ajo.language_name
                for ajo in self.ajos
                if ajo.lingvo
                and ajo.language_name
                and get_effective_status(ajo) == "translated"
            )
        elif by == "untranslated":
            # Count only untranslated
            language_counts = Counter(
                ajo.language_name
                for ajo in self.ajos
                if ajo.lingvo
                and ajo.language_name
                and get_effective_status(ajo) == "untranslated"
            )
        else:
            return []

        return language_counts.most_common()

    @staticmethod
    def get_language_frequency_info(language: str | Lingvo) -> dict[str, Any] | None:
        """
        Get frequency statistics for a language from Lingvo properties.
        Leverages data already embedded in Lingvo objects.

        Args:
            language: Language name, code, or Lingvo object

        Returns:
            Dictionary with frequency data or None if not available
        """
        if isinstance(language, str):
            lingvo = converter(language)
        else:
            lingvo = language

        if not lingvo:
            return None

        # Check if frequency data exists
        if not all([lingvo.rate_daily, lingvo.rate_monthly, lingvo.rate_yearly]):
            return None

        return {
            "language": lingvo.name,
            "rate_daily": lingvo.rate_daily,
            "rate_monthly": lingvo.rate_monthly,
            "rate_yearly": lingvo.rate_yearly,
            "statistics_link": lingvo.link_statistics,
            "num_months": lingvo.num_months,
        }

    # ==================== Overall Statistics ====================

    def get_overall_stats(self) -> dict[str, Any]:
        """Get overall statistics across all requests."""
        # Collect all statuses using helper method
        statuses = [get_effective_status(ajo) for ajo in self.ajos]

        total = len(self.ajos)
        translated = statuses.count("translated")
        doublecheck = statuses.count("doublecheck")

        translation_pct = (
            int(round(((translated + doublecheck) / total) * 100, 0))
            if total > 0
            else 0
        )

        return {
            "total_requests": total,
            "untranslated": statuses.count("untranslated"),
            "missing_assets": statuses.count("missing"),
            "in_progress": statuses.count("inprogress"),
            "needs_review": doublecheck,
            "translated": translated,
            "translation_percentage": translation_pct,
            "unique_languages": len(self.get_all_languages()),
        }

    def get_direction_stats(self) -> dict[str, dict[str, int | float]]:
        """Get statistics on translation directions using Counter."""
        directions = Counter(ajo.direction for ajo in self.ajos if ajo.direction)
        total = len(self.ajos)

        return {
            "to_english": {
                "count": directions["english_to"],
                "percentage": round((directions["english_to"] / total) * 100, 2)
                if total > 0
                else 0,
            },
            "from_english": {
                "count": directions["english_from"],
                "percentage": round((directions["english_from"] / total) * 100, 2)
                if total > 0
                else 0,
            },
            "non_english": {
                "count": directions["english_none"],
                "percentage": round((directions["english_none"] / total) * 100, 2)
                if total > 0
                else 0,
            },
        }

    # ==================== Time-based Analysis ====================

    def get_fastest_translations(self) -> FastestStats:
        """Find the fastest processed requests."""
        fastest: FastestStats = {
            "to_translated": {"time": float("inf"), "id": None},
            "to_review": {"time": float("inf"), "id": None},
            "to_claimed": {"time": float("inf"), "id": None},
        }

        translation_times = []

        for ajo in self.ajos:
            if not hasattr(ajo, "time_delta") or not ajo.time_delta:
                continue

            time_delta = ajo.time_delta
            created = ajo.created_utc
            ajo_id = ajo.id

            # Check translated
            if "translated" in time_delta:
                diff = time_delta["translated"] - created
                translation_times.append(diff)
                if diff < fastest["to_translated"]["time"]:
                    fastest["to_translated"] = {"time": int(diff), "id": ajo_id}

            # Check doublecheck
            if "doublecheck" in time_delta:
                diff = time_delta["doublecheck"] - created
                if diff < fastest["to_review"]["time"]:
                    fastest["to_review"] = {"time": int(diff), "id": ajo_id}

            # Check in progress
            if "inprogress" in time_delta:
                diff = time_delta["inprogress"] - created
                if diff < fastest["to_claimed"]["time"]:
                    fastest["to_claimed"] = {"time": int(diff), "id": ajo_id}

        # Calculate averages
        if translation_times:
            avg_hours = round(sum(translation_times) / len(translation_times) / 3600, 2)
            fastest["average_translation_hours"] = avg_hours

        return fastest

    # ==================== Identification Analysis ====================

    def get_identification_stats(self) -> dict[str, dict[str, int]]:
        """
        Analyze posts that were identified from 'Unknown'.
        Now normalizes language names/codes to prevent duplicates.
        """
        identified = defaultdict(int)
        misidentified = defaultdict(int)

        for ajo in self.ajos:
            if not hasattr(ajo, "language_history") or not ajo.language_history:
                continue

            history = ajo.language_history

            # Filter out None/empty values and flatten any nested lists
            cleaned_history = []
            for item in history:
                if item:
                    # Handle case where item might be a list
                    if isinstance(item, list):
                        # Skip nested lists or use first item
                        if item and isinstance(item[0], str):
                            cleaned_history.append(item[0])
                    elif isinstance(item, str):
                        cleaned_history.append(item)

            if len(cleaned_history) < 2:
                continue

            # Normalize language names in history using converter
            normalized_history = []
            for lang in cleaned_history:
                # Skip if not a string (extra safety)
                if not isinstance(lang, str):
                    continue

                # Try to convert to standard name
                lingvo = converter(lang)
                if lingvo:
                    normalized_history.append(lingvo.name)
                else:
                    # Keep original if can't convert (e.g., "Unknown", "Generic")
                    normalized_history.append(lang)

            if len(normalized_history) < 2:
                continue

            # Posts identified from Unknown
            if normalized_history[0] == "Unknown" and normalized_history[-1] not in [
                "Unknown",
                "Multiple Languages",
            ]:
                identified[normalized_history[-1]] += 1

            # Posts misidentified (wrong initial language)
            elif normalized_history[0] not in [
                "Unknown",
                "Generic",
                "Multiple Languages",
            ]:
                if normalized_history[0] != normalized_history[-1]:
                    pair = f"{normalized_history[0]} → {normalized_history[-1]}"
                    misidentified[pair] += 1

        return {
            "identified_from_unknown": dict(identified),
            "misidentified_pairs": dict(misidentified),
        }

    # ==================== Helper Methods ====================

    @staticmethod
    def _expand_multiple_language_posts(ajos: list[Ajo]) -> list[Ajo]:
        """
        Split defined multiple language posts into separate entries.
        This mimics the behavior of cerbo_defined_multiple_unpacker.
        """
        expanded = []

        for ajo in ajos:
            if ajo.is_defined_multiple and isinstance(ajo.status, dict):
                # Split into individual language entries
                for lang_code, status_value in ajo.status.items():
                    # Create a new Ajo instance with the same data
                    temp_ajo = Ajo.from_dict(ajo.to_dict())

                    # Set the language for this specific entry
                    temp_ajo.preferred_code = lang_code
                    temp_ajo.initialize_lingvo()

                    # Set the status for this language
                    temp_ajo.status = status_value
                    temp_ajo.type = "single"
                    temp_ajo.is_defined_multiple = False

                    # Update the ID to make it unique
                    temp_ajo._id = f"{ajo.id}_{lang_code}"

                    expanded.append(temp_ajo)
            else:
                expanded.append(ajo)

        return expanded

    @staticmethod
    def _calculate_directions(language_ajos: list[Ajo]) -> str:
        """
        Calculate direction ratios for a language using Counter.

        Returns:
            Formatted ratio string (e.g., "2.5:1" or "10:5")
        """
        directions = Counter(ajo.direction for ajo in language_ajos)

        # Calculate ratio
        to_count = directions.get("english_to", 0)
        from_count = directions.get("english_from", 0)

        if to_count > 0 and from_count > 0:
            ratio = round(to_count / from_count, 2)
            return f"{ratio}:1"
        else:
            return f"{to_count}:{from_count}"

    def _clear_cache(self) -> None:
        """Clear the LRU cache for get_language_stats when data changes."""
        self.get_language_stats.cache_clear()

    # ==================== Export Methods ====================

    def to_dict(self) -> dict[str, Any]:
        """Export all statistics as a dictionary."""
        return {
            "overall": self.get_overall_stats(),
            "directions": self.get_direction_stats(),
            "languages": {
                lang: self.get_language_stats(lang) for lang in self.get_all_languages()
            },
            "identifications": self.get_identification_stats(),
            "fastest": self.get_fastest_translations(),
        }


# ==================== Usage Example ====================

if __name__ == "__main__":
    # Example 1: Initialize and load a specific month
    lumo = Lumo()

    # Load all posts from September 2023
    start_x, end_x = Lumo.month_to_unix_range(2023, 9)
    print(f"September 2023 Unix range: {start_x} to {end_x}")

    # Example 2: Load with instance defaults
    lumo_with_defaults = Lumo(
        start_time=Lumo.date_to_unix(2024, 9, 1),
        end_time=Lumo.date_to_unix(2024, 9, 30, 23, 59, 59),
    )

    lumo_with_defaults.load_ajos()
    print(f"Total posts: {len(lumo_with_defaults)}")

    while True:
        # Get language input from user
        desired_language = input(
            "\nEnter language (name or code, or 'x' to exit): "
        ).strip()

        if desired_language.lower() == "x":
            break

        # Use converter for flexible language matching
        lingvo_input = converter(desired_language)
        if not lingvo_input:
            print(f"Language '{desired_language}' not recognized. Try again.")
            continue

        # Filter by language
        filtered_ajos = lumo_with_defaults.filter_by_language(lingvo_input)

        if not filtered_ajos:
            print(f"No posts found for {lingvo_input.name}")
            continue

        print(f"\n=== Found {len(filtered_ajos)} posts for {lingvo_input.name} ===\n")

        for ajo_x in filtered_ajos[:10]:  # Show first 10
            print(f"Title: {ajo_x.title_original}")
            print(f"Link: https://redd.it/{ajo_x.id}")
            print(f"Status: {ajo_x.status}")
            print(f"Date: {time_convert_to_string(ajo_x.created_utc)}")
            print("-" * 50)

        # Show statistics for this language
        stats = lumo_with_defaults.get_language_stats(lingvo_input.name)
        if stats:
            print(f"\n=== Statistics for {lingvo_input.name} ===")
            print(f"Total requests: {stats['total_requests']}")
            print(f"Translated: {stats['translated']}")
            print(f"Translation %: {stats['translation_percentage']}%")
            print(f"Direction ratio: {stats['directions']}")

    print("\n=== Lumo Session Complete ===")
    print("Available methods:")
    print("  - lumo.load_month(year, month)")
    print("  - lumo.load_last_days(days)")
    print("  - lumo.load_all_time()")
    print("  - lumo.load_for_user(username)")
    print("  - lumo.load_single_post(post_id)")
    print("  - lumo.filter_by_language(language)  # Accepts codes or names!")
    print("  - lumo.get_language_stats(language)")
    print("  - lumo.get_stats_for_languages('German, French, Spanish')")
    print("  - lumo.get_overall_stats()")
    print("  - lumo.get_direction_stats()")
