#!/usr/bin/env python3
from config import Paths, load_settings


def _fetch_wenyuan_settings():
    """Fetches Wenju-specific settings."""
    return load_settings(Paths.SETTINGS["WENJU_SETTINGS"])


WENYUAN_SETTINGS = _fetch_wenyuan_settings()
