#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
import json
import re
import time
from collections import Counter
from datetime import datetime, timezone
from typing import Dict

from config import SETTINGS, logger
from connection import REDDIT, USERNAME
from database import db
from discord_utils import send_discord_alert
from notifications import notifier_internal
from responses import RESPONSE
from tasks import task
from time_handling import get_current_utc_date


@task(schedule="daily")
def send_internal_post_digest():
    """
    Check for new internal posts in the last 24 hours and send
    notifications for unprocessed ones. This is usually meta/community,
    and this allows for messages to be sent en masse at once.
    """
    # Calculate timestamp for 24 hours ago
    cutoff_time = int(time.time()) - (24 * 60 * 60)

    # Fetch all posts from the last 24 hours
    query = """
        SELECT id, created_utc, content 
        FROM internal_posts 
        WHERE created_utc >= ?
    """
    posts = db.fetchall_main(query, (cutoff_time,))

    for post in posts:
        post_id = post["id"]
        content_str = post["content"]

        # Parse the content JSON
        try:
            content = json.loads(content_str)
        except json.JSONDecodeError:
            logger.warning(f"Warning: Could not parse content for post {post_id}")
            continue

        # Skip if already processed
        if content.get("processed", False):
            continue

        # Get the post_type and submission ID
        post_type = content.get("post_type")
        submission_id = content.get("id")

        if not post_type or not submission_id:
            logger.warning(f"Warning: Missing post_type or id for post {post_id}")
            continue

        # Get the Reddit submission object
        try:
            submission = REDDIT.submission(id=submission_id)
        except Exception as e:
            logger.error(f"Error fetching submission {submission_id}: {e}")
            continue

        # Send notifications
        notifier_internal(post_type, submission)

        # Update the processed flag in the database
        content["processed"] = True
        updated_content = json.dumps(content)

        update_query = """
            UPDATE internal_posts 
            SET content = ? 
            WHERE id = ?
        """
        cursor = db.cursor_main
        cursor.execute(update_query, (updated_content, post_id))
        db.conn_main.commit()

    return


@task(schedule="weekly")
def weekly_unknown_thread():
    """
    Posts the Weekly 'Unknown' thread: a round-up of all posts from the last
    seven days still marked as "Unknown".
    """
    r = REDDIT.subreddit(SETTINGS["subreddit"])
    today_str = get_current_utc_date()

    # Get the current week number for the post title
    current_week_utc = datetime.now(timezone.utc).strftime("%U")

    unknown_entries = []

    # Retrieve 'Unknown' posts from the past week
    for item in r.search('flair:"Unknown"', sort="new", time_filter="week"):
        if item.link_flair_css_class == "unknown":
            title_safe = item.title.replace("|", " ")  # Avoid Markdown table conflicts
            post_date = datetime.fromtimestamp(item.created_utc).strftime("%Y-%m-%d")
            unknown_entries.append(
                f"| {post_date} | **[{title_safe}]({item.permalink})** | u/{item.author} |"
            )

    if not unknown_entries:
        logger.debug("[WJ] unknown_thread: No 'Unknown' posts found this week.")
        return

    # Prepare the thread content
    unknown_entries.reverse()  # Oldest first
    unknown_content = "\n".join(unknown_entries)

    thread_title = (
        f'[META] Weekly "Unknown" Identification Thread — {today_str} '
        f"(Week {current_week_utc})"
    )
    body = RESPONSE.WEEKLY_UNKNOWN_THREAD.format(unknown_content=unknown_content)

    # Submit and distinguish the post
    submission = r.submit(title=thread_title, selftext=body, send_replies=False)
    submission.mod.distinguish()
    logger.info(
        f"[WJ] unknown_thread: Posted weekly 'Unknown' thread (Week {current_week_utc})."
    )

    return


def analyze_bot_mod_log(start_time: int, end_time: int) -> Dict[str, int]:
    """
    Analyze mod log actions performed by u/translator-BOT in r/translator.

    Args:
        start_time: Unix timestamp for the start of the time range
        end_time: Unix timestamp for the end of the time range

    Returns:
        Dictionary mapping action types to their counts
        Example: {'removelink': 5, 'approvelink': 3, 'sticky': 1}
    """
    subreddit = REDDIT.subreddit(SETTINGS["subreddit"])
    action_counts: Dict[str, int] = {}

    # Fetch mod log entries for translator-BOT
    # limit=None fetches as many as possible (PRAW will paginate automatically)
    for log_entry in subreddit.mod.log(mod=USERNAME, limit=None):
        # Check if the log entry is within our time range
        if start_time <= log_entry.created_utc <= end_time:
            action_type = log_entry.action
            action_counts[action_type] = action_counts.get(action_type, 0) + 1
        elif log_entry.created_utc < start_time:
            # Since logs are returned newest first, we can break once we're past our range
            break

    return action_counts


@task(schedule="weekly")
def weekly_bot_action_report():
    """
    Generate a weekly report of u/translator-BOT mod actions and post to r/translatorBOT.
    """
    # Get timestamps for the last week
    end_time = int(time.time())
    start_time = end_time - (7 * 24 * 60 * 60)  # 7 days ago

    # Get the action data
    action_data = analyze_bot_mod_log(start_time, end_time)

    # Format dates
    start_date = datetime.fromtimestamp(start_time).strftime("%Y-%m-%d")
    end_date = datetime.fromtimestamp(end_time).strftime("%Y-%m-%d")

    # Get week number
    end_datetime = datetime.fromtimestamp(end_time)
    week_number = end_datetime.isocalendar()[1]

    # Calculate total actions
    total_actions = sum(action_data.values())

    # Build the report content
    report_sections = []

    # Summary section
    avg_actions_per_day = total_actions / 7  # 7 days in a week

    summary = f"""## Summary
    - **Analysis Period**: {start_date} to {end_date}
    - **Total Actions**: {total_actions:,}
    - **Average Actions per Day**: {avg_actions_per_day:,.1f}
    - **Unique Action Types**: {len(action_data)}
    """
    report_sections.append(summary)

    # Action breakdown section (sorted alphabetically)
    if action_data:
        breakdown = [
            "## Action Breakdown",
            "| Action | Count | Percentage |",
            "|--------|-------|------------|",
        ]

        # Sort alphabetically by action name
        for action in sorted(action_data.keys()):
            count = action_data[action]
            percentage = (count / total_actions * 100) if total_actions > 0 else 0
            breakdown.append(f"| {action} | {count:,} | {percentage:.1f}% |")

        report_sections.append("\n".join(breakdown))
    else:
        report_sections.append("## Action Breakdown\nNo actions found in this period.")

    # Compile the full report
    report_content = "\n\n".join(report_sections)

    # Post to r/translatorBOT
    subreddit = REDDIT.subreddit("translatorBOT")
    title = f"u/translator-BOT Mod Action Statistics — {end_date} (Week {week_number})"

    submission = subreddit.submit(title=title, selftext=report_content)

    logger.info(f"[WJ] Report posted: {submission.url}")

    return


def _analyze_mod_removals(start_time: int, end_time: int) -> dict:
    """
    Analyze mod removal comments to count rule violations.

    Args:
        start_time: UTC timestamp for the start of the analysis period
        end_time: UTC timestamp for the end of the analysis period

    Returns:
        Dictionary with rule counts and metadata
    """
    subreddit = REDDIT.subreddit(SETTINGS["subreddit"])
    mod_team_account = REDDIT.redditor(f"{subreddit}-ModTeam")

    # Regex pattern to match rules like [Rule #T1], [Rule #G4], etc.
    rule_pattern = re.compile(r"\[Rule #([A-Z]\d+)]", re.IGNORECASE)

    rule_violations = []
    total_comments_checked = 0

    # 1. Fetch comments from u/translator-ModTeam
    logger.info(f"Fetching comments from u/{subreddit}-ModTeam...")
    try:
        for comment in mod_team_account.comments.new(limit=None):
            total_comments_checked += 1

            # Check if comment is within our time range
            if not (start_time <= comment.created_utc <= end_time):
                # If we've passed the end time, we can break (comments are sorted newest first)
                if comment.created_utc < start_time:
                    break
                continue

            # Extract rules from comment body
            rules_found = rule_pattern.findall(comment.body)
            for rule in rules_found:
                rule_upper = rule.upper()
                rule_violations.append(rule_upper)
                logger.info(
                    f"Found Rule #{rule_upper} in ModTeam comment: "
                    f"https://www.reddit.com/{comment.permalink}"
                )

    except Exception as e:
        logger.error(f"Error fetching comments from u/translator-ModTeam: {e}")

    # 2. Fetch distinguished comments from r/translator moderators
    logger.info("Fetching distinguished mod comments from r/translator...")
    try:
        # Get moderators list
        moderators = [mod.name for mod in subreddit.moderator()]

        # Fetch recent comments from the subreddit
        for comment in subreddit.comments(limit=None):
            total_comments_checked += 1

            # Check if comment is within our time range
            if not (start_time <= comment.created_utc <= end_time):
                if comment.created_utc < start_time:
                    break
                continue

            # Check if comment is from a moderator and is distinguished
            if (
                comment.author
                and comment.author.name in moderators
                and comment.distinguished
            ):
                # Extract rules from comment body
                rules_found = rule_pattern.findall(comment.body)
                for rule in rules_found:
                    rule_upper = rule.upper()
                    rule_violations.append(rule_upper)
                    logger.info(
                        f"Found Rule #{rule_upper} in distinguished comment: "
                        f"https://www.reddit.com/{comment.permalink}"
                    )

    except Exception as e:
        logger.error(f"Error fetching distinguished comments: {e}")

    # Count the violations
    violation_counts = Counter(rule_violations)

    # Prepare results
    results = {
        "start_time": start_time,
        "end_time": end_time,
        "start_date": datetime.fromtimestamp(start_time).strftime(
            "%Y-%m-%d %H:%M:%S UTC"
        ),
        "end_date": datetime.fromtimestamp(end_time).strftime("%Y-%m-%d %H:%M:%S UTC"),
        "total_comments_checked": total_comments_checked,
        "total_violations": len(rule_violations),
        "unique_rules_violated": len(violation_counts),
        "violation_counts": dict(violation_counts.most_common()),
    }

    # Log summary
    logger.info("Rule violation analysis complete:")
    logger.info(f"  Period: {results['start_date']} to {results['end_date']}")
    logger.info(f"  Total mod comments checked: {total_comments_checked}")
    logger.info(f"  Total violations found: {results['total_violations']}")
    logger.info(f"  Unique rules violated: {results['unique_rules_violated']}")
    logger.info(f"  Top 5 violations: {violation_counts.most_common(5)}")

    return results


@task(schedule="monthly")
def monthly_rule_violation_report():
    """
    Generate a monthly report of rule violations and send via Discord webhook.
    """

    # Get timestamps for the last month
    end_time = int(time.time())
    start_time = end_time - (30 * 24 * 60 * 60)  # 30 days ago

    results = _analyze_mod_removals(start_time, end_time)

    # Format the report
    subject_line = (
        f"Monthly r/translator Rule Violation Report - {results['end_date'][:10]}"
    )

    # Build the report content
    report_sections = []

    # Summary section
    summary = f"""## Summary
- **Analysis Period**: {results["start_date"]} to {results["end_date"]}
- **Total Comments Checked**: {results["total_comments_checked"]:,}
- **Total Violations Found**: {results["total_violations"]}
- **Unique Rules Violated**: {results["unique_rules_violated"]}
"""
    report_sections.append(summary)

    # Violation breakdown section
    if results["violation_counts"]:
        breakdown = [
            "## Rule Violation Breakdown",
            "| Rule | Count | Percentage |",
            "|------|-------|------------|",
        ]

        for rule, count in results["violation_counts"].items():
            percentage = (
                (count / results["total_violations"] * 100)
                if results["total_violations"] > 0
                else 0
            )
            breakdown.append(f"| Rule #{rule} | {count} | {percentage:.1f}% |")

        report_sections.append("\n".join(breakdown))
    else:
        report_sections.append(
            "## Rule Violation Breakdown\nNo violations found in this period."
        )

    # Compile the full report
    total_data = "\n\n".join(report_sections)

    # Send via Discord
    send_discord_alert(subject_line, total_data, "notification")
    logger.info("Monthly rule violation report sent via Discord.")

    return results


if __name__ == "__main__":
    weekly_bot_action_report()
