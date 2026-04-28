# Technical Information

[← Back to Home](./index.md)

* All routines are currently run on a [Raspberry Pi 4](https://www.raspberrypi.com/products/raspberry-pi-4-model-b/) running [Raspberry Pi OS](https://www.raspberrypi.com/software/). Ziwen runs through the shared scheduler every three minutes so it can check for new posts, messages, and commands.
  * In the past, routines have also been run from a [Raspberry Pi 3B+](https://www.raspberrypi.com/products/raspberry-pi-3-model-b-plus/) and [AWS](https://aws.amazon.com/).
* Ziwen's databases and required files are routinely backed up.
* If Ziwen will be down for any reason, there will be a stickied announcement on r/translator.

## Runtime Layout

The main entry points are:

* `main_ziwen.py`: runs the regular r/translator cycle for posts, edited comments, progress tracking, comment commands, messages, and verification requests.
* `main_wenju.py`: dispatches scheduled maintenance tasks by schedule name.
* `main_wenyuan.py`: provides an interactive statistics and reporting menu.
* `main_zhongsheng.py`: runs the Discord bot and registers slash commands from `/zhongsheng`.
* `main_hermes.py`: runs the standalone r/language_exchange matching bot.
* `main_chinese_reference.py`: runs the Chinese Reference lookup bot for Chinese-language subreddits.

The scheduler lives in `scheduler/runner.py`. It launches Ziwen, Wenju, Hermes, and Chinese Reference as subprocesses and uses `scheduler/lock.py` to hold file locks so two copies of the same job do not run at once. Zhongsheng is long-running and managed separately as a systemd service.

Configuration and path constants are centralized in `config.py`. Runtime data is stored under `_data`, with settings in `_data/settings`, SQLite databases in `_data/databases`, logs in `_data/logs`, reports in `_data/reports`, and templates in `_data/templates`.

## Code Organization

* `models/` contains the primary data objects (`Lingvo`, `Titolo`, `Komando`, `Instruo`, `Ajo`, `Kunulo`, and `Diskuto`).
* `processes/` contains top-level Ziwen cycle work for posts, comments, messages, and Wenyuan statistics.
* `ziwen_commands/` contains one handler module per Reddit command.
* `ziwen_lookup/` contains CJK, Wiktionary, Wikipedia, OpenStreetMap, matching, and lookup cache helpers.
* `reddit/` wraps Reddit login, sending, notifications, verification, messaging, and wiki operations.
* `monitoring/` handles edit tracking, duplicate detection, points, closeout checks, and usage statistics.
* `integrations/` contains external services such as Discord alerts, AI calls, image handling, and search.
* `wenju/`, `wenyuan/`, `zhongsheng/`, and `hermes/` contain routine-specific functionality.

## Naming Conventions

The r/translator bot routines are named after the courtesy names of prominent [Han dynasty](https://en.wikipedia.org/wiki/Han_dynasty) people:

* [Wenju](https://en.wikipedia.org/wiki/Kong_Rong) (文舉)
* [Wenyuan](https://en.wikipedia.org/wiki/Zu_Chongzhi) (文遠)
* [Zhongsheng](https://en.wikipedia.org/wiki/Ban_Chao) (仲升)
* [Ziwen](https://en.wikipedia.org/wiki/Zhang_Qian) (子文)
* [Zifang](https://en.wikipedia.org/wiki/Zhang_Liang_(Western_Han)) (子房, [deprecated](./deprecated.md))

Generally, statistics-related routines are named with an initial `w`, and command-related routines are named with an initial `z`.

Major classes in the routines are named after [Esperanto](https://en.wikipedia.org/wiki/Esperanto) [nouns](https://en.wikipedia.org/wiki/Esperanto#Grammar) that correspond roughly to their purpose.
