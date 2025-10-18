# Title Processing

[← Back to Home](./index.md)

## Introduction

This document covers the logic Ziwen uses when it parses incoming posts to r/translator. This logic is mostly contained in `title_handling.py`. When new requests are made to the community, the bot will parse its title in `ziwen_posts.py` and assign attributes to it based on its title.

## Single-Language Posts

Ziwen independently determines the right source and target languages from post titles. r/translator encourages people to follow the [proper formatting guidelines](https://www.reddit.com/r/translator/wiki/request-guidelines#wiki_how_should_i_submit_requests_for_translations.3F), especially the inclusion of `>` in the title. However, it's okay for someone to submit a title like `[English to Dutch] Text Paragraph`, even if it doesn't have the `>`, as Ziwen is intentionally written to be tolerant of bad formatting in post titles and to account for as many variations as possible.

Ziwen will filter out/reject titles that match the following criteria:

1. **The title does not include a target language.** An example of this would be the title `Translate pls`. 
2. The post's long title "buries the lede" and puts the target language towards the end without brackets. An example of this would be the title `Could somebody please translate these two words from Japanese to English.`
3. **The title does not include a source language.** An example of this would be the title `Translate to English please`. 
4. **The post is only for English.** An example of this would be the title `[English >English] "seak out" meaning`. We redirect such inquiries to r/englishlearning or r/grammar.

With each rejection, Ziwen also suggests a new title for the post that would adhere to the formatting guidelines. That new title is included in a comment that's posted to the post and Ziwen automatically generates a resubmit link for the OP that pre-fills that new title in.

#### Long Posts

If a post is:

* A link to a YouTube video longer than 5 minutes with no timestamp in the link. (This is listed as `video_long_seconds` in `settings.yaml`)
* A text-only post with more than 1500 characters (about 300 English words on average, or 3/4 of an [A4 page](https://www.adobe.com/uk/creativecloud/design/discover/a4-format.html)). (This is listed as `post_long_characters` in `settings.yaml`)

Ziwen will add the text `(Long)` after the flair text. Hence, a post with [this 16-minute video](https://www.youtube.com/watch?v=zwee-4O70FU) would have the flair text `Japanese (Long)`. 

Moderators can manually toggle a post's "long" status by using the [command](./commands.md) `!long`. 

#### Badly-Formatted Title Posts

r/translator encourages people to follow the [proper formatting guidelines](https://www.reddit.com/r/translator/wiki/rules), especially the inclusion of `>` in the title. However, it's okay for someone to submit a title like `[English to Dutch] Text Paragraph`, even if it doesn't have the `>`, as Ziwen is intentionally written to be tolerant of bad formatting in post titles and to account for as many variations as possible.

Ziwen will filter out/reject titles that match the following criteria:

1. **The title does not include a target language.** An example of this would be the title `Translate pls`. 
2. **The post's long title "[buries the lede](https://www.merriam-webster.com/wordplay/bury-the-lede-versus-lead)"** and puts the target language towards the end without brackets. An example of this would be the title `Could somebody please translate these two words from Japanese to English.`
3. **The title does not include a source language.** An example of this would be the title `Translate to English please`. 
4. **The post is only for English.** An example of this would be the title `[English >English] "seak out" meaning`. We redirect such inquiries to r/englishlearning, r/transcription (for handwriting issues) or r/grammar.

With each rejection, Ziwen also suggests a new title for the post that would adhere to the formatting guidelines. That new title is included in a comment that's posted to the post and Ziwen automatically generates a resubmit link for the OP that pre-fills that new title in, though this resubmit link usually only works on desktop and not on mobile.

## Multiple-Language Posts

The vast majority of posts on r/translator are for a single language, but Ziwen also has support for posts that request translations for multiple languages. If the title has certain keywords instead (e.g. `all`, `any`, `every`), the "multiple" category will be a broad one meant for any language.


#### Defined Multiple Posts

"Defined multiple" posts are posts where the requester has *defined multiple* specific languages that they'd like their request to be for. A post with the title `[English > German, French, Italian] My genealogical records` would be such an example. Defined multiple posts are treated somewhat differently by Ziwen, as they have specific requirements that can be fulfilled, unlike regular multiple posts.  

If a post's title has two or more target languages but one of them is English (e.g. `[Chinese > English/Spanish]`, Ziwen will _not_ parse it as a "defined multiple" post.

 | 'Multiple' Post Type | Number of Languages             | Can State Commands be Used? |  
|----------------------|---------------------------------|-----------------------------|
 | *defined*            | a specific number more than one | Yes                  |                         
| *general*            | any and all languages           | No                          |


The state commands (`!doublecheck`, `!translated`, `!claim` and `!missing`) (see [this page](./commands.md) for more) can be used on *defined multiple* posts by appending language names or codes (e.g. `!translated:de`). These commands will not work on *general multiple* posts.

#### Notes

* The `preferred_code` for multiple posts is `multiple` (not [standard ISO 639-3](https://en.wikipedia.org/wiki/ISO_639-3#Special_codes) `mul`)
* Ziwen will *not* assign a post the "multiple" category if there are more than one *source* languages. (e.g. `[Chinese/Japanese >English]`) This is because the vast majority of such posts aren't actually for more than one language; the OP is usually just unsure which language it actually is.
* Reddit limits flair text to 64 characters. Consequently, if a *defined multiple* post contains so many target languages that their codes won't all fit in the flair, Ziwen will either truncate the number of language codes to fit in the flair or just set it as an *all multiple* post.

## Internal Posts

Internal posts are posts that are _not_ for a language; that is, they're not requests. Currently, there are two types of supported internal posts on r/translator:

* **Meta** posts, which are information or discussion posts about the operations of the subreddit or community (e.g. rules discussions, bot updates).
* **Community** posts, which include the translation challenges, thank-you posts, or other posts related to r/translator, but are not *about* it. 