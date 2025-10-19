# Python Models

[← Back to Home](./index.md)

## Introduction

This page offers an overview of the various primary classes (models) that represent information used by the bot routines. Most of them are extensions of [PRAW](https://github.com/praw-dev/praw) objects that have been adapted to specific usage cases. 

All models are named according to analogous nouns from [Esperanto](https://en.wikipedia.org/wiki/Esperanto). 

## Lingvo

From Esperanto *[lingvo](https://en.wiktionary.org/wiki/lingvo#Esperanto)*, "language".

This is the primary class that represents a language (or in some cases a language-like category)  for bot operations. More about it can be read [here](./language_processing.md).

### Example

```
{'countries_associated': ['MX',
                          'VE',
                          'AR',
                          'BO',
                          'CL',
                          'CO',
                          'CR',
                          'CU',
                          'DO',
                          'EC',
                          'SV',
                          'GQ',
                          'GT',
                          'HN',
                          'NI',
                          'PA',
                          'PY',
                          'PE',
                          'PR',
                          'UY'],
 'countries_default': None,
 'country': None,
 'family': 'Indo-European',
 'greetings': 'Hola',
 'language_code_1': 'es',
 'language_code_2b': None,
 'language_code_3': 'spa',
 'link_ethnologue': 'https://www.ethnologue.com/language/spa',
 'link_statistics': 'https://www.reddit.com/r/translator/wiki/spanish',
 'link_wikipedia': 'https://en.wikipedia.org/wiki/Spanish_language',
 'mistake_abbreviation': None,
 'name': 'Spanish',
 'name_alternates': ['Castilian',
                     'Espanol',
                     'Spainish',
                     'Mexican',
                     'Castilian',
                     'Español',
                     'Spain',
                     'Esp',
                     'Chilean',
                     'Castellano',
                     'Españo'],
 'num_months': 112,
 'population': 527976150,
 'rate_daily': 2.85,
 'rate_monthly': 85.52,
 'rate_yearly': 1026.24,
 'script_code': None,
 'subreddit': 'spanish',
 'supported': True,
 'thanks': 'Gracias'}
```

### Attributes

| Attribute              | Type          | Description                                                                                                                |
|------------------------|---------------|----------------------------------------------------------------------------------------------------------------------------|
| `countries_associated` | `list[str]`   | List of two-letter ISO 3166 country codes (other than the default) where the language is officially used or widely spoken. |
| `countries_default`    | `str \| None` | Default country as a two-letter ISO 3166 country code associated with this language, if any (e.g. `"ES"` for Spain).       |
| `country`              | `str \| None` | The primary or current country context in use (e.g. Canadian French would have `CA` here). In most cases this is `None`.   |
| `family`               | `str`         | The linguistic family this language belongs to (e.g. `"Indo-European"`).                                                   |
| `greetings`            | `str`         | Common greeting used in this language (e.g. `"Hola"`). Defaults to `Hello` if not present in the dataset.                  |
| `language_code_1`      | `str`         | ISO 639-1 two-letter language code (e.g. `"es"`).                                                                          |
| `language_code_2b`     | `str \| None` | ISO 639-2/B three-letter bibliographic code, if applicable.                                                                |
| `language_code_3`      | `str`         | ISO 639-3 three-letter code for the language (e.g. `"spa"`).                                                               |
| `link_ethnologue`      | `str`         | URL to the language’s [Ethnologue reference page](https://www.ethnologue.com/language/spa/).                               |
| `link_statistics`      | `str`         | URL to the subreddit wiki page with [statistics for this language](http://www.reddit.com/r/translator/wiki/spanish).       |
| `link_wikipedia`       | `str`         | URL to the corresponding [Wikipedia article about the language](https://en.wikipedia.org/wiki/Spanish_language).           |
| `mistake_abbreviation` | `str \| None` | Alternate or incorrect abbreviation sometimes used for this language. (e.g. `jp` for Japanese)                             |
| `name`                 | `str`         | Standard English name of the language (e.g. `"Spanish"`).                                                                  |
| `name_alternates`      | `list[str]`   | Known alternate spellings or names for the language, including misspellings and endonyms.                                  |
| `num_months`           | `int`         | Number of months for which statistics have been recorded (that is, requests were made on r/translator).                    |
| `preferred_code`       | `str`         | Standard code for this language used on r/translator.                                                                      |
| `population`           | `int`         | Estimated number of speakers worldwide, as of 2019.                                                                        |
| `rate_daily`           | `float`       | Average daily post rate for this language.                                                                                 |
| `rate_monthly`         | `float`       | Average monthly post rate for this language.                                                                               |
| `rate_yearly`          | `float`       | Projected yearly post rate for this language.                                                                              |
| `script_code`          | `str \| None` | ISO 15924 script code (e.g. `"Latn"`, `"Cyrl"`) if it's an unknown post, but the script is defined.                        |
| `subreddit`            | `str`         | Name of the largest [subreddit dedicated to this language](www.reddit.com/r/Spanish/) (e.g. `"spanish"`).                  |
| `supported`            | `bool`        | Whether this language is officially supported by the bot with a post flair.                                                |
| `thanks`               | `str`         | Common word of gratitude in the language (e.g. `"Gracias"`). Defaults to `Thanks` if not present.                          |

Note that not all attributes are necessarily present in all lingvos.

## Titolo

From Esperanto *[titolo](https://en.wiktionary.org/wiki/titolo#Esperanto)*, "title".

This class represents the parsed information from a post's title to r/translator, including its source and target languages as well as people to notify for. More about it can be read [here](./title_processing.md).

### Example

```
{'ai_assessed': False,
 'direction': 'english_to',
 'final_code': 'fa',
 'final_text': 'Persian',
 'language_country': None,
 'notify_languages': [<Lingvo: Persian (fa)>],
 'source': [<Lingvo: Persian (fa)>],
 'target': [<Lingvo: English (en)>],
 'title_actual': "What does my grandparents' carpet say?",
 'title_original': "[Persian->English] What does my grandparents' carpet say? ",
 'title_processed': "[Persian->English] What does my grandparents' carpet say?"}
```

### Attributes

### Attributes

| Attribute | Type | Description                                                                                                                                              |
|------------|------|----------------------------------------------------------------------------------------------------------------------------------------------------------|
| `ai_assessed` | `bool` | Indicates whether the title or post was evaluated automatically by the AI-based heuristic. This is generally only `True` for extremely malformed titles. |
| `direction` | `str` | Direction of translation, indicating which way translation occurs (e.g. `"english_to"`).                                                                 |
| `final_code` | `str` | The preferred language code representing the final identified target or source language (e.g. `"fa"`).                                                   |
| `final_text` | `str` | Standard name of the final identified language (e.g. `"Persian"`).                                                                                       |
| `language_country` | `str \| None` | Optional country context for the language (e.g. `"CA"` for French Canadian), if specified in the title.                                                  |
| `notify_languages` | `list[Lingvo]` | List of `Lingvo` objects representing languages to notify (that is, which translators to send messages to).                                              |
| `source` | `list[Lingvo]` | One or more `Lingvo` objects corresponding to the detected source languages.                                                                             |
| `target` | `list[Lingvo]` | One or more `Lingvo` objects corresponding to the detected target languages.                                                                             |
| `title_actual` | `str` | Cleaned/simplified version of the Reddit post title after removing the language tag formatting.                                                          |
| `title_original` | `str` | Original unaltered Reddit title text as submitted by the user.                                                                                           |
| `title_processed` | `str` | Final standardized version of the title after parsing and normalization, as processed by the title handling function `process_title()`.                   |


## Komando

From Esperanto *[komando](https://en.wiktionary.org/wiki/komando#Esperanto)*, "command".

This class represents an individual command and the data it contains. If the data it contains is a language, it is represented as a Lingvo. For example, a command such as `!identify:bengali` would be represented as an `identify` Komando containing a `Bengali (Lingvo)` data payload.

For [lookups](./lookup.md), the data will instead be the terms searched, and the languages associated with those terms, if applicable. 

### Examples

```
# Command without argument
{'name': 'translated', 
 'data': [], 
 'specific_mode': False}

# Command with argument
{'name': 'identify', 
 'data': [<Lingvo: Uzbek (uz)>], 
  'specific_mode': False}  

# CJK lookup
{'name': 'cjk_lookup',
 'data': [['zh', '中文']], 
 'specific_mode': False}

# Wikipedia lookup
{'name': 'wikipedia_lookup', 
 'data': ['Volapuk'], 
 'specific_mode': False}
```

### Attributes

| Attribute | Type | Description                                                                                                                                                                                                                |
|------------|------|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `name` | `str` | The command keyword or identifier being executed (e.g. `"translated"`, `"identify"`, `"cjk_lookup"`, `"wikipedia_lookup"`).                                                                                                |
| `data` | `list` | Argument(s) passed to the command. Can contain `Lingvo` objects, strings, or lists of values depending on the command type.                                                                                                |
| `specific_mode` | `bool` | Indicates that a specific string or value within `data` was explicitly requested by the user, rather than inferred automatically. (e.g. `Latn` to specifically request the script identification rather than the language. |

## Instruo

From Esperanto *[instruo](https://en.wiktionary.org/wiki/instruo#Esperanto)*, "instruction".

This class represents a Reddit comment *containing* commands as Komandos. For example, if a comment contains both `!identify:ja` and `{{Meiji Emperor}}` in it, it would be equivalent to an Instruo with both an `identify` Komando and a `wikipedia_lookup` Komando.

### Example

### Attributes

## Ajo

From Esperanto *[aĵo](https://en.wiktionary.org/wiki/a%C4%B5o#Esperanto)*, "thing".

This class represents a Reddit translation request. It includes many attributes that are necessary for tracking its status and progress. 

### Example

```
{
    "author": "SimilarPerspective47",
    "created_utc": 1759444445,
    "direction": "english_to",
    "id": "1nwi9d2",
    "image_hash": null,
    "is_identified": false,
    "is_long": false,
    "language_history": [
        "Arabic"
    ],
    "original_source_language_name": [
        "Arabic"
    ],
    "original_target_language_name": [
        "English"
    ],
    "output_post_flair_css": null,
    "output_post_flair_text": null,
    "preferred_code": "ar",
    "status": "untranslated",
    "title": "Furniture’s inscription",
    "title_original": "[Arabic > English] Furniture’s inscription",
    "type": "single"
}
```

### Attributes

| Attribute | Type | Description                                                                                                    |
|------------|------|----------------------------------------------------------------------------------------------------------------|
| `author` | `str` | Username of the Reddit post author (no `u/`).                                                                  |
| `created_utc` | `int` | UTC timestamp representing when the post was created.                                                          |
| `direction` | `str` | Translation direction (e.g. `"english_to"`).                                                                   |
| `id` | `str` | Unique Reddit post ID.                                                                                         |
| `image_hash` | `str \| None` | Optional hash reference for the image associated with the post.                                                |
| `is_identified` | `bool` | Indicates whether the language has been identified as a different language from what was originally submitted. |
| `is_long` | `bool` | True if the title or text is considered to be overly long.                                                     |
| `language_history` | `list[str]` | A list of languages indicating the identification history of this request.                                     |
| `original_source_language_name` | `list[str]` | Source Lingvos(s) extracted from the title.                                                                    |
| `original_target_language_name` | `list[str]` | Target Lingvos(s) extracted from the title.                                                                    |
| `output_post_flair_css` | `str \| None` | CSS class used to style the post flair, if any. This is deprecated and primarily exists in older Ajos.         |
| `output_post_flair_text` | `str \| None` | Text displayed in the post flair, if any. This is deprecated and primarily exists in older Ajos.               |
| `preferred_code` | `str` | Preferred language code for this translation.                                                                  |
| `status` | `str` | Current translation status (e.g. `"untranslated"`, `"translated"`).                                            |
| `title` | `str` | Simplified version of the post title as processed by `process_title()`, without the language tag.              |
| `title_original` | `str` | Original Reddit post title as submitted by the user.                                                           |
| `type` | `str` | Post type classification (e.g. `"single"` or `"multiple"`).                                                    |

## Kunulo

From Esperanto *[kunulo](https://en.wiktionary.org/wiki/kunulo#Esperanto)*, "companion".

This class is perhaps the most idiosyncratic of the classes here. A Kunulo represents all the comments on a post that have been previously made by the bot. The bot looks at invisible Markdown codes in its comments, that are not visible to readers (e.g. `[](#comment_unknown)`), so that functions required to delete or update those comments can be easily made.

This was formerly (and confusingly) called Komento in the 1.x versions of the bot, and was renamed to avoid confusion.

### Examples

```
{'_data': {'comment_unknown': [('njpal88', None)]},
 '_op_thanks': True,
 '_submission': Submission(id='1o7pjsn')}
 
{'_data': {'comment_cjk': [('nk398my', ['改善', '心', '美', '念', '道'])]},
 '_op_thanks': False,
 '_submission': Submission(id='1o9lu1n')}
```

### Attributes

| Attribute | Type | Description                                                                                                                                                                                                                                                       |
|------------|------|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `_data` | `dict` | Stores categorized comment data, mapping comment tags (e.g. `"comment_unknown"`, `"comment_cjk"`) to lists of tuples. Each tuple contains a Reddit comment ID and its associated parsed data (e.g. recognized characters for lookup or `None` for most comments). |
| `_op_thanks` | `bool` | Indicates whether the original poster (OP) had already expressed thanks or acknowledgment in response to the comment thread.                                                                                                                                      |
| `_submission` | `Submission` | Reference to the PRAW Reddit submission object associated with the comment (e.g. `Submission(id='1o7pjsn')`).                                                                                                                                                     |


## Diskuto

From Esperanto *[diskuto](https://en.wiktionary.org/wiki/diskuto#Esperanto)*, "discussion".

This is a much less complicated equivalent to Ajo. This class represents an *internal post" that is not a request, including meta and community posts.

### Example

```
{"created_utc": 1748894490,
 "id": "1l1s1sx",
 "post_type": "meta",
 "processed": false,
 "title_original": "[META] r/translator Statistics — May 2025"
}
```

### Attributes

| Attribute | Type | Description                                                                                                                  |
|------------|------|------------------------------------------------------------------------------------------------------------------------------|
| `created_utc` | `int` | UTC timestamp representing when the post was created.                                                                        |
| `id` | `str` | Unique Reddit post ID (e.g. `"1l1s1sx"`).                                                                                    |
| `post_type` | `str` | Type of post (e.g. `"meta"`, `community`).                                                                                   |
| `processed` | `bool` | Indicates whether the post has been processed by the bot and notifications sent out to people subscribed to that `post_type`. |
| `title_original` | `str` | Original Reddit post title as submitted.                                                                                     |

