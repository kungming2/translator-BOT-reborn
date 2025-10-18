# Verification

[← Back to Home](./index.md)

## Introduction

**[Verified](www.reddit.com/r/translator/wiki/verified)** is a status on the subreddit that just indicates that moderators have checked that the user has been a positive contributor to the community, and applications are made by commenting on a [regular verification thread](https://www.reddit.com/r/translator/search/?q=title%3Averified&include_over_18=on&restrict_sr=on&t=all&sort=new) that's automatically posted every six months. 

## Verification Script

Verification posts are automatically posted every six months by Reddit's [native auto-scheduling feature](https://www.reddit.com/r/modnews/comments/jkf5yh/schedule_posts_as_automoderator/). Ziwen gets the most recent verification post on the subreddit with `get_verified_thread()`, and looks to see if there are any new requests as comments.

If there are, the bot will parse the request and send a notification to the moderators on the Discord server for them to check. Mods can manually update the user's flair or use the `!verify` [command](./commands.md) to automatically parse their current flair and apply the verified one. 