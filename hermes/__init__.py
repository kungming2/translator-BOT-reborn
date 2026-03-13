#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
Hermes — a language-exchange matching bot for r/Language_Exchange.

This package loads its own settings from hermes_settings.yaml at import
time and exposes them as the module-level HERMES_SETTINGS dict.
"""

from pathlib import Path

from config import Paths, load_settings

HERMES_SETTINGS: dict = load_settings(Path(Paths.HERMES["HERMES_SETTINGS"]))
