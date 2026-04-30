# Points

[← Back to Home](./index.md)

## Introduction

The points system on r/translator is designed to serve as a way for community members to track their contributions. 

## Design Principles

1. **Points are somewhat weighted by language**, since the opportunity to translate posts is not always equal on this subreddit. For example, [Japanese](https://en.wikipedia.org/wiki/Japanese_language) is at least 150 times more requested than [Tamil](https://en.wikipedia.org/wiki/Tamil_language). The points system has a "language multiplier" (see below) that is used for awarding translation points.
2. **People who contribute should get some points**, even if their comment isn't the first one with `!translated` in it. Thus, someone who verifies a translation is correct, identifies an "Unknown" post, or writes something substantive will get some points, too, since they help keep our subreddit organized and informative.
3. **Points won't be displayed "live" in flairs**. This is unlike comparable discovery/solving subreddits like [r/excel](https://www.reddit.com/r/excel/), [r/PhotoshopRequest](https://www.reddit.com/r/PhotoshopRequest/), or [r/findareddit](https://www.reddit.com/r/findareddit/). On those other subreddits, commenters *can't* give themselves points; only the OP can. In our subreddit, translators *themselves* mark the posts as resolved since OPs generally have no way of assessing the translation themselves. The objective is also to make the points system one of recognition rather than competition, so people are motivated by more than a small number next to their name. 

## Language Multiplier

The formula for the language multiplier is `round(35 / [percent of posts per month])`, up to a cap of `20`. The percent value is read as the displayed percentage number from the latest row of the language's recorded statistics wiki page. The multiplier is cached by month and will therefore adjust over time as languages get less or more popular. Hypothetically, if 35% of posts in a single month were for Arabic, its multiplier would go down to `1` next month.

#### Examples (from 2017-09)

| Language | Percent of Posts | Multiplier |
|----------|------------------|------------|
| [Japanese](https://www.reddit.com/r/translator/wiki/japanese) | 35.89% | 1 |
| [Chinese](https://www.reddit.com/r/translator/wiki/chinese) | 17.53% | 2 |
| [German](https://www.reddit.com/r/translator/wiki/german) | 6.45% | 5 |
| [Arabic](https://www.reddit.com/r/translator/wiki/arabic) | 5.06% | 7 |
| [Spanish](https://www.reddit.com/r/translator/wiki/spanish) | 2.95% | 12 |
| [Hebrew](https://www.reddit.com/r/translator/wiki/hebrew) | 0.60% | 20 |
| [Tamil](https://www.reddit.com/r/translator/wiki/tamil) | 0.24% | 20 |

#### Point Values

| Item                                             | Points Value                                    |
|--------------------------------------------------|-------------------------------------------------|
| *!translated* (provided a translation)           | 1 + (1 * language multiplier)                   |
| *!doublecheck*  (provided a translation)         | 1 + (1 * language multiplier)                   |
| *!identify*                                      | 3                                               |
| `` `...` `` Character/word Lookup                | 2                                               |
| `{{...}}` Wikipedia Lookup                       | 1                                               |
| Long non-OP comment over 120 characters          | 1 + round(0.25 * language multiplier)           |
| *!translated* (confirming another's translation) | 1 (and full points awarded to other translator) |
| *!missing*                                       | 1                                               |
| *!claim*                                         | 1                                               |
| *!page*                                          | 1                                               |
| *!search*                                        | 1                                               |
| *!transform*                                     | 1                                               |

## Implementation

Points are handled in `monitoring/points.py`. The main entry point is `points_tabulator()`, which is called with the triggering comment, the original submission, the post's `Lingvo`, and optionally the post's `Ajo`.

Point records are written to the `total_points` table in `main.db` with:

* `year_month`;
* `comment_id`;
* `username`;
* `points`;
* `post_id`.

Monthly language multipliers are cached in `cache.db`'s `multiplier_cache` table. If a multiplier is not cached, Ziwen attempts to read the language's statistics wiki page and calculate the multiplier from the latest row. If that fails, the multiplier falls back to `20`. Unknown-language posts use a normalized value of `4` and bypass the wiki/cache lookup.

## Awarding Rules

`!translated` and `!doublecheck` are special. They can award full translation points to the commenter, or to the parent comment author if the command is used as a short reply or verification of another user's translation. In those cases, the commenter may receive helper points while the translator receives the full language-adjusted value.

Other commands with configured values use `command_points` in `settings.yaml`; currently `identify` is worth `3` and `lookup_cjk` is worth `2`. Commands not listed there generally default to `1` point, while commands listed in `commands_no_args` do not receive points by default.

Long comments by non-OP users receive an additional `1 + round(0.25 * multiplier)` points when the lowercased, stripped body is over 120 characters. This is additive, so it can stack with command points or full translation credit. Short OP thank-you replies can credit the parent comment author as the translator if that translator has not already received full translation points for the post.

When full translation credit is awarded, Ziwen also:

* adds the translator to the post's `Ajo` translator list;
* writes the updated `Ajo`;
* creates a `SOLID_CONTRIBUTOR` [mod note](https://www.reddit.com/r/modnews/comments/t8vafc/announcing_mod_notes/) for the translator.

Helper and verification actions can create `HELPFUL_USER` mod notes.

## Retrieval

`points_user_retriever(username)` returns the user's current-month total, all-time total, number of posts participated in, and a month-by-month table. This is used by the message handling flow for user point status requests.

`points_post_retriever(post_id)` returns the point records associated with a post. Zhongsheng uses this to show points data in post lookups.
