# Commands (Reddit)

[← Back to Home](./index.md)

## Introduction

This document details the primary commands that work on r/translator and serve to help requesters and translators keep the community organized.

#### Command Arguments for Languages

Several commands detailed below may either require or accept a language, added on to the command after a colon `:`. Language names with more than one word must be wrapped in double quotes (e.g. `"American Sign Language`), and multiple languages can be chained with a plus sign `+`. Here are some examples of valid input:

#### Specific !identify Functions

Adding a second exclamation mark `!` after a command indicates to the bot that the user is requesting a *specific* ISO 639-3 or ISO 15924 codes. Note that Advanced `!identify` will *not* work with language names, but is meant to be used specifically with these *codes*. Trying to use an Advanced `!identify` command with a language name will result in an error.

Specific identifcation is only meant for single-language posts.

```
!identify:any!                  # Changes the post to Anyin. 
!identify:zmi!                  # Changes the post to Negeri Sembilan Malay. 
!identify:Cyrl!                  # Changes the Unknown post to Cyrillic (Script).
!identify:Latn!                  # Changes the Unknown post to Latin (Script). 
```

**Plain ISO 639-1/3 Codes**

```
!page:ar                                                   # Arabic (ISO 639-1)
!identify:yue                                              # Cantonese (ISO 639-3)
```

**ISO 639-1/3 Codes or Language Names with Country**

Either a country/region name or country code will work.

```
!identify:de-AO                                             # German {Austria}
!identify:fr-CAN                                            # French {Canada}
!id:pt-brazil                                               # Portuguese {Brazil}
!id:cantonese-HK                                            # Cantonese {Hong Kong}
```

**Language Names (between quotes if more than one word)**
```
!identify:dutch                                             # Dutch
!page:manchu                                                # Manchu
!id:"american sign language"                                # American Sign Language
```

**Scripts (for 'Unknown' posts)**
```
!identify:Latn!                                            # Latin (Script)
!id:Sidd!                                                  # Siddham (Script)
!identify:unknown-dsrt                                     # Deseret (Script)
```

## State Commands

The default state of a single-language post on r/translator is *untranslated*. The commands below can change the state of the post for ease of translators' navigation. 

Posts with different states will have a "tag" in their flair with the language code in brackets (e.g. `[MS]` for a Malay post). A couple of rare tags are `[?]` for translated "Unknown" posts, and `[--]` for translated posts without any flair text. This implementation was first suggested by u/nomfood.

*State Commands Note*: A language (or languages) can be included in a state command, but only in a defined multiple post where there are multiple specifically requested languages. In those cases, a command like `!translated:fi` would mark the Finnish component of the request as translated. However, the vast majority of requests do not require or need this syntax.

### Command: *!translated*

#### Function

A **!translated** command from a user will mark a post as translated. The user may be the post's original author or someone else.

* If the command is from someone other than the OP, Ziwen will message the OP letting them know that their post is translated, and encourage them to thank their translator.
* That message also includes a sentence encouraging the OP to keep their post up and not delete it.

#### Notes

* The message will not be sent if the OP has already left a comment thanking translators (including in advance).
* Notifications will not be sent for `!identify` if `!translated` is in the same comment.

### Command: *!doublecheck*

#### Function

A **!doublecheck** command from a user flags the request as "Needs Review." For statistical purposes this state counts towards the translated percentage for a language. 

#### Notes

* This feature was first suggested by u/r1243.
* Notifications will not be sent for `!identify` if `!doublecheck` is in the same comment. 

### Command: *!claim*

#### Function

A **!claim** command from a user will mark a post as "In Progress", serving as a courtesy notice to others that the user intends on completing the translation for that post. 

Only one user can claim a post at any given time. A user who tries to claim an already claimed post will receive a comment from Ziwen telling them that they can't do that. In a defined multiple post, a user can claim a specific language by adding the language code or name (e.g. `!claim:sw`).

#### Notes

* If the post has not been marked as *translated* or *needs review* within eight hours, the flair will be reset to the language's original language category, the state will be set to "untranslated", and the bot's claimed comment will be removed. 
* The internal state code is `inprogress`.

### Command: *!missing*

#### Function

A **!missing** command from a user will mark a post as missing assets that need to be translated. Perhaps the image link doesn't work, or the OP forgot to include the text they want translated. 

* Ziwen will message the OP letting them know their post is missing content to be translated and urge them to add content or delete and re-submit the post.
* The OP is also notified that they can use the special `!reset` command (only usable by OPs and mods, see below) to restore the post's state to "untranslated."

## Post Reference Commands

These commands are used to help organize the subreddit and to provide supplementary information to translators and the OP. All reference commands *must* accept language codes or names as command arguments. 

### Command: *!id/!identify:[language]*


OPs often categorize their posts incorrectly, or they don't know what language their post is and submitted it as "Unknown." An **!identify** command changes the category of a post to the specified language in `[ ]`. The flair text will also be changed to "[language name] (Identified)." If the language name is more than one word, double quotation marks `"` should be used to mark the language name.

This command also has a shorter synonym: `!id`. Both function exactly the same way, though Ziwen will always record its use internally as `!identify` in statistics.

`!identify` will also work with four-letter [ISO 15924](https://en.wikipedia.org/wiki/ISO_15924#List_of_codes) codes for "Unknown" posts, but if said code is also a language name (or is close to the spelling of one), the language itself will have priority for post categorization. For example, `!identify:Thai` will categorize a post as the [Thai language](https://en.wikipedia.org/wiki/Thai_language), *not* as "[Thai (Script)](https://en.wikipedia.org/wiki/Thai_alphabet)". On the other hand, `!identify:Sidd` will categorize a post as "[Siddham (Script)](https://en.wikipedia.org/wiki/Siddha%E1%B9%83_script)" since there are no languages called "Sidd."

#### Defined Multiple !identify

If a post should be for more than one defined language, stringing language names or codes with `+` will change it to a *defined multiple* post. 

    !identify:ru+it+uzbek            # Changes the post flair to Multiple Languages [IT, RU, UZ]


#### Advanced !identify Functions

Adding a second exclamation mark `!` after the `!identify` command unlocks a couple of advanced options for users to work with ISO 639-3 and ISO 15924 codes. Note that Advanced `!identify` will *not* work with language names. It's meant to be used specifically with these *codes*. Trying to use an Advanced `!identify` command with a language name will result in an error reply.


##### Force ISO 639-3 Language Identification

Due to the sheer size of the ISO 639-3 list (it contains over 7800+ languages) it's possible, on very rare occasions, for false positives to happen. It's also possible that the three-letter code is already in use by another more common language - for example, identifying the word "any" will usually result in "Multiple Languages" and not the [Anyin language](https://en.wikipedia.org/wiki/Anyin_language) (ISO 639-3 code: `any`). If that happens, users can force Ziwen to assign a specific ISO 639-3 code by adding a second `!` after the three-letter code. 

    !identify:ocu!                  # Changes the post to Atzingo Matlatzinca. 
    !identify:zmi!                  # Changes the post to Negeri Sembilan Malay. 

##### Force ISO 15924 Script Identification

Ziwen can identify specific scripts with their four-letter [ISO 15924](https://en.wikipedia.org/wiki/ISO_15924#List_of_codes) standard for written scripts on posts. Identifying as a script preserves a post's 'Unknown' status. 

    !identify:Cyrl!                  # Changes the Unknown post to Cyrillic (Script).
    !identify:Latn!                  # Changes the Unknown post to Latin (Script). 

#### Notes

* If the requested phrase or code isn't supported, Ziwen will not process it and will leave an error comment noting that.
* Notifications will be sent out to users in the notifications database if the `!identify` comment *does not* also contain a `!translated` or `!doublecheck` state command.
* This command used to be `!wronglanguage` but was changed in March 2017 to be more accessible to people. This old command was deprecated in August 2018 and replaced with `!id`. 
* The specific language targeting for this command was first suggested by u/ScanianMoose. Before their suggestion, `!wronglanguage` just reset a post to "Unknown."

### Command: *!page:[language]*

#### Function

A **!page:[ ]** command from a user will page other subreddit users who know the language(s) specified. If there are more than three users listed for a language, Ziwen will message three at random. This is best used for unsure identifications and to let people confirm a tentative language identification.

#### Limitations

* Use of this function is restricted to users with accounts fourteen days and older in order to prevent abuse.
* Multiple `!page` commands *can* be included in a single comment to page people from many different languages.
* If there are no users listed for that language in the notifications database, Ziwen will reply to the command with a comment informing the user.

#### Notes

* The usernames that are paged are taken from the notifications database. Paging used to rely on a separate database containing usernames that were manually populated by moderators but that database is no longer in use. As of December 2017, `!page` uses the same notifications database.

### Command: *!search:[term]*

The **!search:[term]** command looks on r/translator to see if anyone has posted something with the search term before. This is most useful for things like 無政府, 吉庆有余, and a whole host of commonly requested phrases that keep showing up on r/translator. The `!search` function  also searches *comments* on r/translator as a regular Reddit search often can only return text in the title or the post itself, but not comments.

This function also serves as a simple way to find thematically similar posts that contain the same content.

#### Examples

    !search:吉慶有餘
    !search:为人民服务
    !search:今古有神奉志士
    !search:علي

#### Notes

* This function is also integrated with the [frequently-requested translations page](www.reddit.com/r/translator/wiki/frequently-requested) and can return information saved on that page. 
* If there are no results for the search term, Ziwen will leave a comment letting the redditor know.
* Ziwen will *not* automatically mark a thread as translated even if the quoted comment contains `!translated`. It'll be up to the person who called the `!search` function to check if the displayed results contain accurate translations.

#### Function

## Moderator/OP Commands

OPs (users who made a request) can also use the following commands:

* `!long` manually toggles a post's "Long" status and deletes the advisory comment.
* `!reset` resets a post to a state as if it had just been processed. This is primarily used in cases where a post was prematurely marked as translated.

Moderators can use the above commands as well as the following:

* `!verify` sets the flair for a user who submitted a verification request.
* `!nuke` bans a user permanently and removes all their posts and comments. This is generally only used for extremely serious trolls.