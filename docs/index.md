# translator-BOT Documentation

This documentation covers the routines, data files, deployment notes, and
maintenance workflows for translator-BOT Reborn. The repository primarily
serves [r/translator](https://www.reddit.com/r/translator/), with related
routines for [r/language_exchange](https://www.reddit.com/r/language_exchange/)
and Chinese-language reference lookup.

## Start Here

| Goal | Page |
|------|------|
| Understand the repository shape and runtime flow. | [Architecture](./architecture.md) |
| Add commands, scheduled tasks, fields, docs, or tests. | [Development](./development.md) |
| Review Reddit command syntax and behavior. | [Commands (Ziwen, Reddit)](./commands.md) |
| Review Discord command syntax and permissions. | [Commands (Zhongsheng, Discord)](./commands_discord.md) |

## Routines

| Routine | Scope | Primary entry point |
|---------|-------|---------------------|
| Ziwen | r/translator Reddit commands, post processing, notifications, verification, and moderation actions. | `main_ziwen.py` |
| Wenju | Scheduled maintenance tasks for shared data, reports, and databases. | `main_wenju.py` |
| Zhongsheng | Discord commands for community oversight and operational checks. | `main_zhongsheng.py` |
| Wenyuan | Statistics, data analysis, and recurring community reports. | `main_wenyuan.py` |
| Hermes | Language-exchange matching for r/language_exchange. | `main_hermes.py` |
| Chinese Reference | Chinese character and word lookup for Chinese-language subreddits. | `main_chinese_reference.py` |

## Language Codes and Syntax

A **language tag** is the user-facing language identifier translator-BOT accepts
in post titles, commands, and lookups. It can be a language name (`Japanese`),
an ISO language code (`fi`, `yue`), or a more specific language-script or
language-region form (`unknown-Hani`, `pt-BR`).

The routines use three international ISO standards that are components of
[IETF language tags](https://en.wikipedia.org/wiki/IETF_language_tag):

* [ISO 639-1/3](https://en.wikipedia.org/wiki/ISO_639), two- or three-letter
  codes for languages (`ar`, `ja`, etc.);
* [ISO 15924](https://en.wikipedia.org/wiki/ISO_15924#List_of_codes),
  four-letter codes for scripts (`Cyrl`, `Latn`, etc.);
* [ISO 3166](https://en.wikipedia.org/wiki/ISO_3166), two- or three-letter
  codes for countries (`GB`, `MX`, etc.).

Ziwen broadly supports ISO 639-1/3 language codes. More specific tags usually
combine a language code with a country code, such as `fr-CA`. Script tags are
mainly used for Unknown posts, such as `unknown-Hani`. See
[Language Processing](./language_processing.md) for parser behavior, supported
aliases, and normalization details.

## Documentation Directory

### Core Architecture and Operations

| Page | Purpose |
|------|---------|
| [Architecture](./architecture.md) | Repository structure, entry points, and routine execution flow. |
| [Technical Information](./technical.md) | Runtime details that do not fit a single routine page. |
| [AI Usage](./ai_usage.md) | External AI API call sites and the data passed to them. |
| [Development](./development.md) | How to add commands, tasks, data fields, docs, and tests. |
| [Data Files](./data_files.md) | Shared `_data` files, generated state, and database outputs. |
| [Models](./models.md) | Shared model objects and their responsibilities. |

### r/translator Features

| Page | Purpose |
|------|---------|
| [Commands (Ziwen, Reddit)](./commands.md) | Reddit command syntax, behavior, and restrictions. |
| [Commands (Zhongsheng, Discord)](./commands_discord.md) | Discord command syntax, roles, and operational usage. |
| [Language Processing](./language_processing.md) | Language tags, aliases, normalization, and parser behavior. |
| [Lookup Functions](./lookup.md) | Lookup command behavior and supported reference sources. |
| [Title Processing](./title_processing.md) | Request title parsing and flair-related behavior. |
| [Verification](./verification.md) | Translator verification workflow and related data. |
| [Points](./points.md) | Points calculation, multipliers, and stored outputs. |

### Other Routine Guides

| Page | Purpose |
|------|---------|
| [Wenju](./wenju.md) | Scheduled maintenance task catalog and behavior. |
| [Wenyuan](./wenyuan.md) | Statistics and reporting workflows. |
| [Chinese Reference](./chinese_reference.md) | Chinese lookup bot behavior and maintenance notes. |
| [Hermes](./hermes.md) | r/language_exchange matching bot behavior. |

### Reference

| Page | Purpose |
|------|---------|
| [Logging Guidelines](./logging_guidelines.pdf) | Logging conventions and expectations. |
| [Version History](./version_history.md) | Project release notes and change history. |
| [Deprecated](./deprecated.md) | Deprecated behavior and historical notes. |
