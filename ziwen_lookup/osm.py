#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
Module to return search results for locations via OpenStreetMap.
...

Logger tag: [L:OSM]
"""

import logging
from typing import Any
from urllib.parse import quote

import requests

from config import logger as _base_logger

logger = logging.LoggerAdapter(_base_logger, {"tag": "L:OSM"})


# ─── Nominatim search ─────────────────────────────────────────────────────────


def search_nominatim(
    query: str, accept_language: str = "en-US,en", coords: list[float] | None = None
) -> list[str]:
    """
    Search OSM Nominatim and return formatted results.

    Args:
        query: Search query string (e.g., "Chongqing")
        accept_language: Language preference (default: "en-US,en")
        coords: List containing [latitude, longitude] (default: None)

    Returns:
        List of formatted result strings
    """
    encoded_query: str = quote(query)
    logger.info(f"Initial query: {query!r}")

    url: str = (
        f"https://nominatim.openstreetmap.org/search?q={encoded_query}"
        f"&accept-language={accept_language}&format=jsonv2"
    )

    headers: dict[str, str] = {"User-Agent": "Python OSM Search Script"}

    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        results: list[dict[str, Any]] = response.json()

        if not results:
            logger.info(f"> No results found for {query}")
            if coords and len(coords) == 2:
                lat: float = round(coords[0], 3)
                lon: float = round(coords[1], 3)
                osm_map_link: str = (
                    f"https://www.openstreetmap.org/?mlat={lat}&mlon={lon}&zoom=15"
                )
                google_maps_link: str = f"https://www.google.com/maps?q={lat},{lon}"
                return [f"([OSM]({osm_map_link}), [Google]({google_maps_link}))"]
            return []
        else:
            logger.info(f"> Found {len(results)} results for {query}")

        formatted_results: list[str] = []
        for result in results:
            display_name: str = result.get("display_name", "Unknown")
            osm_type: str = result.get("osm_type", "")
            osm_id: str = result.get("osm_id", "")
            category: str = result.get("category", "unknown")
            place_type: str = result.get("type", "unknown")
            lat = round(float(result.get("lat", "")), 3)
            lon = round(float(result.get("lon", "")), 3)

            # Convert osm_type to single letter: node->N, way->W, relation->R
            osm_type_letter: str = osm_type[0].upper() if osm_type else ""

            permalink: str = (
                f"https://nominatim.openstreetmap.org/ui/details.html?osmtype="
                f"{osm_type_letter}&osmid={osm_id}&class={category}"
            )

            osm_map_link = (
                f"https://www.openstreetmap.org/?mlat={lat}&mlon={lon}&zoom=15"
            )
            google_maps_link = f"https://www.google.com/maps?q={lat},{lon}"

            formatted: str = (
                f"[{display_name}]({permalink}) ({place_type}) [{lat}, {lon}] "
                f"([OSM]({osm_map_link}), [Google]({google_maps_link}))"
            )
            formatted_results.append(formatted)

        return formatted_results

    except requests.RequestException as e:
        logger.error(f"Error: {e}")
        return []
