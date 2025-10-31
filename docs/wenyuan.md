# Lumo - Translation Statistics Analyzer

## Overview

Lumo is a comprehensive statistics analyzer for translation requests stored in an Ajo database. It provides a clean, intuitive interface for loading, filtering, and analyzing translation data across different time periods, languages, and statuses.

## Table of Contents

- [Installation](#installation)
- [Quick Start](#quick-start)
- [Core Concepts](#core-concepts)
- [API Reference](#api-reference)
  - [Initialization](#initialization)
  - [Time Helper Methods](#time-helper-methods)
  - [Data Loading Methods](#data-loading-methods)
  - [Search & Filter Methods](#search--filter-methods)
  - [Statistics Methods](#statistics-methods)
  - [Export Methods](#export-methods)
- [Usage Examples](#usage-examples)
- [Advanced Usage](#advanced-usage)

---

## Installation

Lumo requires the following dependencies:
- `database` module (with `db` and `search_database`)
- `languages` module (with `converter`)
- `models.ajo` module (with `Ajo` class)
- `time_handling` module (with `time_convert_to_string`)

```python
from processes.wenyuan_stats import Lumo
```

---

## Quick Start

```python
# Initialize Lumo
lumo = Lumo()

# Load all posts from September 2023
lumo.load_month(2023, 9)

# Get statistics for German posts
german_stats = lumo.get_language_stats('German')
print(f"Total German requests: {german_stats['total_requests']}")
print(f"Translation rate: {german_stats['translation_percentage']}%")

# Filter by language
german_posts = lumo.filter_by_language('German')
for post in german_posts:
    print(f"{post.title} - {post.status}")
```

---

## Core Concepts

### Ajo Objects
An **Ajo** represents a single translation request with properties like:
- `id`: Reddit post ID
- `language_name`: Name of the language (e.g., "German", "Japanese")
- `status`: Current status (translated, untranslated, doublecheck, etc.)
- `created_utc`: Unix timestamp of when the post was created
- `direction`: Translation direction (english_to, english_from, english_none)
- `type`: Post type (single or multiple)

### Time Ranges
Lumo works with Unix timestamps (seconds since January 1, 1970). Helper methods are provided to convert between dates and Unix timestamps.

### Defined Multiples
Some posts request translation into multiple languages. Lumo can automatically expand these into individual entries for easier analysis.

---

## API Reference

### Initialization

#### `Lumo(start_time=None, end_time=None)`

Creates a new Lumo instance.

**Parameters:**
- `start_time` (int, optional): Default Unix timestamp for start time
- `end_time` (int, optional): Default Unix timestamp for end time

**Returns:** Lumo instance

**Example:**
```python
# Initialize with no defaults
lumo = Lumo()

# Initialize with time range defaults
lumo = Lumo(
    start_time=Lumo.date_to_unix(2023, 1, 1),
    end_time=Lumo.date_to_unix(2023, 12, 31)
)
```

**Magic Methods:**
- `len(lumo)`: Returns number of loaded Ajos
- `iter(lumo)`: Allows iteration over Ajos
- `lumo[index]`: Allows indexing into Ajos
- `repr(lumo)`: Returns string representation

```python
print(f"Total posts: {len(lumo)}")  # Get count
for ajo in lumo:  # Iterate
    print(ajo.language_name)
first_post = lumo[0]  # Index access
```

---

### Time Helper Methods

#### `Lumo.date_to_unix(year, month, day=1, hour=0, minute=0, second=0)`

Convert a date to Unix timestamp.

**Parameters:**
- `year` (int): Year (e.g., 2023)
- `month` (int): Month (1-12)
- `day` (int): Day of month (default: 1)
- `hour` (int): Hour (default: 0)
- `minute` (int): Minute (default: 0)
- `second` (int): Second (default: 0)

**Returns:** int - Unix timestamp

**Example:**
```python
# January 1, 2023 at midnight
timestamp = Lumo.date_to_unix(2023, 1, 1)

# September 15, 2023 at 3:30 PM
timestamp = Lumo.date_to_unix(2023, 9, 15, 15, 30, 0)
```

---

#### `Lumo.month_to_unix_range(year, month)`

Get Unix timestamp range for an entire month.

**Parameters:**
- `year` (int): Year (e.g., 2023)
- `month` (int): Month (1-12)

**Returns:** tuple - (start_timestamp, end_timestamp)

**Example:**
```python
# Get range for September 2023
start, end = Lumo.month_to_unix_range(2023, 9)
# start = Sept 1, 2023 00:00:00
# end = Sept 30, 2023 23:59:59
```

---

#### `Lumo.last_n_days(days=30)`

Get Unix timestamp range for the last N days.

**Parameters:**
- `days` (int): Number of days to go back (default: 30)

**Returns:** tuple - (start_timestamp, end_timestamp)

**Example:**
```python
# Get last 7 days
start, end = Lumo.last_n_days(7)

# Get last 90 days
start, end = Lumo.last_n_days(90)
```

---

#### `Lumo.all_time_range()`

Get Unix timestamp range from January 1, 2015 to now.

**Returns:** tuple - (start_timestamp, end_timestamp)

**Example:**
```python
start, end = Lumo.all_time_range()
# start = Jan 1, 2015 00:00:00
# end = current time
```

---

### Data Loading Methods

#### `load_ajos(start_time=None, end_time=None, all_time=False)`

Load Ajos from database within time range.

**Parameters:**
- `start_time` (int, optional): Unix timestamp for start
- `end_time` (int, optional): Unix timestamp for end
- `all_time` (bool): If True, load all posts from Jan 1, 2015 to now

**Returns:** list - List of Ajo objects

**Example:**
```python
# Load with explicit timestamps
lumo.load_ajos(
    start_time=Lumo.date_to_unix(2023, 1, 1),
    end_time=Lumo.date_to_unix(2023, 12, 31)
)

# Load using instance defaults
lumo = Lumo(
    start_time=Lumo.date_to_unix(2023, 1, 1),
    end_time=Lumo.date_to_unix(2023, 12, 31)
)
lumo.load_ajos()  # Uses instance defaults

# Load all time
lumo.load_ajos(all_time=True)
```

---

#### `load_month(year, month)`

Convenience method to load all Ajos from a specific month.

**Parameters:**
- `year` (int): Year (e.g., 2023)
- `month` (int): Month (1-12)

**Returns:** list - List of Ajo objects

**Example:**
```python
# Load September 2023
lumo.load_month(2023, 9)

# Load January 2024
lumo.load_month(2024, 1)
```

---

#### `load_last_days(days=30)`

Load Ajos from the last N days.

**Parameters:**
- `days` (int): Number of days to go back (default: 30)

**Returns:** list - List of Ajo objects

**Example:**
```python
# Load last 30 days (default)
lumo.load_last_days()

# Load last 7 days
lumo.load_last_days(7)

# Load last year
lumo.load_last_days(365)
```

---

#### `load_all_time()`

Load ALL Ajos from the beginning (Jan 1, 2015) to now.

**Returns:** list - List of Ajo objects

**Example:**
```python
lumo = Lumo()
lumo.load_all_time()
print(f"Total posts ever: {len(lumo)}")
```

---

#### `load_for_user(username, start_time=None, end_time=None)`

Load all Ajos created by a specific user.

**Parameters:**
- `username` (str): Reddit username (without 'u/')
- `start_time` (int, optional): Unix timestamp for start
- `end_time` (int, optional): Unix timestamp for end

**Returns:** list - List of Ajo objects

**Example:**
```python
# Load all posts by user "translator123"
lumo.load_for_user('translator123')

# Load user posts from September 2023 only
lumo.load_for_user(
    'translator123',
    start_time=Lumo.date_to_unix(2023, 9, 1),
    end_time=Lumo.date_to_unix(2023, 9, 30)
)
```

---

#### `load_single_post(post_id)`

Load a single Ajo by post ID.

**Parameters:**
- `post_id` (str): Reddit post ID

**Returns:** Ajo object or None if not found

**Example:**
```python
ajo = lumo.load_single_post('abc123')
if ajo:
    print(f"Found post: {ajo.title}")
    print(f"Language: {ajo.language_name}")
    print(f"Status: {ajo.status}")
else:
    print("Post not found")
```

---

#### `load_from_list(ajos)`

Load Ajos directly from a list (useful for testing).

**Parameters:**
- `ajos` (list): List of Ajo objects

**Returns:** None (updates internal state)

**Example:**
```python
# Create test Ajos
test_ajos = [ajo1, ajo2, ajo3]

# Load them into Lumo
lumo.load_from_list(test_ajos)
```

---

### Search & Filter Methods

#### `filter_by_time_range(start_time, end_time)`

Filter currently loaded Ajos by a different time range.

**Parameters:**
- `start_time` (int): Unix timestamp for start
- `end_time` (int): Unix timestamp for end

**Returns:** list - Filtered list of Ajos

**Example:**
```python
# Load entire year
lumo.load_month(2023, 9)

# Filter to just first week
first_week = lumo.filter_by_time_range(
    Lumo.date_to_unix(2023, 9, 1),
    Lumo.date_to_unix(2023, 9, 7, 23, 59, 59)
)
print(f"Posts in first week: {len(first_week)}")
```

---

#### `filter_by_language(language)`

Get all requests for a specific language.

**Parameters:**
- `language` (str): Language name (e.g., "German", "Japanese")

**Returns:** list - List of Ajo objects

**Example:**
```python
lumo.load_month(2023, 9)

# Get all German posts
german_posts = lumo.filter_by_language('German')

# Get all Japanese posts
japanese_posts = lumo.filter_by_language('Japanese')

# Iterate over results
for post in german_posts:
    print(f"{post.title} - {post.status}")
```

---

#### `filter_by_status(status)`

Get all requests with a specific status.

**Parameters:**
- `status` (str): Status (translated, untranslated, doublecheck, inprogress, missing)

**Returns:** list - List of Ajo objects

**Example:**
```python
# Get all translated posts
translated = lumo.filter_by_status('translated')

# Get all posts needing review
needs_review = lumo.filter_by_status('doublecheck')

# Get untranslated posts
untranslated = lumo.filter_by_status('untranslated')
```

---

#### `filter_by_type(req_type)`

Get all requests of a specific type.

**Parameters:**
- `req_type` (str): Type (single or multiple)

**Returns:** list - List of Ajo objects

**Example:**
```python
# Get single-language posts
single_posts = lumo.filter_by_type('single')

# Get multiple-language posts
multiple_posts = lumo.filter_by_type('multiple')
```

---

#### `filter_by_direction(direction)`

Get all requests with a specific translation direction.

**Parameters:**
- `direction` (str): Direction (english_to, english_from, english_none)

**Returns:** list - List of Ajo objects

**Example:**
```python
# Get posts translating TO English
to_english = lumo.filter_by_direction('english_to')

# Get posts translating FROM English
from_english = lumo.filter_by_direction('english_from')

# Get posts with no English (e.g., Japanese to Spanish)
non_english = lumo.filter_by_direction('english_none')
```

---

#### `search(**kwargs)`

Flexible search across multiple criteria.

**Parameters:**
- `language` (str, optional): Filter by language name
- `status` (str, optional): Filter by status
- `type` (str, optional): Filter by type
- `direction` (str, optional): Filter by direction
- `author` (str, optional): Filter by author username

**Returns:** list - Filtered list of Ajos

**Example:**
```python
# Complex search: translated German posts from English
results = lumo.search(
    language='German',
    status='translated',
    direction='english_from'
)

# Find all posts by specific user in specific language
results = lumo.search(
    author='translator123',
    language='Japanese'
)

# Find untranslated single-language posts
results = lumo.search(
    status='untranslated',
    type='single'
)
```

---

### Statistics Methods

#### `get_language_stats(language)`

Get comprehensive statistics for a specific language.

**Parameters:**
- `language` (str): Language name

**Returns:** dict or None - Statistics dictionary or None if no data

**Dictionary Keys:**
- `language`: Language name
- `total_requests`: Total number of requests
- `translated`: Number of translated requests
- `needs_review`: Number of requests needing review
- `untranslated`: Number of untranslated requests
- `translation_percentage`: Percentage translated
- `percent_of_all_requests`: Percentage of all loaded requests
- `directions`: Direction ratio string (e.g., "2.5:1")

**Example:**
```python
lumo.load_month(2023, 9)
stats = lumo.get_language_stats('German')

if stats:
    print(f"Language: {stats['language']}")
    print(f"Total requests: {stats['total_requests']}")
    print(f"Translated: {stats['translated']}")
    print(f"Translation rate: {stats['translation_percentage']}%")
    print(f"Direction ratio: {stats['directions']}")
else:
    print("No data found for this language")
```

---

#### `get_all_languages()`

Get list of all unique languages in the dataset.

**Returns:** list - Sorted list of language names

**Example:**
```python
lumo.load_month(2023, 9)
languages = lumo.get_all_languages()

print(f"Languages represented: {len(languages)}")
for lang in languages:
    print(f"  - {lang}")
```

---

#### `get_language_rankings(by='total')`

Get languages ranked by various metrics.

**Parameters:**
- `by` (str): Metric to rank by (total, translated, untranslated)

**Returns:** list - List of (language, count) tuples, sorted descending

**Example:**
```python
lumo.load_month(2023, 9)

# Get top 10 most requested languages
top_languages = lumo.get_language_rankings(by='total')[:10]
for lang, count in top_languages:
    print(f"{lang}: {count} requests")

# Get languages with most translations
most_translated = lumo.get_language_rankings(by='translated')[:5]

# Get languages with most untranslated posts
most_untranslated = lumo.get_language_rankings(by='untranslated')[:5]
```

---

#### `get_overall_stats()`

Get overall statistics across all requests.

**Returns:** dict - Statistics dictionary

**Dictionary Keys:**
- `total_requests`: Total number of requests
- `untranslated`: Number of untranslated requests
- `missing_assets`: Number of requests missing assets
- `in_progress`: Number of requests in progress
- `needs_review`: Number of requests needing review
- `translated`: Number of translated requests
- `translation_percentage`: Overall translation percentage
- `unique_languages`: Number of unique languages

**Example:**
```python
lumo.load_month(2023, 9)
stats = lumo.get_overall_stats()

print(f"Total requests: {stats['total_requests']}")
print(f"Translated: {stats['translated']}")
print(f"Untranslated: {stats['untranslated']}")
print(f"Overall translation rate: {stats['translation_percentage']}%")
print(f"Languages represented: {stats['unique_languages']}")
```

---

#### `get_direction_stats()`

Get statistics on translation directions.

**Returns:** dict - Statistics dictionary with nested dictionaries

**Dictionary Structure:**
```python
{
    'to_english': {'count': int, 'percentage': float},
    'from_english': {'count': int, 'percentage': float},
    'non_english': {'count': int, 'percentage': float}
}
```

**Example:**
```python
lumo.load_month(2023, 9)
directions = lumo.get_direction_stats()

print(f"To English: {directions['to_english']['count']} ({directions['to_english']['percentage']}%)")
print(f"From English: {directions['from_english']['count']} ({directions['from_english']['percentage']}%)")
print(f"Non-English: {directions['non_english']['count']} ({directions['non_english']['percentage']}%)")
```

---

#### `get_fastest_translations()`

Find the fastest processed requests.

**Returns:** dict - Dictionary with fastest processing times

**Dictionary Keys:**
- `to_translated`: Dict with `time` (seconds) and `id`
- `to_review`: Dict with `time` and `id`
- `to_claimed`: Dict with `time` and `id`
- `average_translation_hours`: Average time to translate (hours)

**Example:**
```python
lumo.load_month(2023, 9)
fastest = lumo.get_fastest_translations()

if fastest['to_translated']['id']:
    print(f"Fastest translation: {fastest['to_translated']['time']} seconds")
    print(f"Post ID: {fastest['to_translated']['id']}")
    
if 'average_translation_hours' in fastest:
    print(f"Average translation time: {fastest['average_translation_hours']} hours")
```

---

#### `get_identification_stats()`

Analyze posts that were identified from 'Unknown'.

**Returns:** dict - Statistics dictionary

**Dictionary Keys:**
- `identified_from_unknown`: Dict of language -> count
- `misidentified_pairs`: Dict of "Language A → Language B" -> count

**Example:**
```python
lumo.load_month(2023, 9)
identification = lumo.get_identification_stats()

# Languages identified from Unknown
print("Identified from Unknown:")
for lang, count in identification['identified_from_unknown'].items():
    print(f"  {lang}: {count}")

# Commonly misidentified pairs
print("\nCommonly Misidentified:")
for pair, count in identification['misidentified_pairs'].items():
    print(f"  {pair}: {count}")
```

---

### Export Methods

#### `to_dict()`

Export all statistics as a dictionary.

**Returns:** dict - Complete statistics dictionary

**Dictionary Structure:**
```python
{
    'overall': {...},         # Overall stats
    'directions': {...},      # Direction stats
    'languages': {...},       # Per-language stats
    'identifications': {...}, # Identification stats
    'fastest': {...}          # Fastest translation stats
}
```

**Example:**
```python
lumo.load_month(2023, 9)
all_stats = lumo.to_dict()

# Export to JSON
import json
with open('stats_sept_2023.json', 'w') as f:
    json.dump(all_stats, f, indent=2)

# Access specific sections
print(all_stats['overall']['total_requests'])
print(all_stats['languages']['German']['translation_percentage'])
```

---

## Usage Examples

### Example 1: Monthly Report

```python
from lumo import Lumo

# Initialize and load September 2023
lumo = Lumo()
lumo.load_month(2023, 9)

# Get overall statistics
overall = lumo.get_overall_stats()
print(f"\n=== September 2023 Report ===")
print(f"Total Requests: {overall['total_requests']}")
print(f"Translation Rate: {overall['translation_percentage']}%")
print(f"Languages: {overall['unique_languages']}")

# Get top 5 languages
print(f"\n=== Top 5 Languages ===")
top_langs = lumo.get_language_rankings()[:5]
for lang, count in top_langs:
    stats = lumo.get_language_stats(lang)
    print(f"{lang}: {count} requests ({stats['translation_percentage']}% translated)")

# Get direction breakdown
directions = lumo.get_direction_stats()
print(f"\n=== Translation Directions ===")
print(f"To English: {directions['to_english']['percentage']}%")
print(f"From English: {directions['from_english']['percentage']}%")
print(f"Non-English: {directions['non_english']['percentage']}%")
```

---

### Example 2: Language Deep Dive

```python
from lumo import Lumo

# Load all German posts from 2023
lumo = Lumo()
lumo.load_ajos(
    start_time=Lumo.date_to_unix(2023, 1, 1),
    end_time=Lumo.date_to_unix(2023, 12, 31)
)

# Get German statistics
german_stats = lumo.get_language_stats('German')
print(f"\n=== German Statistics (2023) ===")
print(f"Total Requests: {german_stats['total_requests']}")
print(f"Translated: {german_stats['translated']}")
print(f"Needs Review: {german_stats['needs_review']}")
print(f"Untranslated: {german_stats['untranslated']}")
print(f"Translation Rate: {german_stats['translation_percentage']}%")
print(f"Direction Ratio: {german_stats['directions']}")

# Get all German posts
german_posts = lumo.filter_by_language('German')

# Break down by status
print(f"\n=== Status Breakdown ===")
for status in ['translated', 'doublecheck', 'inprogress', 'untranslated']:
    count = len([p for p in german_posts if p.status == status])
    print(f"{status}: {count}")

# Show recent untranslated
untranslated = [p for p in german_posts if p.status == 'untranslated']
untranslated.sort(key=lambda x: x.created_utc, reverse=True)
print(f"\n=== Recent Untranslated (Last 5) ===")
for post in untranslated[:5]:
    from time_handling import time_convert_to_string
    print(f"  - {post.title_original}")
    print(f"    https://redd.it/{post.id}")
    print(f"    {time_convert_to_string(post.created_utc)}")
```

---

### Example 3: User Activity Analysis

```python
from lumo import Lumo

# Load all posts by user in the last 90 days
lumo = Lumo()
start, end = Lumo.last_n_days(90)
lumo.load_for_user('translator123', start_time=start, end_time=end)

print(f"\n=== User Activity: translator123 ===")
print(f"Total Posts (Last 90 days): {len(lumo)}")

# Language breakdown
langs = lumo.get_all_languages()
print(f"\nLanguages: {len(langs)}")
for lang in langs:
    count = len(lumo.filter_by_language(lang))
    print(f"  - {lang}: {count}")

# Status breakdown
for status in ['translated', 'untranslated', 'doublecheck']:
    count = len(lumo.filter_by_status(status))
    print(f"{status}: {count}")

# Direction preference
directions = lumo.get_direction_stats()
print(f"\n=== Direction Preference ===")
print(f"To English: {directions['to_english']['count']}")
print(f"From English: {directions['from_english']['count']}")
```

---

### Example 4: Historical Analysis

```python
from lumo import Lumo

# Load all Estonian posts ever
lumo = Lumo()
lumo.load_all_time()
estonian = lumo.filter_by_language('Estonian')

print(f"\n=== Estonian - Historical Analysis ===")
print(f"Total Requests (All Time): {len(estonian)}")

# Get statistics
stats = lumo.get_language_stats('Estonian')
print(f"Translation Rate: {stats['translation_percentage']}%")
print(f"Direction Ratio: {stats['directions']}")

# Analyze by year
years = {}
for post in estonian:
    from datetime import datetime
    year = datetime.fromtimestamp(post.created_utc).year
    years[year] = years.get(year, 0) + 1

print(f"\n=== Posts by Year ===")
for year in sorted(years.keys()):
    print(f"{year}: {years[year]} requests")

# Find oldest and newest
estonian.sort(key=lambda x: x.created_utc)
oldest = estonian[0]
newest = estonian[-1]

from time_handling import time_convert_to_string
print(f"\nOldest post: {time_convert_to_string(oldest.created_utc)}")
print(f"Newest post: {time_convert_to_string(newest.created_utc)}")
```

---

### Example 5: Complex Filtering

```python
from lumo import Lumo

# Load September 2023
lumo = Lumo()
lumo.load_month(2023, 9)

# Find translated Japanese posts that were translated FROM English
results = lumo.search(
    language='Japanese',
    status='translated',
    direction='english_from'
)

print(f"\n=== Translated Japanese Posts (From English) ===")
print(f"Total: {len(results)}")

for post in results[:10]:  # Show first 10
    print(f"\n{post.title_original}")
    print(f"  Status: {post.status}")
    print(f"  Link: https://redd.it/{post.id}")
    
    # Show time to translate if available
    if hasattr(post, 'time_delta') and post.time_delta:
        if 'translated' in post.time_delta:
            time_taken = post.time_delta['translated'] - post.created_utc
            hours = round(time_taken / 3600, 1)
            print(f"  Translated in: {hours} hours")
```

---

### Example 6: Comparative Analysis

```python
from lumo import Lumo

# Compare two months
months = [
    (2023, 8, "August 2023"),
    (2023, 9, "September 2023")
]

for year, month, label in months:
    lumo = Lumo()
    lumo.load_month(year, month)
    
    overall = lumo.get_overall_stats()
    top_lang = lumo.get_language_rankings()[0]
    
    print(f"\n=== {label} ===")
    print(f"Total Requests: {overall['total_requests']}")
    print(f"Translation Rate: {overall['translation_percentage']}%")
    print(f"Languages: {overall['unique_languages']}")
    print(f"Top Language: {top_lang[0]} ({top_lang[1]} requests)")
```

---

## Advanced Usage

### Chaining Filters

```python
# Load data
lumo = Lumo()
lumo.load_month(2023, 9)

# Chain multiple filters
german_posts = lumo.filter_by_language('German')
from_english = [p for p in german_posts if p.direction == 'english_from']
untranslated = [p for p in from_english if p.status == 'untranslated']

print(f"Untranslated German posts (from English): {len(untranslated)}")
```

---

### Custom Aggregations

```python
# Load data
lumo = Lumo()
lumo.load_month(2023, 9)

# Group by author
from collections import Counter
authors = Counter(ajo.author for ajo in lumo if ajo.author)
top_posters = authors.most_common(10)

print("Top 10 Posters:")
for author, count in top_posters:
    print(f"  u/{author}: {count} posts")
```

---

### Time Series Analysis

```python
from datetime import datetime
from collections import defaultdict

# Load entire year
lumo = Lumo()
lumo.load_ajos(
    start_time=Lumo.date_to_unix(2023, 1, 1),
    end_time=Lumo.date_to_unix(2023, 12, 31)
)

# Group by month
by_month = defaultdict(int)
for ajo in lumo:
    dt = datetime.fromtimestamp(ajo.created_utc)
    month_key = f"{dt.year}-{dt.month:02d}"
    by_month[month_key] += 1

print("Monthly Request Volume (2023):")
for month in sorted(by_month.keys()):
    print(f"  {month}: {by_month[month]} requests")
```

---

## Tips and Best Practices

1. **Always load data first**: Initialize Lumo, then call a load method before filtering or getting statistics.

2. **Use time helpers**: Prefer `Lumo.date_to_unix()` and `Lumo.month_to_unix_range()` over manual Unix timestamp calculation.

3. **Check for None**: When working with individual Ajos, some may have `None` for certain properties. Lumo's filter methods handle this, but custom code should check.

4. **Leverage convenience methods**: Use `load_month()`, `load_last_days()`, etc. instead of manually calculating time ranges.

5. **Combine filters**: Use `search()` for multiple criteria at once instead of chaining filter methods.

6. **Export for analysis**: Use `to_dict()` to export complete statistics to JSON for external analysis or visualization.

7. **Memory considerations**: When loading `all_time`, be aware this loads all Ajos into memory. For very large datasets, consider loading by month or year.

8. **Reuse instances**: You can call multiple load methods on the same Lumo instance - each load replaces the previous data.

---

## Performance Considerations

### Loading Time

- **Single month**: Fast (typically < 1 second)
- **Full year**: Moderate (1-5 seconds depending on volume)
- **All time**: Slower (5-15 seconds for large databases)

### Memory Usage

- Each Ajo object is relatively lightweight (~1-2 KB)
- 10,000 Ajos ≈ 10-20 MB memory
- `load_all_time()` with 100,000+ Ajos may use significant memory

### Optimization Tips

```python
# Instead of loading all time and filtering
# BAD (loads everything):
lumo.load_all_time()
german = lumo.filter_by_language('German')

# GOOD (loads only what you need):
lumo.load_month(2023, 9)
german = lumo.filter_by_language('German')

# For user-specific analysis, use load_for_user
# BAD (loads everything then filters):
lumo.load_all_time()
user_posts = [ajo for ajo in lumo if ajo.author == 'username']

# GOOD (database-level filtering):
lumo.load_for_user('username')
```

---

## Error Handling

### Common Issues and Solutions

#### Issue: `ValueError: start_time and end_time must be provided`

**Cause**: Called `load_ajos()` without time parameters and no instance defaults.

**Solution**:
```python
# Option 1: Provide times to load_ajos
lumo.load_ajos(
    start_time=Lumo.date_to_unix(2023, 9, 1),
    end_time=Lumo.date_to_unix(2023, 9, 30)
)

# Option 2: Set instance defaults
lumo = Lumo(
    start_time=Lumo.date_to_unix(2023, 9, 1),
    end_time=Lumo.date_to_unix(2023, 9, 30)
)
lumo.load_ajos()

# Option 3: Use convenience methods
lumo.load_month(2023, 9)
```

#### Issue: Empty results from filters

**Cause**: Data not loaded or no matching Ajos.

**Solution**:
```python
lumo = Lumo()
lumo.load_month(2023, 9)

results = lumo.filter_by_language('German')
if not results:
    print("No German posts found in September 2023")
else:
    print(f"Found {len(results)} German posts")
```

#### Issue: `AttributeError: 'NoneType' object has no attribute 'name'`

**Cause**: Some Ajos have invalid `lingvo` objects.

**Solution**: Lumo's built-in filters handle this automatically. If you're writing custom filters, check for None:
```python
# Lumo handles this automatically
german = lumo.filter_by_language('German')

# For custom code, check for None
for ajo in lumo:
    if ajo.lingvo and ajo.language_name:
        print(ajo.language_name)
```

---

## Integration Examples

### Flask Web API

```python
from flask import Flask, jsonify
from lumo import Lumo

app = Flask(__name__)

@app.route('/stats/<int:year>/<int:month>')
def get_month_stats(year, month):
    lumo = Lumo()
    lumo.load_month(year, month)
    return jsonify(lumo.to_dict())

@app.route('/language/<language>/stats')
def get_language_stats(language):
    lumo = Lumo()
    lumo.load_last_days(30)
    stats = lumo.get_language_stats(language)
    if stats:
        return jsonify(stats)
    return jsonify({'error': 'Language not found'}), 404

if __name__ == '__main__':
    app.run(debug=True)
```

---

### Discord Bot Command

```python
import discord
from discord.ext import commands
from lumo import Lumo
from time_handling import time_convert_to_string

bot = commands.Bot(command_prefix='!')

@bot.command()
async def stats(ctx, language: str):
    """Get statistics for a language (last 30 days)"""
    lumo = Lumo()
    lumo.load_last_days(30)
    
    stats = lumo.get_language_stats(language)
    if not stats:
        await ctx.send(f"No data found for {language} in the last 30 days")
        return
    
    embed = discord.Embed(title=f"{language} Statistics (Last 30 Days)")
    embed.add_field(name="Total Requests", value=stats['total_requests'])
    embed.add_field(name="Translated", value=stats['translated'])
    embed.add_field(name="Translation Rate", value=f"{stats['translation_percentage']}%")
    embed.add_field(name="Direction Ratio", value=stats['directions'])
    
    await ctx.send(embed=embed)

@bot.command()
async def untranslated(ctx, language: str, limit: int = 5):
    """Show recent untranslated posts for a language"""
    lumo = Lumo()
    lumo.load_last_days(30)
    
    posts = lumo.search(language=language, status='untranslated')
    posts.sort(key=lambda x: x.created_utc, reverse=True)
    
    if not posts:
        await ctx.send(f"No untranslated {language} posts in the last 30 days")
        return
    
    message = f"**Recent Untranslated {language} Posts:**\n"
    for post in posts[:limit]:
        date = time_convert_to_string(post.created_utc)
        message += f"\n• [{post.title_original}](https://redd.it/{post.id})\n  {date}"
    
    await ctx.send(message)
```

---

### Automated Monthly Report

```python
import schedule
import time
from datetime import datetime
from lumo import Lumo

def generate_monthly_report():
    """Generate report for previous month"""
    now = datetime.now()
    
    # Get previous month
    if now.month == 1:
        year, month = now.year - 1, 12
    else:
        year, month = now.year, now.month - 1
    
    # Load data
    lumo = Lumo()
    lumo.load_month(year, month)
    
    # Generate report
    month_name = datetime(year, month, 1).strftime('%B')
    report = f"""
# {month_name} {year} Translation Statistics Report

## Overview
- Total Requests: {lumo.get_overall_stats()['total_requests']}
- Translation Rate: {lumo.get_overall_stats()['translation_percentage']}%
- Unique Languages: {lumo.get_overall_stats()['unique_languages']}

## Top 10 Languages
"""
    
    for lang, count in lumo.get_language_rankings()[:10]:
        stats = lumo.get_language_stats(lang)
        report += f"\n{lang}: {count} requests ({stats['translation_percentage']}% translated)"
    
    # Save report
    filename = f"report_{year}_{month:02d}.md"
    with open(filename, 'w', encoding='utf-8') as f:
        f.write(report)
    
    print(f"Report generated: {filename}")

# Schedule for first day of each month
schedule.every().month.at("00:00").do(generate_monthly_report)

while True:
    schedule.run_pending()
    time.sleep(3600)  # Check every hour
```

---

### Data Visualization with Matplotlib

```python
import matplotlib.pyplot as plt
from lumo import Lumo

def plot_language_distribution():
    """Create pie chart of top languages"""
    lumo = Lumo()
    lumo.load_month(2023, 9)
    
    # Get top 10 languages
    rankings = lumo.get_language_rankings()[:10]
    languages = [lang for lang, _ in rankings]
    counts = [count for _, count in rankings]
    
    # Create pie chart
    plt.figure(figsize=(10, 8))
    plt.pie(counts, labels=languages, autopct='%1.1f%%')
    plt.title('Top 10 Languages - September 2023')
    plt.savefig('language_distribution.png')
    plt.close()

def plot_monthly_trend():
    """Create line chart of monthly requests"""
    months = []
    totals = []
    
    for month in range(1, 13):
        lumo = Lumo()
        lumo.load_month(2023, month)
        months.append(f"{month:02d}")
        totals.append(len(lumo))
    
    plt.figure(figsize=(12, 6))
    plt.plot(months, totals, marker='o', linewidth=2)
    plt.xlabel('Month')
    plt.ylabel('Total Requests')
    plt.title('Monthly Translation Requests - 2023')
    plt.grid(True, alpha=0.3)
    plt.savefig('monthly_trend.png')
    plt.close()

def plot_translation_rate_comparison():
    """Compare translation rates across languages"""
    lumo = Lumo()
    lumo.load_month(2023, 9)
    
    # Get top 10 languages
    top_langs = lumo.get_language_rankings()[:10]
    languages = []
    rates = []
    
    for lang, _ in top_langs:
        stats = lumo.get_language_stats(lang)
        languages.append(lang)
        rates.append(stats['translation_percentage'])
    
    plt.figure(figsize=(12, 6))
    plt.barh(languages, rates)
    plt.xlabel('Translation Rate (%)')
    plt.title('Translation Rates by Language - September 2023')
    plt.grid(True, alpha=0.3, axis='x')
    plt.tight_layout()
    plt.savefig('translation_rates.png')
    plt.close()

# Generate all plots
plot_language_distribution()
plot_monthly_trend()
plot_translation_rate_comparison()
```

---

### CSV Export

```python
import csv
from lumo import Lumo

def export_language_stats_to_csv(year, month, filename='language_stats.csv'):
    """Export language statistics to CSV"""
    lumo = Lumo()
    lumo.load_month(year, month)
    
    with open(filename, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        
        # Write header
        writer.writerow([
            'Language',
            'Total Requests',
            'Translated',
            'Needs Review',
            'Untranslated',
            'Translation %',
            '% of All Requests',
            'Direction Ratio'
        ])
        
        # Write data for each language
        for lang in lumo.get_all_languages():
            stats = lumo.get_language_stats(lang)
            if stats:
                writer.writerow([
                    stats['language'],
                    stats['total_requests'],
                    stats['translated'],
                    stats['needs_review'],
                    stats['untranslated'],
                    stats['translation_percentage'],
                    stats['percent_of_all_requests'],
                    stats['directions']
                ])
    
    print(f"Exported to {filename}")

# Export September 2023
export_language_stats_to_csv(2023, 9, 'sept_2023_stats.csv')
```

---

## Testing

### Unit Test Example

```python
import unittest
from lumo import Lumo
from models.ajo import Ajo

class TestLumo(unittest.TestCase):
    
    def setUp(self):
        """Create test Ajos"""
        self.test_ajos = []
        
        # Create German Ajos
        for i in range(5):
            ajo = Ajo()
            ajo._id = f'german_{i}'
            ajo._created_utc = 1693526400 + (i * 3600)
            ajo.preferred_code = 'de'
            ajo.initialize_lingvo()
            ajo.status = 'translated' if i % 2 == 0 else 'untranslated'
            ajo.direction = 'english_to'
            ajo.type = 'single'
            self.test_ajos.append(ajo)
        
        # Create Japanese Ajos
        for i in range(3):
            ajo = Ajo()
            ajo._id = f'japanese_{i}'
            ajo._created_utc = 1693526400 + (i * 3600)
            ajo.preferred_code = 'ja'
            ajo.initialize_lingvo()
            ajo.status = 'translated'
            ajo.direction = 'english_from'
            ajo.type = 'single'
            self.test_ajos.append(ajo)
    
    def test_load_from_list(self):
        """Test loading Ajos from a list"""
        lumo = Lumo()
        lumo.load_from_list(self.test_ajos)
        self.assertEqual(len(lumo), 8)
    
    def test_filter_by_language(self):
        """Test language filtering"""
        lumo = Lumo()
        lumo.load_from_list(self.test_ajos)
        
        german = lumo.filter_by_language('German')
        self.assertEqual(len(german), 5)
        
        japanese = lumo.filter_by_language('Japanese')
        self.assertEqual(len(japanese), 3)
    
    def test_filter_by_status(self):
        """Test status filtering"""
        lumo = Lumo()
        lumo.load_from_list(self.test_ajos)
        
        translated = lumo.filter_by_status('translated')
        self.assertEqual(len(translated), 6)  # 3 German + 3 Japanese
        
        untranslated = lumo.filter_by_status('untranslated')
        self.assertEqual(len(untranslated), 2)  # 2 German
    
    def test_get_language_stats(self):
        """Test language statistics"""
        lumo = Lumo()
        lumo.load_from_list(self.test_ajos)
        
        german_stats = lumo.get_language_stats('German')
        self.assertEqual(german_stats['total_requests'], 5)
        self.assertEqual(german_stats['translated'], 3)
        self.assertEqual(german_stats['untranslated'], 2)
    
    def test_get_overall_stats(self):
        """Test overall statistics"""
        lumo = Lumo()
        lumo.load_from_list(self.test_ajos)
        
        stats = lumo.get_overall_stats()
        self.assertEqual(stats['total_requests'], 8)
        self.assertEqual(stats['unique_languages'], 2)
    
    def test_search(self):
        """Test complex search"""
        lumo = Lumo()
        lumo.load_from_list(self.test_ajos)
        
        results = lumo.search(
            language='German',
            status='translated'
        )
        self.assertEqual(len(results), 3)
    
    def test_iteration(self):
        """Test iteration over Lumo"""
        lumo = Lumo()
        lumo.load_from_list(self.test_ajos)
        
        count = 0
        for ajo in lumo:
            count += 1
        self.assertEqual(count, 8)
    
    def test_indexing(self):
        """Test indexing into Lumo"""
        lumo = Lumo()
        lumo.load_from_list(self.test_ajos)
        
        first = lumo[0]
        self.assertIsInstance(first, Ajo)
        
        last = lumo[-1]
        self.assertIsInstance(last, Ajo)

if __name__ == '__main__':
    unittest.main()
```

---

## Troubleshooting

### Debug Mode

```python
from lumo import Lumo

# Enable verbose output
lumo = Lumo()
print(f"Lumo instance created: {lumo}")

# Load data with feedback
print("Loading September 2023...")
lumo.load_month(2023, 9)
print(f"Loaded {len(lumo)} Ajos")

# Check what languages are available
languages = lumo.get_all_languages()
print(f"Available languages: {', '.join(languages)}")

# Test a specific language
test_lang = 'German'
posts = lumo.filter_by_language(test_lang)
print(f"{test_lang} posts: {len(posts)}")
if posts:
    print(f"Sample post: {posts[0].title_original}")
```

---

### Validate Data Quality

```python
from lumo import Lumo

def validate_data_quality(lumo):
    """Check for potential data issues"""
    issues = []
    
    for i, ajo in enumerate(lumo):
        # Check for missing language
        if not ajo.lingvo:
            issues.append(f"Post {ajo.id}: Missing lingvo object")
        
        # Check for invalid status
        valid_statuses = {'translated', 'untranslated', 'doublecheck', 
                         'inprogress', 'missing'}
        if isinstance(ajo.status, str) and ajo.status not in valid_statuses:
            issues.append(f"Post {ajo.id}: Invalid status '{ajo.status}'")
        
        # Check for missing created_utc
        if not ajo.created_utc:
            issues.append(f"Post {ajo.id}: Missing created_utc")
    
    if issues:
        print(f"Found {len(issues)} data quality issues:")
        for issue in issues[:10]:  # Show first 10
            print(f"  - {issue}")
    else:
        print("No data quality issues found")

# Run validation
lumo = Lumo()
lumo.load_month(2023, 9)
validate_data_quality(lumo)
```

---

## Frequently Asked Questions

### Q: How do I get posts from a specific date range?

```python
# Use load_ajos with specific timestamps
lumo = Lumo()
lumo.load_ajos(
    start_time=Lumo.date_to_unix(2023, 9, 1),
    end_time=Lumo.date_to_unix(2023, 9, 15)  # First half of September
)
```

### Q: Can I load data multiple times?

Yes! Each load replaces the previous data:
```python
lumo = Lumo()

# Load September
lumo.load_month(2023, 9)
print(len(lumo))  # e.g., 1000

# Load October (replaces September data)
lumo.load_month(2023, 10)
print(len(lumo))  # e.g., 1200
```

### Q: How do I combine data from multiple months?

Load each month and collect results:
```python
all_german = []

for month in range(1, 13):
    lumo = Lumo()
    lumo.load_month(2023, month)
    german = lumo.filter_by_language('German')
    all_german.extend(german)

print(f"Total German posts in 2023: {len(all_german)}")
```

### Q: What's the difference between filter and search?

- **filter_by_X()**: Single criterion, returns list
- **search()**: Multiple criteria, more flexible

```python
# Filter (single criterion)
german = lumo.filter_by_language('German')

# Search (multiple criteria)
results = lumo.search(
    language='German',
    status='translated',
    direction='english_to'
)
```

### Q: How do I handle empty results?

Always check before processing:
```python
results = lumo.filter_by_language('Esperanto')
if not results:
    print("No Esperanto posts found")
else:
    for post in results:
        print(post.title)
```

### Q: Can I modify Ajos in a Lumo instance?

Yes, but changes won't persist to the database unless you explicitly save them:
```python
lumo = Lumo()
lumo.load_month(2023, 9)

for ajo in lumo:
    # This modifies the in-memory object only
    if ajo.status == 'untranslated':
        ajo.status = 'translated'

# Changes are NOT saved to database
# You'd need to call ajo_writer() for each modified Ajo
```
