# Wenju (Scheduled Maintenance)

[← Back to Home](./index.md)

## Introduction

**[Wenju](https://en.wikipedia.org/wiki/Kong_Rong)** is a maintenance script that collates various tasks needed for maintenance and information. It runs on four different timings, with different functions called on during each timing.

The functions are in `/tasks` and are categorized by their rough function. They are collated by timing in this documentation. Tasks have been gradually added over the years, and consequently the functions vary quite widely in terms of their naming and scope.

## Hourly Functions

* `monitor_controversial_comments()`: Checks r/translator for heavily downvoted comments and alerts moderators to them. 
* `reddit_status_report()`: Checks the [Reddit Status API](https://www.redditstatus.com/) for any issues. Alerts the Discord if there are any current incidents recorded. 
* `update_sidebar_statistics()`: Updates the r/translator sidebar with the latest statistics from the past 24 hours. It edits the sidebar "wikipage" on Old Reddit and edits a widget on New Reddit.

## Daily Functions

* `clean_processed_database()`: Cleans up the processed comments and posts in the database by pruning old entries from the 'old_comments' and 'old_posts' tables,
* `collate_moderator_digest()`: Sends out an overall digest of the subreddit's state, including average number of commands used, activity data, and other information. This also produces a local Markdown report.
* `language_of_the_day()`: randomly selects a language of the day for inclusion in the sidebar of the subreddit as a widget (New Reddit), and as an update to Discord. The function selects ISO 639-1 languages on even days.
* `log_trimmer()`: Trims the events log (where `logger` writes to) to keep only a relatively large amount of recent entries. 
* `modqueue_assessor()`: Checks how many items are in the modqueue and alerts the moderators on Discord if the count exceeds a certain threshold.
* `send_internal_post_digest()`: Check for new internal (e.g. meta/community) posts in the last 24 hours and send notifications for unprocessed ones. Community notifications, especially, have many sign-ups and as such their notifications are deferred to a quieter time.
* `validate_all_yaml_files()`: Checks that all local YAML files used by the bot pass.

## Weekly Functions

* `deleted_posts_assessor()`: Gathers data on individuals who deleted their posts from the subreddit, focusing on those who deleted translated posts without thanking their translators. This is generally considered quite rude by translators, so this routine helps check for repeat offenders. This also produces a local Markdown report.
* `fetch_iso_reports()`: Checks ISO 639-3 code change reports from their [change management page](https://iso639-3.sil.org/code_changes/change_management) and if there's something new, saves that report entry to a YAML file for later alerts.
* `notify_list_statistics_calculator()`: Gather statistics on the state of the notifications database, including how many people are signed up for which languages. This also produces a local Markdown report.
* `update_verified_list()`:  Updates the subreddit wiki page '[verified](https://www.reddit.com/r/translator/wiki/verified)' with a sorted list of verified users organized by language. Also flags users with problematic flairs.
* `weekly_unknown_thread()`: Posts a weekly 'Unknown' thread, which is a round-up of all posts from the last week that are still marked as "Unknown".

## Monthly Functions

* `archive_identified_saved()`: Archive the wikipages of '[identified](https://www.reddit.com/r/translator/wiki/identified)' and '[saved](https://www.reddit.com/r/translator/wiki/saved)' to local Markdown files to prevent the wikipages from getting too large. 'Saved' is not currently used, but is retained for compatibility. 
* `get_language_pages()`: Collect all language wiki pages, parse their statistics, and generate  a statistics JSON file that serves as a machine-readable format of the statistical information.
* `monthly_statistics_unpinner()`: Simple routine that unpins the monthly statistics sticky if it's still up when the timing runs. 
* `points_worth_cacher()`: Caches the [point](./points.md) values of frequently used languages into a local database for faster access. 
* `post_iso_reports_to_reddit()`: Takes the information from `fetch_iso_reports()` and posts the file to r/translatorBOT, as well as updates moderators with that information. 