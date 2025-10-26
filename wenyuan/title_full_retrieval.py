#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
Uses the title_handling process to test a large amount of titles and
then writes it to a local Markdown file, and flags titles of interest
for examination.
"""

import time
import traceback
from datetime import datetime
from pathlib import Path
from typing import List
from dataclasses import dataclass

from config import SETTINGS, get_reports_directory
from connection import REDDIT_HELPER, logger
from models.ajo import ajo_loader, determine_flair_and_update
from title_handling import process_title
from utility import format_markdown_table_with_padding


@dataclass
class PostCategories:
    """Container for categorized posts to avoid managing multiple lists."""

    display: List[str]
    problematic: List[str]
    non_css: List[str]
    multiple: List[str]
    regional: List[str]
    ai_assessed: List[str]

    def __init__(self):
        self.display = []
        self.problematic = []
        self.non_css = []
        self.multiple = []
        self.regional = []
        self.ai_assessed = []


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
    # Store original testing mode setting
    original_testing_mode = SETTINGS.get("testing_mode", False)

    try:
        # Enable testing mode
        SETTINGS["testing_mode"] = True

        # Load the Ajo object
        logger.info(f"Loading Ajo object for ID: {ajo_id}")
        ajo = ajo_loader(ajo_id)

        if ajo is None:
            logger.error(f"Failed to load Ajo object for ID: {ajo_id}")
            return

        # Run flair determination
        logger.info(f"Testing flair determination for Ajo: {ajo_id}")
        determine_flair_and_update(
            ajo, initial_update=initial_update, moderator_set=moderator_set
        )

        # Log the results
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
        # Restore original testing mode setting
        SETTINGS["testing_mode"] = original_testing_mode
        logger.debug(f"Restored testing_mode to: {original_testing_mode}")


"""FULL TITLE RETRIEVER"""


def should_skip_post(post) -> bool:
    """
    Determine if a post should be skipped based on title and flair.

    Consolidates multiple skip conditions into a single function for clarity.
    """
    # Skip posts without language pairs, unless they mention "english" early
    if ">" not in post.title and "english" not in post.title.lower()[:25]:
        return True

    # Skip meta/community posts by checking flair
    if flair := post.link_flair_css_class:
        if "meta" in flair or "community" in flair:
            return True

    return False


def escape_markdown(text: str) -> str:
    """Escape special Markdown characters to prevent rendering issues."""
    special_chars = ["|", "]", "[", ")", "(", "`"]
    for char in special_chars:
        text = text.replace(char, f"\\{char}")
    return text


def get_author_link(post) -> str:
    """
    Extract author name and create a formatted link.

    Returns '[unknown]/[deleted]' if author information is unavailable
            (deleted accounts, etc.).
    """
    try:
        return f"[u/{post.author.name}](https://www.reddit.com/user/{post.author.name})"
    except AttributeError:
        return "[unknown]/[deleted]"


def format_language_list(language_objects) -> str:
    """Convert list of language objects to comma-separated string."""
    return ", ".join(str(lang) for lang in language_objects)


def create_post_entry(post, titolo_data) -> str:
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

    # Extract and format data from Titolo object
    source = format_language_list(titolo_data.source)
    target = format_language_list(titolo_data.target)

    return (
        f"| {source} | {target} | {titolo_data.final_code} | {titolo_data.final_text} | "
        f"[{title_normalized}]({link}) | {author} | "
        f"{titolo_data.title_processed} | {titolo_data.language_country} | {titolo_data.direction} |"
    )


def create_error_entry(post) -> str:
    """
    Create a formatted error entry for problematic posts.

    Logs the full traceback for debugging while returning a formatted row.
    """
    error_traceback = traceback.format_exc()
    print(f"Error processing post '{post.title}': {error_traceback}")

    return f"| !!! | ---  | ---  | ---  | **{post.title}** | --- | --- | --- |"


def categorize_post(entry: str, titolo_data, categories: PostCategories) -> None:
    """
    Categorize a post based on its properties.

    Modifies the categories object in place to add the entry to appropriate lists.
    Posts can appear in multiple categories.
    """
    categories.display.append(entry)

    # Categorize by final_code type
    if titolo_data.final_code == "generic":
        if titolo_data.final_text == "Generic":
            categories.problematic.append(entry)
        else:
            categories.non_css.append(entry)
    elif titolo_data.final_code in {"multiple", "app"}:  # Use set for O(1) lookup
        categories.multiple.append(entry)

    # Track posts with regional language/country info
    if titolo_data.language_country and titolo_data.language_country != "None":
        categories.regional.append(entry)

    # Track AI-assessed posts
    if titolo_data.ai_assessed:
        categories.ai_assessed.append(entry)


def process_single_post(post, categories: PostCategories) -> float:
    """
    Process a single post and categorize it.

    Returns the processing time in seconds.
    Raises exceptions for problematic posts to be handled by caller.
    """
    start_time = time.time()

    titolo_data = process_title(post.title, post)
    entry = create_post_entry(post, titolo_data)
    categorize_post(entry, titolo_data, categories)

    return time.time() - start_time


def build_markdown_section(title: str, header: str, entries: List[str]) -> str:
    """Build a Markdown section with title, header, and entries."""
    if not entries:
        return ""

    return f"\n\n## {title}\n\n{header}{chr(10).join(entries)}"


def build_output_document(categories: PostCategories, header: str) -> str:
    """
    Build the complete Markdown output document.

    Combines all categorized posts into a structured document with sections.
    """
    # Start with all posts
    output = "# Posts Table\n\n" + header + "\n".join(categories.display)
    output_table = format_markdown_table_with_padding(output).replace("```", "")

    # Add optional sections only if they have content
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
    processed_times: List[float],
    elapsed_duration: float,
) -> str:
    """
    Calculate and format processing statistics.

    Returns a formatted Markdown section with all relevant metrics.
    """
    # Avoid division by zero
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


def save_to_file(content: str) -> Path:
    """
    Save content to a dated file in the reports directory.

    Returns the path where the file was saved.
    Raises exceptions if file writing fails.
    """
    # Get today's date in YYYY-MM-DD format
    today_date = datetime.now().strftime("%Y-%m-%d")

    # Resolve the output file path
    folder_to_save = get_reports_directory()
    output_path = Path(folder_to_save) / f"{today_date}_Title_Retrieval.md"

    # Write the file
    output_path.write_text(content, encoding="utf-8")

    return output_path


def fetch_posts(fetch_amount: int) -> List:
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

    # Initialize data structures
    categories = PostCategories()
    processed_times = []

    # Define table header once
    header = (
        "\n| Source | Target | Final Code | Final Text | Post Title | "
        "Author | Title as Processed | Lang/Country | Direction |\n"
        "|---|---|---|---|---|---|---|---|---|\n"
    )

    # Fetch and process posts
    posts = fetch_posts(fetch_amount)

    for post in posts:
        # Skip posts that don't meet criteria
        if should_skip_post(post):
            continue

        # noinspection PyBroadException
        try:
            process_time = process_single_post(post, categories)
            processed_times.append(process_time)
        except Exception:
            # Handle problematic posts without stopping execution
            error_entry = create_error_entry(post)
            categories.display.append(error_entry)
            categories.problematic.append(error_entry)

    # Build output document
    output = build_output_document(categories, header)
    statistics = calculate_statistics(
        len(posts), categories, processed_times, time.time() - start_time
    )
    full_document = output + statistics

    # Display results
    print(full_document)

    # Optionally save to file
    save_to_file(full_document)


if __name__ == "__main__":
    retrieve_titles_test(10)
