#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
This module contains tasks related to checking for updates to the
ISO 639-3 and ISO 15924 standards.
...

Logger tag: [WJ:ISO]
"""

# ─── Imports ──────────────────────────────────────────────────────────────────

import logging
import re
import urllib.request
from collections import defaultdict
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
from integrations.http import get_random_useragent
from reddit.connection import REDDIT, submit_translatorbot_post
from wenju import task

# ─── Module-level constants ───────────────────────────────────────────────────

logger = logging.LoggerAdapter(_base_logger, {"tag": "WJ:ISO"})

ISO_639_3_REPORTS_URL = "https://iso639-3.sil.org/code_changes/change_management"
ISO_15924_REGISTRY_URL = "https://www.unicode.org/iso15924/iso15924.txt"
ISO_15924_STANDARD = "ISO 15924"


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


# ─── ISO 15924 parsing ────────────────────────────────────────────────────────


def _parse_iso15924_registry(registry_text: str) -> list[dict[str, str | bool]]:
    """Parse the semicolon-delimited ISO 15924 registry."""
    updates: list[dict[str, str | bool]] = []

    for raw_line in registry_text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        fields = [field.strip() for field in line.split(";")]
        if len(fields) != 7:
            continue

        (
            code,
            number,
            english_name,
            _french_name,
            property_value_alias,
            unicode_version,
            update_date,
        ) = fields

        if not re.fullmatch(r"[A-Z][a-z]{3}", code):
            continue
        if not re.fullmatch(r"\d{3}", number):
            continue
        try:
            datetime.strptime(update_date, "%Y-%m-%d")
        except ValueError:
            continue

        updates.append(
            {
                "standard": ISO_15924_STANDARD,
                "code": code,
                "number": number,
                "name": english_name,
                "property_value_alias": property_value_alias,
                "unicode_version": unicode_version,
                "date": update_date,
                "link": ISO_15924_REGISTRY_URL,
                "posted": False,
            }
        )

    if not updates:
        raise ValueError("No ISO 15924 records could be parsed.")

    return updates


def _merge_iso15924_updates(
    existing_updates: list[dict],
    fetched_updates: list[dict[str, str | bool]],
) -> list[dict[str, str | bool]]:
    """
    Preserve alert status while replacing the ISO 15924 registry snapshot.

    The first fetch establishes a quiet baseline. On later fetches, any new
    code-and-date identity is treated as a new alert, including an addition
    to a date batch that was already seen.
    """
    posted_by_identity = {
        (str(update.get("code", "")), str(update.get("date", ""))): bool(
            update.get("posted", False)
        )
        for update in existing_updates
    }
    establishing_baseline = not existing_updates

    for update in fetched_updates:
        identity = (str(update["code"]), str(update["date"]))
        update["posted"] = posted_by_identity.get(identity, establishing_baseline)

    return fetched_updates


# ─── Report fetching ──────────────────────────────────────────────────────────


def _fetch_iso639_reports(
    existing_reports: list[dict],
) -> list[dict[str, str | bool]]:
    """Fetch ISO 639-3 reports while preserving their posted status."""
    response = requests.get(
        ISO_639_3_REPORTS_URL,
        headers=get_random_useragent(),
        timeout=10,
    )
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

    existing_map: dict[str, bool] = {
        str(link): bool(report.get("posted", False))
        for report in existing_reports
        if (link := report.get("link")) is not None
    }

    for report in reports:
        report_link = str(report["link"])
        if report_link in existing_map:
            report["posted"] = existing_map[report_link]

    return reports


def _fetch_iso15924_updates(
    existing_updates: list[dict],
) -> list[dict[str, str | bool]]:
    """Fetch and merge the current ISO 15924 registry."""
    response = requests.get(
        ISO_15924_REGISTRY_URL,
        headers=get_random_useragent(),
        timeout=10,
    )
    response.raise_for_status()
    registry_text = response.content.decode("utf-8-sig")
    fetched_updates = _parse_iso15924_registry(registry_text)
    return _merge_iso15924_updates(existing_updates, fetched_updates)


@task(schedule="weekly")
def fetch_iso_reports() -> None:
    """
    Fetch ISO 639-3 reports and ISO 15924 registry updates into one YAML file.

    Each source is fetched independently so a temporary failure from one
    standards body does not prevent the other source from being refreshed.
    """
    try:
        with open(Paths.STATES["ISO_CODES_UPDATES"]) as f:
            loaded_data = yaml.safe_load(f) or []
        existing_data = loaded_data if isinstance(loaded_data, list) else []
    except FileNotFoundError:
        existing_data = []
    except (OSError, yaml.YAMLError) as e:
        logger.error(f"Error loading ISO Codes Updates dataset: {e}")
        return

    iso15924_existing = [
        update
        for update in existing_data
        if isinstance(update, dict) and update.get("standard") == ISO_15924_STANDARD
    ]
    iso639_existing = [
        report
        for report in existing_data
        if isinstance(report, dict) and report.get("standard") != ISO_15924_STANDARD
    ]

    iso639_reports = iso639_existing
    iso15924_updates = iso15924_existing
    successful_fetches = 0

    try:
        iso639_reports = _fetch_iso639_reports(iso639_existing)
        successful_fetches += 1
    except requests.RequestException as e:
        logger.error(f"Error fetching ISO 639-3 reports: {e}")
    except Exception as e:
        logger.error(f"Error processing ISO 639-3 reports: {e}")

    try:
        iso15924_updates = _fetch_iso15924_updates(iso15924_existing)
        successful_fetches += 1
    except requests.RequestException as e:
        logger.error(f"Error fetching ISO 15924 registry: {e}")
    except Exception as e:
        logger.error(f"Error processing ISO 15924 registry: {e}")

    if not successful_fetches:
        return

    updated_data = [*iso639_reports, *iso15924_updates]
    if existing_data == updated_data:
        logger.info("No changes detected. ISO Codes Updates dataset not updated.")
        return

    try:
        with open(Paths.STATES["ISO_CODES_UPDATES"], "w") as f:
            yaml.dump(updated_data, f, default_flow_style=False, sort_keys=False)
    except OSError as e:
        logger.error(f"Error saving ISO Codes Updates dataset: {e}")
        return

    logger.info(
        "Successfully saved "
        f"{len(iso639_reports)} ISO 639-3 reports and "
        f"{len(iso15924_updates)} ISO 15924 records."
    )

    return


# ─── Report posting ───────────────────────────────────────────────────────────


@task(schedule="monthly")
def post_iso_reports_to_reddit() -> None:
    """
    Post recent ISO 639-3 reports and ISO 15924 updates to the documentation
    subreddit if they haven't been posted before. Updates the posted status
    in the shared YAML file after successful posting.
    """
    current_year_utc = datetime.now(UTC).year

    try:
        with open(Paths.STATES["ISO_CODES_UPDATES"]) as f:
            reports = yaml.safe_load(f) or []

        previous_year = current_year_utc - 1
        iso639_reports = [
            r
            for r in reports
            if r.get("standard") != ISO_15924_STANDARD
            if r.get("year") in (str(current_year_utc), str(previous_year))
        ]
        iso15924_updates = [
            r
            for r in reports
            if r.get("standard") == ISO_15924_STANDARD
            and str(r.get("date", ""))[:4]
            in (str(current_year_utc), str(previous_year))
            and not r.get("posted", False)
        ]

        updated = False

        for report in iso639_reports:
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
                submit_translatorbot_post(
                    title,
                    url=pdf_link,
                    flair_id="8bd3439c-3d81-11e7-ac32-0e88f3bc19fa",
                    reddit=REDDIT,
                )

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

        updates_by_date: dict[str, list[dict]] = defaultdict(list)
        for update in iso15924_updates:
            updates_by_date[str(update.get("date", ""))].append(update)

        for update_date, dated_updates in sorted(updates_by_date.items()):
            markdown_lines = []
            for update in sorted(
                dated_updates, key=lambda item: str(item.get("code", ""))
            ):
                code = str(update.get("code", ""))
                number = str(update.get("number", ""))
                name = str(update.get("name", ""))
                unicode_version = str(update.get("unicode_version", ""))
                unicode_note = f"; Unicode {unicode_version}" if unicode_version else ""
                markdown_lines.append(
                    f"* **`{code}` ({number})**: {name}{unicode_note}"
                )

            try:
                submit_translatorbot_post(
                    f"ISO 15924 Update ({update_date})",
                    url=ISO_15924_REGISTRY_URL,
                    flair_id="8bd3439c-3d81-11e7-ac32-0e88f3bc19fa",
                    reddit=REDDIT,
                )

                for update in dated_updates:
                    update["posted"] = True
                updated = True
                logger.info(
                    "Successfully posted "
                    f"{len(dated_updates)} ISO 15924 updates from {update_date}."
                )
            except PRAWException as e:
                logger.error(f"Error posting ISO 15924 update '{update_date}': {e}")
            else:
                send_discord_alert(
                    subject="New ISO 15924 Update",
                    message=(
                        "Unicode has published ISO 15924 updates dated "
                        f"**{update_date}**:\n\n"
                        + "\n".join(markdown_lines)
                        + f"\n\n[View the ISO 15924 registry]"
                        f"({ISO_15924_REGISTRY_URL})."
                    ),
                    webhook_name="notification",
                )
                logger.info("Sent an ISO 15924 alert to Discord.")

        if not iso639_reports and not iso15924_updates:
            logger.info("No unposted recent ISO updates found.")

        if updated:
            with open(Paths.STATES["ISO_CODES_UPDATES"], "w") as f:
                yaml.dump(reports, f, default_flow_style=False, sort_keys=False)
            logger.info("Updated YAML file with posted status.")

    except Exception as e:
        logger.error(f"Error processing reports: {e}")

    return
