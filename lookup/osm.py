#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
Experimental module to return search results for locations via OSM.
"""

from typing import Any
from urllib.parse import quote

import requests

from connection import logger


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
    # URL encode the query (double encoding for the UI link)
    encoded_query: str = quote(query)

    # Build API URL
    url: str = (
        f"https://nominatim.openstreetmap.org/search?q={encoded_query}"
        f"&accept-language={accept_language}&format=jsonv2"
    )

    # Set a user agent (required by Nominatim usage policy)
    headers: dict[str, str] = {"User-Agent": "Python OSM Search Script"}

    try:
        # Make the request
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        results: list[dict[str, Any]] = response.json()

        # Nothing found.
        if not results:
            logger.info(f"> No results found for {query}")
            # If coords provided, return map links with those coordinates
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

        # Format results
        formatted_results: list[str] = []
        for result in results:
            display_name: str = result.get("display_name", "Unknown")
            osm_type: str = result.get("osm_type", "")
            osm_id: str = result.get("osm_id", "")
            category: str = result.get("category", "unknown")
            place_type: str = result.get("type", "unknown")
            lat: float = round(float(result.get("lat", "")), 3)
            lon: float = round(float(result.get("lon", "")), 3)

            # Convert osm_type to single letter: node->N, way->W, relation->R
            osm_type_letter: str = osm_type[0].upper() if osm_type else ""

            # Create Nominatim details permalink
            permalink: str = (
                f"https://nominatim.openstreetmap.org/ui/details.html?osmtype="
                f"{osm_type_letter}&osmid={osm_id}&class={category}"
            )

            # Create map links
            osm_map_link: str = (
                f"https://www.openstreetmap.org/?mlat={lat}&mlon={lon}&zoom=15"
            )
            google_maps_link: str = f"https://www.google.com/maps?q={lat},{lon}"

            # Format output
            formatted: str = (
                f"[{display_name}]({permalink}) ({place_type}) [{lat}, {lon}] "
                f"([OSM]({osm_map_link}), [Google]({google_maps_link}))"
            )
            formatted_results.append(formatted)

        return formatted_results

    except requests.RequestException as e:
        logger.error(f"Error: {e}")
        return []


# Example usage
if __name__ == "__main__":
    while True:
        search_area = input("Please enter the place you want to search for: ")
        results_test = search_nominatim(search_area)
        for result_x in results_test:
            print(result_x)
