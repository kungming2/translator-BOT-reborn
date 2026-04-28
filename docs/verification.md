# Verification

[← Back to Home](./index.md)

## Introduction

**[Verified](www.reddit.com/r/translator/wiki/verified)** is a status on the subreddit that indicates moderators have checked that the user has been a positive contributor to the community. Applications are made by commenting on a [regular verification thread](https://www.reddit.com/r/translator/search/?q=title%3Averified&include_over_18=on&restrict_sr=on&t=all&sort=new) that's automatically posted every six months. 

## Verification Script

Verification posts are automatically posted every six months by Reddit's [native auto-scheduling feature](https://www.reddit.com/r/modnews/comments/jkf5yh/schedule_posts_as_automoderator/). Ziwen retrieves the most recent verification post on the subreddit with `get_verified_thread()`, and looks to see if there are any new requests as comments.

`get_verified_thread()` searches for the newest `title:verified AND flair:meta` post from the last year and only accepts it if the author is a moderator. The resolved post ID is cached when `reddit.verification` is imported; if no post is found, verification parsing is skipped until the module is reloaded.

Ziwen processes root comments on the thread as verification requests. A valid request must:

* Begin with a language name or code and include at least three URLs. 
* Notes may be added optionall after the required information.

Newlines are treated like separators, and any non-URL text after the links is kept as notes for moderators. Requests older than `verification_request_age` minutes are ignored.

For each valid request, Ziwen:

* records the comment in `verification_database` so it is not processed again;
* replies to the requester with the verification acknowledgement template;
* creates a `HELPFUL_USER` mod note for the requester;
* sends a Discord alert with the request link, language, user, and notes.

Malformed root-level requests receive a reply asking the user to start over. Nested malformed comments are ignored.

Mods can manually update the user's flair or use the `!verify` [command](./commands.md). `!verify` must be called by a moderator as a reply to the user's request comment. It reads the first line of the parent comment as the verified language, prepends the verified flair marker, approves the parent comment, messages the moderator who ran the command, records the action in `acted_comments`, and increments verification approval statistics.
