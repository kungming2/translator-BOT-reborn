#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
This module contains tasks related to checking the SIL website for
updates to the ISO 639-3 standard.
...

Logger tag: [WJ:ISO]
"""

# ─── Imports ──────────────────────────────────────────────────────────────────

import logging
import re
import urllib.request
from datetime import UTC, datetime
from io import BytesIO

import requests
import yaml
from lxml import html
from praw.exceptions import PRAWException
from pypdf import PdfReader

from config import Paths
from config import logger as _base_logger
from integrations.discord_utils import send_discord_alert
from reddit.connection import REDDIT, get_random_useragent
from wenju import task

# ─── Module-level constants ───────────────────────────────────────────────────

logger = logging.LoggerAdapter(_base_logger, {"tag": "WJ:ISO"})


# ─── PDF parsing ─────────────────────────────────────────────────────────────


def _parse_iso639_newsletter(pdf_source: str) -> str:
    """
    Parse an ISO 639 MA Newsletter PDF and extract adopted change requests.

    Args:
        pdf_source: URL to the PDF file or local file path

    Returns:
        Markdown-formatted list of adopted change requests
    """
    if pdf_source.startswith(("http://", "https://")):
        req = urllib.request.Request(pdf_source, headers=get_random_useragent())
        with urllib.request.urlopen(req) as response:
            pdf_data = response.read()
        pdf_file = BytesIO(pdf_data)
        reader = PdfReader(pdf_file)
    else:
        reader = PdfReader(pdf_source)

    full_text = ""
    for page in reader.pages:
        full_text += page.extract_text()

    adopted_section_match = re.search(
        r"Change requests that have been adopted.*?(?=Newly posted change requests|$)",
        full_text,
        re.DOTALL | re.IGNORECASE,
    )

    if not adopted_section_match:
        return "No adopted change requests found."

    adopted_section = adopted_section_match.group(0)

    # Pattern: YYYY-NNN, Action [code] Language Name (639-X) -- description
    pattern = r"(\d{4}-\d{3}),\s+(.+?)\s+--"
    matches = re.findall(pattern, adopted_section)

    if not matches:
        return "No change requests could be parsed."

    base_url = "https://iso639-3.sil.org/request/"

    markdown_list = []
    for case_number, instruction in matches:
        instruction = instruction.strip()
        instruction = re.sub(r"\[([a-z]{3})]", r"[`\1`]", instruction)
        request_url = f"{base_url}{case_number}"
        markdown_list.append(f"* **[{case_number}]({request_url})**: {instruction}")

    return "\n".join(markdown_list)


# ─── Report fetching ──────────────────────────────────────────────────────────


@task(schedule="weekly")
def fetch_iso_reports() -> None:
    """
    Fetch ISO 639-3 code change reports and save them to a YAML file.
    Preserves the posted status of existing reports.
    """
    url = "https://iso639-3.sil.org/code_changes/change_management"

    try:
        response = requests.get(url, headers=get_random_useragent(), timeout=10)
        response.raise_for_status()

        tree = html.fromstring(response.content)

        xpath = "/html/body/div[4]/div/section/div[2]/section/div/div/ul[2]//a"
        links = tree.xpath(xpath)

        reports: list[dict[str, str | bool]] = []

        for link in links:
            pdf_link = link.get("href", "")
            file_name = link.text_content().strip()

            if pdf_link and file_name:
                year = file_name.split()[0]
                report = {
                    "link": pdf_link,
                    "name": file_name,
                    "year": year,
                    "posted": False,
                }
                reports.append(report)

        existing_data: list[dict] = []
        try:
            with open(Paths.STATES["ISO_CODES_UPDATES"]) as f:
                existing_data = yaml.safe_load(f) or []
        except FileNotFoundError:
            pass

        existing_map: dict[str, bool] = {
            link: r.get("posted", False)
            for r in existing_data
            if (link := r.get("link")) is not None
        }

        for report in reports:
            if report["link"] in existing_map:
                report["posted"] = existing_map[str(report["link"])]

        if existing_data == reports:
            logger.info("No changes detected. ISO Codes Updates dataset not updated.")
            return

        with open(Paths.STATES["ISO_CODES_UPDATES"], "w") as f:
            yaml.dump(reports, f, default_flow_style=False, sort_keys=False)

        logger.info(f"Successfully fetched and saved {len(reports)} reports.")

    except requests.RequestException as e:
        logger.error(f"Error fetching the page: {e}")
    except Exception as e:
        logger.error(f"Error processing data: {e}")

    return


# ─── Report posting ───────────────────────────────────────────────────────────


@task(schedule="monthly")
def post_iso_reports_to_reddit() -> None:
    """
    Post ISO 639-3 reports from the current year to the documentation
    subreddit if they haven't been posted before. Updates the posted status
    in the YAML file after successful posting.
    """
    subreddit_name = "translatorBOT"
    current_year_utc = datetime.now(UTC).year

    try:
        with open(Paths.STATES["ISO_CODES_UPDATES"]) as f:
            reports = yaml.safe_load(f) or []

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

            try:
                title = f"ISO 639-3 {report_name.title()}"
                submission = subreddit.submit(title=title, url=pdf_link)
                submission.flair.select("8bd3439c-3d81-11e7-ac32-0e88f3bc19fa")

                report["posted"] = True
                updated = True
                logger.info(f"Successfully posted: {report_name}")
            except PRAWException as e:
                logger.error(f"Error posting '{report_name}': {e}")
            else:
                try:
                    markdown_list = _parse_iso639_newsletter(pdf_link)
                    discord_message = (
                        f"SIL has posted a new report: [{report_name}]({pdf_link}).\n\n"
                        f"**Adopted Change Requests:**\n{markdown_list}"
                    )
                except Exception as parse_error:
                    logger.warning(
                        f"Could not parse PDF '{report_name}': {parse_error}"
                    )
                    discord_message = (
                        f"SIL has posted a new report: [{report_name}]({pdf_link})."
                    )

                send_discord_alert(
                    subject="New ISO 639-3 Update",
                    message=discord_message,
                    webhook_name="notification",
                )
                logger.info("Sent an alert to Discord.")

        if updated:
            with open(Paths.STATES["ISO_CODES_UPDATES"], "w") as f:
                yaml.dump(reports, f, default_flow_style=False, sort_keys=False)
            logger.info("Updated YAML file with posted status.")

    except Exception as e:
        logger.error(f"Error processing reports: {e}")

    return
