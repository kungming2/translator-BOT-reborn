# Ziwen Messages

[Back to Home](./index.md)

## Overview

`processes/ziwen_messages.py` handles unread Reddit inbox messages for Ziwen.
It is the inbox-facing dispatcher for user notification subscriptions, status
checks, points lookups, and moderator subscription maintenance.

The module intentionally keeps most command behavior out of the process layer.
It fetches unread inbox items, validates that each item can be handled, routes by
message subject, and then delegates the actual work to `reddit.messaging`.

Note that moderator subscription maintenance through messages may be removed in a future version as [Zhongsheng](commands_discord.md) has equivalent commands which are easier to use (albeit through Discord).

## Runtime Flow

`main_ziwen.py` calls `ziwen_messages()` during the regular Ziwen cycle. The
shared scheduler runs Ziwen every three minutes, so inbox commands are processed
as part of the same routine that handles posts and Reddit comment commands.

Each cycle:

1. Fetches up to 10 unread inbox items with `REDDIT.inbox.unread(limit=10)`.
2. Logs and returns if Reddit raises a configured transient error while fetching.
3. Logs and returns if an unexpected fetch error occurs.
4. Records the `messages_processed` runtime metric when unread items are found.
5. Processes each item independently so one bad message does not stop the rest.
6. Marks each fetched item as read in a `finally` block after processing.

The logger tag for this module is `[ZW:M]`.

## Supported Subjects

| Subject rule | Handler | Purpose |
|--------------|---------|---------|
| `unsubscribe` | `handle_unsubscribe` | Remove one or more notification subscriptions, or all subscriptions. |
| `subscribe` | `handle_subscribe` | Add language or internal post notifications. |
| `status` | `handle_status` | Return notification subscriptions and command statistics. |
| `points` | `handle_points` | Return r/translator points. |
| `add` | `handle_add` | Moderator-only addition of notification subscriptions for another user. |
| `remove` | `handle_remove` | Moderator-only removal of notification subscriptions for another user. |

`unsubscribe` is checked before `subscribe` because the word `unsubscribe`
contains `subscribe`. Any other subject lines are logged and ignored.

## Validation

Before routing a message, the processor applies these checks:

* The unread inbox item must be a `praw.models.Message`. Unsupported inbox item
  types (specifically comments) are logged and skipped.
* `message.author` must exist. Messages from deleted users are skipped.
* `is_valid_user(message_author.name)` must succeed. Invalid authors, such as
  [shadow-banned users](https://www.reddit.com/r/ShadowBan/), are skipped.
* `add` and `remove` require `is_mod(message_author)` before their handlers run.
  Unauthorized moderator commands are logged and ignored.

Skipped messages are still marked read at the end of the item loop.

## Message Body Formats

The detailed parsing lives in `reddit.messaging`, but these are the body formats
the dispatcher sends there.

### Subscribe

`handle_subscribe` reads the message body as a language and internal post type
list. If the body contains `LANGUAGES:`, only the text after that marker is used;
otherwise comment-style lines beginning with `#` are ignored and the remaining
body is parsed. The `LANGUAGES:` prefix handling is for legacy compatibility and will be eventually be removed.

Examples:

```text
French, Japanese, Arabic
```

```text
LANGUAGES:
fr
ja
meta
```

### Unsubscribe

`handle_unsubscribe` uses the same language and internal post type parsing as
subscription requests. If the stripped lowercase body ends with `all`, the user
is purged from all notification subscriptions.

Example:

```text
all
```

### Status

`handle_status` does not require a structured body. It replies with the user's
current notification subscriptions and, when available, appends command
statistics from `user_statistics_loader`. Language subscriptions include both
the language name and notification code, such as `American Sign Language`
(`ase`).

### Points

`handle_points` does not require a structured body. It replies with the user's
r/translator points.

### Moderator Add

`handle_add` expects both `USERNAME:` and `LANGUAGES:` markers. The username is
read from the text after `USERNAME:` and before `LANGUAGES`; language matches are
read from the text after `LANGUAGES:`.

Example:

```text
USERNAME: example_user
LANGUAGES: Spanish, German
```

### Moderator Remove

`handle_remove` removes all notification subscriptions for the target user. If
the body contains `USERNAME:`, the text after that marker is used. Otherwise the
entire stripped body is treated as the username.

Example:

```text
USERNAME: example_user
```

## Side Effects

Handlers in `reddit.messaging` may:

* Reply to the Reddit message.
* Update notification subscription storage through `reddit.notifications`.
* Add moderator notes for subscription changes.
* Increment usage counters.
* Send Discord alerts for failed unsubscribe attempts.
* Read points and command statistics from monitoring modules.

Because message replies and subscription edits happen downstream, changes to
user-visible text usually belong in `responses.py` or `reddit.messaging`, not in
`processes/ziwen_messages.py`.

## Error Handling

Fetch errors are handled before the item loop. Per-message errors are caught
inside the loop:

* `TRANSIENT_ERRORS` are logged as warnings with the message ID.
* Other exceptions are logged with stack traces.
* `message.mark_read()` is attempted even when routing or handler execution
  fails.
* Failures while marking a message read are also logged with stack traces.

This means a handler failure can still consume an unread inbox item. When
debugging a missed message, check `[ZW:M]` logs first, then the downstream
`[MESSAGING]` handler logs.

## Adding a New Message Command

To add a new Reddit message command:

1. Add or update the behavior in `reddit.messaging`.
2. Import the handler in `processes/ziwen_messages.py`.
3. Add the subject routing rule in `ziwen_messages()`.
4. Decide whether the rule should be a substring match or an exact match.
5. Add tests around routing, authorization, invalid authors, and mark-read
   behavior when practical.
6. Update this page and any user-facing command documentation that describes the
   new message command.
