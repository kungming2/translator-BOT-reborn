from datetime import date

import prawcore
from praw.exceptions import RedditAPIException

from config import SETTINGS, logger
from connection import REDDIT
from languages import converter

from wenyuan import WENYUAN_SETTINGS

# Template for new wiki pages - matches existing format
WY_NEW_HEADER = (
    "## {language_name} ({language_family}) ![](%%statistics-h%%)\n"
    "*[Statistics](https://www.reddit.com/r/translator/wiki/statistics) for "
    "/r/translator provided by "
    "[Wenyuan](https://www.reddit.com/r/translator/wiki/wenyuan)*\n\n"
    "Year | Month | Total Requests | Percent of All Requests | Untranslated "
    "Requests | Translation Percentage | RI | View Translated Requests\n"
    "|:-----|------|---------------|-----------------------|-----------------------"
    "|-----------------------|----|-------------------------|\n"
)


# Utility codes that get special handling
UTILITY_CODES = [
    "Unknown",
    "Nonlanguage",
    "Conlang",
    "Multiple Languages",
]


def calculate_ri(
    language_posts: int, total_posts: int, native_speakers: int
) -> float | None:
    """
    Calculate the Representation Index for a language.

    Args:
        language_posts: Number of posts for this language on r/translator
        total_posts: Total number of posts on r/translator
        native_speakers: Number of native speakers worldwide

    Returns:
        RI value or None if calculation not possible
    """
    world_population = WENYUAN_SETTINGS["world_population"] * 1000000

    if total_posts == 0 or native_speakers == 0:
        return None

    # Percentage of r/translator posts
    percent_posts = (language_posts / total_posts) * 100

    # Percentage of world native speakers
    percent_speakers = (native_speakers / world_population) * 100

    # RI = representation on r/translator / representation in world
    ri = percent_posts / percent_speakers

    return round(ri, 2)


def cerbo_wiki_editor(
    language_name, language_family, wiki_language_line, month_year_chunk
):
    """
    A function that writes to the specific wiki page for a language.
    Adapted for backwards compatibility with existing wiki structure.

    :param language_name: The name of the language.
    :param language_family: Its language family.
    :param wiki_language_line: The line containing the information we wish to edit.
    :param month_year_chunk: The month and year to check for (e.g., "2025-05").
    :return: Nothing.
    """
    r = REDDIT.subreddit(SETTINGS["subreddit"])

    # Format the name nicely for wiki URL
    underscore_name = language_name.lower()
    underscore_name = underscore_name.replace(" ", "_")
    underscore_name = underscore_name.replace("'", "_")
    underscore_name = underscore_name.replace("<", "")
    underscore_name = underscore_name.replace(">", "")

    # Special case: "Multiple Languages" wiki page is at /wiki/multiple
    if language_name == "Multiple Languages":
        underscore_name = "multiple"

    # Fetch the wikipage for the language.
    page_content = r.wiki[underscore_name]  # Get it.

    # Actually start adding data to the language's page.
    if language_name not in UTILITY_CODES:  # Regular languages
        try:
            if month_year_chunk not in str(
                page_content.content_md
            ):  # This month has not been recorded on the wiki.
                # Checks to see if there's an entry for the month
                page_content_new = (
                    str(page_content.content_md).rstrip("\n") + wiki_language_line
                )

                # Adds this month's entry to the data from the wikipage
                page_content.edit(
                    content=page_content_new,
                    reason=f"Updating with data from {month_year_chunk}",
                )
                logger.info(
                    f"[WY] Updated wiki entry for {language_name} statistics "
                    f"for the month of {month_year_chunk}."
                )
            else:  # Entry already exists
                logger.info(
                    f"[WY] Wiki entry exists for {language_name} in {month_year_chunk}."
                )
        except prawcore.exceptions.NotFound:
            # Problem with the WikiPage... it doesn't exist.
            # Create a new wikipage.
            template_content = WY_NEW_HEADER.format(
                language_name=language_name, language_family=language_family
            )
            r.wiki.create(
                name=underscore_name,
                content=template_content,
                reason=f"Creating a new statistics wiki page for {language_name}",
            )
            logger.info(f"[WY] Created a new wiki page for {language_name}")
            # Adds this month's entry to the data from the wikipage
            page_content_new = template_content + wiki_language_line
            page_content.edit(
                content=page_content_new,
                reason=f"Updating with data from {month_year_chunk}",
            )
            logger.info(
                f"[WY] Updated wiki entry for {language_name} in {month_year_chunk}"
            )
        except RedditAPIException:
            # Problem with the WikiPage... it doesn't exist.
            logger.warning(f"[WY] Error with {language_name}")
    else:
        # Code for editing utility pages (unknown, conlang etc.)
        try:
            if month_year_chunk not in str(page_content.content_md):
                page_content_new = str(page_content.content_md) + wiki_language_line
                page_content.edit(
                    content=page_content_new,
                    reason=f"Updating with data from {month_year_chunk}",
                )
                logger.info(
                    f"[WY] Updated wiki function entry for {language_name} in {month_year_chunk}"
                )
            else:  # Entry already exists
                logger.info(
                    f"[WY] Wiki function entry exists for {language_name} in {month_year_chunk}"
                )
        except prawcore.exceptions.NotFound:
            logger.warning(f"[WY] Wiki page not found for utility code {language_name}")

    return


def update_monthly_wiki_page(month_year, formatted_content):
    """
    Create or update the monthly statistics wiki page (e.g., /r/translator/wiki/2025_05).

    :param month_year: The month and year in YYYY-MM format (e.g., "2025-05").
    :param formatted_content: The full markdown content for the page.
    :return: The wiki page URL if successful, None otherwise.
    """
    r = REDDIT.subreddit(SETTINGS["subreddit"])

    # Convert YYYY-MM to YYYY_MM for wiki page name
    wiki_page_name = month_year.replace("-", "_")

    try:
        # Try to get existing page
        page_content = r.wiki[wiki_page_name]

        # Check if content already exists (avoid duplicate posts)
        if "## Overall Statistics" in str(page_content.content_md):
            logger.info(f"[WY] Wiki page already exists for {month_year}")
            return f"https://www.reddit.com/r/translator/wiki/{wiki_page_name}"
        else:
            # Update the page
            page_content.edit(
                content=formatted_content, reason=f"Monthly statistics for {month_year}"
            )
            logger.info(f"[WY] Updated wiki page for {month_year}")
            return f"https://www.reddit.com/r/translator/wiki/{wiki_page_name}"

    except prawcore.exceptions.NotFound:
        # Page doesn't exist, create it
        try:
            r.wiki.create(
                name=wiki_page_name,
                content=formatted_content,
                reason=f"Creating monthly statistics page for {month_year}",
            )
            logger.info(f"[WY] Created new wiki page for {month_year}")
            return f"https://www.reddit.com/r/translator/wiki/{wiki_page_name}"
        except Exception as e:
            logger.error(f"[WY] Error creating wiki page for {month_year}: {e}")
            return None
    except Exception as e:
        logger.error(f"[WY] Error updating wiki page for {month_year}: {e}")
        return None


def update_language_wiki_pages(lumo, month_year):
    """
    Update individual language wiki pages with monthly statistics.
    Now uses table format matching existing wiki structure.

    :param lumo: Lumo instance with loaded data.
    :param month_year: The month and year in YYYY-MM format (e.g., "2025-05").
    :return: Number of pages updated.
    """
    all_languages = sorted(lumo.get_all_languages())
    updated_count = 0

    # Get overall stats for RI calculation
    overall_stats = lumo.get_overall_stats()
    total_posts = overall_stats["total_requests"]

    for lang in all_languages:
        stats = lumo.get_language_stats(lang)
        if not stats:
            continue

        lingvo = converter(lang)
        if not lingvo:
            continue

        # Build the wiki line for this language in table format
        year, month = month_year.split("-")

        # Format language name for search URL
        search_lang = lang.replace(" ", "_")
        lang_code = lingvo.preferred_code.upper()

        # Total Requests column with search link
        total_link = (
            f"[{stats['total_requests']}]"
            f'(/r/translator/search?q=flair:"{search_lang}"+OR+flair:"[{lang_code}]"'
            "&sort=new&restrict_sr=on)"
        )

        # Untranslated Requests - just the number (no link in newer format)
        untranslated = stats["untranslated"]

        # RI (Representation Index) - calculate correctly
        ri_value = "---"
        if lingvo.population and lingvo.population > 0:
            ri = calculate_ri(
                language_posts=stats["total_requests"],
                total_posts=total_posts,
                native_speakers=lingvo.population,
            )
            if ri is not None:
                ri_value = str(ri)

        # Build the table row
        wiki_line = (
            f"\n| {year} | {month} | {total_link} | {stats['percent_of_all_requests']}% | "
            f"{untranslated} | {stats['translation_percentage']}% | {ri_value} | --- |"
        )

        # Only update the wiki page if it's not a script code.
        if len(lang_code) != 4:
            # Update the wiki page
            cerbo_wiki_editor(
                language_name=lang,
                language_family=lingvo.family if lingvo.family else "Unknown",
                wiki_language_line=wiki_line,
                month_year_chunk=month_year,
            )
            updated_count += 1
        else:
            logger.info(f"[WY] Skipping {lang} because it's a script code.")

    logger.info(f"[WY] Updated {updated_count} language wiki pages")
    return updated_count


def update_statistics_index_page(month_year):
    """
    Update the main statistics index page with a link to the new monthly page.

    :param month_year: The month and year in YYYY-MM format (e.g., "2025-05").
    :return: True if successful, False otherwise.
    """
    r = REDDIT.subreddit(SETTINGS["subreddit"])

    year, month = month_year.split("-")
    month_name = date(1900, int(month), 1).strftime("%B")
    wiki_page_name = month_year.replace("-", "_")

    # Create the new entry line
    new_entry = f"* [{month_name} {year}](https://www.reddit.com/r/translator/wiki/{wiki_page_name})\n"

    try:
        # Get the statistics index page
        page_content = r.wiki["statistics"]

        # Check if entry already exists
        if wiki_page_name in str(page_content.content_md):
            logger.info(
                f"[WY] Statistics index already contains entry for {month_year}"
            )
            return True

        # Find where to insert (assuming chronological order, newest first)
        content = str(page_content.content_md)

        # Look for a year header or monthly entries section
        # This is a simple append - you may want more sophisticated insertion logic
        if f"## {year}" in content:
            # Insert after the year header
            insertion_point = content.find(f"## {year}") + len(f"## {year}\n\n")
            new_content = (
                content[:insertion_point] + new_entry + content[insertion_point:]
            )
        else:
            # Append to the end
            new_content = content + f"\n## {year}\n\n" + new_entry

        # Update the page
        page_content.edit(
            content=new_content, reason=f"Adding {month_name} {year} statistics"
        )
        logger.info(f"[WY] Updated statistics index page with {month_year}")
        return True

    except Exception as e:
        logger.error(f"[WY] Error updating statistics index page: {e}")
        return False
