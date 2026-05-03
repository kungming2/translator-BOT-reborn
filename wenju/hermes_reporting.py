#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
Wenju wrappers for scheduled Hermes reporting tasks.

Logger tag: [WJ:HM]
"""

# ─── Imports ──────────────────────────────────────────────────────────────────

import logging

from config import logger as _base_logger
from hermes.reporting import post_monthly_statistics
from wenju import task

# ─── Module-level constants ───────────────────────────────────────────────────

logger = logging.LoggerAdapter(_base_logger, {"tag": "WJ:HM"})


# ─── Monthly Hermes reports ───────────────────────────────────────────────────


@task(schedule="monthly")
def monthly_hermes_statistics_post() -> None:
    """Post the previous month's Hermes statistics on the Wenju monthly cycle."""
    post_url = post_monthly_statistics()
    if post_url:
        logger.info(f"Posted Hermes monthly statistics: {post_url}")
    else:
        logger.info("Hermes monthly statistics post already exists; skipped posting.")
