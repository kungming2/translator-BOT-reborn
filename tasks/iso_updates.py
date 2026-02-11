#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
import re
import urllib.request
from datetime import datetime, timezone
from io import BytesIO
from typing import Dict, List

import requests
import yaml
from lxml import html
from praw.exceptions import PRAWException
from pypdf import PdfReader

from config import Paths
from connection import REDDIT, get_random_useragent, logger
from discord_utils import send_discord_alert
from tasks import task


def parse_iso639_newsletter(pdf_source):
    """
    Parse an ISO 639 MA Newsletter PDF and extract adopted change requests.

    Args:
        pdf_source (str): URL to the PDF file or local file path

    Returns:
        str: Markdown-formatted list of adopted change requests
    """
    # Check if it's a local file path
    if pdf_source.startswith(("http://", "https://")):
        # Download from URL with random user agent to avoid 403 errors
        req = urllib.request.Request(pdf_source, headers=get_random_useragent())
        with urllib.request.urlopen(req) as response:
            pdf_data = response.read()
        pdf_file = BytesIO(pdf_data)
        reader = PdfReader(pdf_file)
    else:
        # Read from local file
        reader = PdfReader(pdf_source)

    # Extract text from all pages
    full_text = ""
    for page in reader.pages:
        full_text += page.extract_text()

    # Find the section "Change requests that have been adopted"
    adopted_section_match = re.search(
        r"Change requests that have been adopted.*?(?=Newly posted change requests|$)",
        full_text,
        re.DOTALL | re.IGNORECASE,
    )

    if not adopted_section_match:
        return "No adopted change requests found."

    adopted_section = adopted_section_match.group(0)

    # Pattern to match change requests
    # Format: YYYY-NNN, Action [code] Language Name (639-X) -- description
    pattern = r"(\d{4}-\d{3}),\s+(.+?)\s+--"

    matches = re.findall(pattern, adopted_section)

    if not matches:
        return "No change requests could be parsed."

    # Build the base URL for request links
    # ISO 639-3 change requests typically follow this pattern
    base_url = "https://iso639-3.sil.org/request/"

    # Format as Markdown list
    markdown_list = []
    for case_number, instruction in matches:
        # Clean up the instruction text
        instruction = instruction.strip()

        # Add backticks around language codes [xxx]
        # Pattern matches [xxx] where xxx is typically 3 letters
        instruction = re.sub(r"\[([a-z]{3})]", r"[`\1`]", instruction)

        # Create the request URL
        request_url = f"{base_url}{case_number}"
        # Format as Markdown list item
        markdown_list.append(f"* **[{case_number}]({request_url})**: {instruction}")

    return "\n".join(markdown_list)


@task(schedule="weekly")
def fetch_iso_reports() -> None:
    """
    Fetches ISO 639-3 code change reports and saves them to a YAML file.
    Preserves the posted status of existing reports.
    """
    url = "https://iso639-3.sil.org/code_changes/change_management"

    try:
        # Fetch the page
        response = requests.get(url, headers=get_random_useragent(), timeout=10)
        response.raise_for_status()

        # Parse the HTML
        tree = html.fromstring(response.content)

        # Extract links from the specified xpath
        xpath = "/html/body/div[4]/div/section/div[2]/section/div/div/ul[2]//a"
        links = tree.xpath(xpath)

        reports: List[Dict[str, str]] = []

        for link in links:
            # Get the href attribute
            pdf_link = link.get("href", "")

            # Get the text content (file name)
            file_name = link.text_content().strip()

            if pdf_link and file_name:
                # Extract the year (first word in the file name)
                year = file_name.split()[0]

                # Create report dictionary
                report = {
                    "link": pdf_link,
                    "name": file_name,
                    "year": year,
                    "posted": False,
                }
                reports.append(report)

        # Load existing data to preserve posted status
        existing_data = []
        try:
            with open(Paths.DATASETS["ISO_CODES_UPDATES"], "r") as f:
                existing_data = yaml.safe_load(f) or []
        except FileNotFoundError:
            pass

        # Create a mapping of existing reports by link for quick lookup
        existing_map = {r.get("link"): r.get("posted", False) for r in existing_data}

        # Preserve posted status for reports that already exist
        for report in reports:
            if report["link"] in existing_map:
                report["posted"] = existing_map[report["link"]]

        # Check if contents have changed
        if existing_data == reports:
            logger.debug("No changes detected. ISO Codes Updates dataset not updated.")
            return

        # Write to YAML file
        with open(Paths.DATASETS["ISO_CODES_UPDATES"], "w") as f:
            yaml.dump(reports, f, default_flow_style=False, sort_keys=False)

        logger.info(f"Successfully fetched and saved {len(reports)} reports.")

    except requests.RequestException as e:
        logger.error(f"Error fetching the page: {e}")
    except Exception as e:
        logger.error(f"Error processing data: {e}")

    return


@task(schedule="monthly")
def post_iso_reports_to_reddit() -> None:
    """
    Posts ISO 639-3 reports from the current year to the documentation
    subreddit if they haven't been posted before. Updates the posted status
    in the YAML file after successful posting.
    """
    subreddit_name = "translatorBOT"
    current_year_utc = datetime.now(timezone.utc).year

    try:
        # Load the YAML file
        with open(Paths.DATASETS["ISO_CODES_UPDATES"], "r") as f:
            reports = yaml.safe_load(f) or []

        # Filter reports for the current year and previous year
        previous_year = current_year_utc - 1
        current_and_previous_reports = [
            r
            for r in reports
            if r.get("year") in (str(current_year_utc), str(previous_year))
        ]

        if not current_and_previous_reports:
            logger.info("No reports found for the current or previous year.")
            return

        subreddit = REDDIT.subreddit(subreddit_name)
        updated = False

        for report in current_and_previous_reports:
            pdf_link = report.get("link", "")
            report_name = report.get("name", "")
            posted = report.get("posted", False)

            if not pdf_link:
                logger.debug(f"Skipping report '{report_name}' - no link found.")
                continue

            if posted:
                logger.debug(f"Skipping report '{report_name}' - already posted.")
                continue

            # Post the report
            try:
                title = f"ISO 639-3 {report_name.title()}"
                submission = subreddit.submit(title=title, url=pdf_link)
                submission.flair.select("8bd3439c-3d81-11e7-ac32-0e88f3bc19fa")

                # Update posted status in the report
                report["posted"] = True
                updated = True
                logger.info(f"Successfully posted: {report_name}")
            except PRAWException as e:
                logger.error(f"Error posting '{report_name}': {e}")
            else:
                # Parse the PDF to extract adopted change requests
                try:
                    markdown_list = parse_iso639_newsletter(pdf_link)

                    # Build Discord message with the extracted changes
                    discord_message = (
                        f"SIL has posted a new report: [{report_name}]({pdf_link}).\n\n"
                        f"**Adopted Change Requests:**\n{markdown_list}"
                    )
                except Exception as parse_error:
                    logger.warning(
                        f"Could not parse PDF '{report_name}': {parse_error}"
                    )
                    # Fallback to simple message if parsing fails
                    discord_message = (
                        f"SIL has posted a new report: [{report_name}]({pdf_link})."
                    )

                send_discord_alert(
                    subject="New ISO 639-3 Update",
                    message=discord_message,
                    webhook_name="notification",
                )
                logger.info("Sent an alert to Discord.")

        # Write updated reports back to YAML file if any were posted
        if updated:
            with open(Paths.DATASETS["ISO_CODES_UPDATES"], "w") as f:
                yaml.dump(reports, f, default_flow_style=False, sort_keys=False)
            logger.info("Updated YAML file with posted status.")

    except Exception as e:
        logger.error(f"Error processing reports: {e}")

    return


if __name__ == "__main__":
    fetch_iso_reports()
    post_iso_reports_to_reddit()
