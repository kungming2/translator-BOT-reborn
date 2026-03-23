#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
hermes/tools.py — Manual diagnostic tools for Hermes.

Neither function is called during the normal bot runtime; both are
intended for offline inspection and debugging.

  get_statistics()  — Summarise offered/sought language counts from the DB.
  test_parser()     — Fetch live posts and print title_parser output for each.

Logger tag: [HM:TOOLS]
"""

# ─── Imports ──────────────────────────────────────────────────────────────────

import praw

from config import get_hermes_logger

# ─── Module-level constants ───────────────────────────────────────────────────

logger = get_hermes_logger("HM:TOOLS")


# ─── Database inspection ──────────────────────────────────────────────────────


def get_statistics() -> None:
    """
    Print aggregated language statistics from the current database to stdout.
    Useful for manual inspection; not called during the normal runtime loop.
    """
    from collections import Counter

    from hermes.hermes_database import hermes_db
    from lang.languages import converter

    entries = hermes_db.get_all_entries()
    if not entries:
        logger.info("No language data available for statistics.")
        return

    all_offered: list[str] = []
    all_sought: list[str] = []

    for _, data, _ in entries:
        all_offered.extend(data.get("offering", []))
        all_sought.extend(data.get("seeking", []))

    print(
        f"* Posts in database  : {len(entries):,}\n"
        f"* Unique offered     : {len(set(all_offered)):,}\n"
        f"* Unique sought      : {len(set(all_sought)):,}\n"
    )

    header = (
        "| Language | Code | Count | Percentage |\n"
        "|----------|------|-------|------------|\n"
    )
    row_fmt = "| {name} | `{code}` | {count:,} | {pct:.2%} |"

    for lang_list, label in [(all_offered, "Offered"), (all_sought, "Sought")]:
        counts = Counter(lang_list)
        total = len(lang_list)
        lines: list[str] = []
        for code in sorted(counts):
            count = counts[code]
            lingvo = converter(code)
            name = lingvo.name if lingvo else code
            lines.append(
                row_fmt.format(name=name, code=code, count=count, pct=count / total)
            )
        print(f"## {label}\n" + header + "\n".join(lines) + "\n")


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
        python hermes/main_hermes.py --test
        python hermes/main_hermes.py --test 50
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
