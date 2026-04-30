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

import keyword
import logging
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import yaml

from config import Paths
from config import logger as _base_logger

logger = logging.LoggerAdapter(_base_logger, {"tag": "RESPONSES"})

# ─── Response loader ──────────────────────────────────────────────────────────


class ResponseLoader:
    """
    Load response templates from a YAML file and expose them as attributes.

    Responses are located in templates/responses.yaml and accessed via
    dot notation:

        RESPONSE.ANCHOR_WIKIPEDIA
        RESPONSE.COMMENT_VERIFICATION_RESPONSE.format(...)
    """

    def __init__(
        self, yaml_path: Path | str, *, _data: dict[str, Any] | None = None
    ) -> None:
        """Load response templates from *yaml_path* and expose them as attributes."""
        self._yaml_path: Path = Path(yaml_path).expanduser()
        self._data: dict[str, Any] = (
            self._load_yaml(self._yaml_path) if _data is None else dict(_data)
        )
        self._validate_response_keys(self._data)
        self.responses: SimpleNamespace = SimpleNamespace(**self._data)

    @staticmethod
    def _load_yaml(path: Path | str) -> dict[str, Any]:
        """Read and parse a YAML file containing the bot's responses,
        returning its contents as a dictionary."""
        resolved_path = Path(path).expanduser()
        try:
            with resolved_path.open(encoding="utf-8") as file:
                loaded = yaml.safe_load(file)
        except FileNotFoundError as err:
            raise RuntimeError(
                f"Responses file not found at: {resolved_path.resolve()}"
            ) from err
        except PermissionError as err:
            raise RuntimeError(
                f"Permission denied while reading responses file: {resolved_path.resolve()}"
            ) from err
        except yaml.YAMLError as err:
            raise RuntimeError(
                f"Invalid YAML in responses file: {resolved_path.resolve()}"
            ) from err

        if loaded is None:
            logger.warning(
                f"Responses file is empty at {resolved_path.resolve()}; using empty mapping."
            )
            return {}

        if not isinstance(loaded, dict):
            raise RuntimeError(
                f"Top-level YAML content must be a mapping in {resolved_path.resolve()}, "
                f"got {type(loaded).__name__}."
            )

        return loaded

    @staticmethod
    def _validate_response_keys(data: dict[str, Any]) -> None:
        """Ensure keys can be exposed as Python attributes."""
        invalid_keys = [
            key
            for key in data
            if not isinstance(key, str)
            or not key.isidentifier()
            or keyword.iskeyword(key)
        ]
        if invalid_keys:
            preview = ", ".join(map(str, invalid_keys[:5]))
            suffix = "..." if len(invalid_keys) > 5 else ""
            raise RuntimeError(
                "Invalid response key(s) for attribute access: "
                f"{preview}{suffix}. Keys must be valid Python identifiers."
            )

    def __getattr__(self, item: str) -> Any:
        try:
            return getattr(self.responses, item)
        except AttributeError:
            raise AttributeError(
                f"Response template '{item}' not found in {self._yaml_path}. "
                f"Check that the key exists in the YAML file."
            ) from None

    def __getitem__(self, item: str) -> Any:
        """Dictionary-style access for compatibility with non-attribute usage."""
        try:
            return self._data[item]
        except KeyError:
            raise KeyError(
                f"Response template '{item}' not found in {self._yaml_path}. "
                f"Check that the key exists in the YAML file."
            ) from None

    def get(self, item: str, default: Any = None) -> Any:
        """Dictionary-like optional access."""
        return self._data.get(item, default)


# ─── Module-level singleton ───────────────────────────────────────────────────

try:
    RESPONSE = ResponseLoader(Paths.TEMPLATES["RESPONSES"])
except Exception as e:
    failed_path = Path(Paths.TEMPLATES["RESPONSES"]).expanduser().resolve()
    logger.critical(
        f"Failed to initialize response templates from {failed_path}: {type(e).__name__}: {e}. "
        "Continuing with empty response mapping; template lookups will fail until this is fixed."
    )
    RESPONSE = ResponseLoader(Paths.TEMPLATES["RESPONSES"], _data={})
