# Data Files

[← Back to Home](./index.md)

## Introduction

This document outlines the folders in the primary `_data` folder, which contains all files needed for the bot to run. Files are generally in one of the following formats:

* [CSV](https://en.wikipedia.org/wiki/Comma-separated_values): Tabular data.
* [JSON](https://www.json.org/json-en.html): Data files that generally do not need human queries.
* [Markdown](https://en.wikipedia.org/wiki/Markdown): In this project, this format is generally used for consistency in any text file, even if it does not match the Markdown specification fully. 
* [SQLite](https://en.wikipedia.org/wiki/SQLite): Large databases that need to respond to rapid queries. 
* [YAML](https://yaml.org/): Data files that may need regular human queries.

## Auth

| Filename      | Function                               |
|---------------|----------------------------------------|
| `api.yaml`    | API keys for services used by the bot. | 
| `reddit.yaml` | Authentication information for Reddit. | 


## Archival

Contains two files:

| Filename | Function                                                                    |
|----------|-----------------------------------------------------------------------------|
| `all_identified.md` | Archives all historical post identification data.                           | 
| `all_saved.md` | Archives all saved post identification data (non-template supported posts). | 

## Databases

These are all [SQLite databases](https://sqlite.org/).

| Filename    | Function                                                           |
|-------------|--------------------------------------------------------------------|
| `ajo.db`    | Ajo database for all requests.                                     | 
| `cache.db`  | Contains a cache for comments, CJK lookup, and points multipliers. |
| `main.db`   | Main database for all other information.                           |
| `hermes.db` | Main standalone database for Hermes.                               | 

#### ajo.db Tables

* **ajo_database**: Contains all [ajo](./models.md) records. Note that pre-2.0 Ajos are saved as a Python string representation while post-2.0 ones are saved in [JSON](https://www.json.org/json-en.html); the bot contains compatibility for loading both formats.

#### cache.db Tables

* **comment_cache**: Contains recently posted comments to check against to see if edits have been made to comments with new commands.
* **lookup_cjk_cache**: Contains cached data for recent [CJK lookup](./lookup.md) results.
* **multiplier_cache**: Contains multipliers for [points](./points.md).

#### main.db Tables

* **acted_comments**: Contains a list of comments that have been acted on by non-Ziwen routines. 
* **internal_posts**: Contains internal (meta and community) posts data. Roughly speaking, a stripped-down version of `ajo_database`.
* **notify_internal**: A list of usernames and internal post types that those usernames are subscribed to. (one post type / user per row)
* **notify_users**: A list of usernames and languages that those usernames are subscribed to. (one language_code / user per row)
* **old_comments**: Internal list recording comment IDs that have already been seen and processed by the bot. 
* **old_posts**: Internal list recording post IDs that have already been seen and processed by the bot. 
* **total_commands**: Contains a JSON dictionary recording the total number of commands and actions a user has taken.
* **total_notifications**: Contains a JSON dictionary recording the total number of notifications a user has received, indexed by language code. 
* **total_points**: Large table containing points data per comment, username, and post.
* **verification_database**: Contains verification requests, sorted by username and language.

#### hermes.db Tables

* **entries**: Contains all posts processed by Hermes from r/language_exchange. 
* **processed**: Internal list recording post IDs that have already been seen and processed by the Hermes routine.  

## Datasets

| Filename  | Function                                                                                                                                                                                                                                                                                                                                                                                                                             |
|-----------|--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `dataset_countries.csv` | CSV of countries according to [ISO 3166](https://en.wikipedia.org/wiki/ISO_3166).                                                                                                                                                                                                                                                                                                                                                    | 
| `dataset_iso_codes.csv` | CSV of [ISO 639-3](https://en.wikipedia.org/wiki/ISO_639-3) language codes.                                                                                                                                                                                                                                                                                                                                                          |
| `dataset_iso_script_codes.csv`  | CSV of [ISO 15924](https://en.wikipedia.org/wiki/ISO_15924) script codes.                                                                                                                                                                                                                                                                                                                                                            |
| `zh_buddhist_dict.md` | [CC-CEDICT-formatted](https://cc-cedict.org/wiki/) copy of the [Soothill-Hodous](https://glossaries.dila.edu.tw/data/soothill-hodous.dila.pdf) *[A Dictionary of Chinese Buddhist Terms](mahajana.net/texts/kopia_lokalna/soothill-hodous.html)*.                                                                                                                                                                                    | 
| `zh_cantonese_dict.md` | [CC-CEDICT-formatted](https://cc-cedict.org/wiki/) copy of the [CC-Canto Dictionary](https://cantonese.org/).                                                                                                                                                                                                                                                                                                                        | 
| `zh_ocmc.csv`  | CSV containing data for the [Baxter-Sagart reconstruction of Old Chinese](https://sites.lsa.umich.edu/ocbaxtersagart/).                                                                                                                                                                                                                                                                                                              | 
| `zh_romanization.csv`  | CSV of [Standard Chinese](https://en.wikipedia.org/wiki/Standard_Chinese) syllable correspondences for [Hanyu Pinyin](https://en.wikipedia.org/wiki/Pinyin), [Yale](https://en.wikipedia.org/wiki/Yale_romanization_of_Mandarin), [Wade-Giles](https://en.wikipedia.org/wiki/Wade%E2%80%93Giles), and [GYRM](https://en.wikipedia.org/wiki/Gwoyeu_Romatzyh). The GYRM column is only used as a reference and is not used by the bot. | 
                                                                                             

## Logs

For logs, _running_ refers to a fixed-size buffer that retains the most recent data, which can span days or weeks. _Cumulative_ refers to logs that retain all data recorded since the feature was implemented.

| Filename               | Function                                                                                                                         |
|------------------------|----------------------------------------------------------------------------------------------------------------------------------|
| `log_activity.csv`     | Running log that records runs with the number of used API calls and memory. | 
| `log_counter.json`     | Cumulative JSON log for all commands and actions, sorted by day. Written to by `action_counter()`.                               | 
| `log_error.yaml`       | General error log to record errors and contextual information.                                                                   | 
| `log_events.md`        | Main running log for [logger](https://docs.python.org/3/library/logging.html) events (`INFO` and higher).                        | 
| `log_events_cr.md`     | Main running log for Chinese Reference's events (`INFO` and higher).                                                             |
| `log_events_hermes.md` | Main running log for Hermes's events (`INFO` and higher).                                                                        | 
| `log_filter.md`        | Cumulative log for posts that were filtered out and rejected by [title processing](./title_processing.md).                       | 
| `log_messaging.csv`    | Running log that records runtimes for sending notifications. | 
| `log_testing.md`       | If `testing_mode` in `settings.yaml` is `True`, output that would normally be sent as a comment or message will be directed here. | 

## Reports

No data files *used* by the bot appear here; rather, local text reports generated by it are saved here and sorted according to month.

## Settings

| Filename                  | Function                                                                |
|---------------------------|-------------------------------------------------------------------------|
| `discord_settings.yaml`   | Contains webhook data for Discord alerts.                               | 
| `hermes_settings.yaml`    | Settings for [Hermes](./hermes.md).                                     | 
| `languages_settings.yaml` | Settings for [language name and code parsing](./language_processing.md). | 
| `scheduler_settings.yaml` | Settings for scheduler paths used to run Ziwen, Wenju, Hermes, and Chinese Reference. | 
| `settings.yaml`           | Main settings file.                                                     | 
| `title_settings.yaml`     | Settings for [title parsing](./title_processing.md).                    | 
| `wenju_settings.yaml`     | Settings for maintenance operations.                                    | 

## States

The states folder stores files that are not as frequently updated as logs, but are still occasionally updated.

| Filename               | Function                                                                                                                          |
|------------------------|-----------------------------------------------------------------------------------------------------------------------------------|
| `statistics.json`  | Monthly-generated JSON file that collates all historical statistics information from the subreddit wiki.                          |
| `iso_codes_updates.yaml`  | Data for [change request reports posted to SIL](https://iso639-3.sil.org/code_changes/change_management) (maintainer of ISO 639-3). |
| `language_data.yaml`  | Main dataset for language information, collated from `statistics.json` and other sources.                                        |
| `utility_lingvo_data.yaml`  | Information for the non-language utility codes used by the bot (`unknown`, `multiple`, `generic`).                                |

## Templates

| Filename                     | Function                                     |
|------------------------------|----------------------------------------------|
| `responses.yaml`             | Response templates for the bot.              |
| `moderator_digest.html`      | Template for the moderator status dashboard. |
| `translation_challenge.md` | Markdown text for the translation challenge. |
