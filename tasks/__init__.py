#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
from config import Paths, load_settings


def fetch_wenju_settings():
    return load_settings(Paths.SETTINGS['WENJU_SETTINGS'])


WENJU_SETTINGS = fetch_wenju_settings()
