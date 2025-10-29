#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
import re
import sqlite3
import time
from collections import Counter
from datetime import date

from praw.exceptions import RedditAPIException
from praw.models import TextArea

from config import SETTINGS, get_reports_directory, logger
from connection import (
    REDDIT,
    REDDIT_HELPER,
    create_mod_note,
    reddit_status_check,
    widget_update,
)
from database import db
from discord_utils import send_discord_alert
from languages import (
    converter,
    define_language_lists,
    get_country_emoji,
    get_lingvos,
    select_random_language,
)
from lookup.reference import get_language_reference
from lookup.wp_utils import wikipedia_lookup
from models.ajo import Ajo, ajo_loader
from tasks import WENJU_SETTINGS, task
from time_handling import (
    get_current_utc_date,
    get_current_utc_time,
    time_convert_to_utc,
)
from utility import format_markdown_table_with_padding


@task(schedule="hourly")
def reddit_status_report():
    """
    Wrapper that calls reddit_status_check() and returns a
    Markdown-formatted summary. This is an API that indicates whether
    Reddit is having issues.

    :returns:
        - Markdown text if incidents exist
    """
    incidents = reddit_status_check()

    if incidents is None:
        logger.warning("Unable to reach Reddit Status API.")
        return

    if not incidents:
        logger.debug("No Reddit Status incidents found.")
        return

    lines = ["### ⚠️ Active Reddit Incidents\n"]
    for incident in incidents:
        name = incident.get("name", "Unknown")
        status = incident.get("status", "N/A")
        impact = incident.get("impact", "unknown")
        created = time_convert_to_utc(incident.get("created_at", "N/A"))
        updated = time_convert_to_utc(incident.get("updated_at", "N/A"))
        shortlink = incident.get("shortlink") or incident.get("shortlink_url") or ""

        latest_update = None

        updates = incident.get("incident_updates") or []
        if updates:
            # Take the most recent update by created_at timestamp
            latest_update = (
                sorted(updates, key=lambda u: u.get("created_at", ""), reverse=True)[0]
                .get("body", "")
                .strip()
            )

        logger.info(
            f"[Reddit Incident] {name} — {status.upper()} ({impact})\n"
            f"Created: {created} | "
            f"Updated: {updated}\n"
            f"{('Latest update: ' + latest_update) if latest_update else 'No update text.'}\n"
            f"Link: {shortlink or 'N/A'}"
        )

        title = f"**[{name}]({shortlink})**" if shortlink else f"**{name}**"

        lines.append(
            f"- {title}  \n"
            f"  - **Status:** {status.title()} ({impact})  \n"
            f"  - **Created:** [{created}](https://time.lol/#{created})  \n"
            f"  - **Updated:** [{updated}](https://time.lol/#{updated})"
        )

    alert_text = "\n".join(lines)
    send_discord_alert("Reddit Status", alert_text, "reddit_status")

    return


@task(schedule="hourly")
def monitor_controversial_comments():
    """
    Checks r/translator hourly for heavily downvoted comments
    and flags them for review via a Discord alert.

    :return: None
    """

    # Iterate over the latest 100 comments in the subreddit
    for comment in REDDIT.subreddit(SETTINGS["subreddit"]).comments(limit=100):
        # Extract comment info
        score = comment.score
        removed = comment.removed
        mod_reports = comment.mod_reports
        permalink = comment.permalink
        comment_id = comment.id
        created_utc = int(comment.created_utc)
        author_name = comment.author.name if comment.author else "[deleted]"

        # Check if this comment has already been acted upon
        query = "SELECT comment_id FROM acted_comments WHERE comment_id = ?"
        already_acted = db.fetch_main(query, (comment_id,))

        # Criteria: score <= threshold, not removed, not reported, not already acted upon
        score_threshold = WENJU_SETTINGS["controversial_score_threshold"]
        if (
            score <= score_threshold
            and not removed
            and not mod_reports
            and not already_acted
        ):
            create_mod_note(
                "ABUSE_WARNING",
                author_name,
                f"Authored heavily downvoted comment at https://www.reddit.com/{permalink}",
            )

            # Send alert to Discord
            send_discord_alert(
                "Comment with Excessive Downvotes",
                f"[This comment](https://www.reddit.com{permalink}) "
                f"has many downvotes (`{score}`). Please check the thread.",
                "alert",
            )

            # Record this action in the database
            insert_query = """
                           INSERT INTO acted_comments (comment_id, created_utc, comment_author_username, action_type)
                           VALUES (?, ?, ?, ?) \
                           """
            cursor = db.cursor_main
            cursor.execute(
                insert_query,
                (comment_id, created_utc, author_name, "controversial_comment"),
            )
            db.conn_main.commit()

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
            "SELECT * FROM ajo_database WHERE created_utc >= ?", (cutoff_timestamp,)
        )
    except sqlite3.Error as e:
        logger.error(f"generate_24h_statistics_snippet: Database error: {e}")
        return None

    if not stored_ajos:
        logger.info(
            "generate_24h_statistics_snippet: No posts found in the last 24 hours."
        )
        return None

    # Extract statuses safely.
    statuses = []
    for post_id, _, data, *rest in stored_ajos:
        try:
            ajo_data = ajo_loader(post_id)
            if ajo_data is not None:
                statuses.append(ajo_data.status)
            else:
                logger.warning(f"Ajo `{post_id}` could not be loaded, skipping")
        except Exception as e:
            logger.warning(f"Skipping malformed entry: {e}: {data}")

    if not statuses:
        logger.info("generate_24h_statistics_snippet: No valid statuses found.")
        return None

    # Count post categories.
    count_untranslated = statuses.count("untranslated")
    count_review = statuses.count("doublecheck")
    count_translated = statuses.count("translated")
    total = len(statuses)

    translated_percentage = round(((count_translated + count_review) / total) * 100)

    snippet = (
        f"### Last 24H: "
        f"✗: **{count_untranslated}** "
        f"✓: **{count_review}** "
        f"✔: **{count_translated}** "
        f"({translated_percentage}%)"
    )

    logger.debug(f"generate_24h_statistics_snippet: {snippet}")
    return snippet


@task(schedule="hourly")
def update_sidebar_statistics():
    """
    Updates the r/translator sidebar with the latest statistics
    from the past 24 hours.
    Since June 2019, this function updates the Old Reddit sidebar
    by directly editing the wikipage that hosts it.

    :return: None
    """
    current_time_str = get_current_utc_time()

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
        sidebar_wikipage = REDDIT.subreddit(SETTINGS["subreddit"]).wiki[
            "config/sidebar"
        ]
        sidebar_contents = sidebar_wikipage.content_md.rsplit("\n", 1)[0]
        new_sidebar_contents = f"{sidebar_contents}\n{sidebar_bit}"

        sidebar_wikipage.edit(
            content=new_sidebar_contents,
            reason=f"Updating sidebar at {current_time_str}",
        )

        logger.info(f"Updated Old Reddit sidebar with 24-hour stats: {sidebar_bit}")
    except Exception as e:
        logger.error(f"Failed to update Old Reddit sidebar: {e}")
        return

    # --- Update New Reddit widget ---
    widgets = REDDIT.subreddit(SETTINGS["subreddit"]).widgets
    target_widget_id = "widget_13r63qu7r63we"

    active_widget = next(
        (
            w
            for w in widgets.sidebar
            if isinstance(w, TextArea) and w.id == target_widget_id
        ),
        None,
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


@task(schedule="daily")
def language_of_the_day(selected_language=None):
    """
    Formats text for a randomly selected language of the day (ISO 639-3
    by default) in Markdown for inclusion in the sidebar of the
    subreddit as a widget (New Reddit). If the random language is
    invalid (e.g. a dead language) the function will return `None`
    and fail gracefully.

    :param selected_language: A selected language to override the random
                              selection of languages.
    :return: The text of the widget, or `None` if the information was
             unable to be obtained.
    """
    # Get today's date
    today = date.today()

    # Check if today is an even day. Post ISO 639-1 languages on even
    # days in order to give some more familiar languages.
    if today.day % 2 == 0:
        iso_639_1_day = True
    else:
        iso_639_1_day = False

    # Language selection logic.
    # Select a random language and get its data. (returns a Lingvo)
    if not selected_language and not iso_639_1_day:
        today_language = select_random_language()
    elif not selected_language and iso_639_1_day:
        # Pick a random ISO 639-1 language.
        today_language = select_random_language(True)
        logger.info("Selecting an ISO 639-1 language today.")
    else:
        today_language = converter(selected_language, preserve_country=True)

    wikipedia_search_term = f"ISO_639:{today_language.language_code_3}"
    wikipedia_redirect_link = f"https://en.wikipedia.org/wiki/{wikipedia_search_term}"
    logger.info(
        f"Language of the day is: {today_language.name} "
        f"(`{today_language.language_code_3}`)."
    )

    # Try and fetch the relevant subreddit for that language.
    if iso_639_1_day:
        language_subreddit = today_language.subreddit
        if language_subreddit:
            logger.info(f"> Subreddit for the language is {language_subreddit}.")
    else:
        language_subreddit = None

    # Get data from Wikipedia using the wikipedia_lookup function.
    wikipedia_entry = wikipedia_lookup(wikipedia_search_term)
    if not wikipedia_entry:
        return None

    # Extract just the summary text from the formatted entry.
    # Remove markdown formatting to get clean text for the widget.
    language_entry_summary = wikipedia_entry
    if "\n\n> " in language_entry_summary:
        language_entry_summary = language_entry_summary.split("\n\n> ")[1]
    if "\n\n" in language_entry_summary:
        language_entry_summary = language_entry_summary.split("\n\n")[0]
    language_entry_summary = language_entry_summary.strip()

    # Fetch data from Ethnologue via the Wayback Machine if it's not an
    # ISO 639-1 language, and then refresh the Lingvo.
    if not today_language.language_code_1:
        get_language_reference(today_language.language_code_3)
        # Force refresh
        language_data = get_lingvos(force_refresh=True)
        logger.info("Variable refreshed.")
        # Use the refreshed data directly
        today_language = language_data.get(today_language.language_code_3)

    # Get the language's country/region flag for better formatting.
    if today_language.country:
        country_emoji = get_country_emoji(today_language.country)
    else:
        country_emoji = today_language.country_emoji

    language_family_link = (
        f"https://en.wikipedia.org/wiki/"
        f"{today_language.family.replace('_', ' ')}_languages"
    )

    # Format the text together.
    header = f"#### **{today_language.name}** "
    if today_language.language_code_1:
        header += f"`({today_language.language_code_1}`/`{today_language.language_code_3})`\n\n"
    else:
        header += f"`({today_language.preferred_code})`\n\n"

    # Build the body with conditional country line
    country_line = ""
    if country_emoji is not None:
        country_line = f"* **Country**: {country_emoji} {today_language.country}\n"

    body = (
        f"* **Family**: [{today_language.family}]({language_family_link})\n"
        f"{country_line}"
        f"* **Population**: {today_language.population:,}"
    )

    if language_subreddit:
        body += f"\n* **Subreddit**: {language_subreddit}"
    summary = f"\n\n{language_entry_summary}"
    full_text = header + body + summary

    # Update the widget.
    update_success = widget_update("widget_1dn822a2cowgr", full_text)
    if update_success:
        # Choose 'a' or 'an' based on the first letter of the language family
        article = (
            "an"
            if today_language.family and today_language.family[0].lower() in "aeiou"
            else "a"
        )
        code_string = f"`{today_language.preferred_code}`"

        # Notify Discord.
        language_blurb = (
            f"The language of the day is **[{today_language.name}]"
            f"({wikipedia_redirect_link})** ({code_string}), "
            f"{article} {today_language.family} language. {language_entry_summary}"
        )

        # Build the title with conditional emoji
        if country_emoji is not None:
            title = f"Language of the Day: {country_emoji} {today_language.name}"
        else:
            title = f"Language of the Day: {today_language.name}"

        send_discord_alert(
            title,
            language_blurb,
            "lotd",
        )

    return full_text


@task(schedule="daily")
def modqueue_assessor():
    """
    Checks how many items are in the modqueue and alerts Discord
    if the count exceeds a certain threshold.
    """
    modqueue_items = list(
        REDDIT.subreddit(SETTINGS["subreddit"]).mod.modqueue(limit=None)
    )
    total_items = len(modqueue_items)

    # Count comments and submissions by type prefix
    comment_count = sum(1 for item in modqueue_items if item.fullname.startswith("t1_"))
    submission_count = sum(
        1 for item in modqueue_items if item.fullname.startswith("t3_")
    )

    markdown_summary = (
        f"\n\n- **Total Items**: {total_items}\n"
        f"- **Comments**: {comment_count}\n"
        f"- **Submissions**: {submission_count}"
    )

    if total_items >= WENJU_SETTINGS["max_queue"]:
        send_discord_alert(
            subject=f"{total_items} items in r/translator Modqueue",
            message=(
                f"There are now **{total_items} items** in [the modqueue]"
                f"(https://www.reddit.com/r/translator/about/modqueue). "
                f"Please help clear some of these items if you can."
                f"{markdown_summary}"
            ),
            webhook_name="alert",
        )

    return


@task(schedule="weekly")
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
    for flair in REDDIT.subreddit(SETTINGS["subreddit"]).flair(limit=None):
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
                result = converter(
                    word, False
                ).preferred_code  # We want the language code
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
        # Create Markdown list with user links
        user_links = [
            f"* [u/{username}](https://www.reddit.com/user/{username})"
            for username in users_to_fix
        ]
        user_list = "\n".join(user_links)

        mod_fix_alert = (
            f"The following users have irregular verified flairs:\n{user_list}"
        )
        send_discord_alert("Irregular Verified User Flairs", mod_fix_alert, "alert")

    # Prepare wiki page update.
    verified_page = REDDIT.subreddit(SETTINGS["subreddit"]).wiki["verified"]
    anchor = "## List of Verified Translators on r/translator"

    # Keep the upper portion of the page intact.
    upper_portion = verified_page.content_md.split(anchor, 1)[0]
    date_stamp = f"\n*Last Updated {get_current_utc_date()}*\n"
    final_update = "\n".join([upper_portion, anchor, date_stamp, final_text])

    # Commit the edit.
    verified_page.edit(content=final_update, reason="Updating the verified list.")
    logger.info("> Verified list on the wiki updated.")

    return


@task(schedule="weekly")
def deleted_posts_assessor(
    start_time: int | None = None, end_time: int | None = None
) -> None:
    """
    Gathers data on individuals who deleted their posts from the subreddit,
    focusing on those who deleted translated posts without thanking their translators.

    :param start_time: Starting boundary as a UNIX timestamp.
    :param end_time: Ending boundary as a UNIX timestamp.
    :return: None — saves the report to a Markdown log file.
    """
    reports_directory = get_reports_directory()
    today = get_current_utc_date()

    # Default to the last 7 days if no time range provided
    if start_time is None or end_time is None:
        end_time = int(time.time())
        start_time = end_time - 604800  # 7 days

    # Fetch relevant Ajo entries from the database
    query = "SELECT * FROM ajo_database WHERE created_utc BETWEEN ? AND ?"
    stored_ajos = db.fetchall_ajo(query, (start_time, end_time))
    logger.debug(f"Fetched {len(stored_ajos)} entries from local_database.")

    # Parse and store relevant Ajos keyed by post ID
    relevant_ajos = {row[0]: Ajo.from_dict(row[2]) for row in stored_ajos}

    # Retrieve submissions via Reddit API
    submission_fullnames = [f"t3_{pid}" for pid in relevant_ajos]
    submissions = list(REDDIT_HELPER.info(fullnames=submission_fullnames))

    deleted_submissions = {}
    for submission in submissions:
        author_name = getattr(submission.author, "name", None)
        if author_name:
            logger.debug(f"Author u/{author_name} is active.")
        else:
            deleted_submissions[submission.id] = submission
            logger.debug("Author is deleted.")

    deleted_percentage = (
        len(deleted_submissions) / len(submissions) if submissions else 0
    )
    logger.info(f"Deleted percentage: {deleted_percentage:.2%}")

    authors = []
    translated_deleted = []

    # Compare deleted posts with cached Ajo data
    for post_id, submission in deleted_submissions.items():
        cached = relevant_ajos.get(post_id, {})
        author = cached.get("author", "[unknown]")
        authors.append(author)

        # Flag posts marked as translated or doublecheck
        if cached.get("status") in {"translated", "doublecheck"}:
            translated_deleted.append((submission, author))

    # Identify deleted posts where OP never commented (impolite deletions)
    impolite_entries = []
    for submission, original_author in translated_deleted:
        comments = submission.comments.list()
        if not any(
            getattr(comment.author, "name", None) == original_author
            for comment in comments
        ):
            impolite_entries.append((submission, original_author))

    # Summarize frequent deleters
    active_authors = [a for a in authors if a not in ("[deleted]", "[unknown]")]
    offender_counts = Counter(active_authors)
    top_offenders = offender_counts.most_common(5)

    offenders_text = "#### Most Frequent Deleters\n\n" + "\n".join(
        f"* u/{name}: {count}" for name, count in top_offenders
    )

    # Summarize impolite deletions
    if impolite_entries:
        impolite_table = "\n".join(
            f"| u/{author} | [{submission.title}]"
            f"(https://www.reddit.com{submission.permalink}) |"
            for submission, author in impolite_entries
        )
        impolite_text = (
            "\n\n#### Deleted Without Thanks (Impolite)\n\n"
            "| Username | Link |\n|----|----|\n" + impolite_table
        )
    else:
        impolite_text = "\n\n#### Deleted Without Thanks (Impolite)\n\n_None_"

    # Build the report
    report = (
        f"## Deleted Posts Data for {today}\n\n"
        f"**Deleted Posts Percentage:** {deleted_percentage:.2%} "
        f"({len(deleted_submissions)}/{len(submissions)})\n\n"
        f"{offenders_text}"
        f"{impolite_text}"
    )

    # Save the report to Markdown
    log_path = f"{reports_directory}/{today}_Deleted.md"
    with open(log_path, "w", encoding="utf-8") as f:
        f.write(report)

    logger.info(f"weekly_deleted_posts_assessor: Report saved to {log_path}.")

    return


@task(schedule="weekly")
def notify_list_statistics_calculator() -> None:
    """
    Gather statistics on the state of our notifications database and
    write the results to a Markdown file.

    :return: None
    """
    reports_directory = get_reports_directory()
    today = get_current_utc_date()
    # Fetch ISO 639-1 languages and ensure they are all strings
    iso_639_1_languages_raw = define_language_lists().get("ISO_639_1", [])
    iso_639_1_languages: list[str] = [
        str(code) for code in iso_639_1_languages_raw if code is not None
    ]

    # Fetch all notification subscriptions from the main database
    all_subscriptions = db.fetchall_main(
        "SELECT * FROM notify_users",
        (),  # not actually in AJO but uses fetch_ajo pattern
    )

    if not all_subscriptions:
        logger.warning("[WY] No subscriptions found in notify_users.")
        return

    # Extract unique language codes and ensure they are strings
    all_lang_codes = sorted(
        {str(row[0]) for row in all_subscriptions if row[0] is not None}
    )

    # Build Markdown table of languages and subscriber counts
    format_lines = []
    for code in all_lang_codes:
        if code in SETTINGS["internal_post_types"]:
            continue
        row = db.fetch_main(
            "SELECT COUNT(*) FROM notify_users WHERE language_code = ?",
            (code,),
        )
        code_count = row[0] if row else 0
        name = converter(code).name
        format_lines.append(f"| {name} | `{code}` | {code_count} |")

    # Calculate statistics
    unique_langs = len(all_lang_codes)
    total_subs = len(all_subscriptions)
    average_per = total_subs / unique_langs if unique_langs else 0

    # Identify duplicate subscriptions
    duplicates = [
        item for item, count in Counter(all_subscriptions).items() if count > 1
    ]
    dupe_subs = duplicates or ""

    # Compose summary section
    summary = (
        f"## Notifications Database Data for {today}\n\n"
        f"* Unique entries in notifications database: {unique_langs:,} languages\n"
        f"* Total subscriptions in notifications database: {total_subs:,} subscriptions\n"
        f"* Average notification subscriptions per entry: {average_per:.2f} subscribers\n"
    )

    # Subscriber table section
    header = "\n\n| Language | Code | Subscribers |\n|------|------|-----|\n"
    total_table = header + "\n".join(format_lines)
    total_table = format_markdown_table_with_padding(total_table)
    logger.debug(f"[WY] notify_list_statistics_calculator: Total = {total_subs:,}")

    # Calculate missing ISO 639-1 languages (type-safe)
    ignore_codes = {"bh", "en", "nn", "nb"}
    iso_sorted = sorted(iso_639_1_languages, key=lambda x: x.lower())
    missing_codes = [
        f"| `{code}` | {converter(code).name} |"
        for code in iso_sorted
        if code not in all_lang_codes and len(code) == 2 and code not in ignore_codes
    ]
    missing_num = len(missing_codes)

    missing_section = (
        f"\n### No Subscribers ({missing_num} ISO 639-1 languages)\n"
        "| Code | Language Name |\n|---|----|\n" + "\n".join(missing_codes)
    )
    missing_section = format_markdown_table_with_padding(missing_section)

    # Combine into final Markdown
    final_text = f"{summary}\n{total_table}\n{missing_section}\n\n{dupe_subs}"

    # Write to file
    output_path = f"{reports_directory}/{today}_Notifications.md"
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(final_text)

    logger.info(f"notify_list_statistics_calculator: Report saved to {output_path}.")

    return


if __name__ == "__main__":
    print(language_of_the_day())
