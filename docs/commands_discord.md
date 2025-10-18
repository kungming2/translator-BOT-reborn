# Commands (Reddit)

[← Back to Home](./index.md)

## Introduction

This document details the primary commands that work on the [r/translator Oversight Discord](https://discord.gg/VBAqzmw9WH), which is a Discord server to help with moderation and management of r/translator. The routine **[Zhongsheng](https://en.wikipedia.org/wiki/Ban_Chao)** interfaces with the server to provide reference information for both mods and users alike, and surfaces many of Ziwen's query functions for easy access.

Commands on the server are prefixed with a slash (`/`) in order to differentiate them from the commands on the subreddit, which are prefixed with an exclamation mark (`!`).

## Public Commands

These commands can be used by both moderators with the `Moderator` role on the server, as well as regular users with the `Helper` role. 

### Command: */cjk*

This command is the equivalent of the subreddit's **[CJK Lookup](./lookup.md)**. The syntax for the command is:

```
/cjk [language] [search_term]
```

* `[language]` can be `c/j/k` or any code and name conforming to those three languages.

### Command: */comment*

This command accepts a Reddit comment's URL or its ID, and returns the commands found within it, providing a way to derive an [Instruo](./models.md) and its [Komando](./models.md)s.

Alternately, ending the command with the `--text` flag evaluates the text before it as a comment. 

```
/comment [comment link/ID]
/comment [comment text to test] --text
```

### Command: */describe*

This command accepts an image URL and generates an AI description of it. This description is used in notifications to give recipients a preview of what the submission is for.

```
/image [image url]
```

### Command: */filter*

This command accepts text for a post title and evaluates whether it would pass or fail the [title filtration routine](./title_processing.md).

```
/filter [text]
```

### Command: */guide*

This command provides information about all the other commands. 

```
/guide
/guide [command name]
```

### Command: */lang*

This command is a wrapper for the main language **[converter](./language_processing.md)**. Just like the converter itself, it accepts codes or names, and returns the information in the database on file for the language. The syntax for the command is:

```
/lang [language]
```

Moderators can also add the flag `--add_alt` and an alternate name for the language to add it to the database.

```
/lang [language] --add_alt [alternate name]
```

### Command: */office* (for testing)

This command just retrieves a random quote from **[The Office API](https://akashrajpurohit.github.io/the-office-api/)**. It has nothing to do with r/translator, but is just a fun addition.

```
/office
```

## Moderator Commands

These commands can only be used by moderators with the `Moderator` role on the server.

### Command: */error*

This command retrieves the last three errors recorded in the log.

```
/error
```

### Command: */post*

This command looks through the logs and the database for mentions of this post, detailing which actions were performed on the post, and what its [Ajo](./models.md)'s state is. 

```
/post [post link/ID]
```

### Command: */user*

Similar to `/post`, this command looks through the logs and the database for mentions of this user, though searches of the Ajo database for a user is limited to the last thirty days in the interest of speed. It will also return data if the user has commands and notifications statistics on the subreddit.

```
/user [user profile link/username]
```

### Command: */title*

This command accepts a text string, usually the title of a post, and attempts to derive a [Titulo](./models.md) from it. Adding the `--ai` flag at the end processes the title through a function intended to interpret the source and target language from the title, even if the function could not make sense of it.

```
/title [text]
/title [text] --ai
```
