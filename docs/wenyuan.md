# Wenyuan / Lumo Statistics

Wenyuan is the statistics and reporting workflow for r/translator. The core
analytics API lives in `processes.wenyuan_stats.Lumo`; the monthly Reddit/wiki
report is formatted by `main_wenyuan.py`.

Use this document when you need to load Ajo records, filter them, inspect
language or period statistics, or understand how the monthly statistics page is
assembled.

## Import

```python
from processes.wenyuan_stats import Lumo, get_effective_status
```

## Data Model

`Lumo` works with saved `Ajo` objects from the database. After loading data, it
keeps two related views:

| View | Used for | Notes |
| --- | --- | --- |
| `lumo.ajos` | Language/status statistics, filters, iteration, `len(lumo)` | Defined multiple-language posts are expanded into one synthetic single-language entry per component language. |
| `lumo._source_ajos` | Post-level period aggregates | Original unexpanded Ajos. Used for translator, notification, image, timing, identification, and source-target metrics so shared post metadata is not counted once per component language. |

This distinction is intentional. A defined multiple-language request should
count as each of its component languages in language-level tables, but its
shared post metadata, such as recorded translators or image status, should only
count once in period-level aggregates.

## Loading Data

| Method | Description | Example |
| --- | --- | --- |
| `load_ajos(start_time, end_time, all_time=False)` | Load posts in a Unix timestamp range. Uses instance defaults if provided in `Lumo(start_time, end_time)`. | `lumo.load_ajos(start, end)` |
| `load_month(year, month)` | Load all posts from one calendar month. | `lumo.load_month(2026, 4)` |
| `load_last_days(days=30)` | Load posts from the last N days. | `lumo.load_last_days(14)` |
| `load_all_time()` | Load everything from January 1, 2015 to now. | `lumo.load_all_time()` |
| `load_for_user(username, start_time=None, end_time=None)` | Load posts by a Reddit username, without the `u/` prefix. | `lumo.load_for_user("translator_user")` |
| `load_single_post(post_id)` | Load one post by Reddit ID. Returns the original Ajo or `None`. | `lumo.load_single_post("abc123")` |
| `load_from_list(ajos)` | Load a prepared list of Ajo objects. Useful for tests. | `lumo.load_from_list([ajo1, ajo2])` |

```python
lumo = Lumo()
lumo.load_month(2026, 4)

print(len(lumo))  # expanded request count
```

## Filtering And Search

Filtering methods operate on `lumo.ajos`, so defined multiple-language posts are
searched by their expanded component language entries.

| Method | Description | Example |
| --- | --- | --- |
| `filter_by_language(language)` | Filter by language name, code, or `Lingvo`. Uses `converter()`. | `lumo.filter_by_language("ja")` |
| `filter_by_status(status)` | Filter by effective status. | `lumo.filter_by_status("doublecheck")` |
| `filter_by_direction(direction)` | Filter by translation direction. | `lumo.filter_by_direction("english_from")` |
| `filter_by_type(req_type)` | Filter by Ajo type, usually `single` or `multiple`. | `lumo.filter_by_type("single")` |
| `filter_by_time_range(start, end)` | Filter currently loaded posts to another timestamp range. | `lumo.filter_by_time_range(start, end)` |
| `search(**kwargs)` | Combine language, status, type, direction, and author criteria. | `lumo.search(language="ko", status="inprogress")` |

Status values used by `get_effective_status()` are `translated`,
`untranslated`, `doublecheck`, `inprogress`, and `missing`.

Direction values are `english_to`, `english_from`, and `english_none`.

```python
recent_hindi_claims = lumo.search(
    language="hi",
    status="inprogress",
    direction="english_to",
)
```

## Statistics API

### Language Statistics

| Method | Description | Return shape |
| --- | --- | --- |
| `get_language_stats(language)` | Stats for one language. Cached by the input key. | Dict or `None`. |
| `get_stats_for_languages(language_string)` | Stats for multiple languages parsed by `parse_language_list()`. | Dict keyed by language name. |
| `get_all_languages()` | Sorted list of represented language names. | `list[str]` |
| `get_language_rankings(by="total")` | Languages ranked by `total`, `translated`, or `untranslated`. | `list[tuple[str, int]]` |
| `get_language_frequency_info(language)` | Static Lingvo frequency metadata without loading posts. | Dict or `None`. |

`get_language_stats()` returns:

```python
{
    "language": "Portuguese",
    "total_requests": 85,
    "translated": 68,
    "needs_review": 5,
    "untranslated": 12,
    "translation_percentage": 86,
    "percent_of_all_requests": 8.5,
    "directions": "1.8:1",
}
```

`translation_percentage` treats both `translated` and `doublecheck` as
completed enough for the percentage. The `untranslated` bucket includes
`untranslated`, `missing`, and `inprogress`.

### Overall And Period Statistics

| Method | Description | Notes |
| --- | --- | --- |
| `get_overall_stats()` | Overall status counts, translation percentage, and represented-language count. | Uses expanded language entries. |
| `get_direction_stats()` | Counts and percentages for to-English, from-English, and non-English requests. | Uses expanded language entries. |
| `get_unique_translator_count()` | Number of distinct recorded translators in the loaded period. | Uses original source Ajos and lowercases usernames. |
| `get_notification_stats()` | Total notified users and average notified users per request. | Deduplicates notified users per post. |
| `get_image_stats()` | Image post count and percentage. | Counts source Ajos with `image_hash`. |
| `get_source_target_pairs(limit=10)` | Most common source-target language pairs. | Uses saved original source/target fields and falls back to direction plus current language when needed. |
| `get_fastest_translations()` | Fastest translated, review, and claimed posts plus average/median translation timing. | Timing is based on `time_delta - created_utc`. |
| `get_identification_stats()` | Languages identified from `Unknown` and common misidentified pairs. | Uses `language_history` from original source Ajos. |

Example:

```python
overall = lumo.get_overall_stats()
notifications = lumo.get_notification_stats()
images = lumo.get_image_stats()
pairs = lumo.get_source_target_pairs(limit=20)

print(overall["total_requests"])
print(notifications["average_notified_per_request"])
print(f'{images["image_requests"]} image posts ({images["percentage"]}%)')
for pair, count in pairs:
    print(pair, count)
```

`get_fastest_translations()` returns a partial dictionary. Keys are only present
when timing data exists:

```python
{
    "to_translated": {"time": 420, "id": "def456"},
    "to_review": {"time": 180, "id": "ghi789"},
    "to_claimed": {"time": 75, "id": "jkl012"},
    "average_translation_hours": 5.2,
    "median_translation_seconds": 15120,
    "timed_translation_count": 43,
}
```

### Identification Statistics

`get_identification_stats()` returns two dictionaries:

```python
{
    "identified_from_unknown": {
        "Hebrew": 18,
        "Thai": 12,
    },
    "misidentified_pairs": {
        "Chinese -> Japanese": 4,
        "Hindi -> Urdu": 3,
    },
}
```

Internally, language history entries are normalized through `converter()` when
possible. `Unknown`, `Generic`, and `Multiple Languages` are treated as utility
labels rather than normal language destinations.

## Monthly Reddit/Wiki Report

The monthly report is generated in `main_wenyuan.py` by
`format_lumo_stats_for_reddit(lumo, month_year)`, where `month_year` is a
`YYYY-MM` string.

The report currently includes:

| Section | Source |
| --- | --- |
| Overall statistics | `get_overall_stats()`, `filter_by_type("multiple")`, `get_unique_translator_count()`, `get_notification_stats()`, `get_image_stats()` |
| Language families | `get_all_languages()`, `converter()`, per-language totals |
| Single-language requests | `get_language_stats()`, family metadata, RI calculation, Wikipedia/search links |
| Month-over-month change | Previous monthly wiki page, when available and parseable |
| Translation direction | `get_direction_stats()` |
| Top source-target pairs | `get_source_target_pairs(10)` |
| Unknown identifications | `get_identification_stats()["identified_from_unknown"]` |
| Common misidentified pairs | `get_identification_stats()["misidentified_pairs"]` |
| Quickest processed posts | `get_fastest_translations()` |
| Other utility requests | Utility language filters such as `Generic` and `Unknown` |

The single-language table gets an optional `Change` column only when Wenyuan can
fetch and parse the previous monthly wiki report. The comparison is against the
previous report's `Percent of All Requests` value for the same language. If the
previous page is missing, inaccessible, or has an incompatible table structure,
the entire `Change` column is omitted.

The previous wiki page key is computed from the current `YYYY-MM` month. For
example, `2026-04` compares against `2026_03`, and January rolls back to the
prior December page.

Trend symbols are:

| Current percentage vs previous month | Display |
| --- | --- |
| Greater than previous | Up arrow |
| Less than previous | Down arrow |
| Equal to previous | Right arrow |

These trend arrows are only part of the monthly statistics page. Per-language
wiki pages are generated separately and do not receive the `Change` column.

## Time Helpers

| Method | Description | Example |
| --- | --- | --- |
| `date_to_unix(year, month, day=1, hour=0, minute=0, second=0)` | Convert a UTC date/time to a Unix timestamp. | `Lumo.date_to_unix(2026, 4, 1)` |
| `month_to_unix_range(year, month)` | Return the first and last Unix timestamps for a calendar month. | `Lumo.month_to_unix_range(2026, 4)` |
| `last_n_days(days=30)` | Return a timestamp range for the last N days. | `Lumo.last_n_days(90)` |
| `all_time_range()` | Return January 1, 2015 through now. | `Lumo.all_time_range()` |

## Export And Iteration

| Method | Description |
| --- | --- |
| `to_dict()` | Export overall, direction, language, identification, fastest, translator, notification, image, and source-target stats. |
| `len(lumo)` | Number of expanded loaded Ajos. |
| `iter(lumo)` | Iterate over expanded loaded Ajos. |
| `lumo[index]` | Access an expanded loaded Ajo by index. |
| `repr(lumo)` | Show the loaded Ajo count. |

## Common Recipes

### Generate A Monthly Snapshot

```python
lumo = Lumo()
lumo.load_month(2026, 4)

overall = lumo.get_overall_stats()
fastest = lumo.get_fastest_translations()

print(f'Total expanded requests: {overall["total_requests"]}')
print(f'Translated: {overall["translation_percentage"]}%')
print(f'Unique translators: {lumo.get_unique_translator_count()}')

if "median_translation_seconds" in fastest:
    print(f'Median translation seconds: {fastest["median_translation_seconds"]}')
```

### Find Untranslated Posts For A Language

```python
lumo = Lumo()
lumo.load_last_days(14)

for post in lumo.search(language="vi", status="untranslated"):
    print(f"{post.title} - https://redd.it/{post.id}")
```

### Compare Related Languages

```python
lumo = Lumo()
lumo.load_month(2026, 4)

stats = lumo.get_stats_for_languages("ru, pl, cs, uk, bg")
for language, data in stats.items():
    if data:
        print(f'{language}: {data["translation_percentage"]}% translated')
```

### Inspect Source-Target Pairs

```python
lumo = Lumo()
lumo.load_month(2026, 4)

for pair, count in lumo.get_source_target_pairs(limit=20):
    print(f"{pair}: {count}")
```

### User Activity

```python
from collections import Counter

lumo = Lumo()
lumo.load_for_user("translator_user")

statuses = Counter(get_effective_status(ajo) for ajo in lumo)
print(f"Expanded posts: {len(lumo)}")
print(f"Languages: {', '.join(lumo.get_all_languages())}")
print(statuses)
```

## Notes And Limitations

- Most user-facing language methods accept language names or codes through
  `converter()`.
- `get_language_stats()` caches by the language input string. Loading new data
  clears the cache.
- `filter_by_type("multiple")` operates on the expanded view. Defined
  multiple-language posts are converted to synthetic single-language entries, so
  this is not a reliable source-post count for defined multiples after loading.
- `get_source_target_pairs()` ignores source-target combinations where source
  and target normalize to the same display name.
- The monthly formatter still includes a hard-coded meta/community post count.
  That value is not derived from `Lumo`.
