# Title Processing

[← Back to Home](./index.md)

## Introduction

This document covers the logic Ziwen uses when it parses incoming posts to r/translator, which is mostly contained in `title_handling.py`. When new requests are made to the community, the bot will parse its title in `ziwen_posts.py` and assign attributes to it based on its title.

For transparency about the AI fallback used when rule-based title parsing cannot
identify a language, see [AI Usage](./ai_usage.md).

## Single-Language Posts

Ziwen independently determines the right source and target languages from post titles. r/translator encourages people to follow the [proper formatting guidelines](https://www.reddit.com/r/translator/wiki/request-guidelines#wiki_how_should_i_submit_requests_for_translations.3F), especially the inclusion of `>` in the title. However, it's okay for someone to submit a title like `[English to Dutch] Text Paragraph`, even if it doesn't have the `>`, as Ziwen is intentionally written to be tolerant of bad formatting in post titles and to account for as many variations as possible.

Ziwen filters out some badly formatted titles and English-only requests before
creating an [Ajo](./models.md). Those removals are logged in `log_filter.md`
with the filter codes described below.

With each rejection, Ziwen also suggests a new title for the post that would adhere to the formatting guidelines. That new title is included in a comment that's posted to the post and Ziwen automatically generates a resubmit link for the OP that pre-fills that new title in.

#### Long Posts

If a post is:

* A link to a YouTube video longer than 5 minutes with no timestamp in the link. (This is listed as `video_long_seconds` in `settings.yaml`)
* A text-only post with more than 1500 characters (about 300 English words on average, or 3/4 of an [A4 page](https://www.adobe.com/uk/creativecloud/design/discover/a4-format.html)). (This is listed as `post_long_characters` in `settings.yaml`)

Ziwen will add the text `(Long)` after the flair text. Hence, a post with [this 16-minute video](https://www.youtube.com/watch?v=zwee-4O70FU) would have the flair text `Japanese (Long)`. 

Moderators and OPs can manually toggle a post's "long" status by using the [command](./commands.md) `!long`. 

#### Badly-Formatted Title Posts

r/translator encourages people to follow the [proper formatting guidelines](https://www.reddit.com/r/translator/wiki/rules), especially the inclusion of `>` in the title. However, it's okay for someone to submit a title like `[English to Dutch] Text Paragraph`, even if it doesn't have the `>`, as Ziwen is intentionally written to be tolerant of bad formatting in post titles and to account for as many variations as possible.

Ziwen records the following filter codes when it removes a post for title
formatting or English-only content:

| Code | Meaning |
|------|---------|
| `1` | Ziwen could not find enough title-format clues to treat this as a valid translation request. Usually this means the title is missing a clear language pair or direction, even if it mentions a language. |
| `1A` | The title has a recognizable `to [language]` direction, but it appears too late in the title instead of near the beginning. Ziwen treats that as burying the required language info. |
| `1B` | The title is short and says something like `to English`, but Ziwen cannot find any non-English source language. In practice, it looks like a request with a target but no clear source. |
| `2` | The title uses `>`, but the arrow appears too late in an unbracketed title. Ziwen expects the language direction to be near the front. |
| `EE` | Ziwen parsed the title as English on both sides, such as `English > English`, so it treats the post as English-only rather than a translation request. We redirect such inquiries to r/englishlearning, r/transcription (for handwriting issues), or r/grammar. |

With each rejection, Ziwen also suggests a new title for the post that would adhere to the formatting guidelines. That new title is included in a comment that's added to the post and Ziwen automatically generates a resubmit link for the OP that pre-fills that new title in, though this resubmit link usually only works on desktop and not on mobile.

## Multiple-Language Posts

The vast majority of posts on r/translator are for a single language, but Ziwen also has support for posts that request translations for multiple languages. 

#### Regular Multiple Posts

If the title has certain keywords instead (e.g. `all`, `any`, `every`), the "multiple" category will be a broad one meant for any language. A post of this type cannot accept state commands (see [this page](./commands.md) for more).

#### Defined Multiple Posts

"Defined multiple" posts are posts where the requester has *defined multiple* specific languages that they'd like their request to be for. A post with the title `[English > German, French, Italian] My genealogical records` would be such an example. Defined multiple posts are treated somewhat differently by Ziwen, as they have specific requirements that can be fulfilled, unlike regular multiple posts.  

Ziwen only treats multiple languages as a *defined multiple* post when the multiple languages are specific non-English target languages. Titles with more than one possible source language, such as `[Persian or Urdu > English]` or `[Chinese/Japanese > English]`, are usually ambiguous identification requests rather than requests for several separate translations. Ziwen may notify subscribers for each possible source language, but it will not assign the post the "multiple" category. Moderators and users can still manually assign multiple languages with `!identify` or `!set` when a post is genuinely asking about more than one source language.

If a post's title has two or more target languages but one of them is English (e.g. `[Chinese > English/Spanish]`), Ziwen will _not_ parse it as a "defined multiple" post.

 | 'Multiple' Post Type | Number of Languages             | Can State Commands be Used? |  
|----------------------|---------------------------------|-----------------------------|
 | *defined*            | a specific number more than one | Yes                  |                         
| *general*            | any and all languages           | No                          |


The state commands (`!doublecheck`, `!translated`, `!claim` and `!missing`) (see [this page](./commands.md) for more) can be used on *defined multiple* posts by appending language names or codes (e.g. `!translated:de`). These commands will not work on *general multiple* posts.

#### Notes

* The `preferred_code` for multiple posts is `multiple` (not [standard ISO 639-3](https://en.wikipedia.org/wiki/ISO_639-3#Special_codes) `mul`)
* Reddit limits flair text to 64 characters. Consequently, if a *defined multiple* post contains so many target languages that their codes won't all fit in the flair, Ziwen will either truncate the number of language codes to fit in the flair or just set it as an *all multiple* post.

## Internal Posts

Internal posts are posts that are _not_ for a language; that is, they are not translation requests. Currently, there are two types of supported internal posts on r/translator:

* **Meta** posts, which are information or discussion posts about the operations of the subreddit or community (e.g. rules discussions, bot updates).
* **Community** posts, which include the translation challenges, thank-you posts, or other posts related to r/translator, but are not *about* the community itself.

#### Examples

* Announcement posts about the bot (`meta`)
* Discussion posts about the community (`meta`)
* Monthly statistics posts (`meta`)
* Thank-you posts (`community`)
* Translation challenges (`community`)

#### Notes

More internal post types can be added by editing the `internal_post_types` list in `settings.yaml`.
