# Wenju (Scheduled Maintenance)

[← Back to Home](./index.md)

## Introduction

**[Wenju](https://en.wikipedia.org/wiki/Kong_Rong)** is a maintenance script that collates various tasks needed for maintenance and information. It runs on four different schedules, with different functions called on each schedule.

The functions are in `/wenju` and are categorized by their rough function. They are collated by timing in this documentation. Tasks have been gradually added over the years, and consequently the functions vary quite widely in terms of their naming and scope.

Wenju uses the `@task(schedule="...")` decorator in `wenju.__init__` to register tasks. `run_schedule()` dynamically imports every sibling module in `/wenju`, which triggers decorator registration without maintaining a manual import list. Valid schedule names are `hourly`, `daily`, `weekly`, and `monthly`; `main_wenju.py` validates the command-line argument and dispatches that schedule.

Each task runs independently inside the selected schedule. If one task fails, Wenju logs the exception, writes an error entry, and continues with the remaining tasks. Weekly and monthly schedules send a Discord alert listing successfully executed tasks; hourly and daily schedules do not.

## Hourly Functions

* `monitor_controversial_comments()`: Checks r/translator for heavily downvoted comments and alerts moderators to them. 
* `reddit_status_report()`: Checks the [Reddit Status API](https://www.redditstatus.com/) for any issues. Alerts the Discord if there are any current incidents recorded. 
* `update_sidebar_statistics()`: Updates the r/translator sidebar with the latest statistics from the past 24 hours. It edits the sidebar "wikipage" on Old Reddit and edits a widget on New Reddit.

## Daily Functions

* `archive_modmail()`: Archives modmail conversations older than a pre-configured age where at least one moderator has participated in the conversation.
* `collate_moderator_digest()`: Sends out a link to an HTML digest of the subreddit's overall state, including average number of commands used, activity data, and other information. This also produces a local Markdown report.
* `error_log_trimmer()`: Removes resolved errors older than a configured number of weeks from the error log, keeping it from growing indefinitely.
* `language_of_the_day()`: Randomly selects a language of the day for inclusion in the sidebar of the subreddit as a widget (New Reddit), and as an update to Discord. The function selects ISO 639-1 languages on even days.
* `log_trimmer()`: Trims the events log (where `logger` writes to) to keep only a relatively large amount of recent entries. Also trims the activity CSV log.
* `modqueue_assessor()`: Checks how many items are in the modqueue and alerts the moderators on Discord if the count exceeds a certain threshold.
* `points_worth_cacher()`: Caches the [point](./points.md) values of frequently used languages into a local database for faster access. If the current month does not yet have entries, it purges the previous month's cache and repopulates it.
* `send_internal_post_digest()`: Checks for new internal (e.g. meta/community) posts in the last 24 hours and sends notifications for unprocessed ones. Community notifications, especially, have many sign-ups and as such their notifications are deferred to a quieter time.
* `validate_data_files()`: Checks that all local YAML and JSON files used by the bot are valid. Also runs a validation pass on the Lingvo dataset to catch any malformed language entries. Alerts moderators on Discord if any files fail.

## Weekly Functions

* `clean_processed_database()`: Cleans up the processed comments and posts in the database by pruning old entries from the 'old_comments' and 'old_posts' tables.
* `deleted_posts_assessor()`: Gathers data on individuals who deleted their posts from the subreddit, focusing on those who deleted translated posts without thanking their translators. This is generally considered quite rude by translators, so this routine helps check for repeat offenders. This also produces a local Markdown report.
* `fetch_iso_reports()`: Checks ISO 639-3 code change reports from SIL's [change management page](https://iso639-3.sil.org/code_changes/change_management) and if there's something new, saves that report entry to a YAML file for later alerts.
* `notify_list_statistics_calculator()`: Gathers statistics on the state of the notifications database, including how many people are signed up for which languages. This also produces a local Markdown report.
* `update_verified_list()`:  Updates the subreddit wiki page '[verified](https://www.reddit.com/r/translator/wiki/verified)' with a sorted list of verified users organized by language. Also flags users with problematic flairs.
* `weekly_bot_action_report()`: Generates a weekly report of mod actions on Reddit taken by u/translator-BOT and posts it to r/translatorBOT, including a breakdown of action types and counts for the period.
* `weekly_unknown_thread()`: Posts a weekly 'Unknown' thread to r/translator, which is a round-up of all posts from the last week that are still marked as "Unknown" and have not been assigned a more specific language classification.

## Monthly Functions

* `archive_identified_saved()`: Archives the wikipages of '[identified](https://www.reddit.com/r/translator/wiki/identified)' and '[saved](https://www.reddit.com/r/translator/wiki/saved)' to local Markdown files to prevent the wikipages from getting too large.
* `monthly_rule_violation_report()`: Analyzes the past 30 days of moderation comments to tally rule violations by type, then sends a summary report via Discord.
* `monthly_hermes_statistics_post()`: Posts the previous full calendar month's Hermes statistics to r/translatorBOT. If the post already exists for that month, the task skips posting.
* `monthly_statistics_unpinner()`: Simple routine that unpins the monthly statistics sticky if it's still up when the timing runs. 
* `post_iso_reports_to_reddit()`: Takes the information from `fetch_iso_reports()` and posts the file to r/translatorBOT, as well as updates moderators with that information.
* `refresh_language_statistics()`: Collects all language wiki pages, parses their statistics, and generates a statistics JSON file that serves as a machine-readable format of the statistical information. Also updates the statistics wiki page with a grouped list of links to each individual language's wiki page.
