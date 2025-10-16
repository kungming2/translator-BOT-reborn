#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
Contains functions related to formatting bot responses.
"""

from types import SimpleNamespace

import yaml

from config import Paths


class ResponseLoader:
    """
    Responses are generally formatted as:
    RESPONSE.ANCHOR_WIKIPEDIA
    """

    def __init__(self, yaml_path):
        self._data = self._load_yaml(yaml_path)
        self.responses = SimpleNamespace(**self._data)

    @staticmethod
    def _load_yaml(path):
        with open(path, "r", encoding="utf-8") as file:
            return yaml.safe_load(file)

    def __getattr__(self, item):
        return getattr(self.responses, item)


# To use: RESPONSE.VARIABLE_NAME
RESPONSE = ResponseLoader(Paths.RESPONSES["TEXT"])
