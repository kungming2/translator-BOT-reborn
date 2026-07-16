#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""Build serializable Wenyuan statistics snapshots for reporting surfaces."""

import time

from lang.languages import converter
from processes.wenyuan_stats import (
    Lumo,
    build_comparison_metric,
    get_backlog_count,
)
from time_handling import time_convert_to_string_seconds


def _serialize_period_stats(
    lumo: Lumo, days: int, period_label: str
) -> dict[str, object]:
    """Serialize one loaded Lumo period for dashboard rendering."""
    overall = lumo.get_overall_stats()
    directions = lumo.get_direction_stats()
    notifications = lumo.get_notification_stats()
    images = lumo.get_image_stats()
    fastest = lumo.get_fastest_translations()

    top_languages = []
    ranked_languages = [
        (language, count)
        for language, count in lumo.get_language_rankings(by="total")
        if language.casefold() not in {"unknown", "nonlanguage"}
    ][:15]
    for language, count in ranked_languages:
        stats = lumo.get_language_stats(language)
        lingvo = converter(language)
        top_languages.append(
            {
                "language": language,
                "code": lingvo.preferred_code if lingvo is not None else None,
                "requests": count,
                "percentOfAllRequests": stats["percent_of_all_requests"]
                if stats
                else 0,
                "translationPercentage": stats["translation_percentage"]
                if stats
                else 0,
                "needsReview": stats["needs_review"] if stats else 0,
                "untranslated": stats["untranslated"] if stats else 0,
            }
        )

    source_target_pairs = [
        {"pair": pair, "requests": count}
        for pair, count in lumo.get_source_target_pairs(10)
    ]

    median_seconds = fastest.get("median_translation_seconds")
    average_hours = fastest.get("average_translation_hours")

    return {
        "periodLabel": period_label,
        "days": days,
        "postCount": len(lumo),
        "overall": overall,
        "directions": directions,
        "uniqueTranslators": lumo.get_unique_translator_count(),
        "notifications": notifications,
        "images": images,
        "timing": {
            "averageTranslationHours": average_hours,
            "medianTranslationSeconds": median_seconds,
            "medianTranslationDisplay": time_convert_to_string_seconds(
                int(median_seconds)
            )
            if isinstance(median_seconds, (int, float)) and median_seconds > 0
            else None,
            "timedTranslationCount": fastest.get("timed_translation_count", 0),
        },
        "topLanguages": top_languages,
        "sourceTargetPairs": source_target_pairs,
    }


def build_period_stats_data(
    days: int = 30, *, include_comparison: bool = False
) -> dict[str, object]:
    """Build serializable Wenyuan statistics for the latest N days."""
    current_end = int(time.time())
    current_start = current_end - (days * 86400)
    current_lumo = Lumo()
    current_lumo.load_ajos(current_start, current_end)
    result = _serialize_period_stats(current_lumo, days, f"last {days} days")

    if not include_comparison:
        return result

    previous_lumo = Lumo()
    previous_lumo.load_ajos(current_start - (days * 86400), current_start - 1)
    current_overall = current_lumo.get_overall_stats()
    previous_overall = previous_lumo.get_overall_stats()
    current_timing = current_lumo.get_fastest_translations()
    previous_timing = previous_lumo.get_fastest_translations()

    result["comparison"] = {
        "periodDays": days,
        "metrics": {
            "requests": build_comparison_metric(
                int(current_overall.get("total_requests", 0)),
                int(previous_overall.get("total_requests", 0)),
                lower_is_better=None,
            ),
            "completionRate": build_comparison_metric(
                float(current_overall.get("translation_percentage", 0)),
                float(previous_overall.get("translation_percentage", 0)),
                lower_is_better=False,
            ),
            "medianTranslationSeconds": build_comparison_metric(
                current_timing.get("median_translation_seconds"),
                previous_timing.get("median_translation_seconds"),
                lower_is_better=True,
            ),
            "backlog": build_comparison_metric(
                get_backlog_count(current_overall),
                get_backlog_count(previous_overall),
                lower_is_better=True,
            ),
        },
    }
    result["dailyVolume"] = current_lumo.get_daily_request_volume(days, current_end)
    return result
