# Hermes (Language Matching)

[← Back to Home](./index.md)

## Introduction

**[Hermes](https://en.wikipedia.org/wiki/Hermes) (Ἑρμῆς)** is a bot written by u/kungming2 that matches users on [r/Language_Exchange](https://www.reddit.com/r/language_exchange/) with other users who match their language exchange requirements. It shares its [language identification and processing components](./language_processing.md) with other r/translator routines. The bot posts comments under [u/language_exchangeBOT](https://www.reddit.com/u/language_exchangeBOT).


The bot was formerly [launched on November 15, 2017](https://www.reddit.com/r/language_exchange/comments/7d2sp5/meta_introducing_a_bot_for_rlanguage_exchange/), after [a period of consultation](https://www.reddit.com/r/language_exchange/comments/79jf0p/meta_would_people_be_interested_in_getting/) and [feedback from the community](https://www.reddit.com/r/language_exchange/comments/7ahhve/meta_update_on_bot_operations_question_to_the/). The routine was then named [Huiban](https://en.wikipedia.org/wiki/Ban_Zhao) but was deactivated on [March 29, 2018](https://www.reddit.com/r/language_exchange/comments/887dnm/seeking_japanese_offering_english/dwihikt/) due to a lack of support from the then-inactive moderators. 

The bot was renamed, rewritten, and relaunched on [July 11, 2020](https://www.reddit.com/r/language_exchange/comments/hpg30u/meta_reintroducing_a_matching_bot_for_rlanguage/) with support from the new moderation team.


## Operations

1. Hermes scans new posts as they come in to r/language_exchange and parses the languages mentioned in each post's title and compares it to a database of users' posts.
    * The bot will also record the user's language levels if they mention that they are native for or include a [CEFR label](https://tracktest.eu/english-levels-cefr/) with a language. (e.g. A1, B2, but also "native")
2. The bot will reply with matches to posts that fit the following criteria with language match information:
    * Is two hours or older (to give a bit of a grace period for human replies) *and*
    * Has fewer than five top-level comments by that point (since the purpose of the bot is to help connect people, and that would be somewhat redundant on an active post)
3. Hermes will automatically clear records of posts in its database that are older than 90 days, or if their author has deleted the post.


## Relevance Score

In making matches, Hermes ranks users in its database in a table by a relevance score:

* **5 points** if the OP and the matched user match in both a single offered and sought language pair.
    * e.g., OP is offering Arabic and seeking Spanish, and the relevant user is seeking Arabic and offering Spanish.
* **3 points** if the matched user just offers a language that the OP seeks.
    * e.g., OP is offering Arabic and seeking Spanish, and the relevant user is offering Spanish (but not seeking Arabic).
* **2 points** if the matched user is seeking a language that the OP offers.
    * e.g., OP is offering Arabic and seeking Spanish, and the relevant user is seeking Arabic (but not offering Spanish).
* **1 point** if the matched user has native-level proficiency for the language the OP is seeking.

These points are *cumulative*, so if the OP and a matched user match in more than one language, that user will then be ranked higher in the results. If there are multiple individuals with the same relevance score, the bot will randomly select up to seven users with that score.

## Notes

* Hermes runs every thirty minutes.
* To be automatically removed from the database, a user should just delete any r/Language_Exchange post they've made in the last 90 days.
* Unlike its earlier incarnation as Huiban, the current version of the bot *does not* process information passed to it via private messaging and relies solely on public posts.