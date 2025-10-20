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
"""

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import yaml

from config import Paths


class ResponseLoader:
    """
    Simple class to provide responses as an object attribute for use.
    Responses are located in responses.yaml.

    Responses are generally formatted as:
    RESPONSE.ANCHOR_WIKIPEDIA

    The class loads YAML data at initialization and exposes all top-level keys
    as attributes through a SimpleNamespace, allowing for clean dot-notation access.
    """

    def __init__(self, yaml_path: Path | str) -> None:
        self._data: dict[str, Any] = self._load_yaml(yaml_path)
        self.responses: SimpleNamespace = SimpleNamespace(**self._data)

    @staticmethod
    def _load_yaml(path: Path | str) -> dict[str, Any]:
        with open(path, "r", encoding="utf-8") as file:
            return yaml.safe_load(file)

    def __getattr__(self, item: str) -> Any:
        return getattr(self.responses, item)


# To use: RESPONSE.VARIABLE_NAME
RESPONSE = ResponseLoader(Paths.RESPONSES["TEXT"])
