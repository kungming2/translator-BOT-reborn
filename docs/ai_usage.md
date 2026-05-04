# AI Usage

[<- Back to Home](./index.md)

translator-BOT uses external AI APIs in a few narrow places where rule-based
logic is not enough or where a short accessibility description is useful. This
page documents those call sites and the data passed to the external service for full transparency.

All AI calls go through `integrations/ai.py`. The configured services are:

* [DeepSeek](https://platform.deepseek.com/)
* [OpenAI](https://platform.openai.com)

The shared request helper sends a system instruction and one user prompt to the
selected provider. When an image URL is included, image support is only used for
OpenAI.

## Title Parsing Fallback

Function: `title.title_ai.title_ai_parser()`

Callers: `title.title_handling.process_title()` and
`zhongsheng.title.title_search()`

_Provider: OpenAI_

When it runs:

* During normal Ziwen post processing, after the rule-based title parser cannot
  identify a non-English language from a post title.
* From the Zhongsheng Discord `/title` command when a moderator explicitly adds
  the AI flag.

What is sent:

* The fixed title-parsing instruction stored as `TITLE_PARSING_QUERY` in
  `_data/templates/responses.yaml`.
* The Reddit post title being assessed.
* If available, the public image URL for a direct image post or the first image
  URL from a gallery post.

What is not intentionally sent:

* The post body or comments.
* The author's username.
* Notification subscriber lists.
* Bot databases or private configuration.

How the response is used:

* The bot expects [JSON](https://www.json.org/json-en.html) with source language, target language, and confidence.
* Results below the confidence threshold are rejected.
* Successful language codes are passed back through the repository's language
  converter before they affect flair or notification language state.
* A Discord report alert is sent for moderator review when the fallback path is
  used on a live post.

## Title Reformatting Suggestions

Function: `title.title_ai.format_title_correction_comment()`

Caller: `processes.ziwen_posts.ziwen_posts()`

_Provider: DeepSeek_

When it runs:

* During Ziwen post processing, after a post is removed because its title does
  not meet r/translator title-format requirements.

What is sent:

* The fixed reformatting instruction stored as `TITLE_REFORMATTING_QUERY` in
  `_data/templates/responses.yaml`.
* The removed Reddit post title.

What is not intentionally sent:

* The post body or comments.
* The author's username. The username is only used locally when formatting the
  public reply.
* Bot databases or private configuration.

How the response is used:

* The returned text is treated as a suggested replacement title.
* Ziwen includes that suggestion in a Reddit comment with a prefilled resubmit
  link.

## Image Descriptions for Notifications

Function: `integrations.ai.fetch_image_description()`

Callers: `reddit.notifications.notifier()`,
`zhongsheng.describe.describe_image()`, and
`devtools.check_integrations_ai_image_description()`

_Provider: OpenAI_

When it runs:

* During Reddit notification messages, when a post has a direct image URL that
  should be summarized for recipients.
* From the Zhongsheng Discord `/describe` command when a moderator or helper
  explicitly asks for an image description.
* From the local `devtools.py` AI image-description check.

What is sent:

* The fixed accessibility instruction in `integrations/ai.py`.
* The image-description prompt stored as `IMAGE_DESCRIPTION_QUERY` in
  `_data/templates/responses.yaml`.
* The public image URL.

What is not intentionally sent:

* The post body or comments.
* The author's username.
* Notification subscriber lists.
* Bot databases or private configuration.

NSFW handling:

* If a post is marked NSFW in the notification path, the bot skips the AI call
  and uses a local placeholder message instead.
* The Zhongsheng `/describe` command always treats the supplied URL as an
  explicit operator request and does not apply the notification NSFW skip.

How the response is used:

* The returned text is inserted into Reddit notification messages as an image
  description.
* The prompt asks the service to describe visible text only by appearance and
  context, not to transcribe or translate it.
