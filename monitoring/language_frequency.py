#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""Select and format readable language-request frequencies."""


def generate_language_frequency_markdown(language_list: list) -> str:
    """Generate a Markdown frequency table for the provided Lingvos."""
    header = (
        "| Language Name        | Average Number of Posts | Per   |\n"
        "|----------------------|--------------------------:|:------|\n"
    )
    line_template = (
        "| [{label}]({url})        | {rate:.2f} posts              | {freq} |"
    )
    no_data_template = "| {label:<21} | No recorded statistics     | ---   |"

    lines = []
    for lingvo in language_list:
        language_label = _format_language_frequency_label(lingvo)
        permalink = lingvo.link_statistics
        frequency = describe_language_frequency(lingvo)
        if frequency and permalink:
            line = line_template.format(
                label=language_label,
                url=permalink,
                rate=frequency[0],
                freq=frequency[1],
            )
        else:
            line = no_data_template.format(label=language_label)
        lines.append(line)

    return header + "\n".join(lines)


def _format_language_frequency_label(lingvo: object) -> str:
    """Return a frequency-table label with the notification code when available."""
    language_name = getattr(lingvo, "name", None)
    language_code = getattr(lingvo, "preferred_code", None)
    if language_name and language_code:
        return f"{language_name} (`{language_code}`)"
    return str(language_name or language_code or "")


def describe_language_frequency(lingvo: object) -> tuple[float, str] | None:
    """Return the most readable request frequency as ``(rate, period)``."""
    daily = getattr(lingvo, "rate_daily", None)
    monthly = getattr(lingvo, "rate_monthly", None)
    yearly = getattr(lingvo, "rate_yearly", None)
    if not all(value is not None for value in (daily, monthly, yearly)):
        return None

    assert daily is not None and monthly is not None and yearly is not None
    if daily >= 2:
        return daily, "day"
    if daily > 0.05:
        return monthly, "month"
    return yearly, "year"
