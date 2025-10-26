#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
Lumo - Translation Statistics Analyzer
A clean, modern class for analyzing translation request statistics.
Integrates with the existing database.py and models/ajo.py modules.
"""

import calendar
import time
from collections import Counter, defaultdict
from datetime import datetime
from typing import List, Dict, Optional, Tuple

from database import db, search_database
from languages import converter
from models.ajo import Ajo
from time_handling import time_convert_to_string


class Lumo:
    """Analyzes translation request statistics from a database of Ajos (request objects)."""

    def __init__(
        self, start_time: Optional[int] = None, end_time: Optional[int] = None
    ):
        """
        Initialize Lumo analyzer.

        Args:
            start_time: Unix timestamp for default start time (optional)
            end_time: Unix timestamp for default end time (optional)
        """
        self.ajos: List[Ajo] = []
        self._cache = {}
        self.start_time = start_time
        self.end_time = end_time

        # Earliest possible post date: January 1, 2015
        self.EARLIEST_POST = self.date_to_unix(2015, 1, 1)

    def __iter__(self):
        """Allow direct iteration over Lumo instance."""
        return iter(self.ajos)

    def __len__(self):
        """Return the number of loaded Ajos."""
        return len(self.ajos)

    def __getitem__(self, index):
        """Allow indexing into Lumo instance."""
        return self.ajos[index]

    def __repr__(self):
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
    def month_to_unix_range(year: int, month: int) -> Tuple[int, int]:
        """
        Get Unix timestamp range for an entire month.

        Args:
            year: Year (e.g., 2023)
            month: Month (1-12)

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
    def last_n_days(days: int = 30) -> Tuple[int, int]:
        """
        Get Unix timestamp range for the last N days.

        Args:
            days: Number of days to go back (default: 30)

        Returns:
            Tuple of (start_timestamp, end_timestamp)
        """
        end = int(time.time())
        start = end - (days * 86400)  # 86400 seconds in a day
        return start, end

    @staticmethod
    def all_time_range() -> Tuple[int, int]:
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
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
        all_time: bool = False,
    ) -> List[Ajo]:
        """
        Load Ajos (request objects) from database within time range.

        Args:
            start_time: Unix timestamp for start (uses instance default if not provided)
            end_time: Unix timestamp for end (uses instance default if not provided)
            all_time: If True, load all posts from Jan 1, 2015 to now (overrides time params)

        Returns:
            List of Ajo objects
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

        # Query database for Ajos in time range
        query = "SELECT id, created_utc, ajo FROM ajo_database WHERE created_utc >= ? AND created_utc <= ?"
        results = db.fetchall_ajo(query, (start, end))

        # Parse results into Ajo objects
        from database import _parse_ajo_row

        for result in results:
            parsed = _parse_ajo_row(result, start_utc=start)
            if parsed is None:
                continue

            post_id, created_utc, data = parsed
            try:
                ajo = Ajo.from_dict(data)
                self.ajos.append(ajo)
            except Exception as e:
                # Log error but continue processing
                print(f"Warning: Could not create Ajo from data for {post_id}: {e}")
                continue

        # Expand defined multiple language posts
        self.ajos = self._expand_multiple_language_posts(self.ajos)
        return self.ajos

    def load_month(self, year: int, month: int) -> List[Ajo]:
        """
        Convenience method to load all Ajos from a specific month.

        Args:
            year: Year (e.g., 2023)
            month: Month (1-12)

        Returns:
            List of Ajo objects
        """
        start, end = self.month_to_unix_range(year, month)
        return self.load_ajos(start, end)

    def load_last_days(self, days: int = 30) -> List[Ajo]:
        """
        Convenience method to load Ajos from the last N days.

        Args:
            days: Number of days to go back (default: 30)

        Returns:
            List of Ajo objects
        """
        start, end = self.last_n_days(days)
        return self.load_ajos(start, end)

    def load_all_time(self) -> List[Ajo]:
        """
        Convenience method to load ALL Ajos from the beginning (Jan 1, 2015) to now.

        Returns:
            List of Ajo objects
        """
        return self.load_ajos(all_time=True)

    def load_from_list(self, ajos: List[Ajo]) -> None:
        """Load Ajos directly from a list (useful for testing)."""
        self.ajos = self._expand_multiple_language_posts(ajos)

    def load_for_user(
        self,
        username: str,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
    ) -> List[Ajo]:
        """
        Load all Ajos created by a specific user within an optional time range.

        Args:
            username: Reddit username (without 'u/')
            start_time: Optional Unix timestamp for start
            end_time: Optional Unix timestamp for end

        Returns:
            List of Ajo objects
        """
        # Use search_database function from database.py
        start_utc = start_time or self.start_time
        self.ajos = search_database(username, "user", start_utc=start_utc)

        # Apply end_time filter if provided
        if end_time:
            self.ajos = [ajo for ajo in self.ajos if ajo.created_utc <= end_time]

        # Expand multiple language posts
        self.ajos = self._expand_multiple_language_posts(self.ajos)
        return self.ajos

    def load_single_post(self, post_id: str) -> Optional[Ajo]:
        """
        Load a single Ajo by post ID.

        Args:
            post_id: Reddit post ID

        Returns:
            Ajo object or None if not found
        """
        results = search_database(post_id, "post")
        if results:
            self.ajos = results
            return results[0]
        return None

    # ==================== Search & Filter ====================

    def filter_by_time_range(self, start_time: int, end_time: int) -> List[Ajo]:
        """
        Filter currently loaded Ajos by a different time range.

        Args:
            start_time: Unix timestamp for start
            end_time: Unix timestamp for end

        Returns:
            Filtered list of Ajos
        """
        return [ajo for ajo in self.ajos if start_time <= ajo.created_utc <= end_time]

    def filter_by_language(self, language: str) -> List[Ajo]:
        """Get all requests for a specific language."""
        return [
            ajo
            for ajo in self.ajos
            if ajo.lingvo and ajo.language_name and ajo.language_name == language
        ]

    def filter_by_status(self, status: str) -> List[Ajo]:
        """Get all requests with a specific status."""
        results = []
        for ajo in self.ajos:
            # Handle both string status and dict status (for defined multiples)
            if isinstance(ajo.status, str):
                if ajo.status == status:
                    results.append(ajo)
            elif isinstance(ajo.status, dict):
                if status in ajo.status.values():
                    results.append(ajo)
        return results

    def filter_by_type(self, req_type: str) -> List[Ajo]:
        """Get all requests of a specific type (single/multiple)."""
        return [ajo for ajo in self.ajos if ajo.type == req_type]

    def filter_by_direction(self, direction: str) -> List[Ajo]:
        """Get all requests with a specific translation direction."""
        return [ajo for ajo in self.ajos if ajo.direction == direction]

    def search(self, **kwargs) -> List[Ajo]:
        """
        Flexible search across multiple criteria.

        Kwargs:
            language: Filter by language name
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
                results = [
                    ajo
                    for ajo in results
                    if ajo.language_name and ajo.language_name == value
                ]
            elif key == "status":
                filtered = []
                for ajo in results:
                    if isinstance(ajo.status, str) and ajo.status == value:
                        filtered.append(ajo)
                    elif isinstance(ajo.status, dict) and value in ajo.status.values():
                        filtered.append(ajo)
                results = filtered
            elif key == "type":
                results = [ajo for ajo in results if ajo.type == value]
            elif key == "direction":
                results = [ajo for ajo in results if ajo.direction == value]
            elif key == "author":
                results = [ajo for ajo in results if ajo.author == value]

        return results

    # ==================== Language Statistics ====================

    def get_language_stats(self, language: str) -> Optional[Dict]:
        """
        Get comprehensive statistics for a specific language.

        Returns:
            Dictionary with language statistics or None if no data
        """
        language_ajos = self.filter_by_language(language)

        if not language_ajos:
            return None

        # Collect statuses (handle both single and defined multiple)
        statuses = []
        for ajo in language_ajos:
            try:
                if isinstance(ajo.status, str):
                    statuses.append(ajo.status)
                elif isinstance(ajo.status, dict):
                    # For defined multiples, get the status for this specific language
                    lang_code = ajo.preferred_code
                    if lang_code in ajo.status:
                        statuses.append(ajo.status[lang_code])
            except (AttributeError, TypeError):
                # Skip Ajos with invalid status
                continue

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

        # Calculate direction ratios
        directions = self._calculate_directions(language_ajos)

        return {
            "language": language,
            "total_requests": total,
            "translated": translated,
            "needs_review": doublecheck,
            "untranslated": untranslated,
            "translation_percentage": translation_pct,
            "percent_of_all_requests": percent_of_all,
            "directions": directions,
        }

    def get_all_languages(self) -> List[str]:
        """Get list of all unique languages in the dataset."""
        languages = set()
        for ajo in self.ajos:
            try:
                lang = ajo.language_name
                if lang:
                    languages.add(lang)
            except AttributeError:
                # Skip Ajos with no valid language_name
                continue
        return sorted(list(languages))

    def get_language_rankings(self, by: str = "total") -> List[Tuple[str, int]]:
        """
        Get languages ranked by various metrics.

        Args:
            by: Metric to rank by ('total', 'translated', 'untranslated')

        Returns:
            List of (language, count) tuples, sorted descending
        """
        language_counts = Counter()

        for ajo in self.ajos:
            try:
                lang = ajo.language_name
                if not lang:
                    continue
            except AttributeError:
                continue

            if by == "total":
                language_counts[lang] += 1
            elif by == "translated" and ajo.status == "translated":
                language_counts[lang] += 1
            elif by == "untranslated" and ajo.status == "untranslated":
                language_counts[lang] += 1

        return language_counts.most_common()

    # ==================== Overall Statistics ====================

    def get_overall_stats(self) -> Dict:
        """Get overall statistics across all requests."""
        # Only count single-type posts for status breakdown
        single_ajos = [ajo for ajo in self.ajos if ajo.type == "single"]
        statuses = [ajo.status for ajo in single_ajos if isinstance(ajo.status, str)]

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

    def get_direction_stats(self) -> Dict:
        """Get statistics on translation directions."""
        directions = [ajo.direction for ajo in self.ajos if ajo.type == "single"]
        total = len(self.ajos)

        return {
            "to_english": {
                "count": directions.count("english_to"),
                "percentage": round((directions.count("english_to") / total) * 100, 2)
                if total > 0
                else 0,
            },
            "from_english": {
                "count": directions.count("english_from"),
                "percentage": round((directions.count("english_from") / total) * 100, 2)
                if total > 0
                else 0,
            },
            "non_english": {
                "count": directions.count("english_none"),
                "percentage": round((directions.count("english_none") / total) * 100, 2)
                if total > 0
                else 0,
            },
        }

    # ==================== Time-based Analysis ====================

    def get_fastest_translations(self) -> Dict[str, Dict[str, float | None] | float]:
        """Find the fastest processed requests."""
        fastest: Dict[str, Dict[str, float | None] | float] = {
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

    def get_identification_stats(self) -> Dict:
        """Analyze posts that were identified from 'Unknown'."""
        identified = defaultdict(int)
        misidentified = defaultdict(int)

        for ajo in self.ajos:
            if not hasattr(ajo, "language_history") or not ajo.language_history:
                continue

            history = ajo.language_history
            if len(history) < 2:
                continue

            # Posts identified from Unknown
            if history[0] == "Unknown" and history[-1] not in [
                "Unknown",
                "Multiple Languages",
            ]:
                identified[history[-1]] += 1

            # Posts misidentified (wrong initial language)
            elif history[0] not in ["Unknown", "Generic", "Multiple Languages"]:
                if history[0] != history[-1]:
                    pair = f"{history[0]} → {history[-1]}"
                    misidentified[pair] += 1

        return {
            "identified_from_unknown": dict(identified),
            "misidentified_pairs": dict(misidentified),
        }

    # ==================== Helper Methods ====================

    @staticmethod
    def _expand_multiple_language_posts(ajos: List[Ajo]) -> List[Ajo]:
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
    def _calculate_directions(language_ajos: List[Ajo]) -> str:
        """Calculate direction ratios for a language."""
        directions = {
            "english_to": 0,
            "english_from": 0,
            "english_none": 0,
            "english_both": 0,
        }

        for ajo in language_ajos:
            direction = ajo.direction
            if direction in directions:
                directions[direction] += 1

        # Calculate ratio
        if directions["english_to"] > 0 and directions["english_from"] > 0:
            ratio = round(directions["english_to"] / directions["english_from"], 2)
            return f"{ratio}:1"
        else:
            return f"{directions['english_to']}:{directions['english_from']}"

    # ==================== Export Methods ====================

    def to_dict(self) -> Dict:
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

    # Load all German posts from September 2023
    start_x, end_x = Lumo.month_to_unix_range(2023, 9)
    print(f"September 2024 Unix range: {start_x} to {end_x}")

    # lumo.load_month(2023, 9)

    # Example 2: Load last 30 days
    # lumo.load_last_days(30)

    # Example 3: Load ALL time (from Jan 1, 2015 to now)
    # lumo.load_all_time()
    # estonian_all_time = lumo.filter_by_language('Estonian')

    # Example 4: Load posts by specific user
    # lumo.load_for_user('username')
    # user_stats = lumo.get_overall_stats()

    # Example 5: Load a single post
    # ajo = lumo.load_single_post('abc123')
    # if ajo:
    #     print(f"Loaded post: {ajo.title}")

    # Example 6: Load with instance defaults
    lumo_with_defaults = Lumo(
        start_time=Lumo.date_to_unix(2024, 9, 1),
        end_time=Lumo.date_to_unix(2024, 9, 30, 23, 59, 59),
    )

    lumo_with_defaults.load_ajos()
    # Get length
    print(f"Total posts: {len(lumo_with_defaults)}")

    while True:
        # Get language input from user
        desired_language = input(
            "Enter the language you want to filter by (e.g., German, English, Estonian): "
        ).strip()

        # lumo_with_defaults.load_ajos()  # Uses instance defaults
        for ajo_x in lumo_with_defaults.filter_by_language(
            converter(desired_language).name
        ):
            print(f"{desired_language} post: {ajo_x.title_original}")
            print(f"Link to post: https://redd.it/{ajo_x.id}")
            print(f"Status of post: {ajo_x.status}")
            print(f"Date of post: {time_convert_to_string(ajo_x.created_utc)}")
            print("-" * 9)

        print("\n=== Lumo initialized successfully ===")
        print("Available methods:")
        print("  - lumo.load_month(year, month)")
        print("  - lumo.load_last_days(days)")
        print("  - lumo.load_all_time()")
        print("  - lumo.load_for_user(username)")
        print("  - lumo.load_single_post(post_id)")
        print("  - lumo.filter_by_language(language)")
        print("  - lumo.get_language_stats(language)")
        print("  - lumo.get_overall_stats()")
        print("  - lumo.get_direction_stats()")
