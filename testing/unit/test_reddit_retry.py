#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""Tests for bounded Reddit HTTP 429 retry behavior."""

from unittest.mock import MagicMock

import pytest
from prawcore.exceptions import TooManyRequests
from requests import Response

from reddit.retry import call_with_429_retry


def _too_many_requests(retry_after: str | None = None) -> TooManyRequests:
    response = Response()
    response.status_code = 429
    response._content = b"rate limited"
    if retry_after is not None:
        response.headers["retry-after"] = retry_after
    return TooManyRequests(response)


def test_retries_with_server_retry_after() -> None:
    action = MagicMock(side_effect=[_too_many_requests("2.5"), "ok"])
    sleep = MagicMock()

    result = call_with_429_retry(
        action,
        operation="Read test page",
        fallback_delays=(60.0,),
        sleep=sleep,
    )

    assert result == "ok"
    assert action.call_count == 2
    sleep.assert_called_once_with(2.5)


def test_retries_with_fallback_when_header_is_missing() -> None:
    action = MagicMock(side_effect=[_too_many_requests(), "ok"])
    sleep = MagicMock()

    result = call_with_429_retry(
        action,
        operation="Read test page",
        fallback_delays=(45.0,),
        sleep=sleep,
    )

    assert result == "ok"
    sleep.assert_called_once_with(45.0)


def test_raises_after_bounded_retries_are_exhausted() -> None:
    action = MagicMock(
        side_effect=[
            _too_many_requests(),
            _too_many_requests(),
            _too_many_requests(),
        ]
    )
    sleep = MagicMock()

    with pytest.raises(TooManyRequests):
        call_with_429_retry(
            action,
            operation="Read test page",
            fallback_delays=(10.0, 20.0),
            sleep=sleep,
        )

    assert action.call_count == 3
    assert [call.args[0] for call in sleep.call_args_list] == [10.0, 20.0]
