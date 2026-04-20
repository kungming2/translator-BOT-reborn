#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
Uses the title_handling process to test a large amount of titles and
then writes it to a local Markdown file, and flags titles of interest
for examination.
...

Logger tag: [WY:TITLE]
"""

from __future__ import annotations

import logging
import time
import traceback
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from config import SETTINGS, get_reports_directory
from config import logger as _base_logger
from models.ajo import ajo_loader, determine_flair_and_update
from reddit.connection import REDDIT_HELPER
from title.title_handling import process_title
from utility import format_markdown_table_with_padding

if TYPE_CHECKING:
    from praw.models import Submission

    from models.titolo import Titolo

logger = logging.LoggerAdapter(_base_logger, {"tag": "WY:TITLE"})


# ─── Data structures ──────────────────────────────────────────────────────────


@dataclass
class PostCategories:
    """Container for categorized posts to avoid managing multiple lists."""

    display: list[str]
    problematic: list[str]
    non_css: list[str]
    multiple: list[str]
    regional: list[str]
    ai_assessed: list[str]

    def __init__(self) -> None:
        """Initialise all category lists to empty."""
        self.display = []
        self.problematic = []
        self.non_css = []
        self.multiple = []
        self.regional = []
        self.ai_assessed = []


# ─── Post filtering & formatting ──────────────────────────────────────────────


def should_skip_post(post: Submission) -> bool:
    """
    Determine if a post should be skipped based on title and flair.

    Consolidates multiple skip conditions into a single function for clarity.
    """
    if ">" not in post.title and "english" not in post.title.lower()[:25]:
        return True

    return bool(
        (flair := post.link_flair_css_class)
        and ("meta" in flair or "community" in flair)
    )


def escape_markdown(text: str) -> str:
    """Escape special Markdown characters to prevent rendering issues."""
    special_chars = ["|", "]", "[", ")", "(", "`"]
    for char in special_chars:
        text = text.replace(char, f"\\{char}")
    return text


def get_author_link(post: Submission) -> str:
    """
    Extract author name and create a formatted link.

    Returns '[unknown]/[deleted]' if author information is unavailable
            (deleted accounts, etc.).
    """
    try:
        return f"[u/{post.author.name}](https://www.reddit.com/user/{post.author.name})"
    except AttributeError:
        return "[unknown]/[deleted]"


def format_language_list(language_objects: list) -> str:
    """Convert list of language objects to comma-separated string."""
    return ", ".join(str(lang) for lang in language_objects)


def create_post_entry(post: Submission, titolo_data: Titolo) -> str:
    """
    Create a formatted Markdown table row for a post.

    Extracts all necessary data from Titolo object and formats it
    for display in the output table.
    """
    title_normalized = escape_markdown(post.title)
    if len(title_normalized) > 60:
        title_normalized = title_normalized[:60] + "..."
    link = f"https://www.reddit.com{post.permalink}"
    author = get_author_link(post)

    source = format_language_list(titolo_data.source)
    target = format_language_list(titolo_data.target)

    return (
        f"| {source} | {target} | {titolo_data.final_code} | {titolo_data.final_text} | "
        f"[{title_normalized}]({link}) | {author} | "
        f"{titolo_data.title_processed} | {titolo_data.language_country} | {titolo_data.direction} |"
    )


def _generate_error_entry_line(post: Submission) -> str:
    """
    Create a formatted error entry for problematic posts.

    Logs the full traceback for debugging while returning a formatted row.
    """
    error_traceback = traceback.format_exc()
    print(f"Error processing post '{post.title}': {error_traceback}")

    return f"| !!! | ---  | ---  | ---  | **{post.title}** | --- | --- | --- |"


# ─── Processing ───────────────────────────────────────────────────────────────


def categorize_post(
    entry: str, titolo_data: Titolo, categories: PostCategories
) -> None:
    """
    Categorize a post based on its properties.

    Modifies the categories object in place to add the entry to appropriate lists.
    Posts can appear in multiple categories.
    """
    categories.display.append(entry)

    if titolo_data.final_code == "generic":
        if titolo_data.final_text == "Generic":
            categories.problematic.append(entry)
        else:
            categories.non_css.append(entry)
    elif titolo_data.final_code in {"multiple", "app"}:
        categories.multiple.append(entry)

    if titolo_data.language_country and titolo_data.language_country != "None":
        categories.regional.append(entry)

    if titolo_data.ai_assessed:
        categories.ai_assessed.append(entry)


def process_single_post(post: Submission, categories: PostCategories) -> float:
    """
    Process a single post and categorize it.

    Returns the processing time in seconds.
    Raises exceptions for problematic posts to be handled by caller.
    """
    start_time = time.time()

    titolo_data = process_title(post.title, post, False)
    entry = create_post_entry(post, titolo_data)
    categorize_post(entry, titolo_data, categories)

    return time.time() - start_time


# ─── Output building ──────────────────────────────────────────────────────────


def build_markdown_section(title: str, header: str, entries: list[str]) -> str:
    """Build a Markdown section with title, header, and entries."""
    if not entries:
        return ""

    return f"\n\n## {title}\n\n{header}{chr(10).join(entries)}"


def build_output_document(categories: PostCategories, header: str) -> str:
    """
    Build the complete Markdown output document.

    Combines all categorized posts into a structured document with sections.
    """
    output = "# Posts Table\n\n" + header + "\n".join(categories.display)
    output_table = format_markdown_table_with_padding(output).replace("```", "")

    sections = [
        ("Non-Supported CSS Posts", categories.non_css),
        ("Language/Country Regional Posts", categories.regional),
        ("Multiple (non-defined) Posts", categories.multiple),
        ("AI-Assessed Posts", categories.ai_assessed),
        ("Problematic Posts", categories.problematic),
    ]

    for title, entries in sections:
        output_table += build_markdown_section(title, header, entries)

    return output_table


def calculate_statistics(
    total_posts: int,
    categories: PostCategories,
    processed_times: list[float],
    elapsed_duration: float,
) -> str:
    """
    Calculate and format processing statistics.

    Returns a formatted Markdown section with all relevant metrics.
    """
    accuracy = (
        round(100 * (1 - len(categories.problematic) / total_posts), 4)
        if total_posts > 0
        else 0
    )
    supported = (
        round(100 * (1 - len(categories.non_css) / total_posts), 4)
        if total_posts > 0
        else 0
    )
    avg_time = (
        round(sum(processed_times) / len(processed_times), 4) if processed_times else 0
    )

    return f"""


## Statistics

- **Total Posts Processed:** {total_posts}
- **Non-CSS Supported:** {len(categories.non_css)}
- **Regional Posts:** {len(categories.regional)}
- **Problematic Posts:** {len(categories.problematic)}
- **AI-Assessed Posts:** {len(categories.ai_assessed)}
- **Accuracy:** {accuracy}%
- **Supported:** {supported}%
- **Average Processing Time:** {avg_time}s per post
- **Total Duration:** {round(elapsed_duration, 2)}s
"""


def _save_to_file(content: str) -> Path:
    """
    Save content to a dated file in the reports directory.

    Returns the path where the file was saved.
    Raises exceptions if file writing fails.
    """
    today_date = datetime.now().strftime("%Y-%m-%d")
    folder_to_save = get_reports_directory()
    output_path = Path(folder_to_save) / f"{today_date}_Title_Retrieval.md"

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(content, encoding="utf-8")

    return output_path


# ─── Entry points ─────────────────────────────────────────────────────────────


def fetch_posts(fetch_amount: int) -> list:
    """Fetch posts from the configured subreddit."""
    return list(REDDIT_HELPER.subreddit(SETTINGS["subreddit"]).new(limit=fetch_amount))


def retrieve_titles_test(fetch_amount: int = 1000) -> None:
    """
    Retrieve posts from r/translator and process them through title handling.

    This function is useful for testing changes to converter() or process_title().
    It generates a detailed Markdown report categorizing posts by various criteria.

    Args:
        fetch_amount: Number of posts to retrieve (default: 1000)
    """
    start_time = time.time()

    categories = PostCategories()
    processed_times = []

    header = (
        "\n| Source | Target | Final Code | Final Text | Post Title | "
        "Author | Title as Processed | Lang/Country | Direction |\n"
        "|---|---|---|---|---|---|---|---|---|\n"
    )

    posts = fetch_posts(fetch_amount)

    for post in posts:
        if should_skip_post(post):
            continue

        # noinspection PyBroadException
        try:
            process_time = process_single_post(post, categories)
            processed_times.append(process_time)
        except Exception:
            error_entry = _generate_error_entry_line(post)
            categories.display.append(error_entry)
            categories.problematic.append(error_entry)

    output = build_output_document(categories, header)
    statistics = calculate_statistics(
        len(posts), categories, processed_times, time.time() - start_time
    )
    full_document = output + statistics

    print(full_document)
    _save_to_file(full_document)


def examine_flair_for_ajo(
    ajo_id: str, initial_update: bool = False, moderator_set: bool = False
) -> None:
    """
    Load an Ajo object and test flair determination with testing mode enabled.

    Args:
        ajo_id: The ID of the Ajo/submission to load
        initial_update: If True, always sets flair even if unchanged (default: False)
        moderator_set: If True, skips adding "(Identified)" to flair text (default: False)
    """
    original_testing_mode = SETTINGS.get("testing_mode", False)

    try:
        SETTINGS["testing_mode"] = True

        logger.info(f"Loading Ajo object for ID: {ajo_id}")
        ajo = ajo_loader(ajo_id)

        if ajo is None:
            logger.error(f"Failed to load Ajo object for ID: {ajo_id}")
            return

        logger.info(f"Testing flair determination for Ajo: {ajo_id}")
        determine_flair_and_update(
            ajo, initial_update=initial_update, moderator_set=moderator_set
        )

        logger.info(
            f"Flair Test Results for {ajo_id}:\n"
            f"  CSS Class: {getattr(ajo, 'output_post_flair_css', 'N/A')}\n"
            f"  Flair Text: {getattr(ajo, 'output_post_flair_text', 'N/A')}\n"
            f"  Language: {getattr(ajo.lingvo, 'name', 'N/A') if ajo.lingvo else 'No lingvo'}\n"
            f"  Post Type: {ajo.type}\n"
            f"  Status: {getattr(ajo, 'status', 'N/A')}"
        )

    except Exception as e:
        logger.error(f"Error testing flair for Ajo {ajo_id}: {e}", exc_info=True)

    finally:
        SETTINGS["testing_mode"] = original_testing_mode
        logger.debug(f"Restored testing_mode to: {original_testing_mode}")
