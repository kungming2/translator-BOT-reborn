# translator-BOT Documentation

## Introduction

This repository encompasses several routines that primarily serve **[r/translator](https://www.reddit.com/r/translator/)**. 

#### r/translator Routines

* **Ziwén (子文)** is the component that handles real-time commands for r/translator. Under the username [u/translator-BOT](https://www.reddit.com/user/translator-BOT/), it serves an essential role in community management by posting comments, sending messages, and moderating content. Additionally, it provides users with valuable reference information and notifications about requests for languages they might be interested in.
* **Wénjǔ (文舉)** is the component that handles general maintenance functions for the databases these routines use.
* **Zhòngshēng (仲升)** is the component that interfaces with Discord and responds to commands on our community oversight server. This component primarily surfaces functions of Ziwen for troubleshooting and casual queries.
* **Wényuǎn (文遠)** is the component that handles overall statistics and data analysis.

#### Other Routines

* **Hermes (Ἑρμῆς)** is a language-matching bot that pairs users together based on the languages they know and seek to learn. It serves [r/language_exchange](https://www.reddit.com/r/language_exchange/) and posts under the username [u/language_exchangeBOT](https://www.reddit.com/user/language_exchangeBOT).
* **Chinese Reference** is a streamlined lookup bot for Chinese-language subreddits that provides users with character and word lookup. It posts under the username [u/ChineseLanguageMods](https://www.reddit.com/user/ChineseLanguageMods).

## Language Codes and Syntax

All routines use three international ISO standards for language codes and names, all are which are components of [IETF language tags](https://en.wikipedia.org/wiki/IETF_language_tag):

* [ISO 639-1/3](https://en.wikipedia.org/wiki/ISO_639), two or three-letter codes for languages (`ar`, `ja`, etc.)
* [ISO 15924](https://en.wikipedia.org/wiki/ISO_15924#List_of_codes), four-letter codes for scripts (`Cyrl`, `Latn`, etc.)
* [ISO 3166](https://en.wikipedia.org/wiki/ISO_3166), two or three-letter codes for countries (`GB`, `MX`, etc.)

ISO 639-1/3 codes are universally supported by Ziwen, while for more specific use cases, ISO 3166 codes require a language to be prefixed with a `-` (e.g. `fr-CA`), and ISO 15924 is primarily used on 'Unknown' posts (e.g. `unknown-Hani`).

More information on language processing can be found at the page of the same name below.

## Documentation Directory

**Primary r/translator Processes**

* [Commands (Ziwen, Reddit)](./commands.md)
* [Commands (Zhongsheng, Discord)](./commands_discord.md)
* [Data Files](./data_files.md)
* [Language Processing](./language_processing.md)
* [Lookup Functions](./lookup.md)
* [Models](./models.md)
* [Points](./points.md)
* [Technical Information](./technical.md)
* [Title Processing](./title_processing.md)
* [Verification](./verification.md)
* [Wenju](./wenju.md)
* [Wenyuan](./wenyuan.md)

**Other Routines**
* [Hermes](./hermes.md)

**Miscellaneous**

* [Deprecated](./deprecated.md)
* [Version History](./version_history.md)