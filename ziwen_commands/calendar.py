#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
Handler for the !calendar command, which converts supported calendar dates
to Gregorian dates.
...

Logger tag: [ZW:CALENDAR]
"""

import logging
from datetime import date
from typing import cast

from praw.models import Comment

from config import logger as _base_logger
from models.ajo import Ajo
from models.instruo import Instruo
from models.komando import Komando
from reddit.reddit_sender import reddit_reply
from responses import RESPONSE

logger = logging.LoggerAdapter(_base_logger, {"tag": "ZW:CALENDAR"})


def _format_gregorian_dates(result: date | list[date]) -> str:
    if isinstance(result, date):
        return f"* `{result.isoformat()}`"

    return "\n".join(f"* `{gregorian_date.isoformat()}`" for gregorian_date in result)


def _format_years(years: list[int]) -> str:
    return "\n".join(f"* `{year}`" for year in years)


def _format_calendar_result(payload: str, result: date | list[date]) -> str:
    return RESPONSE.COMMENT_CALENDAR_RESULT.format(
        query=payload,
        gregorian_dates=_format_gregorian_dates(result),
    )


def _format_cycle_year_result(payload: str, years: list[int]) -> str:
    return RESPONSE.COMMENT_CALENDAR_YEAR_RESULT.format(
        query=payload,
        gregorian_years=_format_years(years),
    )


def convert_calendar_payload(payload: str) -> date | list[date] | list[int]:
    from calendar_handling import convert_calendar_payload as convert_payload

    return convert_payload(payload)


def handle(comment: Comment, _instruo: Instruo, komando: Komando, _ajo: Ajo) -> None:
    """
    Command handler called by ziwen_commands().
    Example data:
        [Komando(name='calendar', data=['乙巳'])]
        [Komando(name='calendar', data=['chinese:guimao:4:13'])]
        [Komando(name='calendar', data=['hebrew:5784:Tishrei:1'])]
    """
    logger.info(f"!calendar, from u/{comment.author}.")

    if not komando.data:
        reddit_reply(
            comment,
            RESPONSE.COMMENT_CALENDAR_USAGE + RESPONSE.BOT_DISCLAIMER,
        )
        return

    reply_sections = []
    for payload in komando.data:
        try:
            result = convert_calendar_payload(str(payload))
        except ValueError as exc:
            logger.info(f"Invalid !calendar payload {payload!r}: {exc}")
            reddit_reply(
                comment,
                RESPONSE.COMMENT_CALENDAR_INVALID
                + "\n\n"
                + RESPONSE.COMMENT_CALENDAR_USAGE
                + RESPONSE.BOT_DISCLAIMER,
            )
            return

        if isinstance(result, list) and all(isinstance(item, int) for item in result):
            reply_sections.append(
                _format_cycle_year_result(str(payload), cast(list[int], result))
            )
        else:
            reply_sections.append(
                _format_calendar_result(str(payload), cast(date | list[date], result))
            )

    reddit_reply(
        comment,
        "\n\n".join(reply_sections) + RESPONSE.BOT_DISCLAIMER,
    )
