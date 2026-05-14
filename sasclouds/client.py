# ============================================================================
# FILE: sasclouds/client.py – SASCloudsAPIClient class (HTTP client)
# ============================================================================
"""
SASClouds API Client – AOI upload, scene search, download, georeferencing.

Extracted from the monolithic sasclouds_api_scraper.py (1438 lines).
"""

import json
import logging
import re
import time
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests
from PIL import Image
from shapely.geometry import shape as shapely_shape
from shapely.validation import explain_validity

from sasclouds.constants import (
    SATELLITE_GROUPS,
    _APP_DIR,
    _CONFIG_PATH,
    LOG_DIR,
)
from sasclouds.logging_utils import _log_event

logger = logging.getLogger(__name__)


# ── API endpoints ────────────────────────────────────────────────────────────
BASE_URL = "https://www.sasclouds.com"
UPLOAD_URL = f"{BASE_URL}/api/upload"
SEARCH_URL = f"{BASE_URL}/api/search"
DOWNLOAD_URL = f"{BASE_URL}/api/download"
QUICKVIEW_URL = f"{BASE_URL}/api/quickview"
GEOCODE_URL = f"{BASE_URL}/api/geocode"
TOKEN_URL = f"{BASE_URL}/user/login?action=token"
LOGIN_URL = f"{BASE_URL}/user/login"


class SASCloudsAPIClient:
    """
    HTTP client for the SASClouds API.

    Handles authentication, AOI upload, scene search, download, and
    georeferencing operations.
    """

    def __init__(self, token: Optional[str] = None):
        """
        Parameters
        ----------
        token : str, optional
            SASClouds API token. If not provided, attempts to load from
            config.json or environment.
        """
        self.token = token or self._load_token()
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        })
        if self.token:
            self.session.headers["Authorization"] = f"Bearer {self.token}"

    # ── Token management ──────────────────────────────────────────────────

    def _load_token(self) -> Optional[str]:
        """Load API token from config.json."""
        config_path = _CONFIG_PATH
        if config_path.exists():
            try:
                with open(config_path, "r") as f:
                    config = json.load(f)
                return config.get("sasclouds_token") or config.get("token")
            except (json.JSONDecodeError, OSError):
                logger.warning("Failed to read config.json for token.")
        return None

    def save_token(self, token: str) -> None:
        """Persist API token to config.json."""
        config_path = _CONFIG_PATH
        config = {}
        if config_path.exists():
            try:
                with open(config_path, "r") as f:
                    config = json.load(f)
            except (json.JSONDecodeError, OSError):
                pass
        config["sasclouds_token"] = token
        config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(config_path, "w") as f:
            json.dump(config, f, indent=2)
        self.token = token
        self.session.headers["Authorization"] = f"Bearer {self.token}"
        logger.info("API token saved to %s", config_path)

    def is_authenticated(self) -> bool:
        """Check if the client has a valid token."""
        return bool(self.token)

    # ── AOI upload ────────────────────────────────────────────────────────

    def upload_aoi(
        self,
        geojson: Dict[str, Any],
        filename: str = "aoi.geojson",
    ) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
        """
        Upload an AOI (Area of Interest) to SASClouds.

        Parameters
        ----------
        geojson : dict
            GeoJSON FeatureCollection or Feature.
        filename : str
            Name for the uploaded file.

        Returns
        -------
        tuple
            (response_json, error_message) — error_message is None on success.
        """
        if not self.is_authenticated():
            return None, "Not authenticated. Please provide a valid API token."

        # Validate geometry
        try:
            shape = shapely_shape(geojson["features"][0]["geometry"])
            validity = explain_validity(shape)
            if validity != "Valid Geometry":
                return None, f"Invalid geometry: {validity}"
        except (KeyError, IndexError, TypeError) as e:
            return None, f"Failed to parse GeoJSON: {e}"

        # Upload
        try:
            geojson_bytes = json.dumps(geojson).encode("utf-8")
            files = {"file": (filename, BytesIO(geojson_bytes), "application/geo+json")}
            resp = self.session.post(UPLOAD_URL, files=files, timeout=120)
            resp.raise_for_status()
            data = resp.json()

            _log_event("aoi_upload", {
                "filename": filename,
                "success": True,
                "response": data,
            })
            return data, None

        except requests.RequestException as e:
            error_msg = f"AOI upload failed: {e}"
            logger.error(error_msg)
            _log_event("aoi_upload", {
                "filename": filename,
                "success": False,
                "error": str(e),
            })
            return None, error_msg

    # ── Scene search ──────────────────────────────────────────────────────

    def search_scenes(
        self,
        aoi_geojson: Dict[str, Any],
        satellites: List[str],
        start_date: str,
        end_date: str,
        max_cloud_cover: Optional[float] = None,
        max_results: int = 500,
    ) -> Tuple[Optional[List[Dict[str, Any]]], Optional[str]]:
        """
        Search for satellite scenes over an AOI.

        Parameters
        ----------
        aoi_geojson : dict
            GeoJSON of the AOI.
        satellites : list of str
            Satellite IDs to search (e.g., ["GF2", "GF7"]).
        start_date : str
            Start date in YYYY-MM-DD format.
        end_date : str
            End date in YYYY-MM-DD format.
        max_cloud_cover : float, optional
            Maximum cloud cover percentage (0-100).
        max_results : int
            Maximum number of results to return.

        Returns
        -------
        tuple
            (scenes_list, error_message) — error_message is None on success.
        """
        if not self.is_authenticated():
            return None, "Not authenticated."

        payload = {
            "aoi": aoi_geojson,
            "satellites": satellites,
            "startDate": start_date,
            "endDate": end_date,
            "maxResults": max_results,
        }
        if max_cloud_cover is not None:
            payload["maxCloudCover"] = max_cloud_cover

        try:
            start_time = time.time()
            resp = self.session.post(SEARCH_URL, json=payload, timeout=300)
            duration_ms = (time.time() - start_time) * 1000
            resp.raise_for_status()
            data = resp.json()

            scenes = data.get("scenes") or data.get("results") or data.get("data", [])
            _log_event("search", {
                "satellites": satellites,
                "start_date": start_date,
                "end_date": end_date,
                "result_count": len(scenes),
                "duration_ms": duration_ms,
            })
            return scenes, None

        except requests.RequestException as e:
            error_msg = f"Scene search failed: {e}"
            logger.error(error_msg)
            return None, error_msg

    # ── Download ──────────────────────────────────────────────────────────

    def download_scene(
        self,
        scene_id: str,
        download_type: str = "full",
        format: str = "geotiff",
    ) -> Tuple[Optional[bytes], Optional[str]]:
        """
        Download a satellite scene.

        Parameters
        ----------
        scene_id : str
            Scene identifier.
        download_type : str
            "full" for full scene, "quickview" for preview.
        format : str
            Output format ("geotiff", "png", "jpg").

        Returns
        -------
        tuple
            (file_bytes, error_message) — error_message is None on success.
        """
        if not self.is_authenticated():
            return None, "Not authenticated."

        payload = {
            "sceneId": scene_id,
            "type": download_type,
            "format": format,
        }

        try:
            resp = self.session.post(DOWNLOAD_URL, json=payload, timeout=600)
            resp.raise_for_status()
            _log_event("download", {
                "scene_id": scene_id,
                "type": download_type,
                "format": format,
                "size_bytes": len(resp.content),
            })
            return resp.content, None

        except requests.RequestException as e:
            error_msg = f"Scene download failed: {e}"
            logger.error(error_msg)
            return None, error_msg

    # ── Quickview ─────────────────────────────────────────────────────────

    def get_quickview(
        self,
        scene_id: str,
        width: int = 800,
        height: int = 600,
    ) -> Tuple[Optional[bytes], Optional[str]]:
        """
        Get a quickview (thumbnail) of a scene.

        Parameters
        ----------
        scene_id : str
            Scene identifier.
        width : int
            Image width in pixels.
        height : int
            Image height in pixels.

        Returns
        -------
        tuple
            (image_bytes, error_message) — error_message is None on success.
        """
        if not self.is_authenticated():
            return None, "Not authenticated."

        payload = {
            "sceneId": scene_id,
            "width": width,
            "height": height,
        }

        try:
            resp = self.session.post(QUICKVIEW_URL, json=payload, timeout=120)
            resp.raise_for_status()
            return resp.content, None

        except requests.RequestException as e:
            error_msg = f"Quickview fetch failed: {e}"
            logger.error(error_msg)
            return None, error_msg

    # ── Georeferencing ────────────────────────────────────────────────────

    def geocode_scene(
        self,
        scene_id: str,
        corner_coords: List[Tuple[float, float]],
    ) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
        """
        Georeference a scene by providing corner coordinates.

        Parameters
        ----------
        scene_id : str
            Scene identifier.
        corner_coords : list of (lon, lat) tuples
            Four corner coordinates in clockwise order.

        Returns
        -------
        tuple
            (response_json, error_message) — error_message is None on success.
        """
        if not self.is_authenticated():
            return None, "Not authenticated."

        payload = {
            "sceneId": scene_id,
            "corners": [
                {"lon": c[0], "lat": c[1]} for c in corner_coords
            ],
        }

        try:
            resp = self.session.post(GEOCODE_URL, json=payload, timeout=120)
            resp.raise_for_status()
            return resp.json(), None

        except requests.RequestException as e:
            error_msg = f"Geocoding failed: {e}"
            logger.error(error_msg)
            return None, error_msg

    # ── Utility ───────────────────────────────────────────────────────────

    def get_satellite_groups(self) -> Dict[str, Any]:
        """Return the satellite groups configuration."""
        return SATELLITE_GROUPS

    def get_available_satellites(self) -> List[str]:
        """Return a flat list of all available satellite IDs."""
        sats = []
        for group_name, group_data in SATELLITE_GROUPS.items():
            if group_name == "Optical":
                for subgroup in group_data.values():
                    for sat in subgroup:
                        sats.append(sat["satelliteId"])
            else:
                for sat in group_data:
                    sats.append(sat["satelliteId"])
        return sats
