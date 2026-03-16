#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
Defines the Lingvo class, the core data model representing a single language
or script entry used throughout all r/translator bot routines.

A Lingvo holds identifying codes (ISO 639-1, 639-2B, 639-3, ISO 15924),
display names, community metadata (subreddit, greetings, thanks), and
aggregated statistics. It is intentionally free of I/O or lookup logic;
construction from raw data sources is handled by lang/languages.py.

Key components:
    Lingvo               -- Data model for a language or script entry.
    Lingvo.from_csv_row  -- Construct a minimal Lingvo from an ISO CSV row.
    Lingvo.preferred_code -- Property returning the most commonly used code.
    Lingvo.country_emoji  -- Property returning the flag emoji for the language.

Note: country_emoji calls into lang/countries.py at runtime via a lazy
import to avoid a circular dependency at module load time.

Logger tag: [M:LINGVO]
"""

from __future__ import annotations

from typing import Any


class Lingvo:
    def __init__(self, **kwargs: Any) -> None:
        self.name: str | None = kwargs.get("name")
        self.name_alternates: list[str] = kwargs.get("name_alternates", [])
        self.language_code_1: str | None = kwargs.get("language_code_1")
        self.language_code_2b: str | None = kwargs.get("language_code_2b")
        self.language_code_3: str | None = kwargs.get("language_code_3")
        self.script_code: str | None = kwargs.get("script_code")  # For script entries
        self.country: str | None = kwargs.get("country")  # ISO country code
        self.countries_default: list[str] | None = kwargs.get("countries_default")
        self.countries_associated: list[str] | None = kwargs.get("countries_associated")
        self.family: str | None = kwargs.get("family")
        self.mistake_abbreviation: str | None = kwargs.get("mistake_abbreviation")
        self.population: int | None = kwargs.get("population")
        self.subreddit: str | None = kwargs.get("subreddit")
        self.supported: bool = kwargs.get("supported", False)
        self.thanks: str = kwargs.get("thanks", "Thanks")
        self.greetings: str = kwargs.get("greetings", "Hello")
        self.link_ethnologue: str | None = kwargs.get("link_ethnologue")
        self.link_wikipedia: str | None = kwargs.get("link_wikipedia")

        # Statistics fields
        self.num_months: int | None = kwargs.get("num_months")
        self.rate_daily: float | None = kwargs.get("rate_daily")
        self.rate_monthly: float | None = kwargs.get("rate_monthly")
        self.rate_yearly: float | None = kwargs.get("rate_yearly")
        self.link_statistics: str | None = kwargs.get("link_statistics") or kwargs.get(
            "permalink"
        )  # Maps permalink → statistics_page

    @property
    def preferred_code(self) -> str:
        """Return the best available identifying code for this language."""
        for code in (self.language_code_1, self.language_code_3):
            if code:
                lowered = code.lower()
                if lowered in {"multiple", "generic"}:
                    return lowered
                if lowered != "unknown":
                    return lowered
        return (self.script_code or "unknown").lower()

    def __repr__(self) -> str:
        code = self.preferred_code
        is_script = self.script_code is not None or len(code) == 4
        script_label = " | (script)" if is_script else ""
        return f"<Lingvo: {self.name} ({code}){script_label}>"

    def __str__(self) -> str:
        return self.preferred_code

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Lingvo):
            return NotImplemented
        return self.preferred_code == other.preferred_code

    def __hash__(self) -> int:
        return hash(self.preferred_code)

    @classmethod
    def from_csv_row(cls, row: dict[str, str]) -> Lingvo:
        """
        Create a Lingvo from a language CSV row in Datasets.

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
            num_months=None,
            rate_daily=None,
            rate_monthly=None,
            rate_yearly=None,
            link_statistics=None,
        )

    def to_dict(self) -> dict[str, Any]:
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
            "num_months": self.num_months,
            "rate_daily": self.rate_daily,
            "rate_monthly": self.rate_monthly,
            "rate_yearly": self.rate_yearly,
            "link_statistics": self.link_statistics,
        }

    @property
    def country_emoji(self) -> str | None:
        """
        Dynamically retrieves the country emoji for this language.

        Lazily imports from lang.countries to avoid a circular dependency:
        lang.languages imports Lingvo, and Lingvo.country_emoji calls into
        lang.countries — a top-level import here would create a cycle.
        """
        from lang.countries import get_language_emoji  # lazy to avoid circular import

        emoji = get_language_emoji(self.preferred_code)
        return emoji if emoji else None
