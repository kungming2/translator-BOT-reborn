# Deprecated Features

[← Back to Home](./index.md)

## Introduction

This document outlines the folders in the primary `Data` folder, which contains all files needed for the bot to run. Files are generally in one of the following formats:

* [YAML](https://yaml.org/): Data files that may need regular human queries.
* [JSON](https://www.json.org/json-en.html): Data files that generally do not need human queries.
* [SQLite](https://en.wikipedia.org/wiki/SQLite): Large databases that need to respond to rapid queries. 
* [CSV](https://en.wikipedia.org/wiki/Comma-separated_values): Tabular data.
* [Markdown](https://en.wikipedia.org/wiki/Markdown): In this project, this format is generally used for consistency in any text file, even if it does not match the Markdown specification fully. 

## Root

| Filename | Function                                 |
|----------|------------------------------------------|
| `auth.yaml` | Authentication information and API keys. | 
| `responses.yaml` | Response templates for the bot.          |

## Archival

Contains two files:

| Filename | Function                                                                    |
|----------|-----------------------------------------------------------------------------|
| `all_identified.md` | Archives all historical post identification data.                           | 
| `all_saved.md` | Archives all saved post identification data (non-template supported posts). | 

## Databases

These are all [SQLite databases](https://sqlite.org/).

| Filename   | Function                                              |
|------------|-------------------------------------------------------|
| `ajo.db`   | Ajo database for all requests.                        | 
| `cache.db` | Contains a cache for comments and points multipliers. | 
| `main.db`  | Main database for all other information.              | 

#### ajo.db Tables

* **ajo_database**: Contains all [ajo](./models.md) records. Note that pre-2.0 Ajos are saved as a Python string representation while post-2.0 ones are saved in [JSON](https://www.json.org/json-en.html); the bot contains compatibility for loading both types.

#### cache.db Tables

* **comment_cache**: Contains recently posted comments to check against to see if edits have been made to comments with new commands.
* **lookup_cjk_cache**: Contains cached data for recent [CJK lookup](./lookup.md) results.
* **multiplier_cache**: Contains multipliers for [points](./points.md).

#### ajo_database

* **acted_comments**: Contains a list of comments that have been acted on by non-Ziwen routines. 
* **internal_posts**: Contains internal (meta and community) posts data. Roughly speaking, a stripped-down version of `ajo_database`. 
* **notify_cumulative**: Contains dictionaries recording the total number of notifications a user has received, indexed by language code. 
* **notify_internal**: A list of usernames and internal post types that those usernames are subscribed to. (one post type / user per row)
* **notify_users**: A list of usernames and languages that those usernames are subscribed to. (one language_code / user per row)
* **old_comments**: Internal list recording comment IDs that have already been seen and processed by the bot. 
* **old_posts**: Internal list recording post IDs that have already been seen and processed by the bot. 
* **total_commands**: Contains dictionaries recording the total number of commands and actions a user has taken.
* **total_points**: Large table containing points data per comment, username, and post.
* **verification_database**: Contains verification requests, sorted by username and language.

## Datasets

| Filename  | Function                                                                                                                                                                                                                                                                                                                                                                                                                             |
|-----------|--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `_statistics.json`  | Monthly-generated JSON file that collates all historical statistics information from the subreddit wiki.                                                                                                                                                                                                                                                                                                                             | 
| `buddhist_chinese.md` | [CC-CEDICT-formatted](https://cc-cedict.org/wiki/) copy of the [Soothill-Hodous](https://glossaries.dila.edu.tw/data/soothill-hodous.dila.pdf) *[A Dictionary of Chinese Buddhist Terms](mahajana.net/texts/kopia_lokalna/soothill-hodous.html)*.                                                                                                                                                                                    | 
| `ccanto.md` | [CC-CEDICT-formatted](https://cc-cedict.org/wiki/) copy of the [CC-Canto Dictionary](https://cantonese.org/).                                                                                                                                                                                                                                                                                                                        | 
| `countries.csv` | CSV of countries according to [ISO 3166](https://en.wikipedia.org/wiki/ISO_3166).                                                                                                                                                                                                                                                                                                                                                    | 
| `iso_codes.csv` | CSV of [ISO 639-3](https://en.wikipedia.org/wiki/ISO_639-3) language codes.                                                                                                                                                                                                                                                                                                                                                          | 
| `iso_codes_updates.yaml`  | Data for [change request reports posted to SIL](https://iso639-3.sil.org/code_changes/change_management) (maintainer of ISO 639-3).                                                                                                                                                                                                                                                                                                  | 
| `iso_script_codes.csv`  | CSV of [ISO 15924](https://en.wikipedia.org/wiki/ISO_15924) script codes.                                                                                                                                                                                                                                                                                                                                                            | 
| `language_data.yaml`  | Main dataset for language information, collated from `_statistics.json` and other sources.                                                                                                                                                                                                                                                                                                                                           | 
| `old_chinese.csv`  | CSV containing data for the [Baxter-Sagart reconstruction of Old Chinese](https://sites.lsa.umich.edu/ocbaxtersagart/).                                                                                                                                                                                                                                                                                                              | 
| `romanization_chinese.csv`  | CSV of [Standard Chinese](https://en.wikipedia.org/wiki/Standard_Chinese) syllable correspondences for [Hanyu Pinyin](https://en.wikipedia.org/wiki/Pinyin), [Yale](https://en.wikipedia.org/wiki/Yale_romanization_of_Mandarin), [Wade-Giles](https://en.wikipedia.org/wiki/Wade%E2%80%93Giles), and [GYRM](https://en.wikipedia.org/wiki/Gwoyeu_Romatzyh). The GYRM column is only used as a reference and is not used by the bot. | 
| `utility_lingvo_data.yaml`  | Information for the non-language utility codes used by the bot (`unknown`, `multiple`, `generic`).                                                                                                                                                                                                                                                                                                                                    |

## Logs

For logs, _running_ refers to a fixed-size buffer that retains the most recent data, which can span days or weeks. _Cumulative_ refers to logs that retain all data recorded since the feature was implemented.

| Filename  | Function                                                                                                                          |
|-----------|-----------------------------------------------------------------------------------------------------------------------------------|
| `_log_activity.csv`  | Running log that records cron runs with the number of used API calls and memory. Also records runtimes for sending notifications. | 
| `_log_counter.json` | Cumulative JSON log for all commands and actions, sorted by day. Written to by `action_counter()`.                                | 
| `_log_error.yaml` | General error log to record errors and contextual information.                                                                    | 
| `_log_events.md` | Main running log for [logger](https://docs.python.org/3/library/logging.html) events (`INFO` and higher).                         | 
| `_log_filter.md` | Cumulative log for posts that were filtered out and rejected by [title processing](./title_processing.md).                        | 
| `_log_testing.md` | If `testing_mode` in `settings.yaml` is `True`, output that would normally be left as a comment or message will be directed here. | 

## Reports

No data files *used* by the bot appear here; rather, local text reports generated by it are saved here, sorted according to month.

## Settings

| Filename  | Function                                                                 |
|-----------|--------------------------------------------------------------------------|
| `discord_settings.yaml`  | Contains webhook data for Discord alerts.                                | 
| `languages_settings.yaml` | Settings for [language name and code parsing](./language_processing.md). | 
| `settings.yaml` | Main settings file.                                                      | 
| `title_settings.yaml` | Settings for [title parsing](./title_processing.md).                     | 
| `wenju_settings.yaml` | Settings for maintenance operations.                                     | 