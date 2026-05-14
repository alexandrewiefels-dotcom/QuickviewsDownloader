# sasclouds package — SASClouds API integration
"""
SASClouds API Client – AOI upload, scene search, download, georeferencing.

This package replaces the monolithic sasclouds_api_scraper.py (1438 lines)
with a modular structure:

    sasclouds/
        __init__.py          — Package exports
        constants.py         — Satellite groups, config paths, logging setup
        client.py            — SASCloudsAPIClient class (HTTP client)
        auth.py              — Token scraping, auto-login, Playwright helpers
        file_utils.py        — File conversion (GeoJSON, KML, KMZ, Shapefile ZIP)
        logging_utils.py     — Activity log helpers (JSONL)
        map_utils.py         — Map rendering helpers (warp layer, corner ordering)
"""

from sasclouds.client import SASCloudsAPIClient
from sasclouds.constants import SATELLITE_GROUPS, LOG_DIR, _APP_DIR, _CONFIG_PATH
from sasclouds.auth import (
    fetch_token_from_page,
    auto_login_and_capture_token,
    scrape_token_via_browser,
    ensure_playwright_browser,
)
from sasclouds.file_utils import convert_uploaded_file_to_geojson
from sasclouds.logging_utils import log_search, log_aoi_upload, _log_event
from sasclouds.map_utils import _order_corners_for_download

__all__ = [
    "SASCloudsAPIClient",
    "SATELLITE_GROUPS",
    "LOG_DIR",
    "_APP_DIR",
    "_CONFIG_PATH",
    "fetch_token_from_page",
    "auto_login_and_capture_token",
    "scrape_token_via_browser",
    "ensure_playwright_browser",
    "convert_uploaded_file_to_geojson",
    "log_search",
    "log_aoi_upload",
    "_log_event",
    "_order_corners_for_download",
]
