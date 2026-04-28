# Chinese Reference

[← Back to Home](./index.md)

## Introduction

Chinese Reference is a small lookup bot for Chinese-language subreddits. It shares Ziwen's Chinese lookup code, but runs as a separate routine from `main_chinese_reference.py` and uses a separate Reddit account configured with `CHINESE_*` credentials ([u/ChineseLanguageMods](https://www.reddit.com/user/ChineseLanguageMods) is the standard).

The scheduler runs it every five minutes. It monitors the `chinese` multireddit owned by the configured Reddit account and scans recent comments for Chinese text wrapped in backticks, such as:

```text
`漢字`
`成語`
```

## Behavior

Chinese Reference only handles Chinese text in backticks. Multi-character text is tokenized with the same lookup matching helper used by Ziwen, then each token is sent to the Chinese character or word lookup function as appropriate. The detailed lookup behavior and data sources are covered in [Lookup Functions](./lookup.md).

The routine uses Reddit's saved-comment state as its duplicate guard:

* comments already saved by the bot account are skipped;
* comments with backticks are saved before lookup processing;
* failed or empty lookups are not retried automatically unless the saved state is cleared.

Replies include the normal lookup output plus the bot disclaimer adapted to the subreddit where the comment appeared.

## Operational Notes

Chinese Reference uses `asyncpraw`, not PRAW. Its logs go to `log_events_cr.md` through the `CR` logger path in `config.py`.

The routine does not write to Ziwen's main processed-comment tables. If it stops responding, check:

* `bot-scheduler` service status;
* the Chinese Reference job log under the scheduler log directory;
* `_data/logs/log_events_cr.md`;
* the `CHINESE_APP_ID`, `CHINESE_APP_SECRET`, `CHINESE_USERNAME`, and `CHINESE_PASSWORD` credentials.
