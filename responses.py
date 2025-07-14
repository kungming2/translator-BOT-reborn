#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
Contains functions related to formatting bot responses.
"""
import yaml
from types import SimpleNamespace

from config import Paths


class ResponseLoader:
    def __init__(self, yaml_path):
        self._data = self._load_yaml(yaml_path)
        self.responses = SimpleNamespace(**self._data)

    @staticmethod
    def _load_yaml(path):
        with open(path, 'r', encoding='utf-8') as file:
            return yaml.safe_load(file)

    def __getattr__(self, item):
        return getattr(self.responses, item)


RESPONSE = ResponseLoader(Paths.RESPONSES['TEXT'])
