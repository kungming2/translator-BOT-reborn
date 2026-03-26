#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
Contains functions related to formatting bot responses.

This module provides a centralized way to manage bot response templates by loading
them from a YAML configuration file. The ResponseLoader class exposes these templates
as simple attributes for easy access throughout the codebase.

Usage:
    from responses import RESPONSE

    # Access response templates as attributes
    message = RESPONSE.ANCHOR_WIKIPEDIA
    reply = RESPONSE.COMMENT_VERIFICATION_RESPONSE.format(...)
...

Logger tag: [RESPONSES]
"""

# ─── Imports ──────────────────────────────────────────────────────────────────

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import yaml

from config import Paths

# ─── Response loader ──────────────────────────────────────────────────────────


class ResponseLoader:
    """
    Load response templates from a YAML file and expose them as attributes.

    Responses are located in responses.yaml and accessed via dot notation:

        RESPONSE.ANCHOR_WIKIPEDIA
        RESPONSE.COMMENT_VERIFICATION_RESPONSE.format(...)
    """

    def __init__(self, yaml_path: Path | str) -> None:
        """Load response templates from *yaml_path* and expose them as attributes."""
        self._data: dict[str, Any] = self._load_yaml(yaml_path)
        self.responses: SimpleNamespace = SimpleNamespace(**self._data)

    @staticmethod
    def _load_yaml(path: Path | str) -> dict[str, Any]:
        """Read and parse a YAML file containing the bot's responses,
        returning its contents as a dictionary."""
        with open(path, encoding="utf-8") as file:
            return yaml.safe_load(file)

    def __getattr__(self, item: str) -> Any:
        return getattr(self.responses, item)


# ─── Module-level singleton ───────────────────────────────────────────────────

RESPONSE = ResponseLoader(Paths.TEMPLATES["RESPONSES"])
