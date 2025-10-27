#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
Experimental module to return search results for locations via OSM.
"""

from urllib.parse import quote

import requests


def search_nominatim(query, accept_language="en-US,en"):
    """
    Search OSM Nominatim and return formatted results.

    Args:
        query: Search query string (e.g., "Yongchun, Fujian")
        accept_language: Language preference (default: "en-US,en")

    Returns:
        List of formatted result strings
    """
    # URL encode the query (double encoding for the UI link)
    encoded_query = quote(query)

    # Build API URL
    url = (
        f"https://nominatim.openstreetmap.org/search?q={encoded_query}"
        f"&accept-language={accept_language}&format=jsonv2"
    )

    # Set a user agent (required by Nominatim usage policy)
    headers = {"User-Agent": "Python OSM Search Script"}

    try:
        # Make the request
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        results = response.json()

        # Format results
        formatted_results = []
        for result in results:
            display_name = result.get("display_name", "Unknown")
            osm_type = result.get("osm_type", "")
            osm_id = result.get("osm_id", "")
            category = result.get("category", "unknown")
            place_type = result.get("type", "unknown")
            lat = result.get("lat", "")
            lon = result.get("lon", "")

            # Convert osm_type to single letter: node->N, way->W, relation->R
            osm_type_letter = osm_type[0].upper() if osm_type else ""

            # Create Nominatim details permalink
            permalink = (
                f"https://nominatim.openstreetmap.org/ui/details.html?osmtype="
                f"{osm_type_letter}&osmid={osm_id}&class={category}"
            )

            # Create map links
            osm_map_link = (
                f"https://www.openstreetmap.org/?mlat={lat}&mlon={lon}&zoom=15"
            )
            google_map_link = f"https://www.google.com/maps?q={lat},{lon}"

            # Format output
            formatted = (
                f"[{display_name}]({permalink}) ({place_type}) [{lat}, {lon}] "
                f"([OSM]({osm_map_link}), [Google]({google_map_link}))"
            )
            formatted_results.append(formatted)

        return formatted_results

    except requests.RequestException as e:
        return [f"Error: {str(e)}"]


# Example usage
if __name__ == "__main__":
    while True:
        search_area = input("Please enter the place you want to search: ")
        results_test = search_nominatim(search_area)
        for result_x in results_test:
            print(result_x)
