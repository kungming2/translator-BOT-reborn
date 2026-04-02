#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
Caching functions for lookup scripts.
...

Logger tag: [L:CACHE]
"""

import json
import logging
import re
import sqlite3
import threading
import time
from collections.abc import Awaitable, Callable
from typing import Any

from config import SETTINGS, Paths
from config import logger as _base_logger
from lang.languages import converter

logger = logging.LoggerAdapter(_base_logger, {"tag": "L:CACHE"})


# ─── Cache database access ────────────────────────────────────────────────────

_cache_thread_local = threading.local()


def _get_thread_local_cursor() -> tuple[sqlite3.Cursor, sqlite3.Connection]:
    """
    Return a (cursor, connection) pair bound to the calling thread.

    SQLite connections cannot be shared across threads. When cache functions
    are invoked from a thread-pool worker — via asyncio.to_thread or
    run_in_executor — they run on a different thread from the one that owns
    db.conn_cache, causing a ProgrammingError.

    threading.local() gives each thread its own isolated namespace. The first
    call from a given thread opens a fresh connection to the cache database and
    stores it under _cache_thread_local.conn. All subsequent calls from that
    same thread reuse the existing connection. Thread-pool workers are reused
    by asyncio across coroutine invocations, so at most one connection is
    opened per pooled thread.
    """
    if not hasattr(_cache_thread_local, "conn"):
        conn = sqlite3.connect(Paths.DATABASE["CACHE"])
        conn.row_factory = sqlite3.Row
        _cache_thread_local.conn = conn
    return _cache_thread_local.conn.cursor(), _cache_thread_local.conn


def save_to_cache(data: dict, language_code: str, lookup_type: str) -> None:
    """
    Save parsed CJK lookup data to the lookup_cjk_cache table.
    """
    if language_code == "zh":
        term = data.get("traditional")
        if not term:
            raise ValueError("No traditional character/word found in data")
    elif language_code == "ja":
        term = data.get("term") or data.get("kanji") or data.get("word")
        if not term:
            raise ValueError("No Japanese term found in data")
    elif language_code == "ko":
        term = data.get("term") or data.get("hangul") or data.get("word")
        if not term:
            raise ValueError("No Korean term found in data")
    else:
        term = data.get("term") or data.get("word") or data.get("traditional")
        if not term:
            raise ValueError(
                f"No term found in data for language code '{language_code}'"
            )

    data_json = json.dumps(data, ensure_ascii=False)
    retrieved_utc = int(time.time())

    query = """
        INSERT OR REPLACE INTO lookup_cjk_cache 
        (term, language_code, retrieved_utc, type, data, fetch_count) 
        VALUES (?, ?, ?, ?, ?, 0)
    """

    cursor, conn = _get_thread_local_cursor()
    cursor.execute(query, (term, language_code, retrieved_utc, lookup_type, data_json))
    conn.commit()


def get_from_cache(term: str, language_code: str, lookup_type: str) -> dict | None:
    """
    Retrieve cached CJK lookup data from the database.

    Increments ``fetch_count`` on every cache hit so that hot entries can be
    identified via the ``lookup_cjk_cache`` table.
    """
    max_age_days = SETTINGS["lookup_cjk_cache_age"]
    cutoff_time = int(time.time()) - (max_age_days * 86400)

    query = """
            SELECT data, retrieved_utc
            FROM lookup_cjk_cache
            WHERE term = ?
              AND language_code = ?
              AND type = ?
              AND retrieved_utc >= ?
            """

    cursor, conn = _get_thread_local_cursor()
    cursor.execute(query, (term, language_code, lookup_type, cutoff_time))
    result = cursor.fetchone()

    if result:
        increment_query = """
            UPDATE lookup_cjk_cache
            SET fetch_count = fetch_count + 1
            WHERE term = ?
              AND language_code = ?
              AND type = ?
        """
        cursor.execute(increment_query, (term, language_code, lookup_type))
        conn.commit()

        data_json = result[0]
        try:
            return json.loads(data_json)
        except json.JSONDecodeError:
            return None

    return None


def get_cjk_cache_top_entries(limit: int = 20) -> str:
    """
    Query the lookup_cjk_cache table and return a Markdown table of the
    most-fetched entries, ordered by fetch_count descending.

    :param limit: Maximum number of rows to include (default 20).
    :return: Markdown-formatted table string with columns:
             term, language, type, fetch_count.
    """
    query = """
        SELECT term, language_code, type, fetch_count
        FROM lookup_cjk_cache
        ORDER BY fetch_count DESC
        LIMIT ?
    """
    cursor, _ = _get_thread_local_cursor()
    cursor.execute(query, (limit,))
    rows = cursor.fetchall()

    if not rows:
        logger.error("CJK cache table is empty.")
        return "*No entries found in lookup_cjk_cache.*"

    lines = [
        "| Term | Language | Lookup Type | Cache Fetch Count |",
        "|------|----------|-------------|-------------------|",
    ]
    for row in rows:
        language_lingvo = converter(row["language_code"])
        num_fetches = row["fetch_count"]
        if language_lingvo and num_fetches > 0:
            language_name = language_lingvo.name
            lines.append(
                f"| {row['term']} | {language_name} | {row['type']} | {num_fetches} |"
            )

    return "\n".join(lines)


# ─── Chinese parse / format ───────────────────────────────────────────────────


def parse_zh_output_to_json(markdown_output: str) -> dict[str, Any]:
    """
    Parse the markdown output from zh_word or zh_character into structured
    JSON.

    :param markdown_output: The markdown string returned by zh_word or
                            zh_character
    :return: Dictionary with structured data
    """
    result: dict[str, Any] = {
        "traditional": None,
        "simplified": None,
        "pronunciations": {},
        "meanings": None,  # English translation
        "buddhist_meanings": None,
        "cantonese_meanings": None,
        "chengyu_meaning": None,  # for chengyu
        "chengyu_source": None,  # for chengyu
        "chinese_meaning": None,  # for chengyu
        "literary_source": None,  # for chengyu
        "calligraphy_links": {
            "sfzd_image": None,  # calligraphy image
            "sfds": None,  # SFDS calligraphy link
            "variants": None,  # YTZZD variants dictionary link
        },
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
            result["traditional"] = header_text.strip()
            result["simplified"] = header_text.strip()

    calligraphy_match = re.search(
        r"\*\*Chinese Calligraphy Variants\*\*:\s*"
        r"\[[^]]+]\((https://[^\s)]+shufazidian\.com[^\s)]+)\)",
        markdown_output,
    )
    if calligraphy_match:
        result["calligraphy_links"]["sfzd_image"] = calligraphy_match.group(1).strip()

    # Pattern: *[SFDS](https://www.sfds.cn/4F24/)*
    sfds_match = re.search(
        r"\[SFDS]\((https://www\.sfds\.cn/[^\s)]+)\)", markdown_output
    )
    if sfds_match:
        result["calligraphy_links"]["sfds"] = sfds_match.group(1).strip()

    # Pattern: *[YTZZD](https://dict.variants.moe.edu.tw/dictView.jsp?ID=2007&q=1)*
    variants_match = re.search(
        r"\[YTZZD]\((https://dict\.variants\.moe\.edu\.tw/[^\s)]+)\)",
        markdown_output,
    )
    if variants_match:
        variants_url = variants_match.group(1).strip()
        if "dictView.jsp" in variants_url:
            result["calligraphy_links"]["variants"] = variants_url

    # Extract pronunciations from table
    # Pattern: | **Language** | *pronunciation* |
    pronunciation_patterns = {
        "mandarin_pinyin": r"\|\s*\*\*Mandarin\*\*\s*\(Pinyin\)\s*\|\s*\*([^*]+)\*",
        "mandarin_wade_giles": (
            r"\|\s*\*\*Mandarin\*\*\s*\(Wade-Giles\)\s*\|\s*\*([^*]+)\*"
        ),
        "mandarin_yale": r"\|\s*\*\*Mandarin\*\*\s*\(Yale\)\s*\|\s*\*([^*]+)\*",
        "mandarin_gr": r"\|\s*\*\*Mandarin\*\*\s*\(GR\)\s*\|\s*\*([^*]+)\*",
        "mandarin": r"\|\s*\*\*Mandarin\*\*\s*\|\s*\*([^*]+)\*",
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

    # Pattern: **Meanings**: "text."
    meanings_match = re.search(r'\*\*Meanings\*\*:\s*"([^"]+)"', markdown_output)
    if meanings_match:
        result["meanings"] = meanings_match.group(1).strip()

    buddhist_match = re.search(
        r'\*\*Buddhist Meanings\*\*:\s*"([^"]+)"', markdown_output
    )
    if buddhist_match:
        result["buddhist_meanings"] = buddhist_match.group(1).strip()

    cantonese_match = re.search(
        r'\*\*Cantonese Meanings\*\*:\s*"([^"]+)"', markdown_output
    )
    if cantonese_match:
        result["cantonese_meanings"] = cantonese_match.group(1).strip()

    chinese_meaning_match = re.search(
        r"\*\*Chinese Meaning\*\*:\s*([^\n]+)", markdown_output
    )
    if chinese_meaning_match:
        result["chinese_meaning"] = chinese_meaning_match.group(1).strip()

    literary_source_match = re.search(
        r"\*\*Literary Source\*\*:\s*([^\n(]+)", markdown_output
    )
    if literary_source_match:
        result["literary_source"] = literary_source_match.group(1).strip()

    result["pronunciations"] = {k: v for k, v in result["pronunciations"].items() if v}

    if not any(result["calligraphy_links"].values()):
        result["calligraphy_links"] = None
    else:
        result["calligraphy_links"] = {
            k: v for k, v in result["calligraphy_links"].items() if v is not None
        }

    return result


def format_zh_character_from_cache(cached_data: dict) -> str:
    """
    Reconstruct the zh_character markdown output from cached data.

    :param cached_data: Dictionary with parsed character data
    :return: Formatted markdown string
    """
    trad = cached_data.get("traditional")
    simp = cached_data.get("simplified")
    pronunciations = cached_data.get("pronunciations", {})
    meanings = cached_data.get("meanings", "")
    calligraphy = cached_data.get("calligraphy_links")

    if trad == simp:
        header = f"# [{trad}](https://en.wiktionary.org/wiki/{trad}#Chinese)\n\n"
    else:
        header = (
            f"# [{trad} / {simp}](https://en.wiktionary.org/wiki/{trad}#Chinese)\n\n"
        )

    table = "| Language | Pronunciation |\n|----------|---------------|\n"

    if "mandarin" in pronunciations:
        table += f"| **Mandarin** | *{pronunciations['mandarin']}* |\n"
    elif "mandarin_pinyin" in pronunciations:
        table += f"| **Mandarin** | *{pronunciations['mandarin_pinyin']}* |\n"
    if "cantonese" in pronunciations:
        table += f"| **Cantonese** | *{pronunciations['cantonese']}* |\n"
    if "southern_min" in pronunciations:
        table += f"| **Southern Min** | *{pronunciations['southern_min']}* |\n"
    if "hakka_sixian" in pronunciations:
        table += f"| **Hakka (Sixian)** | *{pronunciations['hakka_sixian']}* |\n"
    if "middle_chinese" in pronunciations:
        table += f"| **Middle Chinese** | \\**{pronunciations['middle_chinese']}* |\n"
    if "old_chinese" in pronunciations:
        table += f"| **Old Chinese** | \\*{pronunciations['old_chinese']}* |\n"
    if "japanese" in pronunciations:
        table += f"| **Japanese** | *{pronunciations['japanese']}* |\n"
    if "korean_hangul" in pronunciations and "korean_romanized" in pronunciations:
        table += f"| **Korean** | {pronunciations['korean_hangul']} (*{pronunciations['korean_romanized']}*) |\n"
    if "vietnamese" in pronunciations:
        table += f"| **Vietnamese** | *{pronunciations['vietnamese']}* |\n"

    calligraphy_section = ""
    if calligraphy:
        sfzd_image = calligraphy.get("sfzd_image")
        sfds = calligraphy.get("sfds")
        variants = calligraphy.get("variants")

        if sfzd_image:
            variant_link = (
                f"[YTZZD]({variants})"
                if variants
                else "[YTZZD](https://dict.variants.moe.edu.tw/)"
            )
            calligraphy_section = (
                f"\n\n**Chinese Calligraphy Variants**: [{trad}]({sfzd_image}) "
                f"(*[SFZD](https://www.shufazidian.com/)*, *[SFDS]({sfds})*, *{variant_link}*)"
            )

    meanings_section = f'\n\n**Meanings**: "{meanings}"'

    if cached_data.get("buddhist_meanings"):
        meanings_section += (
            f'\n\n**Buddhist Meanings**: "{cached_data["buddhist_meanings"]}"'
        )
    if cached_data.get("cantonese_meanings"):
        meanings_section += (
            f'\n\n**Cantonese Meanings**: "{cached_data["cantonese_meanings"]}"'
        )

    footer = (
        f"\n\n\n^Information ^from "
        f"^[Unihan](https://www.unicode.org/cgi-bin/GetUnihanData.pl?codepoint={trad}) ^| "
        f"^[CantoDict](https://www.cantonese.sheik.co.uk/dictionary/characters/{trad}/) ^| "
        f"^[Chinese-Etymology](https://hanziyuan.net/#{trad}) ^| "
        f"^[CHISE](https://www.chise.org/est/view/char/{trad}) ^| "
        f"^[CTEXT](https://ctext.org/dictionary.pl?if=en&char={trad}) ^| "
        f"^[MDBG](https://www.mdbg.net/chinese/dictionary?page=worddict&wdrst=1&wdqb={trad}) ^| "
        f"^[MoE-DICT](https://www.moedict.tw/'{trad}) ^| "
        f"^[MFCCD](https://humanum.arts.cuhk.edu.hk/Lexis/lexi-mf/search.php?word={trad}) ^| "
        f"^[ZDIC](https://www.zdic.net/hans/{simp}) ^| "
        f"^[ZI](https://zi.tools/zi/{trad})"
    )

    return header + table + calligraphy_section + meanings_section + footer


def format_zh_word_from_cache(cached_data: dict) -> str:
    """
    Reconstruct the zh_word markdown output from cached data.

    :param cached_data: Dictionary with parsed word data
    :return: Formatted markdown string
    """
    trad = cached_data.get("traditional")
    simp = cached_data.get("simplified")
    pronunciations = cached_data.get("pronunciations", {})
    meanings = cached_data.get("meanings", "")

    if trad == simp:
        header = f"# [{trad}](https://en.wiktionary.org/wiki/{trad}#Chinese)"
    else:
        header = f"# [{trad} / {simp}](https://en.wiktionary.org/wiki/{trad}#Chinese)"

    table = "\n\n| Language | Pronunciation |\n|---------|--------------|\n"

    def _fix_last_tone(s: str) -> str:
        """Ensure the final superscript tone number is wrapped in parentheses."""
        return re.sub(r"\^(\d)$", r"^(\1)", s)

    if "mandarin_pinyin" in pronunciations:
        table += f"| **Mandarin** (Pinyin) | *{pronunciations['mandarin_pinyin']}* |\n"
    if "mandarin_wade_giles" in pronunciations:
        table += f"| **Mandarin** (Wade-Giles) | *{_fix_last_tone(pronunciations['mandarin_wade_giles'])}* |\n"
    if "mandarin_yale" in pronunciations:
        table += f"| **Mandarin** (Yale) | *{_fix_last_tone(pronunciations['mandarin_yale'])}* |\n"
    if "mandarin_gr" in pronunciations:
        table += f"| **Mandarin** (GR) | *{pronunciations['mandarin_gr']}* |\n"
    if "cantonese" in pronunciations:
        table += f"| **Cantonese** | *{pronunciations['cantonese']}* |\n"
    if "southern_min" in pronunciations:
        table += f"| **Southern Min** | *{pronunciations['southern_min']}* |\n"
    if "hakka_sixian" in pronunciations:
        table += f"| **Hakka (Sixian)** | *{pronunciations['hakka_sixian']}* |\n"

    meanings_section = f'\n\n**Meanings**: "{meanings}"'

    if cached_data.get("chinese_meaning"):
        meanings_section += f"\n\n**Chinese Meaning**: {cached_data['chinese_meaning']}"
    if cached_data.get("literary_source"):
        meanings_section += f"\n\n**Literary Source**: {cached_data['literary_source']}"
    if cached_data.get("buddhist_meanings"):
        meanings_section += (
            f'\n\n**Buddhist Meanings**: "{cached_data["buddhist_meanings"]}"'
        )
    if cached_data.get("cantonese_meanings"):
        meanings_section += (
            f'\n\n**Cantonese Meanings**: "{cached_data["cantonese_meanings"]}"'
        )

    word = trad if trad else simp
    footer = (
        "\n\n^Information ^from "
        f"^[CantoDict](https://www.cantonese.sheik.co.uk/dictionary/search/?searchtype=1&text={trad}) ^| "
        f"^[MDBG](https://www.mdbg.net/chinese/dictionary?page=worddict&wdrst=0&wdqb=c:{word}) ^| "
        f"^[Yellowbridge](https://yellowbridge.com/chinese/dictionary.php?word={word}) ^| "
        f"^[Youdao](https://dict.youdao.com/w/eng/{word}/#keyfrom=dict2.index) ^| "
        f"^[ZDIC](https://www.zdic.net/hans/{simp})"
    )

    return header + table + meanings_section + "\n\n" + footer


# ─── Japanese parse / format ──────────────────────────────────────────────────


def parse_ja_output_to_json(markdown_output: str) -> dict[str, Any]:
    """
    Parse the markdown output from ja_word or ja_character into structured
    JSON.

    :param markdown_output: The markdown string returned by ja_word or
                            ja_character
    :return: Dictionary with structured data, or None if it's a
             multi-character table
    """
    # Skip multi-character table format
    if "| Character |" in markdown_output and "| --- |" in markdown_output:
        header_match = re.search(r"\| Character \|([^\n]+)", markdown_output)
        if header_match:
            header_content = header_match.group(1)
            char_links = re.findall(
                r"\[(.)]\(https://en\.wiktionary\.org", header_content
            )
            if len(char_links) > 1:
                return {}

    result: dict[str, Any] = {
        "word": None,
        "type": None,  # "word" or "character"
        "part_of_speech": None,
        "reading": None,
        "kun_readings": None,
        "on_readings": None,
        "meanings": None,
        "calligraphy_links": None,  # Dict with sfzd_image, sfds, variants
    }

    # Pattern: # [世代](https://...)
    header_match = re.search(r"#\s*\[([^]]+)]", markdown_output)
    if header_match:
        result["word"] = header_match.group(1).strip()

    if "**Kun-readings:**" in markdown_output or "**On-readings:**" in markdown_output:
        result["type"] = "character"

        kun_match = re.search(r"\*\*Kun-readings:\*\*\s*([^\n]+)", markdown_output)
        if kun_match:
            kun_text = kun_match.group(1).strip()
            # Parse readings like "か.わる (*ka . waru*), かわ.る (*kawa . ru*)"
            kun_pairs = re.findall(r"([^\s,]+)\s*\(\*([^)]+)\*\)", kun_text)
            result["kun_readings"] = [
                {"kana": kana.strip(), "romaji": romaji.strip()}
                for kana, romaji in kun_pairs
            ]

        on_match = re.search(r"\*\*On-readings:\*\*\s*([^\n]+)", markdown_output)
        if on_match:
            on_text = on_match.group(1).strip()
            on_pairs = re.findall(r"([^\s,]+)\s*\(\*([^)]+)\*\)", on_text)
            result["on_readings"] = [
                {"kana": kana.strip(), "romaji": romaji.strip()}
                for kana, romaji in on_pairs
            ]

        # Japanese characters can have Chinese calligraphy links
        calligraphy_match = re.search(
            r"\*\*Chinese Calligraphy Variants\*\*:\s*\[.]\(([^)]+)\)\s*"
            r"\(\*\[SFZD]\([^)]+\)\*,\s*\*\[SFDS]\(([^)]+)\)\*,\s*"
            r"\*\[YTZZD]\(([^)]+)\)\*\)",
            markdown_output,
        )
        if calligraphy_match:
            result["calligraphy_links"] = {
                "sfzd_image": calligraphy_match.group(1).strip(),
                "sfds": calligraphy_match.group(2).strip(),
                "variants": calligraphy_match.group(3).strip(),
            }

    else:
        result["type"] = "word"

        pos_match = re.search(r"#####\s*\*([^*]+)\*", markdown_output)
        if pos_match:
            result["part_of_speech"] = pos_match.group(1).strip().lower()

        reading_match = re.search(
            r"\*\*Reading:\*\*\s*(\S+)\s*\(\*([^)]+)\*\)", markdown_output
        )
        if reading_match:
            result["reading"] = {
                "kana": reading_match.group(1).strip(),
                "romaji": reading_match.group(2).strip(),
            }

    meanings_match = re.search(r'\*\*Meanings\*\*:\s*"([^"]+)"', markdown_output)
    if meanings_match:
        result["meanings"] = meanings_match.group(1).strip()

    return result


def format_ja_character_from_cache(cached_data: dict) -> str:
    """
    Reconstruct the ja_character markdown output from cached data.

    :param cached_data: Dictionary with parsed character data
    :return: Formatted markdown string
    """
    word = cached_data.get("word")
    kun_readings = cached_data.get("kun_readings", [])
    on_readings = cached_data.get("on_readings", [])
    meanings = cached_data.get("meanings", "")
    calligraphy = cached_data.get("calligraphy_links")

    header = f"# [{word}](https://en.wiktionary.org/wiki/{word}#Japanese)\n\n"

    kun_formatted = (
        ", ".join([f"{r['kana']} (*{r['romaji']}*)" for r in kun_readings])
        if kun_readings
        else ""
    )
    on_formatted = (
        ", ".join([f"{r['kana']} (*{r['romaji']}*)" for r in on_readings])
        if on_readings
        else ""
    )

    readings_section = ""
    if kun_formatted:
        readings_section += f"**Kun-readings:** {kun_formatted}\n\n"
    if on_formatted:
        readings_section += f"**On-readings:** {on_formatted}"

    calligraphy_section = ""
    if calligraphy:
        sfzd = calligraphy.get("sfzd_image")
        sfds = calligraphy.get("sfds")
        variants = calligraphy.get("variants")
        if sfzd and sfds and variants:
            calligraphy_section = (
                f"\n\n**Chinese Calligraphy Variants**: [{word}]({sfzd}) "
                f"(*[SFZD](https://www.shufazidian.com/)*, *[SFDS]({sfds})*, *[YTZZD]({variants})*)"
            )

    meanings_section = f'\n\n**Meanings**: "{meanings}"'

    footer = (
        f"\n\n\n^Information ^from ^[Jisho](https://jisho.org/search/{word}%20%23kanji) ^| "
        f"^[Tangorin](https://tangorin.com/kanji/{word}) ^| "
        f"^[Weblio](https://ejje.weblio.jp/content/{word})"
    )

    return header + readings_section + calligraphy_section + meanings_section + footer


def format_ja_word_from_cache(cached_data: dict) -> str:
    """
    Reconstruct the ja_word markdown output from cached data.

    :param cached_data: Dictionary with parsed word data
    :return: Formatted markdown string
    """
    word = cached_data.get("word")
    pos = cached_data.get("part_of_speech", "")
    reading = cached_data.get("reading", {})
    meanings = cached_data.get("meanings", "")

    header = f"# [{word}](https://en.wiktionary.org/wiki/{word}#Japanese)\n\n"
    pos_section = f"##### *{pos.title()}*\n\n" if pos else ""

    reading_section = ""
    if reading:
        kana = reading.get("kana", "")
        romaji = reading.get("romaji", "")
        if kana and romaji:
            reading_section = f"**Reading:** {kana} (*{romaji}*)\n\n"

    meanings_section = f'**Meanings**: "{meanings}"'

    footer = (
        f"\n\n^Information ^from ^[Jisho](https://jisho.org/search/{word}%23words) ^| "
        f"^[Kotobank](https://kotobank.jp/word/{word}) ^| "
        f"^[Tangorin](https://tangorin.com/general/{word}) ^| "
        f"^[Weblio](https://ejje.weblio.jp/content/{word})"
    )

    return header + pos_section + reading_section + meanings_section + footer


# ─── Korean parse / format ────────────────────────────────────────────────────


def parse_ko_output_to_json(markdown_output: str) -> dict[str, Any]:
    """
    Parse the markdown output from ko_word into structured JSON.

    :param markdown_output: The markdown string returned by ko_word
    :return: Dictionary with structured data
    """
    result: dict[str, Any] = {
        "word": None,
        "romanization": None,
        "entries": [],  # List of {part_of_speech, meanings: [{origin, definition}]}
    }

    # Pattern: # [애교](https://...)
    header_match = re.search(r"#\s*\[([^]]+)]", markdown_output)
    if header_match:
        result["word"] = header_match.group(1).strip()

    # Split by part of speech sections (##### *Noun*, etc.)
    pos_sections = re.split(r"#####\s*\*([^*]+)\*", markdown_output)[1:]

    for i in range(0, len(pos_sections), 2):
        if i + 1 >= len(pos_sections):
            break

        pos = pos_sections[i].strip()
        content = pos_sections[i + 1]

        entry: dict[str, Any] = {"part_of_speech": pos.lower(), "meanings": []}

        if not result["romanization"]:
            rom_match = re.search(r"\*\*Romanization:\*\*\s*\*([^*]+)\*", content)
            if rom_match:
                result["romanization"] = rom_match.group(1).strip()

        # Pattern: * [水道](link): definition text  or  * definition text (no origin)
        meaning_matches = re.findall(
            r"\*\s*(?:\[([^]]+)]\([^)]+\):\s*)?([^\n*]+)", content
        )

        for origin, definition in meaning_matches:
            definition = definition.strip()
            if (
                definition
                and definition not in ["Romanization:", "Meanings:", "Meanings", ":"]
                and not definition.endswith(":")
                and len(definition) > 3
            ):
                meaning_entry = {"definition": definition}
                if origin:
                    meaning_entry["origin"] = origin.strip()
                entry["meanings"].append(meaning_entry)

        if entry["meanings"]:
            result["entries"].append(entry)

    return result


def format_ko_word_from_cache(cached_data: dict) -> str:
    """
    Reconstruct the ko_word markdown output from cached data.

    :param cached_data: Dictionary with parsed word data
    :return: Formatted markdown string
    """
    word = cached_data.get("word")
    romanization = cached_data.get("romanization", "")
    entries = cached_data.get("entries", [])

    header = f"# [{word}](https://en.wiktionary.org/wiki/{word}#Korean)"

    entries_text = ""
    for entry in entries:
        pos = entry.get("part_of_speech", "").title()
        meanings = entry.get("meanings", [])

        entries_text += f"\n\n##### *{pos}*\n\n"
        entries_text += f"**Romanization:** *{romanization}*\n\n"
        entries_text += "**Meanings**:\n"

        for meaning_entry in meanings:
            definition = meaning_entry.get("definition", "")
            origin = meaning_entry.get("origin")

            if origin:
                entries_text += f"* [{origin}](https://en.wiktionary.org/wiki/{origin}): {definition}\n"
            else:
                entries_text += f"* {definition}\n"

    footer = (
        "\n\n^Information ^from "
        f"^[KRDict](https://krdict.korean.go.kr/eng/dicMarinerSearch/search"
        f"?nation=eng&nationCode=6&ParaWordNo=&mainSearchWord={word}&lang=eng) ^| "
        f"^[Naver](https://korean.dict.naver.com/koendict/#/search?query={word}) ^| "
        f"^[Collins](https://www.collinsdictionary.com/dictionary/korean-english/{word})"
    )

    return header + entries_text + footer


# ─── Cache retrieval with fallback ────────────────────────────────────────────


async def get_cached_or_fetch_zh_character(
    character: str,
    fetch_func: Callable[[str], Awaitable[str]],
) -> str:
    """
    Try to get data from cache first, otherwise fetch from web.

    :param character: Chinese character to look up
    :param fetch_func: Async function to call if cache miss
    :return: Formatted markdown string
    """
    cached = get_from_cache(character, "zh", "zh_character")

    if cached:
        return format_zh_character_from_cache(cached) + " ^⚡"

    return await fetch_func(character)
