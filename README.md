# translator-BOT Reborn

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![python](https://img.shields.io/badge/Python-3.11-3776AB.svg?style=flat&logo=python&logoColor=white)](https://www.python.org)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![Checked with mypy](http://www.mypy-lang.org/static/mypy_badge.svg)](http://mypy-lang.org/)


**translator-BOT** is a set of automated moderation, maintenance, lookup, notification, and reporting routines for [r/translator](https://www.reddit.com/r/translator/), the largest translation community on Reddit.

The project was [first deployed](https://github.com/kungming2/translator-BOT) in late 2016 and rewritten in 2025 to improve readability, maintainability, and extensibility. Most r/translator-facing actions post comments or send messages under [u/translator-BOT](https://www.reddit.com/user/translator-bot/).

## Routines

The main r/translator routines share the same repository and data model:

| Routine Name | Functions                                                                             |
|--------------|---------------------------------------------------------------------------------------|
| Ziwen        | Organizes the community through Reddit bot commands and sends notifications.          |
| Wenju        | Runs regular maintenance and summary functions.                                       |
| Wenyuan      | Gathers statistics and makes monthly posts on the state of the community.             |
| Zhongsheng   | Responds to commands on Discord; mostly for inquiry into the state of bot operations. |

The repository also contains related routines for [r/language_exchange](https://www.reddit.com/r/language_exchange/) and Chinese-language reference lookups. See the documentation index for the full list.

## Documentation

Start with the [documentation index](docs/index.md) for the full table of contents. Common entry points are:

| Page | Purpose |
|------|---------|
| [Architecture](docs/architecture.md) | Understand the repository structure and major components. |
| [Development](docs/development.md) | Add commands, tasks, data fields, docs, and tests. |
| [Commands](docs/commands.md) | Review Ziwen Reddit commands. |
| [Commands (Discord)](docs/commands_discord.md) | Review Zhongsheng Discord commands. |

## Development Quick Start

The project requires Python 3.11 or newer. From the repository root:

```powershell
python -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements.txt
python -m pytest testing/unit -q
```

Production setup requires runtime `_data` files and service configuration described in [Setup](docs/setup.md).

## License

translator-BOT is available under the [MIT License](LICENSE.md).
