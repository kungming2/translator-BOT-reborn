#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
import datetime
import re
import sqlite3
import time
from collections import Counter

from praw.models import TextArea
from praw.exceptions import RedditAPIException

from config import logger
from connection import REDDIT
from database import db
from discord_utils import send_discord_alert
from languages import converter
from main_wenju import task
from tasks import WENJU_SETTINGS


@task(schedule='hourly')
def monitor_controversial_comments():
    """
    Checks r/translator hourly for heavily downvoted comments
    and flags them for review via the bot's own reports.

    :return: None
    """

    # Iterate over the latest 100 comments in the subreddit
    for comment in REDDIT.subreddit('translator').comments(limit=100):

        # Extract comment info
        score = comment.score
        removed = comment.removed
        saved = comment.saved
        mod_reports = comment.mod_reports
        permalink = comment.permalink

        # Criteria: score <= -25, not removed, not reported, not already saved
        if score <= -25 and not removed and not mod_reports and not saved:
            # Send alert to Discord
            send_discord_alert(
                'Comment with Excessive Downvotes',
                f"[This comment](https://www.reddit.com{permalink}) has many downvotes (`{score}`). Please check the thread.",
                'alert'
            )

            # Save the comment to mark it as reviewed
            comment.save()

    return


def _generate_24h_statistics_snippet():
    """
    Retrieves and summarizes post statistics from the last 24 hours.

    :return: A formatted Markdown snippet string if data is available,
             otherwise None.
    """
    # Define time range (last 24 hours).
    cutoff_timestamp = time.time() - 86400  # 24 hours ago

    # Fetch posts created within the last 24 hours.
    try:
        stored_ajos = db.fetchall_ajo(
            "SELECT * FROM ajo_database WHERE created_utc >= ?",
            (cutoff_timestamp,)
        )
    except sqlite3.Error as e:
        logger.error(f"generate_24h_statistics_snippet: Database error: {e}")
        return None

    if not stored_ajos:
        logger.info("generate_24h_statistics_snippet: No posts found in the last 24 hours.")
        return None

    # Extract statuses safely.
    statuses = []
    for _, _, data, *rest in stored_ajos:
        try:
            ajo_data = eval(data)  # consider using `ast.literal_eval()` for safety
            statuses.append(ajo_data.get("status"))
        except Exception as e:
            logger.warning(f"Skipping malformed entry: {e}")

    if not statuses:
        logger.info("generate_24h_statistics_snippet: No valid statuses found.")
        return None

    # Count post categories.
    count_untranslated = statuses.count("untranslated")
    count_review = statuses.count("doublecheck")
    count_translated = statuses.count("translated")
    total = len(statuses)

    translated_percentage = round(
        ((count_translated + count_review) / total) * 100
    )

    snippet = (
        f"### Last 24H: "
        f"✗: **{count_untranslated}** "
        f"✓: **{count_review}** "
        f"✔: **{count_translated}** "
        f"({translated_percentage}%)"
    )

    logger.debug(f"generate_24h_statistics_snippet: {snippet}")
    return snippet


@task(schedule='hourly')
def update_sidebar_statistics():
    """
    Updates the r/translator sidebar with the latest statistics
    from the past 24 hours.
    Since June 2019, this function updates the Old Reddit sidebar
    by directly editing the wikipage that hosts it.

    :return: None
    """
    current_time = datetime.datetime.now()
    current_time_str = current_time.strftime("%Y-%m-%d %H:%M:%S")

    try:
        sidebar_bit = _generate_24h_statistics_snippet()
    except sqlite3.OperationalError:
        # Database is locked — skip this update cycle.
        return

    if not sidebar_bit:
        logger.error(
            "update_sidebar_statistics: No posts found in the last 24 hours — sidebar not updated."
        )
        return

    # --- Update Old Reddit sidebar ---
    try:
        sidebar_wikipage = REDDIT.subreddit('translator').wiki["config/sidebar"]
        sidebar_contents = sidebar_wikipage.content_md.rsplit("\n", 1)[0]
        new_sidebar_contents = f"{sidebar_contents}\n{sidebar_bit}"

        sidebar_wikipage.edit(
            content=new_sidebar_contents,
            reason=f"Updating sidebar on {current_time_str}",
        )

        logger.info(
            f"Updated Old Reddit sidebar with 24-hour stats: {sidebar_bit}"
        )
    except Exception as e:
        logger.error(f"Failed to update Old Reddit sidebar: {e}")
        return

    # --- Update New Reddit widget ---
    widgets = REDDIT.subreddit('translator').widgets
    target_widget_id = "widget_13r63qu7r63we"

    active_widget = next(
        (w for w in widgets.sidebar
         if isinstance(w, TextArea) and w.id == target_widget_id),
        None
    )

    if not active_widget:
        logger.warning("Sidebar text widget not found — skipping widget update.")
        return

    widget_text = sidebar_bit.replace("Last 24H", "Posts").strip()

    try:
        active_widget.mod.update(text=widget_text)  # type: ignore[attr-defined]
        logger.debug("Updated New Reddit sidebar widget with latest statistics.")
    except RedditAPIException:
        logger.error("Reddit API error: failed to update New Reddit sidebar widget.")

    return


@task(schedule='daily')
def modqueue_assessor():
    """
    Checks how many items are in the modqueue and alerts Discord
    if the count exceeds a certain threshold.
    """
    modqueue_items = list(REDDIT.subreddit('translator').mod.modqueue(limit=None))
    total_items = len(modqueue_items)

    # Count comments and submissions by type prefix
    comment_count = sum(1 for item in modqueue_items if item.fullname.startswith("t1_"))
    submission_count = sum(1 for item in modqueue_items if item.fullname.startswith("t3_"))

    markdown_summary = (
        f"\n\n- **Total Items**: {total_items}\n"
        f"- **Comments**: {comment_count}\n"
        f"- **Submissions**: {submission_count}"
    )

    if total_items >= WENJU_SETTINGS['max_queue']:
        send_discord_alert(
            subject=f"{total_items} items in r/translator Modqueue",
            message=(
                f"There are now **{total_items} items** in [the modqueue]"
                f"(https://www.reddit.com/r/translator/about/modqueue). "
                f"Please help clear some of these items if you can."
                f"{markdown_summary}"
            ),
            webhook_name='alert'
        )

    return


@task(schedule='weekly')
def update_verified_list():
    """
    Updates the subreddit wiki page 'verified' with a sorted list of verified
    users organized by language. Also flags users with problematic flairs
    (e.g., missing brackets, incorrect flair class, or misuse of verified emoji).
    """

    formatted_text = []
    users_to_fix = []
    master_list = {}
    users_by_flair = {}

    # Retrieve all users with flair on the subreddit.
    for flair in REDDIT.subreddit('translator').flair(limit=None):
        flair_text = flair.get("flair_text")
        if flair_text:
            master_list[str(flair["user"])] = (
                flair_text,
                flair.get("flair_css_class"),
            )

    # Process users with 'verified' flair.
    for user, (flair_text, flair_css) in master_list.items():

        if flair_css == "verified":
            # Attempt to extract the verified language(s) from brackets.
            match = re.findall(r"\[(.*?)]", flair_text)
            if not match:
                users_to_fix.append(user)
                continue

            verified_for = match[0]

            # Sanitize and split the language text for conversion.
            clean_text = re.sub(r"[^\w\s]", " ", verified_for)
            for word in clean_text.split():
                result = converter(word, False).preferred_code  # We want the language code
                if result:
                    users_by_flair.setdefault(result, []).append(user)

        elif flair_css not in {"verified", "moderator"} and ":verified:" in flair_text:
            # User has a verified emoji but no verified flair class.
            users_to_fix.append(user)

    # Construct the formatted wiki list.
    for language_code in sorted(users_by_flair):
        if language_code == "en":  # Always exclude English.
            continue

        language_name = converter(language_code).name
        unique_users = sorted({u.lower() for u in users_by_flair[language_code]})
        header = f"\n###### `{language_code}` {language_name} ({len(unique_users)})"
        formatted_text.append(header)
        formatted_text.extend(f"* u/{user}" for user in unique_users)

    # Combine everything into final text.
    final_text = "\n".join(formatted_text)

    if users_to_fix:
        final_text += f"\n\nFor moderators, *check*: {users_to_fix}"

    # Prepare wiki page update.
    verified_page = REDDIT.subreddit('translator').wiki["verified"]
    anchor = "## List of Verified Translators on r/translator"

    # Keep the upper portion of the page intact.
    upper_portion = verified_page.content_md.split(anchor, 1)[0]
    date_stamp = f"\n*Last Updated {datetime.date.today():%Y-%m-%d}*\n"
    final_update = "\n".join([upper_portion, anchor, date_stamp, final_text])

    # Commit the edit.
    verified_page.edit(content=final_update, reason="Updating the verified list.")
    logger.info("[WJ] > Verified list on the wiki updated.")

    return


@task(schedule='weekly')
def weekly_notify_list_statistics_calculator():
    """
    Gather statistics on the state of our notifications and
    write the results to a Markdown file.

    :return: None
    """
    today_date = date.today().strftime("%Y-%m-%d")

    # Fetch all notification subscriptions from the database
    cursor_main.execute("SELECT * FROM notify_users")
    all_subscriptions = cursor_main.fetchall()

    # Extract unique language codes
    all_lang_codes = list({sub[0] for sub in all_subscriptions})

    # Build the Markdown table of languages and subscriber counts
    format_lines = []
    for code in sorted(all_lang_codes):
        cursor_main.execute(
            "SELECT COUNT(*) FROM notify_users WHERE language_code = ?", (code,)
        )
        code_num = cursor_main.fetchone()[0]
        name = converter(code)[1] or code.title()  # Meta/community fallback
        format_lines.append(f"{name} | {code_num}")

    # Calculate statistics
    unique_lang = len(all_lang_codes)
    total_subscriptions = len(all_subscriptions)
    average_per = total_subscriptions / unique_lang if unique_lang else 0

    # Identify duplicate subscriptions
    duplicates = [item for item, count in Counter(all_subscriptions).items() if count > 1]
    dupe_subs = duplicates or ""

    # Compose summary section
    summary = (
        f"## Notifications Database Data for {today_date}\n\n"
        f"* Unique entries in notifications database: {unique_lang:,} languages\n"
        f"* Total subscriptions in notifications database: {total_subscriptions:,} subscriptions\n"
        f"* Average notification subscriptions per entry: {average_per:.2f} subscribers\n"
    )

    # Build the subscriber table
    header = "\n\nLanguage | Subscribers\n-----|-----\n"
    total_table = header + "\n".join(format_lines)
    logger.debug(f"[WY] notify_list_statistics_calculator: Total = {total_subscriptions:,}")

    # Calculate missing ISO 639-1 languages
    ignore_codes = {"bh", "en", "nn", "nb"}
    iso_sorted = sorted(MAIN_LANGUAGES.keys(), key=str.lower)
    missing_codes = [
        f"{code} | {converter(code)[1]}"
        for code in iso_sorted
        if code not in all_lang_codes and len(code) == 2 and code not in ignore_codes
    ]
    missing_codes_num = len(missing_codes)

    missing_codes_section = (
        f"\n### No Subscribers ({missing_codes_num} ISO 639-1 languages)\n"
        f"Code | Language\n---|----\n"
        + "\n".join(missing_codes)
    )

    # Combine everything into the final Markdown report
    notify_log_data = f"{summary}\n{total_table}\n{missing_codes_section}\n\n{dupe_subs}"

    # Write to a file labeled with today's date
    output_path = f"{log_directory}/{today_date}_Notifications.md"
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(notify_log_data)

    logger.info("[WJ] weekly_notify_list_statistics_calculator: Notifications data saved.")
