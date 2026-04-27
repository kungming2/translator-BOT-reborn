# Deprecated Features

[← Back to Home](./index.md)

## Introduction

This document outlines some of the routines and functions that were formerly part of the codebase but have been deprecated or sunsetted for various reasons.

## Former Routines

* **Zifang** - a parallel routine that handled Wikipedia lookups and duplicate detection. All of its functions have been fully integrated into Ziwen.
* **Ziwen Streamer** - a routine that streamed submissions from the entire site to cross-post posts with `!translate` or `!translator`. With the introduction of Reddit's native cross-posting ability, the need for this function was made obsolete.
* **Ziwen Hourly** - a routine that updated the sidebar on Old Reddit with information about the last twenty-four hours' statistics, posted the weekly 'Unknown' round-up, and also backed up its files. Its routines were moved into [Wenyuan](./wenyuan.md) and then [Wenju](./wenju.md) today. 

## Former Functions

#### Former Commands

* **!restore** - allowed translators to retrieve information about a post from [Pushshift](https://search-tool.pushshift.io/#_) if the OP had deleted it. Pushshift became a [mod-only tool without an API](https://www.reddit.com/r/pushshift/comments/14ei799/pushshift_live_again_and_how_moderators_can/) in June 2023 and this command became obsolete. 
* **!note** - allowed moderators to save a post and its information to a [central wikipage](www.reddit.com/r/translator/wiki/saved). As the bot's capabilities expanded, the need for a manually updated central wikipage was obviated as there was much more information available in local databases, and the bot could update the page automatically.
* **!reference** - gave users reference information about a language, somewhat like the `/lang` [command of Zhongsheng](./commands_discord.md). It was rarely used on the subreddit and sunsetted.  
* **!rotate** - [allowed users](https://www.reddit.com/r/translator/comments/au2b57/meta_image_rotation_available_via_rotate_courtesy/) to rotate an image a specified number of degrees, or flip it horizontally or vertically. Written by u/AdvancedAverage and running separately on the [u/imagerotationbot](https://www.reddit.com/user/imagerotationbot/) account, it ceased to work in April 2019. Version 2.1's **!transform** command does the same thing natively. 
* **!translate/!translator** - part of Ziwen Streamer, it allowed people to cross-post a post from anywhere on Reddit to r/translator. It did not itself run on r/translator.
* **!delete** - part of Ziwen Streamer, it allowed OPs of a cross-post or the mods to delete a cross-post on r/translator. 
* **!wronglanguage** - was renamed to **!identify/!id**. Its functionality stayed the same.

#### Former Functionality

* **"App" posts** - "multiple" posts could have this special categorization if they were for a software program or application. The community's rules have since been made stricter about for-profit requests, and this became almost never used. Sunsetting it also freed up the code `app` to represent its [correct language](https://en.wikipedia.org/wiki/Apma_language) under ISO 639-3.
* **r/translate corrector** - run under Ziwen Streamer, it corrected mentions of [r/translate](https://www.reddit.com/r/translate/) (a defunct/ghost subreddit) by directing people to r/translator. The subreddit r/translate is now set up as a redirect to r/translator and this was no longer needed.
