# Architecture

[← Back to Home](./index.md)

## Overview

translator-BOT is a set of related routines that share configuration, data files, models, Reddit helpers, and lookup logic. Each top-level routine has a `main_*.py` entry point, while most reusable behavior lives in packages below the repository root.

## Entry Points

| Entry point | Routine | Purpose |
|-------------|---------|---------|
| `main_ziwen.py` | Ziwen | Regular r/translator bot cycle for posts, comment commands, messages, edit tracking, progress tracking, and verification. |
| `main_wenju.py` | Wenju | Runs registered maintenance tasks by schedule name. |
| `main_wenyuan.py` | Wenyuan | Interactive statistics and reporting menu. |
| `main_zhongsheng.py` | Zhongsheng | Long-running Discord slash-command bot. |
| `main_hermes.py` | Hermes | Standalone r/language_exchange matching bot. |
| `main_chinese_reference.py` | Chinese Reference | Standalone async Chinese lookup bot for Chinese-language subreddits. |

Of note: `devtools.py` also serves as a menu with interrogative functions for various Ziwen functions for debugging or checking purposes.

## Shared Core

`config.py` defines the `_data` path layout, loads settings, and configures logging. Most routines import path constants from `Paths` and settings from the YAML files in `_data/settings`.

`models/` contains the shared data objects:

* `Ajo`: translation request record;
* `Diskuto`: internal meta/community post record.
* `Instruo`: Reddit comment containing commands;
* `Komando`: parsed command or lookup request;
* `Kunulo`: bot comments already present on a post;
* `Lingvo`: language or language-like category;
* `Titolo`: parsed Reddit post title;

`database.py` centralizes SQLite access. The main runtime databases are documented in [Data Files](./data_files.md).

## Ziwen Flow

`main_ziwen.py` runs one cycle and exits. In order, it processes:

1. New posts through `processes/ziwen posts py`;
2. Edited comments through `monitoring/edit tracker py`;
3. Claim progress through `monitoring/edit tracker py`;
4. Comment commands through `processes/ziwen comments py`;
5. Private messages through `processes/ziwen messages py`;
6. Verification requests through `reddit/verification py`.

Comment command handlers live in `ziwen_commands/`. The package discovers one module per command and dispatches to that module's `handle()` function.

## Wenju Flow

Wenju is a scheduled task runner rather than a single fixed workflow. `main_wenju.py` expects one schedule argument: `hourly`, `daily`, `weekly`, or `monthly`. It validates that argument, then calls `run_schedule()` from `wenju.__init__`.

Tasks are registered with the `@task(schedule="...")` decorator. Before executing a schedule, Wenju dynamically imports every Python module in `wenju/`; those imports trigger decorator registration. This means adding a new task usually only requires adding a decorated function to a module in `wenju/`, not editing a central task list.

When a schedule runs, each registered task is executed independently. A task exception is logged and written to the error log, but later tasks in the same schedule still run. Weekly and monthly schedules send a Discord completion alert listing successful tasks; hourly and daily schedules run silently unless something logs or errors.

## Wenyuan Menu Entries

Wenyuan's interactive menu is defined in `main_wenyuan.py`. It uses a local `CommandRegistry`, not dynamic module discovery. To add a menu option, add a function in the command definitions area and decorate it with `@registry.register(key, description, category)`.

```python
@registry.register("my_command", "Short description shown in the menu", "data")
def my_command() -> None:
    """Run the command."""
    user_input = input("\n  Enter a value: ").strip()
    if not user_input:
        msg.warn("No value specified.")
        return

    # Do the work here.
```

The decorator arguments control:

* `key`: the exact text the operator types at the prompt;
* `description`: the text shown in the Rich menu table;
* `category`: the menu group.

Current category keys are `posts`, `test`, `data`, `admin`, and `system`. Their labels and display order are controlled by `CommandRegistry.categories` and `CommandRegistry.display_menu()`. If a new category is needed, add it to both places; otherwise the command may register but not appear in the rendered menu because `display_menu()` iterates a fixed category order.

Command functions should return `None` and handle their own input validation. Use the existing `msg.warn()`, `msg.fail()`, `msg.info()`, and `msg.good()` helpers for operator feedback, and use `_console.print()` with Rich tables or Markdown when the output is structured. Let unexpected exceptions propagate to `CommandRegistry.execute()`, which reports the error and logs it with `exc_info=True`.

The menu loop calls `registry.display_menu()`, reads one command key, and passes it to `registry.execute()`. The key `x` is reserved for exit, so do not use it for a command. Registered command keys are sorted alphabetically within each category when displayed.

## Supporting Packages

| Package | Responsibility |
|---------|----------------|
| `hermes/` | Hermes matching logic, database manager, and tools. |
| `integrations/` | Discord alerts, AI clients, image handling, and search helpers. |
| `lang/` | Language and country conversion from datasets and state files. |
| `monitoring/` | Points, edit tracking, duplicate detection, request closeout, and usage statistics. |
| `reddit/` | Reddit login, sending, notifications, messaging, wiki updates, verification, and moderation helpers. |
| `title/` | Post title parsing, filtering, flair determination, and AI title correction support. |
| `wenju/` | Scheduled maintenance tasks and task registry. |
| `wenyuan/` | Statistics utilities, monthly wiki updates, challenge posting, and data validation. |
| `zhongsheng/` | Discord command modules and command registry. |
| `ziwen_lookup/` | CJK, Wiktionary, Wikipedia, OpenStreetMap, lookup matching, async helpers, and lookup cache formatting. |

## Scheduling

`scheduler/runner.py` runs Ziwen, Wenju, Hermes, and Chinese Reference as subprocesses under APScheduler. Each job also uses a file lock from `scheduler/lock.py`, so a slow run will not overlap with the next scheduled run of the same job.

Zhongsheng is different: it is a long-running Discord bot and should be managed as its own [systemd](https://en.wikipedia.org/wiki/Systemd) service.
