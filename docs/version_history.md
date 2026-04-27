#  Version History

[← Back to Home](./index.md)

## Introduction

This page records the version history of the various routines of translator-BOT. Version logging was much more verbose in the bot's earlier days, especially for bugfixes. 

## Legend

| Tag             | Description                                                                                    |
|-----------------|------------------------------------------------------------------------------------------------|
| 🚀 **Feature**  | A key new feature or change of the bot, one that usually merits its own announcement post.     | 
| ✨ **Addition**  | Refinements to existing features of the bot to improve usability, usually noticeable by users. | 
| 🔄 **Change**   | Changes to how the bot operates, usually not noticeable by users.                              | 
| 🛠️ **Bug Fix** | Bug fixes for issues.                                                                          | 
| 🕯️ **Removed** | Features or code handling that was removed.                                                    |

*Entries which are crossed out indicate [removed or irrelevant functionality](deprecated.md).*

##### translator-BOT 2.2 "The Hermes Update" (2026-03-12)

* ✨ ADDITION: Hermes ([u/language_exchangeBOT](www.reddit.com/user/language_exchangeBOT/)) has been fully integrated into the "reborn" codebase. Until now, it had been using older, legacy code written for Ziwen a long time ago (particularly the languages parser). 
    * Hermes now returns seven results for a language match (up from five).
    * Hermes now will prefix its comments with a language-specific greeting.
* ✨ ADDITION: Specific images in galleries can be selected for transformation. For example, `!transform:h:3` will flip the third image in a gallery horizontally. (suggestion for feature and syntax made by u/Stunning_Pen_8332)
* ✨ ADDITION: Module `__main__` environment runtimes have all been moved and centralized in `devtools.py`.
* ✨ ADDITION: Added syntax to return lookup searches for non-English Wikipedia articles. Example: `{{黄河}}:zh`
* ✨ ADDITION: The lookup function for CJK will now consistently be able to update the bot's comment when the terms looked up are changed in the original comment.
* ✨ ADDITION: [Wiktionary](https://en.wiktionary.org/wiki/Wiktionary:Main_Page) lookup has been re-implemented for non-CJK languages.
* ✨ ADDITION: Non-English Wikipedia results can be fetched by appending a language tag to the regular Wikipedia lookup syntax.  
* 🔄 CHANGE: Fix for regional conversion of strings like "Brazilian Portuguese" and "French (Canada)". These should now convert to their proper code-COUNTRY combination (e.g. `pt-BR` and `fr-CA`).
* 🔄 CHANGE: Instruos now can have a `body_remainder` attribute that contains all text that is NOT a command. It will be `None` if there is no body remainder.
* 🔄 CHANGE: Renaming certain modules for consistency (modules should share their routine names with the bot's main routine):
    * `/commands` -> `/ziwen_commands`
    * `/lookup` -> `/ziwen_lookup`
    * `/tasks` -> `/wenju`
* 🔄 CHANGE: `title_handling.py` and `languages.py` have been broken up into modules.
* 🔄 CHANGE: The moderator digest alert has been simplified and its contents are now updated on a local HTML page instead.
* 🔄 CHANGE: Added PID counters to the logger and activity CSV for better disambiguation.
* 🔄 CHANGE: Added a `created_utc` column to the `comment_cache` table to allow for future improvements. 
* 🔄 CHANGE: Hermes now awards an additional point to matches where the offered language is spoken at a native level. 
* 🔄 CHANGE: The edit tracker is now integrated with instruos and komandos.
* 🔄 CHANGE: The project now uses [APScheduler](https://pypi.org/project/APScheduler/) instead of cron.
  * 🔄 CHANGE: Ziwen now runs on a three-minute cycle. 
* 🔄 CHANGE: Aligned [yojijukugo](https://en.wikipedia.org/wiki/Yojijukugo) search's behavior to that of chengyu as an addition to the main `ja_word` function.   
* 🔄 CHANGE: Dealt with typing according to [Mypy](https://mypy-lang.org/).
* 🔄 CHANGE: Added more testing scripts, including integrations. 
* 🔄 CHANGE: Removed the 60-character maximum limit for confirmatory replies awarding points.
* 🔄 CHANGE: Renamed and reorganized files in the `_data` folder (through `config.py`) for more consistency.
* 🔄 CHANGE: Migrated `main.db` dictionaries to use JSON instead of Python dictionary literals.
* 🔄 CHANGE: Added a `fetch_count` counter to the CJK cache to record which terms are being retrieved most often.
* 🔄 CHANGE: Fixed the `!translated` handler so that an OP will not be notified of a translated post if they are the ones calling the command.
* 🔄 CHANGE: Wenju's language of the day update will also update [r/languagelearning](https://www.reddit.com/r/languagelearning)'s sidebar at the same time.
* 🔄 CHANGE: `devtools.py` and `main_wenyuan.py` now also use [Rich](https://github.com/textualize/rich) for better formatting of lookup results.
* 🔄 CHANGE: Split off the Chinese Reference routine's logger output into its own file.
* 🔄 CHANGE: Events output is trimmed for all logs, not just translator-BOT's. 
* 🔄 CHANGE: Using [DeepSeek V4](https://x.com/deepseek_ai/status/2047516922263285776) for title change suggestion queries. Restructured `ai_query()` to more easily switch between services if desired. 
* 🔄 CHANGE: Use normalized names instead of titles for language name matching (would affect language names like [Mi'kmaq](https://en.wikipedia.org/wiki/Mi%27kmaq_language)).
* 🛠️ BUG FIX: Fix `KeyError` in `get_language_emoji` for languages without an associated country (e.g. constructed languages like [Interlingua](https://en.wikipedia.org/wiki/Interlingua)).
* 🛠️ BUG FIX: Fixed bug in properly assessing the expiry of claim comments where the user did not provide a translation after 8 hours. 
* 🛠️ BUG FIX: Fix to prevent non-CJK backtick terms from being added to `lookup_cjk` in instruos.
* 🛠️ BUG FIX: Fix for an incorrect field in the response for image duplicate removals for a similar image posted by different authors.
* 🕯️ REMOVED: Removed the [Babelcarp](https://babelcarp.org/babelcarp/) tea dictionary from `zh_word` as it was returning too many false positives.

##### translator-BOT 2.1 "The Transformation Update" (2026-02-01)

* 🚀 FEATURE: People can use `!transform:[value]` to change the post's image to the right orientation for ease of translating.
    * `[value]` can be positive or negative values of `90` increments (e.g. `90` rotates the image clockwise, while `-90` rotates it counterclockwise). 
    * `[value]` can also be `horizontal`, `h` or `vertical`, `v` to flip the image horizontally or vertically respectively.
* 🚀 FEATURE: The post duplicates detector has been turned on. Duplicates may be detected in one of two ways:
    * Their titles are identical or near-identical and posted by the same author within a short period of time. Recorded in statistics as `Removed duplicates`.
    * Their image hashes (if applicable for image-only posts) are identical or very similar. Recorded in statistics as `Removed image duplicates`.
    * If a suspected duplicate is found, the bot will remove the post and notify the OP.
* ✨ ADDITION: CJK lookups now have some new (optional) syntax.
    * A language tag added to a lookup will force a lookup in that language, even on a post that's of a different language. E.g. `文化`:ja will return a Japanese lookup, even on a Chinese post. 
    * An exclamation mark `!` appended to the lookup (`年年有余`!, `井底之蛙`:zh!) will disable tokenization of the lookup.
* ✨ ADDITION: CJK lookups can now be loaded from a local cache instead for much faster results. Results loaded from a cache are indicated with the lightning emoji (⚡).
* ✨ ADDITION: Calls for the same lookups (CJK) in the comments will be redirected to a pre-existing comment if it already exists.
* ✨ ADDITION: `/post` in Zhongsheng now also includes relevant points data for the post's comments.
* ✨ ADDITION: Wenju will post a weekly action report on its mod actions to r/translatorBOT.
* ✨ ADDITION: Wenju will inform mods with a monthly overview of rule violations that resulted in mod post/comment removals.
* ✨ ADDITION: Modmail conversations that are over 2 days old, where a mod was the last respondent, will now be archived automatically.
* ✨ ADDITION: Reddit's native removal reasons are attached after post or comment removal.
* ✨ ADDITION: Mods can now use `!set` to classify regular posts as internal posts. 
* 🔄 CHANGE: Kunulo object's data for Chinese CJK lookups now properly include only the traditional characters as a base.
* 🔄 CHANGE: Mod posts ending with the emoji 🧪 in the title will not trigger notifications in case of testing.
* 🔄 CHANGE: Over-long cycle runtimes will trigger an alert to Discord.
* 🔄 CHANGE: The `Data` folder has been renamed to `_data` for consistency.
* 🔄 CHANGE: The prefix `[Notification]` has been removed from subjects of messages. This was a legacy of the first time when Reddit tried to merge chats and messages. 
* 🔄 CHANGE: Renamed `message_reply` to the more appropriate `reddit_reply` as it works for more than just messages.
* 🔄 CHANGE: [Jieba](https://github.com/fxsjy/jieba) has been replaced with [rjieba](https://github.com/messense/rjieba-py/tree/main).
* 🛠️ BUG FIX: Chinese tokenization now uses simplified as a base in order to return more accurate results, particularly when it comes to chengyu. This was the behavior in previous 1.x versions of translator-BOT.
* 🛠️ BUG FIX: Fixed an issue when searching katakana matches for Japanese SFX.
* 🛠️ BUG FIX: Fixed the [verified](https://www.reddit.com/r/translator/wiki/verified) page not updating.
* 🛠️ BUG FIX: Fixed the [identified](https://www.reddit.com/r/translator/wiki/identified) page not updating.
* 🛠️ BUG FIX: The points multiplier for languages has been fixed.
* 🛠️ BUG FIX: Slight fix for superscript numbered-tones in Wade-Giles and Yale Cantonese romanization looking strange on New Reddit.
* 🛠️ BUG FIX: Made sure that confirmatory replies to translating comments credit people appropriately with points.

##### translator-BOT 2.0 "The Reborn Update" (2025-10-20)

The various routines (Ziwen, Wenyuan, Wenju, and Zhongsheng) no longer have separate version numbers as of this update, since all of them fully share the same code.

* 🚀 FEATURE: Complete rewrite and re-rationalization of all routines that use the u/translator-BOT account, intended to make everything much more efficient and future changes/bugfixes/additions easier. Code for the rewritten bot may be found on [Github](https://github.com/kungming2/translator-BOT-reborn). 
    * Consequently, some functions which ran outside of Ziwen in a separate routine called Zifang have been reincorporated into the main bot Ziwen. This [includes](https://www.reddit.com/r/translator/comments/14k4xf3/meta_new_bot_features_including_wikipedia_lookup/) Wikipedia lookup, closing out posts, and duplicate detection for new posts.
* 🚀 FEATURE: A new bot named **[Zhongsheng](https://en.wikipedia.org/wiki/Ban_Chao)** can now work with subreddit data to provide useful information and lookups on the [subreddit Discord](https://discord.gg/wabv5NYzdV). More information about its commands and functionality can be found there with the command `/guide`.  
* ✨ ADDITION: Full support for language chaining for all state commands in defined multiple posts (posts where the OP has defined a certain number of languages they want). `!translated:zh`, `!doublecheck:ja+ko`, etc. will work with defined multiple posts.
* ✨ ADDITION: Messages from the bot can now include language-specific greetings to users. (e.g. 你好, Guten Tag.)
* ✨ ADDITION: Better Korean-language lookup results and output, including tokenization of Korean sentences.
* ✨ ADDITION: If it's a request for a image translation, a very short AI description of the image can be included in the notification message (no machine translations will be included in the description). NSFW images will not be described. 
* ✨ ADDITION: Wikipedia pages with coordinate attributes from the lookup function will also include a relevant [OpenStreetMap](https://www.openstreetmap.org) link to that location. 
* 🔄 CHANGE: The codebase is now linted and formatted with [Ruff](https://github.com/astral-sh/ruff).
* 🔄 CHANGE: Time handling bot-wide has been standardized to [UTC](https://en.wikipedia.org/wiki/Coordinated_Universal_Time). 
* 🔄 CHANGE: Wenju will ping [RedditStatus](https://www.redditstatus.com/) hourly to assess if there are any current site-wide incidents.
* 🔄 CHANGE: Signing up for language notifications is more tolerant of non-standard formatting.
* 🔄 CHANGE: Meta/Community posts are now classified as "internal posts" and are stored and processed separately from regular language requests for better consistency.
* 🔄 CHANGE: More accurate and relevant [Sino-Vietnamese](https://en.wikipedia.org/wiki/Sino-Vietnamese) readings of single Han characters in the lookup. (credit to u/TheDeadlyZebra for the suggestion)
* 🔄 CHANGE: Improved simplified/traditional conversion for Chinese (e.g. [王后](https://en.wiktionary.org/wiki/%E7%8E%8B%E5%90%8E) "queen consort" will never be also displayed as the nonsensical 王後 now).
* 🔄 CHANGE: The `!search` function now uses [DuckDuckGo](https://duckduckgo.com/). Frankly, its results aren't as good as Google, but the [module](https://pypi.org/project/googlesearch-python/) we usually use for Google is [currently inoperational](https://github.com/Nv7-GitHub/googlesearch/issues). 
* 🔄 CHANGE: All [2024-2025 updates to ISO 639-3](https://iso639-3.sil.org/code_changes/change_management) have been added to the dataset. New updates will be automatically recorded by the bot and posted to r/translatorBOT.
* 🔄 CHANGE: Chinese subreddit character/word lookup has been transferred to the separate [u/ChineseLanguageMods](www.reddit.com/user/ChineseLanguageMods) account. It still uses the same backend as Ziwen.
* 🔄 CHANGE: Number of notification messages sent for posts has been lowered to 8 in order to work with Reddit's more stringent API rate limits regarding messaging.
* 🔄 CHANGE: Content in multi-line triple backtick sections (`\`\`\``) will be ignored for lookup. 
* 🔄 CHANGE: Translators' contributions are also added to [mod notes](https://www.reddit.com/r/modnews/comments/t8vafc/announcing_mod_notes/). 
* 🔄 CHANGE: Removed all dependence on the Reddit [save](https://praw.readthedocs.io/en/latest/code_overview/models/submission.html) function in some smaller helper functions to mark whether a comment had been processed.
* 🔄 CHANGE: Added a backup function to query [zi.tools](https://zi.tools/) in case CCDB is not [responding](http://ccdb.hemiola.com/). 
* 🔄 CHANGE: Updated [CC-Canto](https://cantonese.org/download.html) to the latest available version.
* 🔄 CHANGE: `zh_word()` will no longer return a blank entry line if no Cantonese readings are found for the word (it'll just omit the line entirely).
* 🔄 CHANGE: Added a `created_utc` column to `old_posts` and `old_comments` tables in the main database for more consistent clearing of previously processed items.
* 🔄 CHANGE: Bot disclaimer/footer has been simplified to just two links.
* 🔄 CHANGE: More [indices](https://sqlite.org/lang_createindex.html) have been added to the main database to speed up large table queries.
* 🔄 CHANGE: [Gwoyeu Romatzyh](en.wikipedia.org/wiki/Gwoyeu_Romatzyh) output is now provided by [python-pinyin](https://github.com/mozillazg/python-pinyin), and the self-written converter has been removed.
* 🔄 CHANGE: Added a cache for CJK lookups. Right now it is write-only but reading support will be introduced later so that lookups for previously searched terms will be much faster and can be retrieved locally.
* 🛠️ BUG FIX: Fixed slightly incorrect Hakka (Sixian) tone formatting in Markdown.
* 🛠️ BUG FIX: Fixed a new bug where [hanzi](https://en.wikipedia.org/wiki/Chinese_characters)-only lookup matches were accidentally being converted to simplified Chinese, even for Japanese.
* 🛠️ BUG FIX: Records of notifications for script codes for now on will save the script codes as well, instead of just "unknown".
* 🛠️ BUG FIX: Fixed a bug where it was impossible to identify multiple-language posts back to a single language.
* 🛠️ BUG FIX: Fixed claim handler not posting claim comments, causing `progress_tracker` crashes when checking expired claims

###### Deprecated Features

* 🕯️ REMOVED: The `App` classification for non-defined `Multiple Languages` posts. This was almost never used even after it was introduced, and with the modern interpretation of Rule #R2, there's no need for it. Its three-letter "special" code also clashed with the language-based categories we use. 
* 🕯️ REMOVED: [Goo](https://help.goo.ne.jp/help/article/2889/) shut down their monolingual Japanese dictionary, so links to their site have been removed from Japanese-lookup results.
* 🕯️ REMOVED: We formerly had a brigading warner routine set up in Wenju to provide moderators with advance warning if a subreddit known for brigading had linked to r/translator. All such subreddits have since been shutdown and this is no longer needed.
* 🕯️ REMOVED: Code for long-defunct commands that were no longer used.
    *  `!reference`: This returned information about a language and has been long removed. There is now an equivalent on the Discord server, `/lang`. 
    *  `!restore`: Formerly sent an archived copy of a text-only post if the OP had deleted it to the translator. It has been non-functional since [Pushshift got taken over by Reddit](https://www.reddit.com/r/pushshift/comments/14ei799/pushshift_live_again_and_how_moderators_can/) and its API was sunsetted.
    * `!translate`/`!translator`: These commands formerly allowed you to ask the bot to cross-post posts to r/translator.
    * `!delete`: Formerly allowed OPs or mods to delete bot cross-posts. 
    * `!note`: A rarely used mod-only command, it manually saved a post with a generic post flair to the [saved languages log](https://www.reddit.com/r/translator/wiki/saved). This has become completely automated now and is no longer necessary. 
    * `+`: Allowed users to manually award a point to a user. This was practically never used.

##### Wenju 1.0 (2024-04-22)

Now (as of v2.0) fully integrated into the entirety of translator-BOT, Wenju was written initially as a means of splitting off regularly scheduled Ziwen and Wenyuan functions into its own routine. 

* ✨ ADDITION: Wenju uses Discord webhooks to alert moderators and users about updates such as verification requests. Previously these were covered by a mix of free-form reports and modmail messages.
* ✨ ADDITION: Language of the day: Randomly chooses a language of the day to display as a widget on New Reddit and as a notification in Discord. Alternates between ISO 639-1 and ISO 639-3 languages in order to balance language diversity and familiarity. 
* ✨ ADDITION: Formats and updates the [verified page](https://www.reddit.com/r/translator/wiki/verified) on the wiki with a list of verified users ordered by language code.
* 🔄 CHANGE: Wenju has a problematic comment warner, which can warn moderators if a comment is getting heavily downvoted. This is frequently associated with troll comments.
* 🔄 CHANGE: Updates the sidebar hourly with an assessment of requests' statuses over the last twenty-four hours. This was originally part of a routine called "Ziwen Hourly", then moved to Wenyuan, then moved to Wenju.
* 🔄 CHANGE: Generates a monthly JSON backup of all the language statistics data on our wiki.
* 🔄 CHANGE: Copies and clears the "[identified](www.reddit.com/r/translator/wiki/identified)" and "[saved](https://www.reddit.com/r/translator/wiki/saved)" wikipages so they don't get too full. (new function)

##### Zifang 1.0 (2023-06-26)

Note that all of Zifang's features have been integrated into Ziwen, as of v2.0.

* 🚀 FEATURE: [Wikipedia lookup](https://www.reddit.com/r/translator/comments/14k4xf3/meta_new_bot_features_including_wikipedia_lookup/) for terms by enclosing them with `{{curly braces}}`.
* 🚀 FEATURE: Duplicate detection for posts submitted in a short period of time with similar titles and images.
* 🚀 FEATURE: Closing out posts: when a post is more than a week old, and has quite a few comments, but hasn't been marked as "translated" or "needs review" yet, the bot will message their authors asking them to "close out" and mark their posts as translated.


##### Ziwen 1.8 "The Restoration Update" (2019-10-05)
* 🚀 FEATURE: ~~Individuals who provided a translation for a deleted text-only post can use the `!restore` command to ask Ziwen to retrieve the now-deleted text.~~
    * ~~Ziwen will attempt to retrieve the text from [Pushshift](http://pushshift.io/). If successful, Ziwen will send the retrieved text as a private message to the translator.~~
    * ~~Calling the `!restore` command on a link/image post will result in a error reply from Ziwen.~~
* ✨ ADDITION: Ziwen now maintains a per-post list of usernames it has already notified. This means that a user *should not* receive a second notification message for a post if they had already received one.
    * An example of such a scenario is one where a `!page` command was used on a post, and then `!identify` for the same language.
* ✨ ADDITION: [Added Chinese character variants](https://www.reddit.com/r/translator/comments/xu3k2q/meta_updates_to_ziwens_lookup_routines/) link to lookup results.
* ✨ ADDITION: [Integration](https://www.reddit.com/r/translator/comments/1chs5k3/meta_improvements_to_search_and/) of YAML on the [Frequently Requested Translations](https://www.reddit.com/r/translator/wiki/frequently-requested) page with the `!search` command.
* 🔄 CHANGE: Cleaned up Chinese and Japanese dictionaries footer and Cantonese/Hakka tones to account for differences between Markdown rendering on Old and New Reddit.
* 🔄 CHANGE: ~~Changed romanization of hangul in Chinese character results to Yale.~~
* 🔄 CHANGE: Changed romanization of hangul in Chinese character results to [Revised Romanization](https://en.wikipedia.org/wiki/Revised_Romanization_of_Korean). (suggestion made by u/zombiegojaejin)

##### Wenyuan 3.0 (2018-04-01)
* ✨ ADDITION: Second complete rewrite of the bot. The rewritten statistics routine uses data from Ziwen's databases for even more accuracy.
* ✨ ADDITION: Wenyuan can now account for deleted posts in its statistics as approximately 10-13% of requests to r/translator are deleted by their OPs. These requests are now recorded and included in the statistics.
* ✨ ADDITION: Added information on "Identification" statistics, including what languages 'Unknown' posts are identified as, common mixed-up pairs, and which post underwent the most language category changes.

##### Ziwen 1.7 "The Ajo Update" (2017-12-09)
* 🚀 FEATURE: Though not externally visible, the backend of Ziwen has been completely revamped. Ziwen now builds a Python class called *[Ajo](https://en.wiktionary.org/wiki/-a%C4%B5o#Esperanto)* from each r/translator post, and the bot will make changes to each *Ajo* before pushing the changes to Reddit. This should result in fewer calls to Reddit, and has resulted in much cleaner code.
* 🚀 FEATURE: [Ziwen can now process commands made in edits](https://www.reddit.com/r/translator/comments/7e2ryc/meta_ziwens_oneyear_anniversary_and_some_small/), up to a two-hour buffer.
* 🚀 FEATURE: [Ziwen can now process country codes as well](https://www.reddit.com/r/translator/comments/7id9m9/meta_bot_support_for_languagecountry_combos_and/) to provide services for regional languages. 
* ✨ ADDITION: Ziwen now calculates approximately how often languages are requested on the subreddit and includes that information in new subscription confirmations. (For frequently requested languages, data from the last 12 months is used to provide more accurate data, credit to u/dudds4 for the suggestion.)
* ✨ ADDITION: Ziwen can send notifications for posts classified as scripts.
* ✨ ADDITION: ~~Ziwen can now crosspost posts from English to another language (using the syntax `<` at the end of the command).~~
* ✨ ADDITION: Ziwen should be able to "replace" its word/character lookup comments when the source data changes.
* ✨ ADDITION: ~~The "App" post category is now treated as a subset of "Multiple Languages" and will be automatically applied to titles which have keywords that indicate that they are for an app request.~~
* ✨ ADDITION: The title format routine can determine a post's direction (to English, from English, etc.).
* ✨ ADDITION: Ziwen stores all *Ajos* in a local cache. This enables Ajos to be used independently of Reddit's data and track how many posts get deleted, among other things.
* ✨ ADDITION: Ziwen will now add Korean, Japanese, and Vietnamese readings of characters to individual Chinese character lookups.
* ✨ ADDITION: Ziwen can mark the *doublecheck* and *translated* states for defined languages of "Multiple Languages" and "App" posts and mark it in the flair.
* ✨ ADDITION: Reformatted Chinese and Japanese multiple-character results to be cleaner.
* ✨ ADDITION: Added a way for the moderator `!set` command to set a defined multiple post.
* ✨ ADDITION: Added Hokkien and Hakka readings of characters and words to the Chinese lookup output.
* ✨ ADDITION: Added [Wade-Giles](https://en.wikipedia.org/wiki/Wade%E2%80%93Giles) and [Yale](https://en.wikipedia.org/wiki/Yale_romanization_of_Mandarin) romanization for lookup results of Chinese words. (suggestion by u/prikaz_da) 
* ✨ ADDITION: Full support for the Reddit redesign's post templates (new linkflairs, basically) has been implemented.
* ✨ ADDITION: Re-enabled Japanese tokenization of sentences with [MeCab](http://taku910.github.io/mecab/). 
* ✨ ADDITION: `!wronglanguage` is now deprecated; `!id` replaces it as a synonym for `!identify`. (credit to u/Darayavaush)
* ✨ ADDITION: Ziwen can now return statistics on how many commands a user has made.
* ✨ ADDITION: Ziwen can now record the time-delta (time difference) between states in its Ajo. This allows Wenyuan to calculate the average amount of time it takes a request to be translated and the time difference between "needs review" and translated, among others.
* ✨ ADDITION: Addition of specialized dictionaries (Buddhist and tea terms) to the Chinese word `lookup`. They can be used as a last resort and also to serve as supplementary information.
* ✨ ADDITION: Added sound effects and given name search to the `lookup` results for Japanese words.
* 🔄 CHANGE: ~~This is a "feature-freeze" version of Ziwen; that is, there will no more major features introduced in the near future. Any bugs will of course be fixed as they pop up, and refinements will still be made.~~
* 🔄 CHANGE: Ziwen can now process languages in submitted posts whose names are multiple words. (e.g. `[American Sign Language > English]`)
* 🔄 CHANGE: Ziwen supports a limited number of conlangs on a local basis (using unallocated space in the ISO 639-3 code list) - including Dothraki, Valyrian, etc. 
* 🔄 CHANGE: The `!page` function is now fully integrated with the notifications database and no longer relies on its own database. It also fully supports all languages now.
* 🔄 CHANGE: Ziwen will send a notification to the mods of this subreddit when a title fails the post categorizing routine.
* 🔄 CHANGE: Ziwen will filter out posts that AutoModerator let through but should have been removed.
* 🔄 CHANGE: Ziwen will automatically remove users from its database that have deleted their accounts.
* 🔄 CHANGE: ~~The sidebar update routine and weekly unknown thread posting routine has been moved back to Wenyuan, which now has an active component that runs every hour.~~
* 🔄 CHANGE: The verification parser now splits requests by newlines instead of pipes.
* 🔄 CHANGE: Added a function that tries to make one last attempt at categorizing a title even if everything else has failed.
* 🔄 CHANGE: ~~Unified the language identification function on crossposting commands. All commands now use the same language identification function.~~ 
* 🔄 CHANGE: Ziwen will alphabetize and remove duplicates from the list of subscribed languages before replying to a subscription status message. 
* 🔄 CHANGE: If there are more than fifty people signed up for a language's notifications, Ziwen will randomly select fifty users to get notifications. 
* 🔄 CHANGE: ~~Added a dynamic "blacklist" for the crosspost function to help prevent abuse of the function.~~
* 🔄 CHANGE: Ziwen will prioritize ISO 639-1 codes (if they exist) over ISO 639-3 ones; so `!identify:deu` will still result in the output being `de` instead of `deu`. 
* 🔄 CHANGE: Addition of a new "Nonlanguage" flair for posts that are not considered to contain linguistic content (ISO 639-3 code: `zxx`). 
* 🔄 CHANGE: Ziwen caches language reference data locally and can return it much quicker if it's been referenced before (now shared with Wenyuan). 
* 🔄 CHANGE: Refinements to Korean and Wiktionary lookup searches.
* 🔄 CHANGE: ~~Disabled the Japanese tokenizer for now as its output was not working as well as it should.~~
* 🔄 CHANGE: Users can now `!identify` a post as a script from anywhere (previously was limited to 'Unknown' posts)
* 🔄 CHANGE: Advanced `!identify` mode is no longer required for script identification. Ziwen will automatically attempt to look for a script code that matches ISO 15924. 
* 🔄 CHANGE: Added support for [Linguist Lists's local use codes](https://en.wikipedia.org/wiki/Wikipedia:WikiProject_Languages/List_of_ISO_639-3_language_codes_used_locally_by_Linguist_List).
* 🔄 CHANGE: Added support for alternate names for ISO 639-3 languages (e.g. "Shanghainese" for "Wu Chinese", "Hokkien" for "Min Nan Chinese", etc.) and ISO 15924 scripts (e.g. "Cryllic" for "Cyrillic").
* 🔄 CHANGE: Posts that fail the title format routine are now primarily removed by Ziwen instead of AutoModerator.
* 🔄 CHANGE: Ziwen will now check for duplicate entries before writing to the notifications database. (duplicates were always handled on the reading side, now they are handled on the writing side as well)
* 🔄 CHANGE: Ziwen can account for cases where people accidentally use square brackets in combination with a command (e.g. `!identify:[xhosa]`).
* 🔄 CHANGE: Manually added code to convert certain erroneous [ISO 3166-1 alpha-2](https://en.wikipedia.org/wiki/ISO_3166-1_alpha-2) country codes into their ISO 639-1 language equivalents (e.g., JP>JA, CN>ZH, GR>EL).
* 🔄 CHANGE: Updated all references to the newly released (2017) version of [ISO 639-3](http://www-01.sil.org/iso639-3/cr_files/639-3_ChangeRequests_2017_Summary.pdf).
* 🔄 CHANGE: Updated the Chinese chengyu lookup function to include literary sources when possible.
* 🔄 CHANGE: Ziwen now stores a couple of variables in Ajos locally for internal purposes. `language_history` tracks the various states of a language and `recorded_translator` stores the usernames of translators as determined by the points function. 
* 🔄 CHANGE: Ziwen will check against the `language_history` list to make sure notifications are only ever sent once per language. (e.g. a post that goes from "Unknown" to "Chinese" to "Unknown" will only have "Unknown" notifications sent once)
* 🔄 CHANGE: Ziwen can now process multiple `!page` commands in a single comment. 
* 🔄 CHANGE: Rewrote certain routines to no longer use the deprecated *submissions* method of PRAW.
* 🔄 CHANGE: Improved comment matching when using the `!search` command. Ziwen will also remove commands from comments it quotes. 
* 🔄 CHANGE: Added support for legacy (largely unused) [ISO 639-2/B codes](https://en.wikipedia.org/wiki/ISO_639-2#B_and_T_codes).
* 🔄 CHANGE: Updated the Middle Chinese and Old Chinese pronunciations to the [Baxter-Sagart 2014 reconstruction](http://ocbaxtersagart.lsait.lsa.umich.edu). (credit to u/sauihdik)
* 🔄 CHANGE: Added handling for backslashes `\` in the word lookup command (the redesign will include those slashes if one is using the rich text editor).
* 🔄 CHANGE: Streamlined the posts filtering routine and added an automated advisory comment for defined multiple posts.
* 🔄 CHANGE: ~~[Ziwen will now limit language notifications](https://www.reddit.com/r/translator/comments/8nceh7/meta_proposed_update_to_notifications_for/) for a single language to around 100 messages per username per month.~~
* 🔄 CHANGE: ~~Streamlined and cleaned up language reference comments by the bot.~~ 
* 🔄 CHANGE: Refinements made to "short thanks" marking posts as translated. The criteria is more stringent now.
* 🔄 CHANGE: ~~Further refinements and formatting adaptations for Wiktionary results.~~ Ziwen will also automatically tokenize sentences if they have spaces.
* 🔄 CHANGE: Ziwen will automatically add a permalink to the post for its response to an invalid `!identify` command.
* 🔄 CHANGE: Ziwen will send a message letting OPs who make a "short thanks" comment know. (credit to u/Darayavaush)
* 🔄 CHANGE: Added [Guoxuedashi](http://shufa.guoxuedashi.com/) and [MFCCD](http://humanum.arts.cuhk.edu.hk/Lexis/lexi-mf/) links to lookup results for Chinese characters.
* 🔄 CHANGE: Added Japanese explanations and literary sources to `lookup` results for yojijukugo.
* 🔄 CHANGE: Transitioned Japanese `lookup`to the Jisho API, which is still in beta. Includes parts of speech now.
* 🔄 CHANGE: Tweaks to the verification parser for consistency.
* 🛠️ BUG FIX: Fixed a CSS bug when marking a generic post as "Long." 
* 🛠️ BUG FIX: Fixed a bug when stacking `!identify` commands with others (including with newlines separating them).
* 🛠️ BUG FIX: Fixed a bug identifying posts as utility categories.
* 🛠️ BUG FIX: Added handling for a situation if someone issued a crosspost command and deleted the command immediately after. 
* 🛠️ BUG FIX: Added handling for situations where subscription messages had "+" instead of spaces. (probably a result of certain mobile apps)
* 🛠️ BUG FIX: Fixed a bug that would prevent assignment of linkflair when the "Multiple Languages" text exceeded 64 characters. Ziwen will now truncate the flair text appropriately to fit.
* 🛠️ BUG FIX: Fixed a small bug that came from a conflict between short thanks commands and `!translated`.
* 🛠️ BUG FIX: Fixed the streamer responding to commands that included `!translate` but were longer strings (e.g. !translateobliterate)
* 🛠️ BUG FIX: Fixed a bug with readings of mixed-kana-kanji Japanese words (e.g. 唐揚げ).
* 🛠️ BUG FIX: Fixed a bug identifying "Multiple Languages" posts as single-language posts.
* 🛠️ BUG FIX: Added handling for a situation with a nonsense script identification. (e.g. `!identify:ffff`)
* 🛠️ BUG FIX: Added handling for languages with hyphens (e.g. Ai-Cham) or "English" (e.g. "Middle English") in their name.
* 🛠️ BUG FIX: Added handling for a non-English request with regional variations (e.g. "Cuban Spanish > German")
* 🛠️ BUG FIX: Fixed a bug with `!reset` being used on 'Unknown' posts.
* 🛠️ BUG FIX: Fixed a bug related to parsing the original post of a crosspost that had deleted/removed comments. 
* 🛠️ BUG FIX: Fixed a bug with fetching Unihan data for some obscure Chinese characters. 
* 🛠️ BUG FIX: Changed the logic of Ziwen identifying language names in text. Now excludes obscure ISO 639-3 languages.
* 🛠️ BUG FIX: Added proper handling for languages with apostrophes in them (e.g. "K'iche'"). 
* 🛠️ BUG FIX: Improved handling of `!claim` commands.
* 🛠️ BUG FIX: Added proper handling if a wiki page that Ziwen writes to becomes too long.
* 🛠️ BUG FIX: Fixed some issues with writing defined multiple Ajos to the database.
* 🛠️ BUG FIX: Fixed getting invalid results from Korean Naver lookup; Ziwen will also no longer respond with a comment if there are zero results from the ` word lookup. 
* 🛠️ BUG FIX: Ziwen will clean up its comment reply to an invalid `!identify` command if the comment is edited with a proper one.
* 🛠️ BUG FIX: Fixed an occasional bug with getting hiragana-only readings with the lookup command.
* 🛠️ BUG FIX: Fixed a rare bug with obtaining Wade-Giles/Yale romanization for Chinese lookup words.
* 🛠️ BUG FIX: Fixed a bug with `!search` attempting to get a post link from the subreddit's own base URL. 
* 🛠️ BUG FIX: Fixed a bug with unknown katakana words getting treated as kanji for lookup purposes.
* 🛠️ BUG FIX: Fixed a bug with identified "defined multiple" posts getting random reference data as a comment.
* 🛠️ BUG FIX: Fixed a bug where "defined multiple" Ajos occasionally would get non-matching data.
* 🛠️ BUG FIX: Fixed a bug where attempting to send a notification to a suspended user would throw an exception.
* 🛠️ BUG FIX: Fixed a bug where a `!search` result was longer than Reddit's maximum of 10,000 characters.
* 🛠️ BUG FIX: Fixed a bug in retrieving calligraphy overall image.

##### Wenyuan 2.4 (2017-11-15)
* ✨ ADDITION: Added Wikipedia article links to the monthly data output. 
* ✨ ADDITION: ~~World population is now retrieved dynamically from the [World Population API](http://api.population.io/).~~
* ✨ ADDITION: Integrated the count for specific language requests into the main reference table.
* ✨ ADDITION: Now includes general information on the status of the notifications database in the monthly data output.
* 🔄 CHANGE: ~~Merged the Ziwen Hourly routine (updated sidebar, maintenance, etc.) with Wenyuan for simplicity. Thus, Wenyuan now also has an active component.~~ (Note: this is now part of Wenju)
* 🔄 CHANGE: Reference information for non-CSS supported languages is now cached locally (shared with Ziwen). 
* 🔄 CHANGE: Some general rewriting to make the bot more resilient and error-free.
* 🔄 CHANGE: Updated the sidebar update function to use more accurate data.
* 🛠️ BUG FIX: Fixed a bug that prevented saving data for some non-CSS supported languages. 
* 🕯️ REMOVED: Removed all `timestamp` links that were based on cloudsearch, as Reddit has deprecated the system for user-facing interfaces. 

##### Ziwen 1.6 "The Points Update" (2017-10-07)
* 🚀 FEATURE: [New points system](https://www.reddit.com/r/translator/comments/74xgy5/meta_earn_points_on_rtranslator/): Contributors to r/translator will automatically get points for making translations, helping keep the community organized, and using bot functions. 
* 🚀 FEATURE: Users can message the bot with `Points` in the subject to get a rundown of how many points they've earned this month, as well as overall.
* ✨ ADDITION: Ziwen's notification response will now include a native-language "thank you" for subscriptions.  
* ✨ ADDITION: Added more dictionary links for Chinese word lookup results. 
* ✨ ADDITION: The points status output now includes a nice table of the months the user has participated in and the number of posts their points were awarded for. This is for future-proofing. 
* ✨ ADDITION: Support for flairing incoming posts as scripts instead of languages (for example, Cuneiform, Braille, etc.) These posts have the "Unknown" flair. 
* ✨ ADDITION: "Multiple Language" requests for specific languages will now have those language tags included in their linkflair, separated by commas. (e.g. `Multiple Languages [AR, DA, UZ]`)
* 🔄 CHANGE: Japanese surname results will now have capitalized romaji readings. 
* 🔄 CHANGE: ~~Ziwen will now post a more informative response to an invalid advanced `!identify` command.~~ 
* 🔄 CHANGE: ~~Ziwen now *automatically* backs up its database files to Box every day. (It relied on manual backups before)~~
* 🔄 CHANGE: ~~Ziwen Streamer now writes to the same error log as the main routine.~~
* 🔄 CHANGE: Refinements to the way the bot makes sense of requests for more than one language. The bot should be able to differentiate situations where the user has listed more than one target language. 
* 🔄 CHANGE: Quality of life adjustments for title formatting - alternate names for English (Ingles, Ingerris, etc) is now supported. The bot also has a hard list of words that it won't apply fuzzy spelling matching to - for example, Javanese posts kept getting corrected to Japanese. 
* 🔄 CHANGE: Notifications will now be sent to people signed up for both languages if a request is for two non-English languages (e.g. Dutch to Indonesian). 
* 🛠️ BUG FIX: Fixed a situation where Ziwen would delete its attribution comment on one of its crossposts. 
* 🛠️ BUG FIX: Fixed a situation where Ziwen would delete processed posts' id from its database (a relic from the [ReplyBot](https://praw.readthedocs.io/en/stable/tutorials/reply_bot.html) tutorial routine). Posts and comments are now stored on separate tables.  

##### Wenyuan 2.3 (2017-11-15)
* ✨ ADDITION: ~~Added the ability to submit posts on the status of the bot to the profile. Also added the ability to delete those statuses.~~

##### 1.5 "The Progress Update" (2017-07-22)
* 🚀 FEATURE:[ New claiming/in progress function](https://www.reddit.com/r/translator/comments/6pdjn0/meta_new_feature_claim_translation_requests_youre/) (`!claim`): Users can now claim an individual translation thread as something they're working on. Ziwen will automatically reset the flair if no translation is given after a certain amount of time. (credit to u/songluck)
* 🚀 FEATURE: ~~[Cross-posting now works from everywhere on Reddit](https://www.reddit.com/r/translator/comments/6sni74/meta_now_you_can_crosspost_translation_requests/). This is run by a separate script and is no longer part of the main Ziwen runtime.~~
* 🚀 FEATURE: ~~People often accidentally link to the subreddit by listing r/translate - the bot will now post a reply that corrects this.~~ 
* ✨ ADDITION: [Full support](https://www.reddit.com/r/translator/comments/6vomng/meta_rtranslator_commands_and_notifications_now/) for all [ISO 639-3 languages](https://en.wikipedia.org/wiki/List_of_ISO_639-3_codes) for commands and notifications. 
* ✨ ADDITION: ~~Full support for Reddit's [native cross-posting feature](https://www.reddit.com/r/modnews/comments/6vths0/beta_crossposting_better_attribution_for_cat/) (which is still in beta).~~
* ✨ ADDITION: ~~Now uses [Pushshift to power cross-posting behavior](https://www.reddit.com/r/translator/comments/b1z1n9/meta_update_to_improve_the_reliability_and/).~~
* ✨ ADDITION: Support for identification of [ISO 15924](https://en.wikipedia.org/wiki/ISO_15924#List_of_codes) script codes on "Unknown" posts. 
* ✨ ADDITION: Added a notifications status link to all notification messages (previously, it was only sent when someone signed up for a new language). 
* ✨ ADDITION: Added an automatic link to message this subreddit in the comment Ziwen posts when someone tries to use a language code or name it cannot make sense of. 
* ✨ ADDITION: If a plain `!translate` or `!translator` command is called on a post which already has a language mentioned in the title, the bot will crosspost it as that language instead of "Unknown."
* ✨ ADDITION: Reconstructed pronunciations for Old Chinese and Middle Chinese is now available for individual Chinese character lookup. 
* ✨ ADDITION: Pronunciations for Sinitic languages has been reformatted into a cleaner-looking table. 
* ✨ ADDITION: If a multiple request is for two or more *defined* languages, Ziwen will send notifications to those signed up for those languages, not those listed for "multiple."
* ✨ ADDITION: ~~Also allow the requester of a crosspost to remove it with `!delete`.~~
* ✨ ADDITION: If a crosspost request is made from a known language learning subreddit (e.g. r/LearnJapanese) but has no specified language, the bot will crosspost it as that subreddit's language instead of "Unknown."
* ✨ ADDITION: Ziwen's crosspost response will now include a native "thank you" for many languages (e.g. ขอบคุณ for a Thai request)
* 🔄 CHANGE: The sidebar update routine has been renamed to the hourly routine and can now post the weekly 'Unknown' threads automatically. 
* 🔄 CHANGE: Tweaks and refinements to the title formatting routine. 
* 🔄 CHANGE: ~~Tweaks to the formatting of the language reference output to include ISO 639-1 codes for languages which are specified in that standard, and include [MultiTree](http://www.multitree.org) links.~~ 
* 🔄 CHANGE: ~~The language reference output also will include the language's subreddit if available. (e.g. r/french for French)~~
* 🔄 CHANGE: Integrated an action counter into Ziwen so that it can record how many times various commands are called and actions are completed. 
* 🔄 CHANGE: ~~Moderator `ping` now also returns the counters for that day.~~
* 🔄 CHANGE: Adapted the notifications language routine to be more tolerant of formatting errors. Now also accepts spaces, slashes, and returns as separators. The routine will also no longer write English as a code to the database, though it will still appear to users as a subscribed language. (There are almost no English-only posts on r/translator)
* 🔄 CHANGE: Character lookup supports the search of [CJK Unified Ideographs Extension B-F](https://en.wikipedia.org/wiki/CJK_Unified_Ideographs_Extension_B) characters. There are no online dictionaries that contain info for these *extremely* rare characters, so the result will still be "not found", however. (If an online dictionary is available that supports these characters, support will be added)
* 🔄 CHANGE: Refinements to the `!search` function results, mostly to exclude previous `!search` requests from showing up as results.
* 🛠️ BUG FIX: Fixed a syntax change that was preventing the bot from deleting its "long" warning messages.
* 🛠️ BUG FIX: Fixed an error that would pop up when attempting to warn a user of a long post, and that post was not a supported language. 
* 🛠️ BUG FIX: ~~Fixed a "too long" error that would occur if a moderator pinged and the errors were too long for a Reddit message (>10K characters).~~ 
* 🛠️ BUG FIX: ~~Fixed accidental cross-posting of `!translated` commands used *outside* of r/translator.~~ 
* 🛠️ BUG FIX: ~~Ziwen will now replace language reference information if there is a newer `!identify` command called on a post.~~ 
* 🛠️ BUG FIX: Fixed an out of place reference "information" comment for identified "Multiple Languages" posts. 
* 🛠️ BUG FIX: ~~Fixed a bug where false matches would popup for the re-post checker routine of cross-posting.~~ (Thanks u/ScanianMoose)
* 🛠️ BUG FIX: Fixed a situation where the notifications language routine would write the same language multiple times in a subscription message to the database if the requester used different names for the same language (anti-duplicate code for *sending* already existed). 
* 🛠️ BUG FIX: Added an error exception for processing regional YouTube videos that are not available at the bot's location. 
* 🛠️ BUG FIX: Quick fix for verification requests that *don't* have notes.
* 🛠️ BUG FIX: ~~Further refinement for the duplicate check when crossposting text-only posts.~~
* 🛠️ BUG FIX: Fixed a bug in the Japanese 四字熟語 *yojijukugo* routine. 
* 🛠️ BUG FIX: ~~Added stronger validation for the r/translate detector function.~~ 
* 🛠️ BUG FIX: ~~Added a means to gracefully handle situations where the original post that was crossposted was deleted (this prevents the bot from editing its earlier comment).~~ 

###### Wenyuan 2.2 (2017-05-20)
* 🛠️ BUG FIX: Emergency update to the latest version of PRAW (v4.5.1), as some change on Reddit's backend stopped Wenyuan written in PRAW3 from connecting to Reddit.

##### Ziwen 1.4 "The Maintenance Update" (2017-05-18)
* 🚀 FEATURE: Emergency update to the latest version of PRAW (v4.5.1), as some change on Reddit's backend stopped Ziwen, which was written in PRAW3, from connecting to Reddit. 
* 🚀 FEATURE: The use of PRAW4 has also resulted in a substantial speed boost. 
* ✨ ADDITION: Added ability to unsubscribe from specific language notifications (previously it was all or nothing).
* ✨ ADDITION: Added ability to subscribe to 'Meta' and 'Community' posts. 
* ✨ ADDITION: Ziwen will now reply directly to notification messages instead of sending an entirely new message. 
* ✨ ADDITION: ~~Added function so OPs of cross-posts can now comment `!delete` to remove their cross-post from r/translator.~~
* ✨ ADDITION: ~~Ziwen will now edit its first reply comment to a cross-post request if it received a `!translated` command.~~ 
* ✨ ADDITION: ~~Added a more robust function to prevent double-posting of cross-posts. Ziwen will check against previous submitted text as well as links.~~
* ✨ ADDITION: Posts removed by Ziwen during post filtering will have a custom comment that will help OPs resubmit their translation request, properly formatted, with just one click. 
* ✨ ADDITION: ~~Ziwen will now include the last two errors logged when pinged by a moderator for a status update.~~ 
* 🔄 CHANGE: Simple fix to improve matches for r/translator `!search` commands.
* 🔄 CHANGE: ~~Fix to ensure r/languagelearning `!search` results don't exceed 10K characters.~~ 
* 🔄 CHANGE: Moderators check is now retrieved dynamically from Reddit.
* 🔄 CHANGE: ~~Wikipedia summaries for reference commands now consist of the first 3 sentences (previously first 500 characters)~~
* 🔄 CHANGE: ~~Ziwen posts gets the posts from the last three minutes instead of the last one due to Reddit's slowness.~~ 
* 🔄 CHANGE: The link in most messages and comments has been changed to use Reddit permalinks instead of redd.it short-form URLs. This is better for mobile compatibility. 
* 🔄 CHANGE: The romanization of Japanese *kana* has been changed to use inline italics text instead, as our furigana format is dependent on CSS formatting and is not readable on mobile. 
* 🔄 CHANGE: Ziwen will now write its runtime errors to a text file as a log. 
* 🔄 CHANGE: Ziwen can now account for an extra space after the colon in `identify` commands. (this often happens on mobile) 
* 🛠️ BUG FIX: Bug fix for marking non-ISO 639-1 language posts as translated. 
* 🛠️ BUG FIX: Bug fix for handling incorrectly formatted notification subscription messages, or messages that contain non-existent languages. 
* 🛠️ BUG FIX: Bug fix for extra punctuation characters being part of the language match in the cross-posting command. 
* 🛠️ BUG FIX: Bug fix when Ziwen would try to look up commands quoted in `!search` results. 
* 🛠️ BUG FIX: Bug fix for Wiktionary links, which were not included for JapanTools data lookups. 
* 🛠️ BUG FIX: ~~Bug fix for cross-posting titles which were almost at 300 characters (Reddit's maximum).~~ (thanks to u/donbarich)
* 🛠️ BUG FIX: ~~Bug fix for some ISO 639-3 languages' Wikipedia summaries not showing up in the reference output.~~ 
* 🛠️ BUG FIX: Bug fix for people getting paged twice. 
* 🛠️ BUG FIX: Bug fix for Ziwen editing the cross-post comment more than once to indicate it's been translated. 
* 🛠️ BUG FIX: Bug fix for notifications when the user has deleted their account. 
* 🛠️ BUG FIX: Bug fix for marking a post without any flair as translated and various QOL fixes. 

###### Wenyuan 2.1 (2017-05-17)
* ✨ ADDITION: Non-supported languages are now integrated into the overall languages chart. Statistics wiki pages for them will also be generated as new requests come in.
* ✨ ADDITION: Wenyuan now uses Ziwen's language reference function to dynamically retrieve population and language family data for non-supported languages.

##### Ziwen 1.3 "The Cross-posting Update" (2017-04-25)
* 🚀 FEATURE: ~~[New cross-posting function](https://www.reddit.com/r/translator/comments/6b74rw/meta_easily_crosspost_translation_requests_from/): Ziwen can cross-post requests from selected subreddits to r/translator.~~ 
* ✨ ADDITION: Lookups for Chinese and Japanese *sentences* are now supported - Ziwen will automatically segment sentences and return word data based on that segmentation.
* ✨ ADDITION: Japanese character lookup now supports individual hiragana particles (e.g. `は`, `え`, etc)
* 🔄 CHANGE: Better formatting of Wiktionary lookup results. 
* 🔄 CHANGE: ~~The default "Unknown" identification boilerplate comment has been moved to Ziwen from AutoModerator.~~ 
* 🔄 CHANGE: Turned *off* the link between the paging function and the `!doublecheck` command. 
* 🛠️ BUG FIX: Bug fix for Arabic reference information (bot was referencing the wrong ISO 639-3 code). 

##### Ziwen 1.2 "The Statistics Update" (2017-04-05)
* 🚀 FEATURE: Ziwen now incorporates language tags into *Translated* and *Needs Review* posts for better statistics recording by Wenyuan. 
* ✨ ADDITION: Ziwen now uses fuzzy matching with ~~[Fuzzywuzzy](https://pypi.python.org/pypi/fuzzywuzzy)~~ to better account for misspelling of language names in titles (e.g. "Japanase" will be correctly identified as "Japanese," and so on.)
* ✨ ADDITION: Better integration with the language tags (e.g. "[ZH]") for CJK lookup in translated posts.
* 🔄 CHANGE: Implemented a rewritten Chinese calligraphy search function that's much more consistent and reliable. 
* 🔄 CHANGE: ~~More consistent retrieval of Wiktionary lookup for non-CJK languages.~~
* 🔄 CHANGE: Commands are now more "stackable;" that is, one can more consistently use a few of them at the same time. 
* 🛠️ BUG FIX: Bug fixes to better integrate with Wenyuan's statistics-gathering functions. 
* 🛠️ BUG FIX: Bug fix for Korean lookup with no results. 

###### Wenyuan 2.0 (2017-04-01)
* 🔄 CHANGE: First complete rewrite of the bot. All statistics calculations are done client-side rather than relying on Reddit's search function. As a result, Wenyuan no longer uses data from posts' titles to count statistics. Instead, it relies on data encoded in flairs. 
* 🔄 CHANGE: Integration with Ziwen's new *translated* flair language tags for greater accuracy and speed.

###### Wenyuan 1.0 (2017-03-14)
* 🔄 CHANGE: `!wronglanguage` changed to `!identify` after a [public request for feedback](https://www.reddit.com/r/translator/comments/61m09r/meta_proposal_to_change_the_wronglanguage_command/).
* 🛠️ BUG FIX: Bug fixes.

##### Ziwen 1.1 "The Notifications Update" (2017-02-21)
* 🚀 FEATURE: [Added support for receiving notifications](https://www.reddit.com/r/translator/comments/5vhc4s/meta_introducing_language_notifications_on/) from Ziwen about specific language posts. 
* 🔄 CHANGE: ~~Page lists have been moved to a single CSV file instead of multiple text files.~~ 

##### Ziwen 1.0 "The Reference Update" (2017-02-09)
* 🚀 FEATURE: [Full release of Ziwen](https://www.reddit.com/r/translator/comments/5mbj29/meta_new_bot_functions_hanzikanji_lookup_language/) with language reference lookup, search functionality, and Chinese/Japanese character/word lookup.
* ✨ ADDITION: [Wiktionary lookup and title processing added](https://www.reddit.com/r/translator/comments/5ukxfg/meta_bot_upgrades_lookup_function_for_all/).

###### Wenyuan 0.9 (2017-01-11)
* 🚀 FEATURE: Added function to post a weekly post summing up all remaining unidentified "Unknown" posts. (Note: now part of Wenju)

##### Ziwen 0.8 (2016-12-20)
* 🔄 CHANGE: Addition of the mod-accessible ~~`!note`~~ and `!set` commands.

##### Ziwen 0.6 (2016-11-18)
* 🚀 FEATURE: [Initial release with paging functions](https://www.reddit.com/r/translator/comments/5dl40d/meta_new_page_function_for_rtranslator_and_more/) for languages.

###### Wenyuan 0.7 (2016-11-13)
* ✨ ADDITION: Added language family data.  
* ✨ ADDITION: Wenyuan can now write statistics data to the subreddit wiki.
* ✨ ADDITION: Introduction of the RI calculation. 
* 🔄 CHANGE: Bot rewritten to allow for targeted month output (for example, to retrieve data for July 2016 only).
* 🔄 CHANGE: ~~Added [Bojie](https://en.wikipedia.org/wiki/Cai_Yong) subroutine to retrieve data from months prior to the subreddit redesign.~~

###### [Wenyuan 0.6](https://www.reddit.com/r/translator/comments/5ahwgr/meta_rtranslator_language_statistics_october_2016/) (2016-10-24)
* 🚀 FEATURE:  [Initial version written by u/doug89](https://www.reddit.com/r/RequestABot/comments/591mch/requesting_a_bot_that_can_tabulate_number_of/) with terminal-only output. The bot could only search for data a month prior to its run time (later termed the [Pingzi](https://en.wikipedia.org/wiki/Zhang_Heng) subroutine)