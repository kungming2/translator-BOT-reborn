#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
hermes/tools.py — Manual diagnostic tools for Hermes.

Neither function is called during the normal bot runtime; both are
intended for offline inspection and debugging.

  get_statistics()  — Summarise offered/sought language counts from the DB.
  format_statistics_for_reddit() — Format statistics as Markdown.
  test_parser()     — Fetch live posts and print title_parser output for each.
  parse_title_diagnostic() — Parse one title for devtools diagnostics.

Logger tag: [HM:TOOLS]
"""

# ─── Imports ──────────────────────────────────────────────────────────────────

from collections import Counter
from dataclasses import dataclass

import praw

from config import Paths, get_specific_logger

# ─── Module-level constants ───────────────────────────────────────────────────

logger = get_specific_logger("HM:TOOLS", log_path=Paths.HERMES["HERMES_EVENTS"])


# ─── Database inspection ──────────────────────────────────────────────────────


@dataclass(frozen=True)
class HermesStatistics:
    """Aggregated Hermes language statistics for a database time range."""

    start_utc: int | None
    end_utc: int | None
    post_count: int
    unique_offered: int
    unique_sought: int
    offered_counts: Counter[str]
    sought_counts: Counter[str]


@dataclass(frozen=True)
class HermesTitleDiagnostic:
    """Parsed Hermes title data for devtools diagnostics."""

    title: str
    offering: list[str]
    seeking: list[str]
    levels: dict[str, str]


def get_statistics(
    start_utc: int | None = None, end_utc: int | None = None
) -> HermesStatistics:
    """
    Return aggregated language statistics from the current Hermes database.

    If both timestamps are provided, only entries with posted_utc in the
    half-open range [start_utc, end_utc) are included.
    """
    from hermes.hermes_database import hermes_db

    if (start_utc is None) != (end_utc is None):
        raise ValueError("start_utc and end_utc must be provided together.")
    if start_utc is not None and end_utc is not None:
        if start_utc >= end_utc:
            raise ValueError("start_utc must be earlier than end_utc.")
        entries = hermes_db.get_entries_between(start_utc, end_utc)
    else:
        entries = hermes_db.get_all_entries()

    if not entries:
        logger.info("No language data available for statistics.")

    all_offered: list[str] = []
    all_sought: list[str] = []

    for _, data, _ in entries:
        all_offered.extend(data.get("offering", []))
        all_sought.extend(data.get("seeking", []))

    return HermesStatistics(
        start_utc=start_utc,
        end_utc=end_utc,
        post_count=len(entries),
        unique_offered=len(set(all_offered)),
        unique_sought=len(set(all_sought)),
        offered_counts=Counter(all_offered),
        sought_counts=Counter(all_sought),
    )


def format_statistics_for_reddit(stats: HermesStatistics) -> str:
    """Format Hermes statistics as a Markdown report."""
    from lang.languages import converter

    post_count_label = (
        "Posts in period" if stats.start_utc is not None else "Posts in database"
    )
    lines = [
        f"* {post_count_label:<18}: {stats.post_count:,}",
        f"* Unique offered     : {stats.unique_offered:,}",
        f"* Unique sought      : {stats.unique_sought:,}",
        "",
    ]

    header = (
        "| Language | Code | Count | Percentage |\n"
        "|----------|------|-------|------------|\n"
    )
    row_fmt = "| {name} | `{code}` | {count:,} | {pct:.2%} |"

    for counts, label in [
        (stats.offered_counts, "Offered"),
        (stats.sought_counts, "Sought"),
    ]:
        total = sum(counts.values())
        table_lines: list[str] = []
        for code in sorted(counts):
            count = counts[code]
            lingvo = converter(code)
            name = lingvo.name if lingvo else code
            percentage = count / total if total else 0
            table_lines.append(
                row_fmt.format(name=name, code=code, count=count, pct=percentage)
            )
        if not table_lines:
            table_lines.append("| None | `-` | 0 | 0.00% |")
        lines.append(f"## {label}\n{header}" + "\n".join(table_lines))
        lines.append("")

    return "\n".join(lines).strip()


def print_statistics(start_utc: int | None = None, end_utc: int | None = None) -> None:
    """Print aggregated Hermes language statistics to stdout."""
    print(format_statistics_for_reddit(get_statistics(start_utc, end_utc)))


# ─── Parser diagnostics ───────────────────────────────────────────────────────


def test_parser(reddit: praw.Reddit, limit: int = 100) -> None:
    """
    Fetch the most recent *limit* posts from r/Language_Exchange, run each
    title through ``title_parser``, and print a compact summary so parser
    behaviour can be verified against real data without a full bot run.

    Args:
        reddit: An authenticated PRAW Reddit instance (REDDIT_HERMES).
        limit:  Number of posts to fetch (default 100).

    Usage:
        python devtools.py
        Select hermes > parse recent r/Language_Exchange titles.
    """
    from hermes.matching import title_parser
    from lang.languages import converter

    posts = list(reddit.subreddit("language_exchange").new(limit=limit))
    posts.reverse()  # oldest first, matching normal processing order

    col_w = 80
    print(f"{'TITLE':<{col_w}}  {'OFFERING':<30}  {'SEEKING':<30}  LEVELS")
    print("-" * (col_w + 70))

    unparsed = 0
    for post in posts:
        title = post.title
        offering, seeking, levels = title_parser(title, include_iso_639_3=True)

        def _fmt_codes(codes: list[str]) -> str:
            """Format a list of ISO codes as 'Language Name [code]' strings."""
            if not codes:
                return "—"
            parts = []
            for code in codes:
                lingvo = converter(code)
                name = lingvo.name if lingvo else code
                parts.append(f"{name} [{code}]")
            return ", ".join(parts)

        def _fmt_levels(lvls: dict[str, str]) -> str:
            """Format a levels dict as a space-separated 'code=level' string."""
            if not lvls:
                return ""
            return "  ".join(f"{k}={v}" for k, v in lvls.items())

        truncated = title if len(title) <= col_w else title[: col_w - 1] + "…"
        o_str = _fmt_codes(offering)
        s_str = _fmt_codes(seeking)
        l_str = _fmt_levels(levels)

        if not offering and not seeking:
            unparsed += 1
            marker = "  ← UNPARSED"
        else:
            marker = ""

        print(f"{truncated:<{col_w}}  {o_str:<30}  {s_str:<30}  {l_str}{marker}")
        print("-" * (col_w + 70))

    print(f"{len(posts)} posts fetched.  {unparsed} unparsed.")


# ─── Title diagnostics ────────────────────────────────────────────────────────


def parse_title_diagnostic(
    title: str, include_iso_639_3: bool = True
) -> HermesTitleDiagnostic:
    """
    Parse one manually supplied post title for devtools diagnostics.

    Args:
        title:             Title string to parse.
        include_iso_639_3: If True, also accept ISO 639-3 codes (default True).
    """
    from hermes.matching import title_parser

    offering, seeking, levels = title_parser(title, include_iso_639_3=include_iso_639_3)
    return HermesTitleDiagnostic(
        title=title,
        offering=offering,
        seeking=seeking,
        levels=levels,
    )
