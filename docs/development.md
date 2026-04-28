# Development

[← Back to Home](./index.md)

## General Workflow

Prefer existing registries and package boundaries. Most features are discovered automatically from modules, but parser settings and docs often still need explicit updates.

For code changes, run the smallest relevant test first, then broader checks if the change touches shared behavior. Useful commands include:

```bash
python -m pytest testing/unit -q
python -m pytest testing/integrations -q
python -m py_compile main_ziwen.py main_wenju.py main_zhongsheng.py
```

## Adding a Ziwen Command

Ziwen Reddit commands live in `ziwen_commands/`.

1. Add a module named for the command, such as `ziwen_commands/example.py`.
2. Define `handle(comment, instruo, komando, ajo) -> None`.
3. Add the user-facing trigger to `_data/settings/settings.yaml`:
   * `commands_with_args` for required `!command:arg` commands;
   * `commands_optional_args` for commands that can be bare or accept `:arg`;
   * `commands_no_args` for bare commands;
   * `commands_skip_conversion` if the argument is not a language.
4. Add `command_aliases` if the command has a synonym.
5. Add `command_points` if the command should not use the default point behavior.
6. Update [Commands](./commands.md) or [Lookup Functions](./lookup.md).
7. Add or update tests for parsing in `models/komando.py` or behavior in the command handler.

The command package discovers modules automatically. A module without `handle()` will not be registered.

## Adding a Zhongsheng Command

Zhongsheng Discord commands live in `zhongsheng/`.

1. Add a command module or update an existing one.
2. Import `command` from `zhongsheng`.
3. Decorate the async function with `@command(name, help_text, roles=None)`.
4. Use `roles=["Moderator"]` or another role list for restricted commands.
5. Keep Discord responses under Discord's message limits, or use `send_long_message()`.
6. Update the command guide in `zhongsheng/__init__.py` so that the guide command can return the proper information about the command.
7. Update [Commands (Discord)](./commands_discord.md).

`register_commands()` dynamically imports every Python file in `zhongsheng/`, then registers decorated functions as hybrid slash commands.

## Adding a Wenju Task

Wenju tasks live in `wenju/` and use a decorator registry.

1. Add the function to the appropriate module or create a new module in `wenju/`.
2. Decorate it with `@task(schedule="hourly")`, `daily`, `weekly`, or `monthly`.
3. Keep task failures local where practical; `run_schedule()` catches task exceptions and continues with later tasks.
4. Update [Wenju](./wenju.md) with the task name, schedule, and purpose.
5. Add tests if the task parses data, mutates files, writes database rows, or has nontrivial branching.

Wenju dynamically imports every sibling module before running a schedule, so no central task list needs to be edited.

## Adding a Lingvo or Data Field

Language data is built from `_data/states/language_data.yaml`, `_data/states/utility_lingvo_data.yaml`, and the static datasets in `_data/datasets`.

When adding a new field:

1. Add the field to the source YAML or CSV.
2. Update `models/lingvo.py` if the field should be exposed as an attribute.
3. Update `lang/languages.py` if parsing, normalization, validation, or fallback behavior changes.
4. Update `validate_lingvo_dataset()` expectations if needed.
5. Update [Language Processing](./language_processing.md), [Models](./models.md), or [Data Files](./data_files.md).
6. Add or update tests in `testing/unit/test_languages.py` and any affected title or command tests.

Be careful with alternate names. They affect fuzzy conversion and can change command parsing, title parsing, and notification routing.

## When to Update Docs and Tests

Update docs when a change affects:

* Public Reddit command syntax or behavior;
* Discord command syntax, permissions, or output;
* Setup, service management, credentials, settings, or schedules;
* Data files, database tables, logs, or generated reports;
* Language parsing, title parsing, lookup behavior, points, or verification;
* Adding or removing a routine, task, model field, or integration.

Add tests when a change affects parsing, routing, scoring, database writes, cache behavior, or user-visible command output. For small docs-only edits, tests are not required.
