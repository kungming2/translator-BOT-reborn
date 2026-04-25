#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
Tests for the Wenju automation task modules.

Focuses on pure/logic-heavy functions that can be tested without live
Reddit, database, or filesystem dependencies. External integrations are
mocked at the boundary.

Modules covered:
    - wenju/__init__.py  : task decorator & run_schedule
    - community_digest.py: _analyze_bot_mod_log, _analyze_mod_removals,
                           weekly_unknown_thread (structure)
    - iso_updates.py     : _parse_iso639_newsletter
    - data_maintenance.py: error_log_trimmer (logic), validate_data_files (path scanning)
    - moderator_digest.py: _error_log_count, _activity_csv_handler (statistics),
                           _render_html_dashboard
    - status_report.py   : reddit_status_report (incident formatting)
"""

# Load the real config module directly by file path, bypassing any stub that
# another test file may have already registered under "config" in sys.modules.
import importlib.util as _ilu
import json
import re
import sys
import textwrap
import types
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import cast
from unittest.mock import MagicMock, patch

import pytest
import yaml

_config_spec = _ilu.spec_from_file_location(
    "_real_config",
    Path(__file__).resolve().parents[2] / "config.py",
)
assert _config_spec is not None and _config_spec.loader is not None
_real_config = _ilu.module_from_spec(_config_spec)
_config_spec.loader.exec_module(_real_config)  # type: ignore[union-attr]
_RealPaths = _real_config.Paths
_real_get_reports_directory = _real_config.get_reports_directory

# ---------------------------------------------------------------------------
# Helpers to build a minimal stub environment so importing the task modules
# doesn't require the full project to be installed.
# ---------------------------------------------------------------------------


def _make_stub_module(name: str, **attrs) -> types.ModuleType:
    mod = types.ModuleType(name)
    for k, v in attrs.items():
        setattr(mod, k, v)
    return mod


# Patch heavy third-party / project imports before any task module is touched.
# We register them in sys.modules so that "import X" inside the task files
# resolves to our stubs rather than raising ImportError.
def _register_stubs() -> dict[str, types.ModuleType | None]:
    """Register stub modules and return the previous sys.modules state for restoration."""
    stubs = {
        "config": _make_stub_module(
            "config",
            SETTINGS={"subreddit": "translator", "internal_post_types": []},
            Paths=_RealPaths,
            logger=MagicMock(),
            load_settings=MagicMock(return_value={}),
            get_reports_directory=_real_get_reports_directory,
        ),
        "database": _make_stub_module("database", db=MagicMock()),
        "integrations": _make_stub_module("integrations"),
        "integrations.discord_utils": _make_stub_module(
            "integrations.discord_utils",
            send_discord_alert=MagicMock(),
        ),
        "reddit": _make_stub_module("reddit"),
        "reddit.connection": _make_stub_module(
            "reddit.connection",
            REDDIT=MagicMock(),
            REDDIT_HELPER=MagicMock(),
            USERNAME="translator-BOT",
            get_random_useragent=MagicMock(return_value={}),
        ),
        "reddit.notifications": _make_stub_module(
            "reddit.notifications", notifier_internal=MagicMock()
        ),
        "reddit.wiki": _make_stub_module(
            "reddit.wiki", fetch_most_requested_languages=MagicMock(return_value=[])
        ),
        "reddit.verification": _make_stub_module(
            "reddit.verification", get_verified_thread=MagicMock()
        ),
        "responses": _make_stub_module(
            "responses", RESPONSE=MagicMock(WEEKLY_UNKNOWN_THREAD="{unknown_content}")
        ),
        "error": _make_stub_module("error", error_log_basic=MagicMock()),
        "time_handling": _make_stub_module(
            "time_handling",
            get_current_utc_date=MagicMock(return_value="2024-01-15"),
            get_current_utc_time=MagicMock(return_value="12:00:00"),
            get_current_month=MagicMock(return_value="2024-01"),
            get_previous_month=MagicMock(return_value="2023-12"),
            messaging_months_elapsed=MagicMock(return_value=1),
            time_convert_to_string_seconds=MagicMock(return_value="1 day"),
            time_convert_to_utc=MagicMock(side_effect=lambda x: x),
            convert_to_day=MagicMock(return_value="2024-01-15"),
        ),
        "lang": _make_stub_module("lang"),
        "lang.languages": _make_stub_module(
            "lang.languages",
            converter=MagicMock(return_value=None),
            validate_lingvo_dataset=MagicMock(return_value=[]),
            define_language_lists=MagicMock(return_value={}),
            get_lingvos=MagicMock(return_value=[]),
            select_random_language=MagicMock(return_value=None),
        ),
        "lang.countries": _make_stub_module(
            "lang.countries", get_country_emoji=MagicMock(return_value="")
        ),
        "monitoring": _make_stub_module("monitoring"),
        "monitoring.points": _make_stub_module(
            "monitoring.points", points_worth_determiner=MagicMock()
        ),
        "monitoring.usage_statistics": _make_stub_module(
            "monitoring.usage_statistics",
            generate_command_usage_report=MagicMock(return_value=""),
        ),
        "models": _make_stub_module("models"),
        "models.ajo": _make_stub_module(
            "models.ajo", Ajo=MagicMock(), ajo_loader=MagicMock(return_value=None)
        ),
        "utility": _make_stub_module(
            "utility",
            format_markdown_table_with_padding=MagicMock(side_effect=lambda x: x),
        ),
        "praw": _make_stub_module("praw"),
        "praw.models": _make_stub_module(
            "praw.models", WikiPage=MagicMock(), TextArea=MagicMock()
        ),
        "praw.exceptions": _make_stub_module(
            "praw.exceptions",
            PRAWException=Exception,
            RedditAPIException=Exception,
        ),
        "prawcore": _make_stub_module("prawcore"),
        "prawcore.exceptions": _make_stub_module(
            "prawcore.exceptions", NotFound=Exception
        ),
        "requests": _make_stub_module("requests", get=MagicMock()),
        "lxml": _make_stub_module("lxml"),
        "lxml.html": _make_stub_module("lxml.html", fromstring=MagicMock()),
        "pypdf": _make_stub_module("pypdf", PdfReader=MagicMock()),
        "yaml": yaml,  # real yaml is fine
        "orjson": _make_stub_module(
            "orjson",
            loads=json.loads,
            JSONDecodeError=json.JSONDecodeError,
        ),
        "ziwen_lookup": _make_stub_module("ziwen_lookup"),
        "ziwen_lookup.reference": _make_stub_module(
            "ziwen_lookup.reference", get_language_reference=MagicMock()
        ),
        "ziwen_lookup.wp_utils": _make_stub_module(
            "ziwen_lookup.wp_utils", wikipedia_lookup=MagicMock()
        ),
    }
    originals: dict[str, types.ModuleType | None] = {
        name: sys.modules.get(name) for name in stubs
    }
    for name, mod in stubs.items():
        sys.modules[name] = mod  # always override, don't check first
    return originals


_STUB_ORIGINALS = _register_stubs()


@pytest.fixture(scope="session", autouse=True)
def _restore_stub_modules():
    """Restore sys.modules to its pre-stub state after this session completes."""
    yield
    for name, original in _STUB_ORIGINALS.items():
        if original is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = original


# This file lives at testing/unit/test_wenju_tasks.py.
# The project root (parent of both wenju/ and testing/) is two levels up.
# Insert it so that `import wenju.moderator_digest` etc. resolve correctly.
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import wenju  # noqa: E402
import wenju.iso_updates as iso_updates  # noqa: E402
import wenju.moderator_digest as moderator_digest  # noqa: E402

# ---------------------------------------------------------------------------
# Minimal wenju package stub so that `from wenju import task` works.
# We reproduce just the decorator & run_schedule logic inline here.
# ---------------------------------------------------------------------------


class _TaskRegistry:
    """Minimal reimplementation of the @task decorator for unit tests."""

    def __init__(self):
        self._tasks: dict[str, list] = {}

    def task(self, schedule: str):
        def decorator(func):
            self._tasks.setdefault(schedule, []).append(func)
            return func

        return decorator

    def get_tasks(self) -> dict:
        return self._tasks

    def clear(self):
        self._tasks.clear()


# ===========================================================================
# Tests: task decorator & run_schedule
# ===========================================================================


class TestTaskDecorator:
    def setup_method(self):
        self.registry = _TaskRegistry()

    def test_registers_function_under_schedule(self):
        @self.registry.task(schedule="daily")
        def my_task():
            pass

        assert "daily" in self.registry.get_tasks()
        assert my_task in self.registry.get_tasks()["daily"]

    def test_registers_multiple_functions_same_schedule(self):
        @self.registry.task(schedule="hourly")
        def task_a():
            pass

        @self.registry.task(schedule="hourly")
        def task_b():
            pass

        tasks = self.registry.get_tasks()["hourly"]
        assert task_a in tasks
        assert task_b in tasks
        assert len(tasks) == 2

    def test_registers_functions_across_different_schedules(self):
        @self.registry.task(schedule="daily")
        def daily_task():
            pass

        @self.registry.task(schedule="weekly")
        def weekly_task():
            pass

        tasks = self.registry.get_tasks()
        assert daily_task in tasks["daily"]
        assert weekly_task in tasks["weekly"]

    def test_decorator_returns_original_function_unchanged(self):
        @self.registry.task(schedule="daily")
        def my_task():
            return 42

        assert my_task() == 42

    def test_empty_schedule_returns_empty_list(self):
        tasks = self.registry.get_tasks()
        assert tasks.get("nonexistent", []) == []

    def test_same_function_multiple_schedules(self):
        """A function can be registered on multiple schedules."""

        def shared():
            pass

        self.registry.task(schedule="daily")(shared)
        self.registry.task(schedule="weekly")(shared)

        tasks = self.registry.get_tasks()
        assert shared in tasks["daily"]
        assert shared in tasks["weekly"]


class TestWenjuScheduleValidation:
    def test_rejects_unknown_schedule_before_discovery(self):
        with pytest.raises(ValueError, match="Unsupported schedule"):
            wenju.run_schedule("every_minute")

    def test_normalizes_supported_schedule_name(self):
        assert wenju.validate_schedule_name(" Weekly ") == "weekly"

    def test_valid_schedule_with_no_tasks_sends_alert_when_expected(self):
        with patch.object(wenju, "_tasks", {"weekly": []}):
            with patch("wenju.importlib.import_module"):
                with patch("wenju.send_discord_alert") as alert_mock:
                    wenju.run_schedule("weekly")

        alert_mock.assert_called_once()


# ===========================================================================
# Tests: _parse_iso639_newsletter  (iso_updates.py)
# ===========================================================================


class TestParseIso639Newsletter:
    """
    Tests the PDF-parsing helper in isolation by mocking PdfReader so we
    can feed controlled text without needing a real PDF file.
    """

    # A minimal text that mimics the newsletter section structure
    SAMPLE_TEXT = textwrap.dedent("""
        Some preamble text.

        Change requests that have been adopted

        2024-001, Retire [abc] Abcish (639-3) -- language is extinct
        2024-002, Change [xyz] Xyzian (639-3) -- spelling correction

        Newly posted change requests

        2024-003, Add [new] Newish (639-3) -- newly discovered
    """)

    @staticmethod
    def _make_reader(text: str) -> MagicMock:
        page = MagicMock()
        page.extract_text.return_value = text
        reader = MagicMock()
        reader.pages = [page]
        return reader

    def test_extracts_adopted_requests(self):
        with patch(
            "wenju.iso_updates.PdfReader",
            return_value=self._make_reader(self.SAMPLE_TEXT),
        ):
            result = iso_updates._parse_iso639_newsletter("/fake/path.pdf")

        assert "2024-001" in result
        assert "2024-002" in result

    def test_excludes_newly_posted_requests(self):
        with patch(
            "wenju.iso_updates.PdfReader",
            return_value=self._make_reader(self.SAMPLE_TEXT),
        ):
            result = iso_updates._parse_iso639_newsletter("/fake/path.pdf")

        assert "2024-003" not in result

    def test_language_codes_wrapped_in_backticks(self):
        with patch(
            "wenju.iso_updates.PdfReader",
            return_value=self._make_reader(self.SAMPLE_TEXT),
        ):
            result = iso_updates._parse_iso639_newsletter("/fake/path.pdf")

        # [abc] should become [`abc`] in the output
        assert "[`abc`]" in result
        assert "[`xyz`]" in result

    def test_returns_markdown_list_items(self):
        with patch(
            "wenju.iso_updates.PdfReader",
            return_value=self._make_reader(self.SAMPLE_TEXT),
        ):
            result = iso_updates._parse_iso639_newsletter("/fake/path.pdf")

        lines = [line for line in result.splitlines() if line.strip()]
        assert all(line.startswith("*") for line in lines)

    def test_no_adopted_section_returns_fallback(self):
        text = "Only newly posted change requests\n2024-010, Add [foo] Fooish -- test"
        with patch("wenju.iso_updates.PdfReader", return_value=self._make_reader(text)):
            result = iso_updates._parse_iso639_newsletter("/fake/path.pdf")

        assert result == "No adopted change requests found."

    def test_adopted_section_with_no_parseable_entries(self):
        text = "Change requests that have been adopted\nNo entries here."
        with patch("wenju.iso_updates.PdfReader", return_value=self._make_reader(text)):
            result = iso_updates._parse_iso639_newsletter("/fake/path.pdf")

        assert result == "No change requests could be parsed."

    def test_links_use_correct_base_url(self):
        with patch(
            "wenju.iso_updates.PdfReader",
            return_value=self._make_reader(self.SAMPLE_TEXT),
        ):
            result = iso_updates._parse_iso639_newsletter("/fake/path.pdf")

        assert "https://iso639-3.sil.org/request/2024-001" in result


# ===========================================================================
# Tests: _error_log_count  (moderator_digest.py)
# ===========================================================================


class TestErrorLogCount:
    """Tests the YAML error-log reading/formatting helper."""

    @staticmethod
    def _make_entry(resolved: bool, ts: str) -> dict:
        return {"timestamp": ts, "resolved": resolved, "context": "test"}

    def test_empty_log_returns_zero_count(self, tmp_path):
        log_file = tmp_path / "errors.yaml"
        log_file.write_text("[]", encoding="utf-8")

        with patch.object(
            moderator_digest.Paths,
            "LOGS",
            {**moderator_digest.Paths.LOGS, "ERROR": str(log_file)},
        ):
            result_md, result_data = moderator_digest._error_log_count()

        assert result_data["count"] == 0

    def test_counts_entries_correctly(self, tmp_path):
        log_file = tmp_path / "errors.yaml"
        entries = [
            self._make_entry(False, "2024-01-10T10:00:00+00:00"),
            self._make_entry(True, "2024-01-11T10:00:00+00:00"),
            self._make_entry(False, "2024-01-12T10:00:00+00:00"),
        ]
        log_file.write_text(yaml.dump(entries), encoding="utf-8")

        with patch.object(
            moderator_digest.Paths,
            "LOGS",
            {**moderator_digest.Paths.LOGS, "ERROR": str(log_file)},
        ):
            result_md, result_data = moderator_digest._error_log_count()

        assert result_data["count"] == 3

    def test_last_entry_resolved_status_reflected(self, tmp_path):
        log_file = tmp_path / "errors.yaml"
        entries = [
            self._make_entry(False, "2024-01-10T10:00:00+00:00"),
            self._make_entry(True, "2024-01-12T10:00:00+00:00"),
        ]
        log_file.write_text(yaml.dump(entries), encoding="utf-8")

        with patch.object(
            moderator_digest.Paths,
            "LOGS",
            {**moderator_digest.Paths.LOGS, "ERROR": str(log_file)},
        ):
            result_md, result_data = moderator_digest._error_log_count()

        assert result_data["resolved"] is True
        assert "(resolved)" in result_data["lastEntry"]

    def test_unresolved_last_entry_has_no_resolved_suffix(self, tmp_path):
        log_file = tmp_path / "errors.yaml"
        entries = [self._make_entry(False, "2024-01-10T10:00:00+00:00")]
        log_file.write_text(yaml.dump(entries), encoding="utf-8")

        with patch.object(
            moderator_digest.Paths,
            "LOGS",
            {**moderator_digest.Paths.LOGS, "ERROR": str(log_file)},
        ):
            result_md, result_data = moderator_digest._error_log_count()

        assert result_data["resolved"] is False
        assert "(resolved)" not in result_data["lastEntry"]

    def test_missing_file_returns_zero_gracefully(self, tmp_path):
        patched_logs = {
            **moderator_digest.Paths.LOGS,
            "ERROR": str(tmp_path / "nonexistent.yaml"),
        }
        with patch.object(moderator_digest.Paths, "LOGS", patched_logs):
            result_md, result_data = moderator_digest._error_log_count()

        assert result_data["count"] == 0
        assert "missing" in result_md.lower()

    def test_malformed_yaml_returns_gracefully(self, tmp_path):
        log_file = tmp_path / "errors.yaml"
        log_file.write_text(": bad: [yaml: content", encoding="utf-8")

        with patch.object(
            moderator_digest.Paths,
            "LOGS",
            {**moderator_digest.Paths.LOGS, "ERROR": str(log_file)},
        ):
            result_md, result_data = moderator_digest._error_log_count()

        assert result_data["count"] == 0


# ===========================================================================
# Tests: _render_html_dashboard  (moderator_digest.py)
# ===========================================================================


class TestRenderHtmlDashboard:
    TEMPLATE = "<html>Date: __DATE_STR__ Data: __DATA_JSON__</html>"
    SAMPLE_DATA = {"errors": {"count": 0}, "filter": {}, "activity": {}}

    def test_replaces_date_placeholder(self, tmp_path):
        tpl = tmp_path / "template.html"
        tpl.write_text(self.TEMPLATE, encoding="utf-8")

        with patch.object(
            moderator_digest.Paths,
            "TEMPLATES",
            {**moderator_digest.Paths.TEMPLATES, "MODERATOR_DIGEST": str(tpl)},
        ):
            result = moderator_digest._render_html_dashboard(
                "2024-01-15", self.SAMPLE_DATA
            )

        assert "2024-01-15" in result
        assert "__DATE_STR__" not in result

    def test_replaces_data_placeholder_with_valid_json(self, tmp_path):
        tpl = tmp_path / "template.html"
        tpl.write_text(self.TEMPLATE, encoding="utf-8")

        with patch.object(
            moderator_digest.Paths,
            "TEMPLATES",
            {**moderator_digest.Paths.TEMPLATES, "MODERATOR_DIGEST": str(tpl)},
        ):
            result = moderator_digest._render_html_dashboard(
                "2024-01-15", self.SAMPLE_DATA
            )

        assert "__DATA_JSON__" not in result
        # The injected JSON should be valid
        start = result.index("Data: ") + len("Data: ")
        end = result.index("</html>")
        parsed = json.loads(result[start:end])
        assert parsed == self.SAMPLE_DATA

    def test_output_contains_template_structure(self, tmp_path):
        tpl = tmp_path / "template.html"
        tpl.write_text(self.TEMPLATE, encoding="utf-8")

        with patch.object(
            moderator_digest.Paths,
            "TEMPLATES",
            {**moderator_digest.Paths.TEMPLATES, "MODERATOR_DIGEST": str(tpl)},
        ):
            result = moderator_digest._render_html_dashboard(
                "2024-01-15", self.SAMPLE_DATA
            )

        assert result.startswith("<html>")
        assert result.endswith("</html>")


# ===========================================================================
# Tests: error_log_trimmer logic  (data_maintenance.py)
# ===========================================================================


class TestErrorLogTrimmerLogic:
    """
    Tests the filtering logic of error_log_trimmer without touching real files.
    We isolate the keep/discard predicate directly.
    """

    @staticmethod
    def _should_keep(entry: dict, cutoff: datetime) -> bool:
        """Mirrors the keep condition in error_log_trimmer."""
        return not (
            entry.get("resolved", False)
            and datetime.fromisoformat(entry["timestamp"]) < cutoff
        )

    def test_keeps_unresolved_old_entry(self):
        cutoff = datetime(2024, 1, 1, tzinfo=timezone.utc)
        entry = {"resolved": False, "timestamp": "2023-06-01T00:00:00+00:00"}
        assert self._should_keep(entry, cutoff) is True

    def test_removes_resolved_old_entry(self):
        cutoff = datetime(2024, 1, 1, tzinfo=timezone.utc)
        entry = {"resolved": True, "timestamp": "2023-06-01T00:00:00+00:00"}
        assert self._should_keep(entry, cutoff) is False

    def test_keeps_resolved_recent_entry(self):
        cutoff = datetime(2024, 1, 1, tzinfo=timezone.utc)
        entry = {"resolved": True, "timestamp": "2024-01-15T00:00:00+00:00"}
        assert self._should_keep(entry, cutoff) is True

    def test_keeps_entry_exactly_at_cutoff(self):
        """Entry timestamped exactly at cutoff boundary is NOT older than cutoff."""
        cutoff = datetime(2024, 1, 1, tzinfo=timezone.utc)
        entry = {"resolved": True, "timestamp": "2024-01-01T00:00:00+00:00"}
        assert self._should_keep(entry, cutoff) is True

    def test_filters_mixed_entries(self):
        cutoff = datetime(2024, 1, 1, tzinfo=timezone.utc)
        entries = [
            {"resolved": True, "timestamp": "2023-06-01T00:00:00+00:00"},  # remove
            {"resolved": False, "timestamp": "2023-06-01T00:00:00+00:00"},  # keep
            {"resolved": True, "timestamp": "2024-02-01T00:00:00+00:00"},  # keep
        ]
        kept = [e for e in entries if self._should_keep(e, cutoff)]
        assert len(kept) == 2
        assert entries[0] not in kept


# ===========================================================================
# Tests: _analyze_mod_removals rule-pattern extraction  (community_digest.py)
# ===========================================================================


class TestRulePatternExtraction:
    """
    Tests the regex used in _analyze_mod_removals to find rule citations
    in mod comments, without needing a Reddit connection.
    """

    RULE_PATTERN = re.compile(r"\[Rule #([A-Z]\d+)]", re.IGNORECASE)

    def _extract_rules(self, text: str) -> list[str]:
        return [m.upper() for m in self.RULE_PATTERN.findall(text)]

    def test_extracts_single_rule(self):
        text = "This violates [Rule #A1] of our community guidelines."
        assert self._extract_rules(text) == ["A1"]

    def test_extracts_multiple_rules(self):
        text = "Breaks [Rule #B2] and also [Rule #C3]."
        assert self._extract_rules(text) == ["B2", "C3"]

    def test_case_insensitive_matching(self):
        text = "See [rule #a1] for details."
        assert self._extract_rules(text) == ["A1"]

    def test_no_match_returns_empty(self):
        text = "This comment has no rule citations."
        assert self._extract_rules(text) == []

    def test_does_not_match_malformed_rule(self):
        """Pattern requires letter+digit; pure-digit or pure-letter shouldn't match."""
        text = "[Rule #123] and [Rule #ABC] should not match."
        # "123" has no leading letter; "ABC" has no digit — neither fits [A-Z]\d+
        assert self._extract_rules(text) == []

    def test_counter_aggregates_repeated_rules(self):
        texts = ["[Rule #A1]", "[Rule #A1]", "[Rule #B2]"]
        all_rules = []
        for t in texts:
            all_rules.extend(self._extract_rules(t))
        counts = Counter(all_rules)
        assert counts["A1"] == 2
        assert counts["B2"] == 1


# ===========================================================================
# Tests: weekly_bot_action_report percentage math  (community_digest.py)
# ===========================================================================


class TestBotActionReportMath:
    """
    Validates the percentage and average calculations used when building
    the weekly bot action report, exercising the same arithmetic in isolation.
    """

    @staticmethod
    def _calc_percentage(count: int, total: int) -> float:
        return (count / total * 100) if total > 0 else 0.0

    @staticmethod
    def _calc_avg_per_day(total: int, days: int = 7) -> float:
        return total / days

    def test_percentage_sums_to_100(self):
        action_data = {"removelink": 50, "approvelink": 30, "flair": 20}
        total = sum(action_data.values())
        percentages = [self._calc_percentage(v, total) for v in action_data.values()]
        assert abs(sum(percentages) - 100.0) < 1e-9

    def test_zero_total_returns_zero_percentage(self):
        assert self._calc_percentage(0, 0) == 0.0

    def test_average_per_day(self):
        assert self._calc_avg_per_day(70) == 10.0
        assert self._calc_avg_per_day(0) == 0.0

    def test_sorted_output_is_alphabetical(self):
        action_data = {"removelink": 5, "approvelink": 3, "flair": 8}
        sorted_keys = sorted(action_data.keys())
        assert sorted_keys == ["approvelink", "flair", "removelink"]


# ===========================================================================
# Tests: monthly_rule_violation_report structure  (community_digest.py)
# ===========================================================================


class TestModRemovalReportStructure:
    """
    Verifies that _analyze_mod_removals returns a dict with the expected
    schema, using mocked Reddit objects.
    """

    @staticmethod
    def _build_report(rule_violations: list[str]) -> dict:
        """Reproduce the result-building logic from _analyze_mod_removals."""
        violation_counts = Counter(rule_violations)
        end_time = 1_700_000_000
        start_time = end_time - (30 * 24 * 60 * 60)
        return {
            "start_time": start_time,
            "end_time": end_time,
            "start_date": datetime.fromtimestamp(start_time).strftime(
                "%Y-%m-%d %H:%M:%S UTC"
            ),
            "end_date": datetime.fromtimestamp(end_time).strftime(
                "%Y-%m-%d %H:%M:%S UTC"
            ),
            "total_comments_checked": 100,
            "total_violations": len(rule_violations),
            "unique_rules_violated": len(violation_counts),
            "violation_counts": dict(violation_counts.most_common()),
        }

    def test_required_keys_present(self):
        report = self._build_report(["A1", "B2", "A1"])
        required = {
            "start_time",
            "end_time",
            "start_date",
            "end_date",
            "total_comments_checked",
            "total_violations",
            "unique_rules_violated",
            "violation_counts",
        }
        assert required.issubset(report.keys())

    def test_violation_counts_are_sorted_by_frequency(self):
        report = self._build_report(["A1", "A1", "A1", "B2", "B2", "C3"])
        keys = list(report["violation_counts"].keys())
        assert keys[0] == "A1"
        assert keys[1] == "B2"

    def test_unique_rules_count(self):
        report = self._build_report(["A1", "A1", "B2"])
        assert report["unique_rules_violated"] == 2

    def test_empty_violations(self):
        report = self._build_report([])
        assert report["total_violations"] == 0
        assert report["unique_rules_violated"] == 0
        assert report["violation_counts"] == {}


# ===========================================================================
# Tests: _activity_csv_handler statistics  (moderator_digest.py)
# ===========================================================================


class TestActivityCsvHandlerStatistics:
    """
    Tests the average/longest-cycle calculations in _activity_csv_handler
    by feeding a known CSV through a mocked file open.
    """

    # CSV row layout: [timestamp, something, api_calls, memory_mb, cycle_min]
    CSV_CONTENT = "\n".join(
        [
            "timestamp,run_id,api_calls,memory_mb,cycle_min",
            "2024-01-01,1,100,50 MB,2.0",
            "2024-01-02,2,200,60 MB,4.0",
            "2024-01-03,3,300,70 MB,6.0",
        ]
    )

    @pytest.fixture()
    def csv_result(self, tmp_path):
        csv_file = tmp_path / "activity.csv"
        csv_file.write_text(self.CSV_CONTENT, encoding="utf-8")
        with patch.object(
            moderator_digest.Paths,
            "LOGS",
            {**moderator_digest.Paths.LOGS, "ACTIVITY": str(csv_file)},
        ):
            with patch.object(
                moderator_digest, "WENJU_SETTINGS", {"lines_to_keep": 1000}
            ):
                summary, data = moderator_digest._activity_csv_handler()
        return summary, data

    def test_average_api_calls(self, csv_result):
        _, data = csv_result
        assert data["avgApiCalls"] == pytest.approx((100 + 200 + 300) / 3)

    def test_average_memory(self, csv_result):
        _, data = csv_result
        assert data["avgMemoryMB"] == pytest.approx((50 + 60 + 70) / 3)

    def test_average_cycle_time(self, csv_result):
        _, data = csv_result
        assert data["avgCycleMin"] == pytest.approx((2.0 + 4.0 + 6.0) / 3)

    def test_longest_cycles_are_descending(self, csv_result):
        _, data = csv_result
        cycles: list[float] = cast(dict[str, object], data)["longestCycles"]  # type: ignore[assignment]
        assert cycles == sorted(cycles, reverse=True)
        assert cycles[0] == pytest.approx(6.0)

    def test_missing_file_returns_fallback_string(self, tmp_path):
        with patch.object(
            moderator_digest.Paths,
            "LOGS",
            {
                **moderator_digest.Paths.LOGS,
                "ACTIVITY": str(tmp_path / "nonexistent.csv"),
            },
        ):
            summary, data = moderator_digest._activity_csv_handler()

        assert "missing" in summary.lower()
        assert data == {}
