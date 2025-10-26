import datetime
import json
import os
import time
from typing import Optional

from wasabi import msg

from config import Paths, logger
from database import db


def data_validator() -> None:
    """
    Checks the databases and log files to verify they're up-to-date.
    Displays a warning if databases or logs may need to be updated.
    """
    to_warn = False
    warnings = []
    hours_difference = 24 * 60 * 60  # 24 hours in seconds
    current_now = time.time()

    # Check the Points database
    month_year = datetime.datetime.fromtimestamp(current_now).strftime("%Y-%m")
    query = "SELECT * FROM total_points WHERE year_month = ?"
    username_month_points_data = db.fetchall_main(query, (month_year,))

    # If there's no data from the current month's points...
    if len(username_month_points_data) == 0:
        to_warn = True
        warnings.append("No point data found for current month")

    # Check the Ajo database
    most_recent_time = 1000000000  # Initial small value
    query = "SELECT id, created_utc FROM ajo_database"
    stored_ajos = db.fetchall_ajo(query)

    for ajo in stored_ajos:
        time_created = int(ajo["created_utc"])  # Get the UTC time it was created
        if most_recent_time < time_created:
            most_recent_time = time_created

    # Get the time difference
    time_difference = current_now - most_recent_time
    if time_difference > hours_difference:
        to_warn = True
        hours_old = time_difference / 3600
        warnings.append(f"Most recent Ajo entry is {hours_old:.1f} hours old")

    # Check log files for recent activity
    log_files_to_check = {
        "COUNTER": Paths.LOGS["COUNTER"],
        "FILTER": Paths.LOGS["FILTER"],
        "EVENTS": Paths.LOGS["EVENTS"],
        "ACTIVITY": Paths.LOGS["ACTIVITY"],
    }

    for log_name, log_path in log_files_to_check.items():
        last_date = _get_last_date_from_log(log_path, log_name)
        if last_date:
            days_old = _calculate_days_old(last_date, current_now)
            if days_old > 1:  # Warn if more than 1 day old
                to_warn = True
                warnings.append(
                    f"{log_name} log is {days_old} days old (last: {last_date})"
                )

    # Display warning if needed
    if to_warn:
        msg.info("\n" + "=" * 60)
        msg.warn("| WARNING: Database/log files may need updating")
        msg.info("=" * 60)
        for warning in warnings:
            msg.info(f"| * {warning}")
        msg.info("=" * 60)
        msg.warn("| Please consider updating to the latest versions.")
        msg.info("=" * 60 + "\n")
    else:
        msg.good("✓ All databases and logs are up-to-date")

    return


def _get_last_date_from_log(log_path: str, log_type: str) -> Optional[str]:
    """
    Extract the most recent date from a log file.

    Args:
        log_path: Path to the log file
        log_type: Type of log (COUNTER, FILTER, EVENTS, ACTIVITY)

    Returns:
        Date string in YYYY-MM-DD format, or None if not found
    """
    if not os.path.exists(log_path):
        logger.debug(f"Log file not found: {log_path}")
        return None

    try:
        if log_type == "COUNTER":
            # JSON file with date keys
            with open(log_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if data:
                    # Get the most recent date key
                    dates = [k for k in data.keys() if _is_valid_date(k)]
                    return max(dates) if dates else None

        elif log_type in ["FILTER", "EVENTS"]:
            # Markdown files with dates in lines
            with open(log_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
                # Read from end to find most recent date
                for line in reversed(lines):
                    date = _extract_date_from_line(line)
                    if date:
                        return date

        elif log_type == "ACTIVITY":
            # CSV file with dates in first column
            with open(log_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
                if len(lines) > 1:  # Skip header if present
                    last_line = lines[-1].strip()
                    if last_line:
                        # Date might be in first or second column
                        parts = last_line.split(",")
                        for part in parts[:3]:  # Check first 3 columns
                            date = _extract_date_from_text(part.strip())
                            if date:
                                return date

    except Exception as e:
        logger.debug(f"Error reading {log_type} log at {log_path}: {e}")

    return None


def _extract_date_from_line(line: str) -> Optional[str]:
    """Extract a date in YYYY-MM-DD format from a line of text."""
    return _extract_date_from_text(line)


def _extract_date_from_text(text: str) -> Optional[str]:
    """
    Extract a date in YYYY-MM-DD format from text.

    Args:
        text: Text potentially containing a date

    Returns:
        Date string in YYYY-MM-DD format, or None
    """
    import re

    # Look for YYYY-MM-DD pattern
    pattern = r"\b(\d{4}-\d{2}-\d{2})\b"
    match = re.search(pattern, text)
    if match:
        date_str = match.group(1)
        if _is_valid_date(date_str):
            return date_str
    return None


def _is_valid_date(date_str: str) -> bool:
    """
    Check if a string is a valid date in YYYY-MM-DD format.

    Args:
        date_str: String to validate

    Returns:
        True if valid date, False otherwise
    """
    try:
        datetime.datetime.strptime(date_str, "%Y-%m-%d")
        return True
    except (ValueError, TypeError):
        return False


def _calculate_days_old(date_str: str, current_timestamp: float) -> int:
    """
    Calculate how many days old a date string is.

    Args:
        date_str: Date in YYYY-MM-DD format
        current_timestamp: Current Unix timestamp

    Returns:
        Number of days old (rounded)
    """
    try:
        date_obj = datetime.datetime.strptime(date_str, "%Y-%m-%d")
        date_timestamp = date_obj.timestamp()
        days_old = (current_timestamp - date_timestamp) / 86400  # seconds in a day
        return int(days_old)
    except (ValueError, TypeError):
        return 0


if __name__ == "__main__":
    data_validator()
