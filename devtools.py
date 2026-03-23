#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
Central dev/debugging entrypoint.

Run individual check functions or execute this file directly to run all checks.
"""

import asyncio
import logging
from pprint import pprint

from wasabi import msg

from config import SETTINGS, enable_debug_logging
from database import initialize_all_databases, search_database
from error import display_event_errors
from hermes.tools import get_statistics, test_parser
from integrations.ai import fetch_image_description
from integrations.search_handling import build_search_results, fetch_search_reddit_posts
from lang.languages import converter
from lang.languages import logger as lang_logger
from lang.languages import parse_language_list
from models.ajo import Ajo, ajo_loader, determine_flair_and_update
from models.instruo import Instruo
from models.komando import extract_commands_from_text
from models.kunulo import Kunulo
from monitoring.points import points_post_retriever, points_user_retriever
from reddit.connection import (
    REDDIT_HELPER,
    get_random_useragent,
    reddit_status_check,
    search_removal_reasons,
    submission_from_input,
)
from reddit.notifications import fetch_usernames_for_lingvo
from reddit.startup import template_retriever
from reddit.verification import get_verified_thread
from reddit.wiki import fetch_most_requested_languages
from title.title_handling import process_title
from utility import fetch_youtube_length, is_valid_image_url
from wenju.iso_updates import fetch_iso_reports
from ziwen_lookup.ja import ja_character, ja_word
from ziwen_lookup.ko import ko_word
from ziwen_lookup.match_helpers import lookup_matcher
from ziwen_lookup.wiktionary import wiktionary_search
from ziwen_lookup.wp_utils import wikipedia_lookup
from ziwen_lookup.zh import (
    old_chinese_search,
    variant_character_search,
    zh_character,
    zh_word,
    zh_word_chengyu_supplement,
)

# ─── lang ─────────────────────────────────────────────────────────────────────


def check_lang_converter() -> None:
    """Interactive test for the language converter."""
    enable_debug_logging()
    my_test = input("Enter the string you wish to test with the converter: ")
    with msg.loading(f"Converting '{my_test}'..."):
        converter_result = converter(my_test)
    if converter_result:
        msg.good(
            f"Input: `{my_test}` → Preferred Code: {converter_result.country_emoji} "
            f"`{converter_result.preferred_code}`"
        )
        pprint(vars(converter_result))
        msg.info(f"Country flag emoji: {converter_result.country_emoji}")
    else:
        msg.warn("Did not match anything.")


def check_lang_parse() -> None:
    """Interactive test for the language list parser."""
    lang_logger.setLevel(logging.DEBUG)
    language_list_input = input(
        "Enter the language list from a subscription message to parse: "
    )
    with msg.loading("Parsing language list..."):
        parse_result = parse_language_list(language_list_input)
    pprint(parse_result)


# ─── error ────────────────────────────────────────────────────────────────────


def check_error_display_event_errors() -> None:
    """Display ERROR-level entries from the events log within the last N days."""
    days_raw = input("Number of days to look back (default 7): ").strip()
    days = int(days_raw) if days_raw.isdigit() else 7
    with msg.loading(f"Scanning events log for errors in the last {days} day(s)..."):
        results = display_event_errors(days)
    if results:
        msg.warn(f"{len(results)} error(s) found:")
        for line in results:
            print(line)
    else:
        msg.good(f"No errors found in the last {days} day(s).")


# ─── integrations ─────────────────────────────────────────────────────────────


def check_integrations_search() -> None:
    """Interactive test for Reddit search and result formatting."""
    while True:
        my_search = input("Please enter your search term (x to back out): ").strip()
        if my_search.lower() == "x":
            return
        with msg.loading(f"Searching Reddit for '{my_search}'..."):
            searched_posts = fetch_search_reddit_posts(my_search)
        msg.info(build_search_results(searched_posts, my_search))


def check_integrations_ai_image_description() -> None:
    """ai: Fetch and display an AI-generated description for an image URL."""
    image_url = input("Enter a public image URL (x to back out): ").strip()
    if image_url.lower() == "x":
        return
    with msg.loading("Fetching image description..."):
        description = fetch_image_description(image_url)
    if description:
        msg.good(f"Description: {description}")
    else:
        msg.fail("Failed to fetch image description.")


# ─── hermes ───────────────────────────────────────────────────────────────────


def check_hermes_statistics() -> None:
    """Print aggregated language statistics from the Hermes database."""
    get_statistics()


def check_hermes_parser() -> None:
    """Fetch live posts and print title_parser output for each."""
    limit_raw = input("Number of posts to fetch (default 100): ").strip()
    limit = int(limit_raw) if limit_raw.isdigit() else 100
    with msg.loading(f"Fetching {limit} posts..."):
        test_parser(REDDIT_HELPER, limit=limit)


# ─── monitoring ───────────────────────────────────────────────────────────────


def check_monitoring_user() -> None:
    """Look up point totals for a given Reddit username."""
    my_username = input("Enter a Reddit username: ")
    with msg.loading(f"Retrieving points for u/{my_username}..."):
        result = points_user_retriever(my_username)
    msg.info(str(result))


def check_monitoring_post() -> None:
    """Look up all point records for a given Reddit post ID."""
    my_post_id = input("Enter a Reddit post ID: ")
    with msg.loading(f"Retrieving point records for {my_post_id}..."):
        my_post_result = points_post_retriever(my_post_id)
    if my_post_result:
        msg.info(f"Point records for post {my_post_id}:")
        for my_comment_id, my_username, my_points in my_post_result:
            msg.info(
                f"  Comment {my_comment_id} | u/{my_username} | {my_points} points"
            )
    else:
        msg.warn(f"No point records found for post ID: {my_post_id}")


# ─── title ────────────────────────────────────────────────────────────────────


def check_title_manual() -> None:
    """Test the title parser against a manually entered title string."""
    logger_title = logging.getLogger("title_handling")
    logger_title.setLevel(logging.DEBUG)
    my_test = input("Enter the title string you wish to test: ")
    titolo_output = process_title(my_test, None, False)
    pprint(vars(titolo_output))


def check_title_reddit() -> None:
    """Fetch the last 50 live Reddit posts and run each through the title parser."""
    logger_title = logging.getLogger("title_handling")
    logger_title.setLevel(logging.INFO)
    with msg.loading("Fetching 50 live posts..."):
        submissions = list(REDDIT_HELPER.subreddit(SETTINGS["subreddit"]).new(limit=50))
    for submission in submissions:
        msg.divider(submission.title[:60])
        titolo_output = process_title(submission.title, submission, False)
        pprint(vars(titolo_output))


# ─── database ─────────────────────────────────────────────────────────────────


def check_database_search() -> None:
    """Search the Ajo database by username or post ID."""
    term_to_search = input("Enter the search term (username or post_id): ")
    type_to_search = input("Enter the search type (user/post): ")
    with msg.loading("Searching database..."):
        derived_ajos = search_database(term_to_search, type_to_search)
    for item in derived_ajos:
        msg.divider(str(getattr(item, "id", "result")))
        pprint(vars(item))


def check_database_initialize() -> None:
    """Initialize all databases if they do not already exist."""
    with msg.loading("Initializing databases..."):
        initialize_all_databases()
    msg.good("Database initialization complete.")


# ─── utility ──────────────────────────────────────────────────────────────────


def check_utility_youtube() -> None:
    """Fetch and display the duration of a YouTube video by URL."""
    test_url = input("Enter a YouTube URL: ").strip()
    with msg.loading("Fetching video length..."):
        length_seconds = fetch_youtube_length(test_url)
    if length_seconds is not None:
        msg.good(f"Video length: {length_seconds} seconds")
    else:
        msg.fail("Failed to fetch video length.")


def check_utility_is_valid_image_url() -> None:
    """Validate whether a URL is recognised as a valid image URL."""
    test_url = input("Enter a URL to validate as an image URL: ").strip()
    with msg.loading("Checking URL..."):
        result = is_valid_image_url(test_url)
    if result:
        msg.good(f"'{test_url}' is a valid image URL.")
    else:
        msg.warn(f"'{test_url}' is NOT a valid image URL.")


# ─── models ───────────────────────────────────────────────────────────────────


def check_models_ajo_url() -> None:
    """ajo: Load a Reddit post by URL or ID, parse its title and build an Ajo."""
    test_url = input("Enter a Reddit post URL or ID (x to back out): ")
    if test_url.strip().lower() == "x":
        return
    with msg.loading("Loading submission and building Ajo..."):
        test_post = submission_from_input(test_url)
        if not test_post:
            msg.fail("Invalid submission.")
            return
        test_titolo = process_title(test_post.title)
        post_ajo = Ajo.from_titolo(test_titolo, test_post)
    msg.divider("titolo")
    pprint(vars(test_titolo))
    msg.divider("ajo")
    pprint(vars(post_ajo))


def check_models_ajo_live() -> None:
    """ajo: Fetch the last 3 live Reddit posts and build an Ajo for each."""
    with msg.loading("Fetching 3 live posts..."):
        submissions = list(REDDIT_HELPER.subreddit(SETTINGS["subreddit"]).new(limit=3))
    for submission_new in submissions:
        msg.divider(submission_new.title[:60])
        ajo_new = Ajo.from_titolo(process_title(submission_new.title), submission_new)
        pprint(vars(ajo_new))


def check_models_ajo_load() -> None:
    """ajo: Load an Ajo from the database by ID and determine its flair."""
    test_ajo_input = input("Enter the ID of the Ajo: ")
    with msg.loading(f"Loading Ajo {test_ajo_input}..."):
        test_ajo = ajo_loader(test_ajo_input)
    if test_ajo is None:
        msg.fail(f"Could not load Ajo with ID: {test_ajo_input}")
    else:
        msg.divider("ajo")
        msg.info(f"ID: {test_ajo.id}")
        msg.info(f"Lingvo: {test_ajo.lingvo}")
        msg.info(f"Language Name: {test_ajo.language_name}")
        pprint(vars(test_ajo))
        determine_flair_and_update(test_ajo)
        msg.good(f"Flair CSS : {test_ajo.output_post_flair_css}")
        msg.good(f"Flair text: {test_ajo.output_post_flair_text}")


def check_models_kunulo() -> None:
    """kunulo: Load a Reddit submission by URL or ID and build a Kunulo from its comments."""
    test_url = input("Enter a Reddit post URL or ID (x to back out): ")
    if test_url.strip().lower() == "x":
        return
    with msg.loading("Building Kunulo from submission..."):
        test_post = submission_from_input(test_url)
        test_kunulo = Kunulo.from_submission(test_post)
    pprint(test_kunulo)


def check_models_instruo_url() -> None:
    """instruo: Load a Reddit comment by URL and build an Instruo from it."""
    comment_url = input("Enter Reddit comment URL (x to back out): ").strip()
    if comment_url.lower() == "x":
        return
    try:
        with msg.loading("Loading comment and building Instruo..."):
            test_comment = REDDIT_HELPER.comment(url=comment_url)
            test_ajo = ajo_loader(test_comment.submission.id)
            parent_lingvos = [test_ajo.lingvo] if test_ajo else []
            test_instruo = Instruo.from_comment(
                test_comment, parent_languages=parent_lingvos
            )
        msg.good(f"Instruo created: {test_instruo}")
        pprint(vars(test_instruo))
    except Exception as ex:
        msg.fail(f"Error: {ex}")


def check_models_instruo_text() -> None:
    """instruo: Enter raw text and check whether it contains a command."""
    testing_text = input("Enter text to parse for commands: ")
    test_instruo = Instruo.from_text(testing_text)
    msg.info(str(test_instruo))


def check_models_komando() -> None:
    """komando: Enter raw comment text and extract all Komando commands from it."""
    my_input = input("Enter the comment text with commands you'd like to test here: ")
    commands_new = extract_commands_from_text(my_input)
    if not commands_new:
        msg.warn("No commands found.")
    else:
        for command_new in commands_new:
            msg.good(f"* {command_new}")


# ─── ziwen_lookup ─────────────────────────────────────────────────────────────


def check_ziwen_lookup_zh_character() -> None:
    """zh: Look up a single Chinese character."""
    my_test = input("Enter a Chinese character to look up: ")
    with msg.loading(f"Looking up '{my_test}'..."):
        result = asyncio.run(zh_character(my_test))
    msg.info(str(result))


def check_ziwen_lookup_zh_word() -> None:
    """zh: Look up a Chinese word."""
    my_test = input("Enter a Chinese word to look up: ")
    with msg.loading(f"Looking up '{my_test}'..."):
        result = asyncio.run(zh_word(my_test))
    msg.info(str(result))


def check_ziwen_lookup_zh_chengyu() -> None:
    """zh: Look up chengyu supplement data for a 4-character Chinese word."""
    my_test = input("Enter a chengyu to look up: ")
    with msg.loading(f"Looking up '{my_test}'..."):
        result = asyncio.run(zh_word_chengyu_supplement(my_test))
    msg.info(str(result))


def check_ziwen_lookup_zh_variant() -> None:
    """zh: Search for variant characters."""
    my_test = input("Enter a Chinese character to search for variants: ")
    with msg.loading("Searching for variants..."):
        result = variant_character_search(my_test)
    msg.info(str(result))


def check_ziwen_lookup_zh_other() -> None:
    """zh: Run the other/old Chinese readings search."""
    my_test = input("Enter a Chinese character for other readings: ")
    with msg.loading("Fetching other readings..."):
        result = old_chinese_search(my_test)
    msg.info(str(result))


def check_ziwen_lookup_ja_character() -> None:
    """ja: Look up a single Japanese character."""
    my_test = input("Enter a Japanese character to look up: ")
    with msg.loading(f"Looking up '{my_test}'..."):
        result = ja_character(my_test)
    msg.info(str(result))


def check_ziwen_lookup_ja_word() -> None:
    """ja: Look up a Japanese word."""
    my_test = input("Enter a Japanese word to look up: ")
    with msg.loading(f"Looking up '{my_test}'..."):
        result = asyncio.run(ja_word(my_test))
    msg.info(str(result))


def check_ziwen_lookup_ko_word() -> None:
    """ko: Look up a Korean word."""
    my_input = input("Enter a Korean word to search for: ")
    with msg.loading(f"Looking up '{my_input}'..."):
        result = ko_word(my_input)
    if result:
        msg.info(str(result))
    else:
        msg.warn(f"No results found for '{my_input}'")


def check_ziwen_lookup_wikipedia() -> None:
    """wp: Search Wikipedia for a term."""
    my_search = input("What would you like to search Wikipedia for? ")
    with msg.loading(f"Searching Wikipedia for '{my_search}'..."):
        result = wikipedia_lookup([my_search], "en")
    msg.info(str(result))


def check_ziwen_lookup_match_helpers() -> None:
    """match: Run the lookup matcher on a phrase and language code."""
    msg.info("Note: Backticks will be automatically added around your phrase.")
    test_phrase = input("Enter phrase: ")
    lang_code = input("Enter language code (zh/ja/ko): ")
    phrase_with_backticks = f"`{test_phrase.strip()}`"
    with msg.loading("Running lookup matcher..."):
        test_result = lookup_matcher(phrase_with_backticks, lang_code)
    msg.good(f"Result: {test_result}")


def check_ziwen_lookup_wiktionary() -> None:
    """wiktionary: Look up a word and language on Wiktionary."""
    test_input = input("Enter a word to look up in Wiktionary: ")
    test_language = input("Enter the language to look up the word for: ")
    with msg.loading(f"Looking up '{test_input}' ({test_language}) on Wiktionary..."):
        result = wiktionary_search(test_input, test_language)
    pprint(result)


# ─── reddit ───────────────────────────────────────────────────────────────────


def check_reddit_status() -> None:
    """connection: Fetch unresolved Reddit incidents."""
    with msg.loading("Checking Reddit status..."):
        result = reddit_status_check()
    if result is None:
        msg.fail("Could not reach the Reddit Status API.")
    elif not result:
        msg.good("No unresolved Reddit incidents.")
    else:
        for incident in result:
            msg.divider(incident.get("name", "Incident"))
            msg.warn(
                f"[{incident.get('status', '').upper()}]  "
                f"Created: {incident.get('created_at')}  "
                f"Updated: {incident.get('updated_at')}"
            )


def check_reddit_removal_reasons() -> None:
    """connection: Search subreddit removal reasons by keyword."""
    test_prompt = input(
        "Enter search prompt for removal reasons (x to back out): "
    ).strip()
    if test_prompt.lower() == "x":
        return
    with msg.loading("Searching removal reasons..."):
        reason_id = search_removal_reasons(test_prompt)
    if reason_id:
        msg.good(f"Found removal reason ID: {reason_id}")
    else:
        msg.warn(f"No removal reason found matching '{test_prompt}'.")


def check_reddit_useragent() -> None:
    """connection: Generate and display a random user agent."""
    ua = get_random_useragent()
    msg.info(f"User-Agent : {ua['User-Agent']}")
    msg.info(f"Accept     : {ua['Accept']}")


def check_reddit_wiki_most_requested() -> None:
    """wiki: Fetch the most requested languages from the wiki statistics page."""
    with msg.loading("Fetching wiki data..."):
        result = fetch_most_requested_languages()
    msg.info(str(result))


def check_reddit_startup_templates() -> None:
    """startup: Retrieve and display current link flair templates."""
    with msg.loading("Retrieving flair templates..."):
        result = template_retriever()
    msg.info(str(result))


def check_reddit_verified_thread() -> None:
    """verification: Fetch the ID of the current verified thread."""
    with msg.loading("Fetching verified thread ID..."):
        result = get_verified_thread()
    msg.good(str(result))


def check_reddit_notifications() -> None:
    """notifications: Fetch usernames subscribed to a given language."""
    notifications_test = input(
        "Enter a language to retrieve notifications for (x to back out): "
    )
    if notifications_test.strip().lower() == "x":
        return
    with msg.loading(f"Fetching subscribers for '{notifications_test}'..."):
        notifications_lingvo = converter(notifications_test)
        if notifications_lingvo:
            notifications_data = fetch_usernames_for_lingvo(notifications_lingvo)
            msg.good(f"Signups for `{notifications_test}`: {len(notifications_data)}")
            msg.info(str(notifications_data))
        else:
            msg.fail(f"Invalid language: {notifications_test}")


# ─── wenju ────────────────────────────────────────────────────────────────────


def check_wenju_fetch_iso_reports() -> None:
    """iso_updates: Fetch and save the latest ISO 639-3 change reports."""
    with msg.loading("Fetching ISO 639-3 reports..."):
        fetch_iso_reports()
    msg.good("ISO report fetch complete.")


# ─── Menu runner ──────────────────────────────────────────────────────────────
#
# Two-level menu structure:
#   SECTIONS maps a top-level key → (section label, {sub-key: (label, fn)})
# Adding a new section: append an entry to SECTIONS.
# Adding a check to an existing section: append to its inner dict.

SECTIONS = {
    "1": (
        "database",
        {
            "1": ("search", check_database_search),
            "2": ("initialize all", check_database_initialize),
        },
    ),
    "2": (
        "error",
        {
            "1": ("display event errors", check_error_display_event_errors),
        },
    ),
    "3": (
        "hermes",
        {
            "1": ("db statistics", check_hermes_statistics),
            "2": ("parser diagnostics", check_hermes_parser),
        },
    ),
    "4": (
        "integrations",
        {
            "1": ("ai: image description", check_integrations_ai_image_description),
            "2": ("search", check_integrations_search),
        },
    ),
    "5": (
        "lang",
        {
            "1": ("converter", check_lang_converter),
            "2": ("parse language list", check_lang_parse),
        },
    ),
    "6": (
        "models",
        {
            "1": ("ajo: from URL", check_models_ajo_url),
            "2": ("ajo: live posts", check_models_ajo_live),
            "3": ("ajo: load by ID", check_models_ajo_load),
            "4": ("instruo: from URL", check_models_instruo_url),
            "5": ("instruo: from text", check_models_instruo_text),
            "6": ("komando: from text", check_models_komando),
            "7": ("kunulo: from URL", check_models_kunulo),
        },
    ),
    "7": (
        "monitoring",
        {
            "1": ("user points", check_monitoring_user),
            "2": ("post points", check_monitoring_post),
        },
    ),
    "8": (
        "reddit",
        {
            "1": ("connection: status check", check_reddit_status),
            "2": ("connection: removal reasons", check_reddit_removal_reasons),
            "3": ("connection: user agent", check_reddit_useragent),
            "4": ("notifications: by language", check_reddit_notifications),
            "5": ("startup: flair templates", check_reddit_startup_templates),
            "6": ("verification: verified thread", check_reddit_verified_thread),
            "7": ("wiki: most requested langs", check_reddit_wiki_most_requested),
        },
    ),
    "9": (
        "title",
        {
            "1": ("manual test", check_title_manual),
            "2": ("live Reddit posts", check_title_reddit),
        },
    ),
    "10": (
        "utility",
        {
            "1": ("is valid image URL", check_utility_is_valid_image_url),
            "2": ("youtube length", check_utility_youtube),
        },
    ),
    "11": (
        "wenju",
        {
            "1": ("iso_updates: fetch reports", check_wenju_fetch_iso_reports),
        },
    ),
    "12": (
        "ziwen_lookup",
        {
            "1": ("ja: character", check_ziwen_lookup_ja_character),
            "2": ("ja: word", check_ziwen_lookup_ja_word),
            "3": ("ko: word", check_ziwen_lookup_ko_word),
            "4": (
                "match: matcher/sentence tokenizer",
                check_ziwen_lookup_match_helpers,
            ),
            "5": ("wiktionary", check_ziwen_lookup_wiktionary),
            "6": ("wp: wikipedia", check_ziwen_lookup_wikipedia),
            "7": ("zh: character", check_ziwen_lookup_zh_character),
            "8": ("zh: chengyu", check_ziwen_lookup_zh_chengyu),
            "9": ("zh: other readings", check_ziwen_lookup_zh_other),
            "10": ("zh: variant", check_ziwen_lookup_zh_variant),
            "11": ("zh: word", check_ziwen_lookup_zh_word),
        },
    ),
}


def _section_menu(label: str, checks: dict) -> None:
    """Display and run the sub-menu for a single section."""
    while True:
        msg.divider(label)
        for key, (sublabel, _) in checks.items():
            print(f"  {key}. {sublabel}")
        print("  x. Back")

        choice = input("Select a check: ").strip().lower()

        if choice == "x":
            break
        elif choice in checks:
            _, fn = checks[choice]
            fn()
        else:
            msg.warn("Invalid choice, please try again.")


def _main_menu() -> None:
    """Main entry point for using dev tools."""
    enable_debug_logging()
    while True:
        msg.divider("dev_tools")
        for key, (label, checks) in SECTIONS.items():
            print(
                f"  {key}. {label}  ({len(checks)} check{'s' if len(checks) != 1 else ''})"
            )
        print("  x. Exit")

        choice = input("Select a section: ").strip().lower()

        if choice == "x":
            msg.info("Exiting.")
            break
        elif choice in SECTIONS:
            label, checks = SECTIONS[choice]
            _section_menu(label, checks)
        else:
            msg.warn("Invalid choice, please try again.")


if __name__ == "__main__":
    _main_menu()
