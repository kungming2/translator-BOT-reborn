# Commands (Reddit)

[← Back to Home](./index.md)

## Introduction

These are the Reddit comment commands handled by **Ziwen**, the r/translator
bot. They help requesters and translators update post status, correct language
flair, call people who know a language, and search for previous translations.

## Quick Guide

Most users only need a few commands:

| Command | Use it when... | Example |
|---------|----------------|---------|
| `!translated` | A request has been translated. | `!translated` |
| `!doublecheck` | A translation is present, but needs review. | `!doublecheck` |
| `!claim` | You are working on a request and want others to know. | `!claim` |
| `!missing` | The post is missing the text, image, or other content to translate. | `!missing` |
| `!identify` / `!id` | The post is in the wrong language category, or the language is known. | `!identify:ja` |
| `!page` | You want Ziwen to notify users who know a language. | `!page:arabic` |
| `!search` | You want to find earlier r/translator posts with the same text or phrase. | `!search:吉慶有餘` |
| `!transform` | An attached image needs to be rotated or flipped. | `!transform:90` |

## Language Arguments

Some commands take a **language tag** after a colon. A language tag can be a
language name, an ISO language code, or a more specific language-region or
Unknown-script form. See [Language Processing](./language_processing.md) for
the detailed parser behavior.

Use quotes around language names with more than one word. Use `+` to chain
multiple languages when a command supports multiple language arguments.
Country and region names or codes can be added with a hyphen when a language
needs a regional form.

```text
!identify:hy                       # Armenian
!identify:fr-CA                    # French {Canada}
!identify:german                   # German
!identify:"Swiss German"           # Swiss German
!id:"old church slavonic"          # Old Church Slavonic
!id:pt-brazil                      # Portuguese {Brazil}
!id:cantonese-HK                   # Cantonese {Hong Kong}
!identify:ru+it+uzbek              # Multiple Languages [IT, RU, UZ]
```

For `!identify`, ambiguous short codes can use strict mode with a second
exclamation mark after the code. That behavior is covered in the `!identify`
section below. Strict identification is intended for single-language posts.

## State Commands

State commands change the visible status of a translation request.

| State | Meaning |
|-------|---------|
| Untranslated | The default state. The request has not been translated yet. |
| Translated | The request has been translated. |
| Needs Review | A translation is present, but someone wants another translator to check it. |
| In Progress | Someone has claimed the request and is working on it. |
| Missing | The request is missing content needed for translation. |

State flairs include a bracketed language code, such as `[MS]` for Malay. Two
rare special cases are `[?]` for translated Unknown posts and `[--]` for
translated posts with no flair text.

For normal single-language posts, use state commands without a language
argument. For a defined multiple-language post, you can target one component by
adding a language tag:

```text
!translated
!doublecheck
!claim
!translated:fi
!doublecheck:ja+ko
```

The language-targeted form only applies to defined multiple-language posts where
the requested languages are listed individually. It is not needed for most
requests.

### `!translated`

Marks the post as translated. The command can be used by the original poster or
by another user.

If someone other than the original poster uses `!translated`, Ziwen messages the
original poster to say the post has been translated and asks them to thank their
translator. That message is skipped if the original poster has already thanked
translators in a comment, including thanking them in advance. It also asks the
original poster to keep the post up instead of deleting it after translation.

If `!translated` appears in the same comment as `!identify`, Ziwen does not send
new language notifications for that `!identify` command.

### `!doublecheck`

Marks the post as **Needs Review**. Use this when a translation exists but should
be checked by another translator.

For statistics, Needs Review counts as a completed translation state.

If `!doublecheck` appears in the same comment as `!identify`, Ziwen does not send
new language notifications for that `!identify` command.

### `!claim`

Marks the post as **In Progress** and leaves a courtesy notice that you are
working on the translation. Only one user can claim the same post or defined
language component at a time. If another user tries to claim something already
claimed, Ziwen replies to explain that the post or language component is already
claimed.

Claims expire after eight hours if the post is not marked `!translated` or
`!doublecheck`. When a claim expires, Ziwen resets the post to the untranslated
state and removes the claim comment.

Internally, this state is stored as `inprogress`.

### `!missing`

Marks the post as **Missing** when the requester has not included the content
needed for translation, such as a broken image link or missing text.

Ziwen messages the original poster asking them to add the missing content or
delete and resubmit the post. The message also tells them they can use `!reset`
to restore the post once the missing content is fixed.

## Post Reference Commands

Reference commands help correct language information, contact volunteers, or
find existing translations.

### `!identify:[language]` / `!id:[language]`

Changes the post's language category. Use this when a post was submitted under
the wrong language, or when an Unknown post has been identified. The flair text
is updated to show the identified language.

`!id` is a short form of `!identify`. Both do the same thing, and Ziwen records
both forms internally as `!identify`.

```text
!identify:dutch                   # Dutch                       
!identify:ban                     # Balinese                       
!id:"american sign language"      # American Sign Language
!identify:pt-BR                   # Portuguese {Brazil}
!identify:unknown-Dsrt            # Deseret (Script)
```

`!identify` can also classify a post as a defined multiple-language request by
chaining languages with `+`:

```text
!identify:ru+it+uzbek             # Multiple Languages [IT, RU, UZ]
```

For scripts, use an ISO 15924 code such as `Latn`, `Cyrl`, or `Sidd`, or use an
Unknown-script tag such as `unknown-Hani`. Script identification keeps the post
under the Unknown language category while making the script visible in the flair.

```text
!identify:Latn                   # Latin (Script)
!identify:Cyrl                   # Cyrillic (Script) 
!identify:unknown-Hani           # Han Characters (Script)
```

If a code or short word is ambiguous, use strict mode by adding a second `!`
after the code. Strict mode is for ISO codes, not language names; using a
language name with strict mode returns an error.

```text
!identify:any!                     # Anyin
!identify:ocu!                     # Atzingo Matlatzinca
!identify:Latn!                    # Latin script
```

Strict mode is mainly for rare ISO 639-3 false positives and ambiguous short
strings. For example, `any` may be read as a general word unless strict mode is
used for the ISO 639-3 code for Anyin.

When a four-letter script code is also a language name, the language name takes
priority in normal mode. For example, `!identify:Thai` identifies Thai as a
language, not Thai script. A code such as `Sidd` identifies Siddham script
because there is no language named Sidd.

If Ziwen cannot understand the requested language or code, it replies with an
error and leaves the post unchanged.

Ziwen sends notifications for the newly identified language unless the same
comment also contains `!translated` or `!doublecheck`.

Historical note: this command replaced the older `!wronglanguage` command. The
old command was deprecated after `!identify` and its shorter `!id` form became
available.

### `!page:[language]`

Messages users who are listed in the notifications database for the requested
language. If more than three users are available for that language, Ziwen chooses
three at random.

Use `!page` for tentative identifications, unusual scripts, or posts where
someone with specific language knowledge should take a look.

```text
!page:ar
!page:manchu
!page:fr+it
```

Limitations:

* The caller's Reddit account must be at least fourteen days old.
* If no users are listed for that language, Ziwen replies to say so.
* Multiple `!page` commands can be used in one comment, but `+` chaining is
  usually clearer.

Paged usernames come from the same notifications database used for normal
language notifications.

### `!search:[term]`

Searches r/translator for earlier posts and comments containing the term. This
is useful for common phrases, inscriptions, slogans, repeated requests, and
thematically similar posts. Searching comments is included because normal Reddit
search often only finds text in titles or post bodies.

```text
!search:吉慶有餘
!search:为人民服务
!search:今古有神奉志士
!search:علي
```

`!search` can also return entries from the
[frequently requested translations page](https://www.reddit.com/r/translator/wiki/frequently-requested).

If there are no results, Ziwen replies to say that nothing was found.

Ziwen does not automatically mark a post as translated just because a search
result contains `!translated`. The person using `!search` still needs to check
whether the returned translation actually applies.

## Other Commands

### `!transform:[value]`

Rotates or flips an attached image and replies with a corrected image link.
This works on image posts, text posts with embedded images, link posts, and
gallery posts.

Supported values:

| Value | Result |
|-------|--------|
| `90` | Rotate 90 degrees clockwise. |
| `-90` | Rotate 90 degrees counterclockwise. |
| `180` | Rotate 180 degrees. |
| `270` | Rotate 270 degrees clockwise. |
| `-180` | Rotate 180 degrees counterclockwise. |
| `-270` | Rotate 270 degrees counterclockwise. |
| `h` or `horizontal` | Flip horizontally. |
| `v` or `vertical` | Flip vertically. |

`0` and `360` are invalid rotation values because they would return the same
image. Use one of the supported values above instead.

Examples:

```text
!transform:90
!transform:-90
!transform:horizontal
!transform:v
!transform:90:3                  # Transform the third image in a gallery
```

Notes:

* Transformed images are uploaded to [ImgBB](https://imgbb.com/) and deleted
  automatically after 7 days.
* Ziwen downsamples transformed images to reduce upload size and processing
  time.
* Gallery posts are limited to the first 10 images, even though Reddit galleries
  can contain up to 20 images.

## Original Poster and Moderator Commands

These commands are restricted because they change post state or moderator data.

Original posters and moderators can use:

| Command | What it does |
|---------|--------------|
| `!long` | Toggles a post's Long status and removes the advisory comment. |
| `!reset` | Resets a post as if Ziwen had just processed it. This is mainly for posts that were marked translated too early or fixed after being marked missing. |

Moderators can also use:

| Command | What it does |
|---------|--------------|
| `!nuke` | Permanently bans a user and removes their posts and comments. This is for severe abuse cases. |
| `!set:[language]` | Sets a post's language like `!identify`, but as a moderator action. It can also reclassify a post as an internal `meta` or `community` post. |
| `!verify` | Updates flair for a user who submitted a verification request. |

## Related Lookup Syntax

Ziwen also has lookup functions that do not use `!command` syntax, such as CJK
backtick lookups and Wikipedia-style lookups. Those are documented separately in
[Lookup Functions](./lookup.md).
