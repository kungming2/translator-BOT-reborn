import unicodedata
from datetime import date

from convertdate import hebrew, islamic, persian

STEMS = ["jia", "yi", "bing", "ding", "wu", "ji", "geng", "xin", "ren", "gui"]
CHINESE_STEMS = ["甲", "乙", "丙", "丁", "戊", "己", "庚", "辛", "壬", "癸"]
BRANCHES = [
    "zi",
    "chou",
    "yin",
    "mao",
    "chen",
    "si",
    "wu",
    "wei",
    "shen",
    "you",
    "xu",
    "hai",
]
CHINESE_BRANCHES = [
    "子",
    "丑",
    "寅",
    "卯",
    "辰",
    "巳",
    "午",
    "未",
    "申",
    "酉",
    "戌",
    "亥",
]

CYCLE = [STEMS[i % 10] + BRANCHES[i % 12] for i in range(60)]
CHINESE_CYCLE = [CHINESE_STEMS[i % 10] + CHINESE_BRANCHES[i % 12] for i in range(60)]
CHINESE_TO_PINYIN_CYCLE = dict(zip(CHINESE_CYCLE, CYCLE, strict=True))
PINYIN_TO_CHINESE_CYCLE = dict(zip(CYCLE, CHINESE_CYCLE, strict=True))
DATED_CALENDARS = {
    "hebrew": (hebrew.to_gregorian, hebrew.from_gregorian),
    "jewish": (hebrew.to_gregorian, hebrew.from_gregorian),
    "islamic": (islamic.to_gregorian, islamic.from_gregorian),
    "hijri": (islamic.to_gregorian, islamic.from_gregorian),
    "muslim": (islamic.to_gregorian, islamic.from_gregorian),
    "persian": (persian.to_gregorian, persian.from_gregorian),
    "jalali": (persian.to_gregorian, persian.from_gregorian),
    "iranian": (persian.to_gregorian, persian.from_gregorian),
}
CHINESE_CALENDARS = {"chinese", "lunar", "lunisolar"}
SUPPORTED_CALENDARS = DATED_CALENDARS.keys() | CHINESE_CALENDARS
MONTH_NAMES = {
    "hebrew": {
        "nisan": 1,
        "nissan": 1,
        "iyyar": 2,
        "iyar": 2,
        "sivan": 3,
        "tammuz": 4,
        "tamuz": 4,
        "av": 5,
        "elul": 6,
        "tishrei": 7,
        "tishri": 7,
        "cheshvan": 8,
        "heshvan": 8,
        "marcheshvan": 8,
        "marheshvan": 8,
        "kislev": 9,
        "tevet": 10,
        "teveth": 10,
        "shevat": 11,
        "shvat": 11,
        "adar": 12,
        "adar1": 12,
        "adari": 12,
        "adar2": 13,
        "adarii": 13,
        "adarbet": 13,
        "adarbeit": 13,
        "veadar": 13,
    },
    "islamic": {
        "muharram": 1,
        "safar": 2,
        "rabi al-awwal": 3,
        "rabi alawwal": 3,
        "rabi i": 3,
        "rabi awal": 3,
        "rabi ath-thani": 4,
        "rabi al-thani": 4,
        "rabi althani": 4,
        "rabi ii": 4,
        "rabi thani": 4,
        "jumada al-awwal": 5,
        "jumada alawwal": 5,
        "jumada i": 5,
        "jumada awal": 5,
        "jumada al-thani": 6,
        "jumada althani": 6,
        "jumada ii": 6,
        "jumada thani": 6,
        "rajab": 7,
        "shaban": 8,
        "shaaban": 8,
        "sha'ban": 8,
        "ramadan": 9,
        "ramazan": 9,
        "shawwal": 10,
        "dhu al-qidah": 11,
        "dhu alqidah": 11,
        "dhu al-qa'dah": 11,
        "dhul qidah": 11,
        "dhul qadah": 11,
        "dhu al-hijjah": 12,
        "dhu alhijjah": 12,
        "dhul hijjah": 12,
        "dhulhijjah": 12,
    },
    "persian": {
        "farvardin": 1,
        "ordibehesht": 2,
        "ordibehisht": 2,
        "khordad": 3,
        "tir": 4,
        "mordad": 5,
        "amordad": 5,
        "shahrivar": 6,
        "mehr": 7,
        "aban": 8,
        "azar": 9,
        "dey": 10,
        "day": 10,
        "bahman": 11,
        "esfand": 12,
        "espand": 12,
        "esfandarmad": 12,
        "esfandarmadh": 12,
    },
}
MONTH_NAME_CALENDAR_ALIASES = {
    "jewish": "hebrew",
    "hijri": "islamic",
    "muslim": "islamic",
    "jalali": "persian",
    "iranian": "persian",
}


def normalize_lookup_key(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value.lower())
    return "".join(
        char
        for char in normalized
        if not unicodedata.combining(char)
        and unicodedata.category(char) != "Cf"
        and char not in {" ", "-", "_"}
    )


def normalize_calendar_name(calendar_type: str) -> str:
    return normalize_lookup_key(calendar_type)


def month_to_number(calendar_type: str, month: int | str) -> int:
    if isinstance(month, int):
        return month

    try:
        return int(month)
    except (TypeError, ValueError):
        pass

    calendar_name = normalize_calendar_name(calendar_type)
    month_calendar = MONTH_NAME_CALENDAR_ALIASES.get(calendar_name, calendar_name)
    month_names = MONTH_NAMES.get(month_calendar, {})
    normalized_month = normalize_lookup_key(month)
    month_number = next(
        (
            number
            for month_name, number in month_names.items()
            if normalize_lookup_key(month_name) == normalized_month
        ),
        None,
    )
    if month_number is None:
        raise ValueError(f"Unknown {calendar_type} month: {month}")

    return month_number


def day_to_number(day: int | str) -> int:
    try:
        return int(day)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Day must be numeric: {day}") from exc


def _dated_calendar_to_gregorian(
    calendar_type: str,
    year: int,
    month: int | str,
    day: int | str,
) -> date:
    calendar_name = normalize_calendar_name(calendar_type)
    converter = DATED_CALENDARS.get(calendar_name)
    if converter is None:
        supported = ", ".join(sorted(SUPPORTED_CALENDARS))
        raise ValueError(
            f"Unsupported calendar: {calendar_type}. Supported: {supported}"
        )

    month_number = month_to_number(calendar_name, month)
    day_number = day_to_number(day)
    to_gregorian, from_gregorian = converter
    gregorian = date(*to_gregorian(year, month_number, day_number))
    if from_gregorian(gregorian.year, gregorian.month, gregorian.day) != (
        year,
        month_number,
        day_number,
    ):
        raise ValueError(
            f"Invalid {calendar_type} date: {year}-{month_number}-{day_number}"
        )

    return gregorian


def hebrew_to_gregorian(year: int, month: int | str, day: int | str) -> date:
    return _dated_calendar_to_gregorian("hebrew", year, month, day)


def islamic_to_gregorian(year: int, month: int | str, day: int | str) -> date:
    return _dated_calendar_to_gregorian("islamic", year, month, day)


def persian_to_gregorian(year: int, month: int | str, day: int | str) -> date:
    return _dated_calendar_to_gregorian("persian", year, month, day)


def _parse_calendar_payload(payload: str) -> tuple[str, str, str, str]:
    parts = [part.strip() for part in payload.split(":", 3)]
    if len(parts) != 4 or any(not part for part in parts):
        raise ValueError(f"Invalid calendar payload: {payload}")

    return parts[0], parts[1], parts[2], parts[3]


def calendar_to_gregorian(
    calendar_type: str,
    year_or_cycle: int | str,
    month: int | str,
    day: int | str,
    *,
    reference: date | None = None,
    start: int = 1900,
    end: int = 2100,
    leap_month: bool = False,
    count: int = 2,
) -> date | list[date]:
    calendar_name = normalize_calendar_name(calendar_type)
    if calendar_name in CHINESE_CALENDARS:
        return lunar_notation_to_recent_solar(
            str(year_or_cycle),
            month_to_number(calendar_name, month),
            day_to_number(day),
            reference=reference,
            start=start,
            end=end,
            leap_month=leap_month,
            count=count,
        )

    try:
        year = int(year_or_cycle)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"{calendar_type} conversion requires a numeric year: {year_or_cycle}"
        ) from exc

    return _dated_calendar_to_gregorian(calendar_type, year, month, day)


convert_calendar_to_gregorian = calendar_to_gregorian


def convert_calendar_payload(payload: str) -> date | list[date] | list[int]:
    if ":" not in payload:
        return recent_sexagenary_years(payload)

    calendar_type, sep, cycle_year = payload.partition(":")
    if (
        sep
        and normalize_calendar_name(calendar_type) in CHINESE_CALENDARS
        and ":" not in cycle_year
    ):
        return recent_sexagenary_years(cycle_year)

    calendar_type, year_or_cycle, month, day = _parse_calendar_payload(payload)
    return calendar_to_gregorian(calendar_type, year_or_cycle, month, day)


def format_sexagenary_year_query(name: str) -> str:
    normalized = normalize_lookup_key(name)
    pinyin = CHINESE_TO_PINYIN_CYCLE.get(normalized, normalized)
    characters = PINYIN_TO_CHINESE_CYCLE.get(pinyin)
    if characters is None:
        raise ValueError(f"Unknown sexagenary year: {name}")

    if normalized in CHINESE_TO_PINYIN_CYCLE:
        return f"{characters} ({pinyin})"

    return f"{pinyin} ({characters})"


def format_calendar_query(payload: str) -> str:
    if ":" not in payload:
        return format_sexagenary_year_query(payload)

    calendar_type, sep, cycle_year = payload.partition(":")
    if not sep or normalize_calendar_name(calendar_type) not in CHINESE_CALENDARS:
        return payload

    if ":" not in cycle_year:
        return f"{calendar_type}:{format_sexagenary_year_query(cycle_year)}"

    try:
        calendar_type, year_or_cycle, month, day = _parse_calendar_payload(payload)
    except ValueError:
        return payload

    return (
        f"{calendar_type}:{format_sexagenary_year_query(year_or_cycle)}:{month}:{day}"
    )


def normalize_sexagenary_year(name: str) -> str:
    normalized = normalize_lookup_key(name)
    return CHINESE_TO_PINYIN_CYCLE.get(normalized, normalized)


def sexagenary_years(name: str, start: int = 1900, end: int = 2100) -> list[int]:
    name = normalize_sexagenary_year(name)
    if name not in CYCLE:
        raise ValueError(f"Unknown sexagenary year: {name}")

    idx = CYCLE.index(name)

    # 1984 is jiazi, cycle index 0
    return [y for y in range(start, end + 1) if (y - 1984) % 60 == idx]


def recent_sexagenary_years(
    name: str,
    *,
    reference: date | None = None,
    start: int = 1900,
    end: int = 2100,
    count: int = 3,
) -> list[int]:
    if reference is None:
        reference = date.today()

    candidates = [
        year for year in sexagenary_years(name, start, end) if year <= reference.year
    ]
    if not candidates:
        raise ValueError("No valid matching sexagenary years found.")

    return candidates[-count:]


def lunar_notation_to_recent_solar(
    ganzhi: str,
    lunar_month: int,
    lunar_day: int,
    *,
    reference: date | None = None,
    start: int = 1900,
    end: int = 2100,
    leap_month: bool = False,
    count: int = 2,
) -> list[date]:
    from lunardate import LunarDate

    if reference is None:
        reference = date.today()

    candidates: list[date] = []

    for y in sexagenary_years(ganzhi, start, end):
        try:
            solar = LunarDate(y, lunar_month, lunar_day, leap_month).toSolarDate()
            if solar <= reference:
                candidates.append(solar)
        except ValueError:
            pass

    if not candidates:
        raise ValueError("No valid matching lunar dates found.")

    return candidates[-count:]


if __name__ == "__main__":
    print(lunar_notation_to_recent_solar("yisi", 1, 1))
    print(calendar_to_gregorian("islamic", 1321, "Dhu al-Hijjah", 12))
