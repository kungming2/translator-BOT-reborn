#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
Handles subreddit wiki reading and writing.
Note this is distinct from Wikipedia functions, which are in
lookup/wp_utils.py.
"""

import re
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from dateutil.relativedelta import relativedelta
import prawcore
import yaml
from yaml.parser import ParserError

from config import SETTINGS
from connection import REDDIT, REDDIT_HELPER, logger
from discord_utils import send_discord_alert
from responses import RESPONSE

if TYPE_CHECKING:
    from languages import Lingvo


def fetch_wiki_statistics_page(lingvo_object: "Lingvo") -> str | None:
    """Fetches the relevant statistics page from the subreddit wiki.
    This will account for the limitations that are inherent in the
    wiki naming schema, as well as any redirects the mods have
    set up.

    :return: A wiki URL, or `None` if no wiki page exists.
    """

    # If the link is already part of the object, return it.
    if lingvo_object.link_statistics:
        return lingvo_object.link_statistics

    # Format the language name to match subreddit wiki naming conventions.
    # Replace dashes and apostrophes with underscores.
    wiki_page_name = lingvo_object.name.replace(" ", "_").replace("'", "_")
    logger.debug(f"Accessing wiki page at /{wiki_page_name.lower()}.")
    wiki_page = f"{wiki_page_name.lower()}"

    # Attempt to fetch the wiki page content
    subreddit = REDDIT_HELPER.subreddit(SETTINGS["subreddit"])
    try:
        page = subreddit.wiki[wiki_page]
        content = page.content_md.strip()

        # Check if the page contains only an embedded image link like ![](%%statistics-x%%)
        match = re.fullmatch(r"!\[]\(%%(statistics[-_\w]+)%%\)", content)
        if match:
            redirect_target = match.group(1)
            return f"https://www.reddit.com/r/{subreddit.display_name}/wiki/{redirect_target}"

        # Otherwise, treat it as a normal page
        return f"https://www.reddit.com/r/{subreddit.display_name}/wiki/{wiki_page}"

    except prawcore.exceptions.NotFound:
        return None


def _extract_single_language_statistics_table(markdown_text: str) -> str | None:
    # Use regex to extract the table under "### Single-Language Requests"
    pattern = re.compile(
        r"### Single-Language Requests\s*\n"  # Match the header
        r"(?:.+\|.+\n)+"  # Match header and separator rows
        r"(?:.+\|.+\n?)*"  # Match all table rows
    )
    match = pattern.search(markdown_text)
    return match.group(0).strip() if match else None


def _assess_most_requested_languages(table_text: str) -> dict[str, int]:
    """Used by fetch_most_requested_languages() below.
    Actual processing table logic."""
    lines = table_text.strip().splitlines()

    # Skip the first two header lines
    data_lines = lines[2:]

    lang_dict = {}

    for line in data_lines:
        columns = [col.strip() for col in line.split("|")]
        if len(columns) < 10:
            continue  # Skip malformed rows

        # Extract total requests (e.g. [159])
        match_total = re.search(r"\[(\d+)]", columns[2])
        total_requests = int(match_total.group(1)) if match_total else 0

        # Extract language code from last column
        match_code = re.search(r"ISO_639:([a-zA-Z\-]+)", columns[9])
        lang_code = match_code.group(1) if match_code else None

        if lang_code:
            lang_dict[lang_code] = total_requests

    # Sort by total_requests descending
    sorted_dict = dict(
        sorted(lang_dict.items(), key=lambda item: item[1], reverse=True)[:15]
    )
    return sorted_dict


def fetch_most_requested_languages() -> list[str]:
    """This function will return the most requested languages
    based on the statistics post from x months ago. This allows for
    some lead time in case statistics updates are not timely, for some
    reason.

    :return: A list of language codes, ordered by most-requested to least.
    """
    months_difference = SETTINGS["points_months_delta"]

    three_months_ago = datetime.now(timezone.utc) - relativedelta(
        months=months_difference
    )
    three_months_ago = three_months_ago.strftime("%Y_%m")  # Underscore is intentional

    reference_page = REDDIT_HELPER.subreddit(SETTINGS["subreddit"]).wiki[
        three_months_ago
    ]
    reference_page_content = reference_page.content_md.strip()
    reference_table = _extract_single_language_statistics_table(reference_page_content)
    languages_frequency_sorted = _assess_most_requested_languages(reference_table)

    return list(languages_frequency_sorted.keys())


def update_wiki_page(
    action: str,
    formatted_date: str,
    title: str,
    post_id: str,
    flair_text: str,
    new_flair: str | None = None,
    user: str | None = None,
) -> None:
    """
    Updates a wiki page on the subreddit wiki with new data, based on
    the action argument. Primarily, this is only used for identify now,
    in order to collate identified posts into a main list of changes.
    Save is retained for compatibility purposes and in case it can be
    repurposed.

    Args:
        action: Either "save" or "identify" to determine which wiki page to update
        formatted_date: The formatted date string for the entry
        title: The post title
        post_id: The Reddit post ID
        flair_text: The current flair text
        new_flair: The new flair (for identify action)
        user: The username (for identify action)
    """
    if action == "save":
        # Adding to the "saved" wiki page
        page = REDDIT.subreddit(SETTINGS["subreddit"]).wiki["saved"]
        new_entry = f"| {formatted_date} | [{title}](https://redd.it/{post_id}) | {flair_text} |"
    elif action == "identify":
        # Adding to the "identified" wiki page
        page = REDDIT.subreddit(SETTINGS["subreddit"]).wiki["identified"]
        new_entry = (
            f"| {formatted_date} | [{title}](https://redd.it/{post_id}) | "
            f"{flair_text} | {new_flair} | u/{user} |"
        )
    else:
        raise ValueError(f"Invalid action: {action}. Must be 'save' or 'identify'")

    updated_content = f"{page.content_md}\n{new_entry}"

    try:
        page.edit(
            content=updated_content,
            reason=f"Ziwen: updating the {action} wiki page with a new link",
        )
    except (prawcore.exceptions.Forbidden, prawcore.exceptions.TooLarge) as e:
        # This should not happen often, as Wenju automatically archives
        # entries every month, but is retained here just in case.

        logger.warning(f"[ZW] Save_Wiki: The {action} wiki page is full.")
        send_discord_alert(
            f"'{action}' Wiki Page Full",
            RESPONSE.MSG_WIKIPAGE_FULL.format(action),
            "alert",
        )
        # For permission issues
        if isinstance(e, prawcore.exceptions.Forbidden):
            raise PermissionError("Insufficient permissions to edit the wiki page")
        # For size issues
        else:
            raise ValueError("Content too large for the wiki page")
    else:
        logger.info(f"[ZW] Save_Wiki: Updated the {action} wiki page.")

    return


"""
SEARCH FREQUENTLY-REQUESTED TRANSLATIONS

These are functions associated with checking the YAML entries on the
frequently-requested translations page. Currently, this is paired with
the `!search` function.
"""


def _frequently_requested_wiki() -> list[dict[str, Any]] | None:
    """
    Accesses the "Frequently Requested Translations" page on the wiki
    and "reads" from it. That page is in YAML.

    :return: A Python dictionary of all entries.
    """
    wiki_page = REDDIT_HELPER.subreddit(SETTINGS["subreddit"]).wiki[
        "frequently-requested"
    ]
    processed_data = wiki_page.content_md
    alert_mods = False

    # Convert YAML text into a Python list.
    yaml_data = processed_data.split("### Entries")[1].strip()
    yaml_data = yaml_data.replace("    ---", "---")
    try:
        frt_data = yaml.safe_load_all(yaml_data)
    except yaml.YAMLError:
        frt_data = None
        alert_mods = True

    # Valid YAML to process.
    # Convert to Python list and remove blank entries.
    if not alert_mods:
        try:
            frt_data = list(frt_data)
        except ParserError:
            frt_data = None
            alert_mods = True
        else:
            frt_data = [x for x in frt_data if x is not None]

    if alert_mods:
        # Send Discord alert.
        message_body = (
            "The [FRT](https://www.reddit.com/r/translator/wiki/frequently-requested) "
            "wikipage seems to have problems with YAML data. Please check and correct "
            "the data's formatting with [YAMLLint](https://www.yamllint.com/)."
        )
        send_discord_alert("FRT YAML Malformed Syntax", message_body, "alert")

    return frt_data


def search_integration(search_term: str) -> str | None:
    """
    Searches the frequently-requested translation wikipage for a term.

    :param search_term: Search term we are searching for.
    :return: None if the search term does not match anything,
             a formatted string of the results if found.
    """
    search_term = search_term.lower()  # All keywords should be in lower-case.
    frt_data = _frequently_requested_wiki()
    term_data = {}
    link_data = []
    example_data = []

    # Iterate over the entries, looking for the search term.
    for entry in frt_data:
        entry_keywords = entry["keywords"]
        entry_keywords = [x.lower() for x in entry_keywords]
        if search_term in entry_keywords:
            logger.info(
                "[ZW] search_integration: Keyword found in "
                "frequently requested translations."
            )
            term_data = entry
            break

    if not term_data:
        # Exit if no keywords were found.
        logger.info(
            "[ZW] search_integration: No keywords found in "
            "frequently requested translations."
        )
        return None
    else:
        # Format the header and the body text.
        header = (
            f"## [Frequently-Requested Translation]"
            f"(https://www.reddit.com/r/translator/wiki/frequently-requested)"
            f"\n\n**{term_data['entry']}** (*{term_data['language']}*)\n\n"
        )
        keywords = [f"`{x}`" for x in term_data["keywords"]]
        header += "*Keywords*: " + ", ".join(keywords) + "\n\n"
        body = f"> {term_data['explanation']}"
        body = body.replace("  ", " ")  # In case of extra spaces.

        # Format the external links.
        if term_data.get("links")[0]:
            for link in term_data["links"]:
                actual_index = term_data["links"].index(link) + 1
                link_data.append(f"[Link {actual_index}]({link})")
            link_data = ", ".join(link_data)
        else:
            link_data = ""

        # Format the Reddit examples.
        if term_data.get("examples")[0]:
            for example in term_data["examples"]:
                example_index = term_data["examples"].index(example) + 1
                example_data.append(f"[Example {example_index}]({example})")
            example_data = ", ".join(example_data)
        else:
            example_data = ""

        # Put everything together.
        total_term = f"{header}{body}\n"
        if link_data:
            total_term += "\n* " + link_data
        if example_data:
            total_term += "\n* " + example_data

        return total_term


if __name__ == "__main__":
    print(fetch_most_requested_languages())
