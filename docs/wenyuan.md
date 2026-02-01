# Lumo - Translation Statistics Analyzer

Complete quick reference for all available functions.

## Import
```python
from processes.wenyuan_stats import Lumo, get_effective_status
```

---

## Loading Data

| Method | Description | Example |
|--------|-------------|---------|
| `load_ajos(start_time, end_time, all_time)` | Load with custom time range | `lumo.load_ajos(start, end)` |
| `load_month(year, month)` | Load specific month | `lumo.load_month(2024, 3)` |
| `load_last_days(days)` | Load last N days | `lumo.load_last_days(7)` |
| `load_all_time()` | Load everything since 2015 | `lumo.load_all_time()` |
| `load_for_user(username, start_time, end_time)` | Load user's posts | `lumo.load_for_user('user456')` |
| `load_single_post(post_id)` | Load single post | `lumo.load_single_post('xyz789')` |
| `load_from_list(ajos)` | Load from list (testing) | `lumo.load_from_list([ajo1, ajo2])` |

---

## Filtering

| Method | Description | Example |
|--------|-------------|---------|
| `filter_by_language(language)` | Filter by language (name or code) | `lumo.filter_by_language('ja')` |
| `filter_by_status(status)` | Filter by status | `lumo.filter_by_status('doublecheck')` |
| `filter_by_direction(direction)` | Filter by direction | `lumo.filter_by_direction('english_from')` |
| `filter_by_type(type)` | Filter by type | `lumo.filter_by_type('multiple')` |
| `filter_by_time_range(start, end)` | Filter loaded data by time | `lumo.filter_by_time_range(start, end)` |
| `search(**kwargs)` | Multiple criteria | `lumo.search(language='ko', status='inprogress')` |

**Status values**: `translated`, `untranslated`, `doublecheck`, `inprogress`, `missing`

**Direction values**: `english_to`, `english_from`, `english_none`

**Type values**: `single`, `multiple`

---

## Statistics Methods

### Language Statistics

| Method | Description | Example |
|--------|-------------|---------|
| `get_language_stats(language)` | Stats for single language (cached) | `lumo.get_language_stats('fr')` |
| `get_stats_for_languages(language_string)` | Stats for multiple languages | `lumo.get_stats_for_languages('zh+ar+ru')` |
| `get_all_languages()` | List all unique languages | `lumo.get_all_languages()` |
| `get_language_rankings(by)` | Top languages ranked | `lumo.get_language_rankings(by='translated')` |
| `get_language_frequency_info(language)` | Frequency data (static) | `Lumo.get_language_frequency_info('es')` |

### Overall Statistics

| Method | Description | Example |
|--------|-------------|---------|
| `get_overall_stats()` | Overall statistics | `lumo.get_overall_stats()` |
| `get_direction_stats()` | Direction breakdown | `lumo.get_direction_stats()` |
| `get_fastest_translations()` | Fastest processing times | `lumo.get_fastest_translations()` |
| `get_identification_stats()` | Language identification stats | `lumo.get_identification_stats()` |

---

## Time Helper Methods (Static)

| Method | Description | Example |
|--------|-------------|---------|
| `date_to_unix(year, month, day, hour, minute, second)` | Convert date to timestamp | `Lumo.date_to_unix(2024, 6, 20)` |
| `month_to_unix_range(year, month)` | Get month timestamp range | `Lumo.month_to_unix_range(2024, 11)` |
| `last_n_days(days)` | Get last N days range | `Lumo.last_n_days(90)` |
| `all_time_range()` | Get all-time range | `Lumo.all_time_range()` |

---

## Utility Functions

### get_effective_status()

Module-level function for consistent status handling.
```python
from processes.wenyuan_stats import get_effective_status

status = get_effective_status(ajo)
# Returns: 'translated', 'untranslated', 'doublecheck', 'inprogress', 'missing'
```

**Note**: For defined multiple posts with mixed statuses, returns the "dominant" status based on priority.

### get_language_frequency_info() (Static)

Get typical frequency without loading data.
```python
freq = Lumo.get_language_frequency_info('Italian')
print(f"{freq['rate_monthly']:.1f} posts/month")
```

---

## Export Methods

| Method | Description | Example |
|--------|-------------|---------|
| `to_dict()` | Export all statistics as dict | `lumo.to_dict()` |

---

## Magic Methods

| Method | Description | Example |
|--------|-------------|---------|
| `len(lumo)` | Get number of loaded Ajos | `print(len(lumo))` |
| `iter(lumo)` | Iterate over Ajos | `for ajo in lumo: ...` |
| `lumo[index]` | Access Ajo by index | `last = lumo[-1]` |
| `repr(lumo)` | String representation | `print(lumo)` |

---

## Detailed Examples

### get_language_stats()
```python
stats = lumo.get_language_stats('Portuguese')

# Returns dict with:
{
    'language': 'Portuguese',
    'total_requests': 85,
    'translated': 68,
    'needs_review': 5,
    'untranslated': 12,
    'translation_percentage': 86,
    'percent_of_all_requests': 8.5,
    'directions': '1.8:1'
}
```

### get_stats_for_languages()
```python
stats = lumo.get_stats_for_languages('Japanese, Korean, Chinese')
# or with codes
stats = lumo.get_stats_for_languages('ja+ko+zh')

# Returns dict mapping language names to their stats
for lang, data in stats.items():
    print(f"{lang}: {data['total_requests']} requests")
```

### get_overall_stats()
```python
overall = lumo.get_overall_stats()

# Returns dict with:
{
    'total_requests': 1500,
    'untranslated': 250,
    'missing_assets': 15,
    'in_progress': 80,
    'needs_review': 55,
    'translated': 1100,
    'translation_percentage': 77,
    'unique_languages': 52
}
```

### get_direction_stats()
```python
directions = lumo.get_direction_stats()

# Returns dict with:
{
    'to_english': {'count': 720, 'percentage': 48.0},
    'from_english': {'count': 580, 'percentage': 38.7},
    'non_english': {'count': 200, 'percentage': 13.3}
}
```

### get_language_rankings()
```python
# Rank by total requests (default)
top = lumo.get_language_rankings(by='total')[:10]

# Rank by translated
top = lumo.get_language_rankings(by='translated')[:10]

# Rank by untranslated
top = lumo.get_language_rankings(by='untranslated')[:10]

# Returns list of tuples: [('Spanish', 220), ('Arabic', 185), ...]
```

### get_fastest_translations()
```python
fastest = lumo.get_fastest_translations()

# Returns dict with:
{
    'to_translated': {'time': 420, 'id': 'def456'},
    'to_review': {'time': 180, 'id': 'ghi789'},
    'to_claimed': {'time': 75, 'id': 'jkl012'},
    'average_translation_hours': 5.2
}
```

### get_identification_stats()
```python
identification = lumo.get_identification_stats()

# Returns dict with:
{
    'identified_from_unknown': {
        'Hebrew': 18,
        'Thai': 12,
        'Armenian': 7
    },
    'misidentified_pairs': {
        'Chinese → Japanese': 4,
        'Hindi → Urdu': 3
    }
}
```

### search()
```python
# Search with multiple criteria
results = lumo.search(
    language='ar',           # Language name or code
    status='translated',     # Status
    type='single',          # Type
    direction='english_from', # Direction
    author='polyglot99'     # Author username
)
```

### filter_by_time_range()
```python
# Load entire year
lumo.load_ajos(
    start_time=Lumo.date_to_unix(2024, 1, 1),
    end_time=Lumo.date_to_unix(2024, 12, 31)
)

# Filter to Q1 only
start = Lumo.date_to_unix(2024, 1, 1)
end = Lumo.date_to_unix(2024, 3, 31, 23, 59, 59)
q1_posts = lumo.filter_by_time_range(start, end)
```

---

## Common Usage Patterns

### Monthly Report
```python
lumo = Lumo()
lumo.load_month(2024, 7)

overall = lumo.get_overall_stats()
print(f"Total: {overall['total_requests']}")
print(f"Translated: {overall['translation_percentage']}%")

top_langs = lumo.get_language_rankings()[:5]
for lang, count in top_langs:
    stats = lumo.get_language_stats(lang)
    print(f"{lang}: {count} ({stats['translation_percentage']}% translated)")
```

### Find Untranslated Posts
```python
lumo = Lumo()
lumo.load_last_days(14)

vietnamese = lumo.search(language='vi', status='untranslated')
for post in vietnamese:
    print(f"{post.title} - https://redd.it/{post.id}")
```

### Compare Languages
```python
lumo = Lumo()
lumo.load_month(2024, 5)

stats = lumo.get_stats_for_languages('ru, pl, cs, uk, bg')
for lang, data in stats.items():
    if data:
        print(f"{lang}: {data['translation_percentage']}% translated")
```

### User Activity
```python
lumo = Lumo()
lumo.load_for_user('linguist2024')

print(f"Total posts: {len(lumo)}")

langs = lumo.get_all_languages()
print(f"Languages: {', '.join(langs)}")

from collections import Counter
statuses = Counter(get_effective_status(ajo) for ajo in lumo)
for status, count in statuses.items():
    print(f"{status}: {count}")
```

### Historical Analysis
```python
lumo = Lumo()
lumo.load_all_time()

turkish = lumo.filter_by_language('tr')
print(f"Total Turkish posts ever: {len(turkish)}")

stats = lumo.get_language_stats('Turkish')
print(f"Translation rate: {stats['translation_percentage']}%")
```

### Find Posts Needing Review
```python
lumo = Lumo()
lumo.load_last_days(30)

review_needed = lumo.filter_by_status('doublecheck')
print(f"Posts needing review: {len(review_needed)}")

for post in review_needed[:10]:
    print(f"{post.language_name}: {post.title}")
```

### Language Deep Dive
```python
lumo = Lumo()
lumo.load_month(2024, 10)

# Get all Italian posts
italian_posts = lumo.filter_by_language('it')
print(f"Total Italian posts: {len(italian_posts)}")

# Break down by direction
to_english = [p for p in italian_posts if p.direction == 'english_to']
from_english = [p for p in italian_posts if p.direction == 'english_from']

print(f"To English: {len(to_english)}")
print(f"From English: {len(from_english)}")
```

### Multiple Criteria Search
```python
lumo = Lumo()
lumo.load_last_days(60)

# Find in-progress Hindi posts translating to English
results = lumo.search(
    language='hi',
    status='inprogress',
    direction='english_to'
)

print(f"Found {len(results)} posts")
for post in results:
    print(f"https://redd.it/{post.id}")
```

---

## Quick Reference
```python
# Load data
lumo.load_month(2024, 8)
lumo.load_last_days(45)
lumo.load_all_time()
lumo.load_for_user('translator789')
lumo.load_single_post('qrs456')
lumo.load_from_list([ajo1, ajo2])

# Filter
lumo.filter_by_language('sv')
lumo.filter_by_status('inprogress')
lumo.filter_by_direction('english_none')
lumo.filter_by_type('single')
lumo.filter_by_time_range(start, end)
lumo.search(language='nl', status='translated')

# Statistics
lumo.get_language_stats('pt')
lumo.get_stats_for_languages('fi+no+da+sv')
lumo.get_all_languages()
lumo.get_language_rankings(by='untranslated')
lumo.get_overall_stats()
lumo.get_direction_stats()
lumo.get_fastest_translations()
lumo.get_identification_stats()

# Time helpers
Lumo.date_to_unix(2024, 12, 15)
Lumo.month_to_unix_range(2024, 4)
Lumo.last_n_days(120)
Lumo.all_time_range()

# Utilities
get_effective_status(ajo)
Lumo.get_language_frequency_info('el')

# Export
lumo.to_dict()

# Iteration
len(lumo)
for ajo in lumo: ...
middle = lumo[len(lumo)//2]
```