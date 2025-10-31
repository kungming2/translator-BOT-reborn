#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""Caching functions for lookup scripts."""

import json
import re
import time
from typing import Dict

from database import db

"""CACHE INPUT/OUTPUT"""


def save_to_cache(data: Dict, language_code: str, lookup_type: str) -> None:
    """
    Save parsed CJK lookup data to the lookup_cjk_cache table.

    :param data: Dictionary with parsed data (output from parse_zh_output_to_json)
    :param language_code: Language code (e.g., "zh", "ja", "ko")
    :param lookup_type: Lookup type (e.g., "zh_word", "zh_character")
    """
    # Determine which field to use as the term key based on language
    if language_code == "zh":
        term = data.get("traditional")
        if not term:
            raise ValueError("No traditional character/word found in data")
    elif language_code == "ja":
        # For Japanese, use the kanji/kana as the term
        term = data.get("term") or data.get("kanji") or data.get("word")
        if not term:
            raise ValueError("No Japanese term found in data")
    elif language_code == "ko":
        # For Korean, use the hangul as the term
        term = data.get("term") or data.get("hangul") or data.get("word")
        if not term:
            raise ValueError("No Korean term found in data")
    else:
        # Generic fallback - try common field names
        term = data.get("term") or data.get("word") or data.get("traditional")
        if not term:
            raise ValueError(
                f"No term found in data for language code '{language_code}'"
            )

    # Convert data dict to JSON string
    data_json = json.dumps(data, ensure_ascii=False)

    # Get current UTC timestamp
    retrieved_utc = int(time.time())

    # Prepare the insert query with REPLACE to handle updates
    query = """
        INSERT OR REPLACE INTO lookup_cjk_cache 
        (term, language_code, retrieved_utc, type, data) 
        VALUES (?, ?, ?, ?, ?)
    """

    cursor = db.cursor_cache
    cursor.execute(query, (term, language_code, retrieved_utc, lookup_type, data_json))
    db.conn_cache.commit()


def get_from_cache(
    term: str, language_code: str, lookup_type: str, max_age_days: int = 30
) -> Dict | None:
    """
    Retrieve cached CJK lookup data from the database.

    :param term: The term to look up (e.g., traditional Chinese, Japanese kanji, Korean hangul)
    :param language_code: Language code (e.g., "zh", "ja", "ko")
    :param lookup_type: Lookup type (e.g., "zh_word", "zh_character")
    :param max_age_days: Maximum age of cached data in days (default: 30)
    :return: Parsed dictionary if found and not expired, None otherwise
    """
    cutoff_time = int(time.time()) - (max_age_days * 86400)

    query = """
            SELECT data, retrieved_utc
            FROM lookup_cjk_cache
            WHERE term = ? \
              AND language_code = ? \
              AND type = ? \
              AND retrieved_utc >= ? \
            """

    cursor = db.cursor_cache
    cursor.execute(query, (term, language_code, lookup_type, cutoff_time))
    result = cursor.fetchone()

    if result:
        data_json = result[0]
        try:
            return json.loads(data_json)
        except json.JSONDecodeError:
            return None

    return None


"""CHINESE CACHING"""


def parse_zh_output_to_json(markdown_output: str) -> Dict[str, any]:
    """
    Parse the markdown output from zh_word or zh_character into structured JSON.

    :param markdown_output: The markdown string returned by zh_word or zh_character
    :return: Dictionary with structured data
    """
    result: Dict[str, any] = {
        "traditional": None,
        "simplified": None,
        "pronunciations": {},
        "meanings": None,
        "buddhist_meanings": None,
        "cantonese_meanings": None,
        "tea_meanings": None,
        "chengyu_meaning": None,  # for chengyu
        "chengyu_source": None,  # for chengyu
    }

    # Extract traditional and simplified forms from header
    # Pattern: # [多謝 / 多谢] or # [字]
    header_match = re.search(r"#\s*\[([^]]+)]", markdown_output)
    if header_match:
        header_text = header_match.group(1)
        if "/" in header_text:
            parts = header_text.split("/")
            result["traditional"] = parts[0].strip()
            result["simplified"] = parts[1].strip()
        else:
            # Same for both
            result["traditional"] = header_text.strip()
            result["simplified"] = header_text.strip()

    # Extract pronunciations from table
    # Pattern: | **Language** | *pronunciation* |
    pronunciation_patterns = {
        "mandarin_pinyin": r"\|\s*\*\*Mandarin\*\*\s*\(Pinyin\)\s*\|\s*\*([^*]+)\*",
        "mandarin_wade_giles": r"\|\s*\*\*Mandarin\*\*\s*\(Wade-Giles\)\s*\|\s*\*([^*]+)\*",
        "mandarin_yale": r"\|\s*\*\*Mandarin\*\*\s*\(Yale\)\s*\|\s*\*([^*]+)\*",
        "mandarin_gr": r"\|\s*\*\*Mandarin\*\*\s*\(GR\)\s*\|\s*\*([^*]+)\*",
        "mandarin": r"\|\s*\*\*Mandarin\*\*\s*\|\s*\*([^*]+)\*",  # for zh_character
        "cantonese": r"\|\s*\*\*Cantonese\*\*\s*\|\s*\*([^*]+)\*",
        "southern_min": r"\|\s*\*\*Southern Min\*\*\s*\|\s*\*([^*]+)\*",
        "hakka_sixian": r"\|\s*\*\*Hakka \(Sixian\)\*\*\s*\|\s*\*([^*]+)\*",
        "japanese": r"\|\s*\*\*Japanese\*\*\s*\|\s*\*([^*]+)\*",
        "vietnamese": r"\|\s*\*\*Vietnamese\*\*\s*\|\s*\*([^*]+)\*",
        "middle_chinese": r"\|\s*\*\*Middle Chinese\*\*\s*\|\s*\\?\*\*?([^*|]+)\*?",
        "old_chinese": r"\|\s*\*\*Old Chinese\*\*\s*\|\s*\\?\*([^*|]+)\*",
    }

    # Special pattern for Korean (has both Hangul and romanization)
    korean_match = re.search(
        r"\|\s*\*\*Korean\*\*\s*\|\s*([^(]+)\s*\(\*([^)]+)\*\)", markdown_output
    )
    if korean_match:
        result["pronunciations"]["korean_hangul"] = korean_match.group(1).strip()
        result["pronunciations"]["korean_romanized"] = korean_match.group(2).strip()

    for key, pattern in pronunciation_patterns.items():
        match = re.search(pattern, markdown_output)
        if match:
            result["pronunciations"][key] = match.group(1).strip()

    # Extract main meanings
    # Pattern: **Meanings**: "text."
    meanings_match = re.search(r'\*\*Meanings\*\*:\s*"([^"]+)"', markdown_output)
    if meanings_match:
        result["meanings"] = meanings_match.group(1).strip()

    # Extract Buddhist meanings
    buddhist_match = re.search(
        r'\*\*Buddhist Meanings\*\*:\s*"([^"]+)"', markdown_output
    )
    if buddhist_match:
        result["buddhist_meanings"] = buddhist_match.group(1).strip()

    # Extract Cantonese meanings
    cantonese_match = re.search(
        r'\*\*Cantonese Meanings\*\*:\s*"([^"]+)"', markdown_output
    )
    if cantonese_match:
        result["cantonese_meanings"] = cantonese_match.group(1).strip()

    # Extract Tea meanings
    tea_match = re.search(r'\*\*Tea Meanings\*\*:\s*"([^"]+)"', markdown_output)
    if tea_match:
        result["tea_meanings"] = tea_match.group(1).strip()

    # Extract Chinese meaning (for chengyu)
    chinese_meaning_match = re.search(
        r"\*\*Chinese Meaning\*\*:\s*([^\n]+)", markdown_output
    )
    if chinese_meaning_match:
        result["chinese_meaning"] = chinese_meaning_match.group(1).strip()

    # Extract Literary Source (for chengyu)
    literary_source_match = re.search(
        r"\*\*Literary Source\*\*:\s*([^\n(]+)", markdown_output
    )
    if literary_source_match:
        result["literary_source"] = literary_source_match.group(1).strip()

    # Clean up empty fields
    result["pronunciations"] = {k: v for k, v in result["pronunciations"].items() if v}

    return result


# Example usage
if __name__ == "__main__":
    import asyncio
    import sys

    # Add parent directory to path to import zh module
    sys.path.insert(0, "..")
    from zh import zh_character, zh_word

    async def cache_writer():
        """Interactive test function for caching zh_word and zh_character lookups."""
        print("\n=== Chinese Word/Character Lookup Cache Tester ===\n")

        while True:
            print("\nOptions:")
            print("1. Lookup and cache a word (zh_word)")
            print("2. Lookup and cache a character (zh_character)")
            print("3. Check cache for a term")
            print("x. Exit")

            choice = input("\nEnter your choice: ").strip()

            if choice == "x":
                print("Exiting...")
                break

            if choice == "1":
                word = input("Enter Chinese word to lookup: ").strip()
                if not word:
                    print("No input provided.")
                    continue

                print(f"\nLooking up '{word}'...")
                try:
                    result = await zh_word(word)
                    print("\n--- Raw Result ---")
                    print(result)

                    print("\n--- Parsing to JSON ---")
                    parsed = parse_zh_output_to_json(result)
                    print(json.dumps(parsed, ensure_ascii=False, indent=2))

                    print("\n--- Saving to cache ---")
                    save_to_cache(parsed, "zh", "zh_word")
                    print("✓ Saved to cache successfully!")

                except Exception as e:
                    print(f"Error: {e}")
                    import traceback

                    traceback.print_exc()

            elif choice == "2":
                char = input("Enter Chinese character to lookup: ").strip()
                if not char:
                    print("No input provided.")
                    continue

                print(f"\nLooking up '{char}'...")
                try:
                    result = await zh_character(char)
                    print("\n--- Raw Result ---")
                    print(result)

                    print("\n--- Parsing to JSON ---")
                    parsed = parse_zh_output_to_json(result)
                    print(json.dumps(parsed, ensure_ascii=False, indent=2))

                    print("\n--- Saving to cache ---")
                    save_to_cache(parsed, "zh", "zh_character")
                    print("✓ Saved to cache successfully!")

                except Exception as e:
                    print(f"Error: {e}")
                    import traceback

                    traceback.print_exc()

            elif choice == "3":
                term = input("Enter term to check in cache: ").strip()
                if not term:
                    print("No input provided.")
                    continue

                lookup_type = input("Type (zh_word/zh_character): ").strip()
                if lookup_type not in ["zh_word", "zh_character"]:
                    print("Invalid type. Must be 'zh_word' or 'zh_character'")
                    continue

                print(f"\nChecking cache for '{term}' ({lookup_type})...")
                cached = get_from_cache(term, "zh", lookup_type)

                if cached:
                    print("\n✓ Found in cache:")
                    print(json.dumps(cached, ensure_ascii=False, indent=2))
                else:
                    print("\n✗ Not found in cache (or expired)")

    # Run the async test function
    asyncio.run(cache_writer())
