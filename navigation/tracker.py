# ============================================================================
# FILE: navigation/tracker.py – Core tracking functions
# ============================================================================
"""
Core navigation tracking functions for the OrbitShow application.

Extracted from the monolithic navigation_tracker.py (1089 lines).
"""

import json
import logging
import os
import platform
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

import streamlit as st
import pandas as pd
from shapely.geometry import Point

logger = logging.getLogger(__name__)


# ── Constants ────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent
ADMIN_DATA_DIR = BASE_DIR / "logs"
ADMIN_DATA_DIR.mkdir(parents=True, exist_ok=True)

NAVIGATION_LOG_FILE = ADMIN_DATA_DIR / "navigation_log.json"
SEARCH_HISTORY_DIR = ADMIN_DATA_DIR / "search_history"
SEARCH_HISTORY_DIR.mkdir(parents=True, exist_ok=True)

EVENT_PAGE_VIEW = "page_view"
EVENT_USER_ACTION = "user_action"
EVENT_AOI_UPLOAD = "aoi_upload"
EVENT_COUNTRY_SELECT = "country_select"
EVENT_SEARCH = "search"
EVENT_SATELLITES_SELECT = "satellites_select"
EVENT_TASKING = "tasking"


# ── Initialisation ──────────────────────────────────────────────────────────

def init_navigation_tracker():
    """Initialise session state for navigation tracking."""
    if "session_start" not in st.session_state:
        st.session_state.session_start = datetime.now()
    if "session_id" not in st.session_state:
        st.session_state.session_id = str(uuid.uuid4())[:8]
    if "navigation_history" not in st.session_state:
        st.session_state.navigation_history = []
    if "action_count" not in st.session_state:
        st.session_state.action_count = 0
    if "current_page" not in st.session_state:
        st.session_state.current_page = "unknown"


# ── Client info helpers ─────────────────────────────────────────────────────

def get_user_ip() -> str:
    """Get the user's IP address from Streamlit's server context."""
    try:
        return st.context.headers.get("X-Forwarded-For", "unknown")
    except Exception:
        return "unknown"


def get_user_country() -> str:
    """Get the user's country from IP geolocation via ip-api.com."""
    try:
        ip = get_user_ip()
        if ip == "unknown" or ip.startswith("127.") or ip.startswith("192.168."):
            return "Local"
        import requests as _req
        resp = _req.get(f"http://ip-api.com/json/{ip}", timeout=3)
        if resp.status_code == 200:
            data = resp.json()
            if data.get('status') == 'success':
                return data.get('country', 'Unknown')
    except Exception:
        pass
    return "Unknown"


def get_user_browser() -> str:
    """Get the user's browser from user agent."""
    try:
        ua = st.context.headers.get("User-Agent", "")
        if "Chrome" in ua:
            return "Chrome"
        elif "Firefox" in ua:
            return "Firefox"
        elif "Safari" in ua:
            return "Safari"
        elif "Edge" in ua:
            return "Edge"
        return "Other"
    except Exception:
        return "Unknown"


def get_user_platform() -> str:
    """Get the user's platform."""
    return platform.system()


def get_client_info() -> Dict[str, str]:
    """Return a dict with client info for tracking entries."""
    return {
        "ip": get_user_ip(),
        "country": get_user_country(),
        "browser": get_user_browser(),
        "platform": get_user_platform(),
    }


# ── Internal helpers ────────────────────────────────────────────────────────

def _save_to_jsonl(entry: Dict[str, Any], filename: str):
    """Append a JSON entry to a JSONL file."""
    filepath = ADMIN_DATA_DIR / filename
    try:
        with open(filepath, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, default=str) + "\n")
    except OSError as e:
        logger.warning("Failed to write %s: %s", filename, e)


def _save_to_navigation_log(entry: Dict[str, Any]):
    """Append an entry to the navigation log JSON file."""
    try:
        logs = []
        if NAVIGATION_LOG_FILE.exists():
            with open(NAVIGATION_LOG_FILE, "r", encoding="utf-8") as f:
                logs = json.load(f)
        logs.append(entry)
        with open(NAVIGATION_LOG_FILE, "w", encoding="utf-8") as f:
            json.dump(logs, f, indent=2, default=str)
    except (OSError, json.JSONDecodeError) as e:
        logger.warning("Failed to write navigation log: %s", e)


def _ensure_datetime(value) -> datetime:
    """Ensure a value is a datetime object."""
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value)
        except (ValueError, TypeError):
            return datetime.now()
    elif isinstance(value, datetime):
        return value
    return datetime.now()


# ── Tracking functions ──────────────────────────────────────────────────────

def track_page_view(page_name: str, extra_data: Optional[Dict[str, Any]] = None):
    """Enregistre une visite de page."""
    init_navigation_tracker()

    time_on_previous_page = 0
    if st.session_state.navigation_history:
        last_entry = st.session_state.navigation_history[-1]
        last_timestamp = _ensure_datetime(last_entry.get("timestamp"))
        time_on_previous_page = (datetime.now() - last_timestamp).total_seconds()
        st.session_state.navigation_history[-1]["time_spent_sec"] = time_on_previous_page

    entry = {
        "timestamp": datetime.now().isoformat(),
        "event_type": EVENT_PAGE_VIEW,
        "page": page_name,
        "session_duration_sec": (datetime.now() - st.session_state.session_start).total_seconds(),
        "session_id": st.session_state.session_id,
        "action_count": st.session_state.action_count,
        "time_on_previous_page_sec": time_on_previous_page,
        **get_client_info(),
    }

    if extra_data:
        entry.update(extra_data)

    if time_on_previous_page is not None and st.session_state.navigation_history:
        entry["arrived_from"] = st.session_state.navigation_history[-1].get("page") if st.session_state.navigation_history else None

    st.session_state.navigation_history.append(entry)
    st.session_state.current_page = page_name

    _save_to_jsonl(entry, f"tracking_{datetime.now().strftime('%Y%m%d')}.jsonl")
    _save_to_navigation_log(entry)


def track_user_action(action_name: str, action_details: Optional[Dict[str, Any]] = None):
    """Enregistre une action utilisateur."""
    init_navigation_tracker()

    st.session_state.action_count += 1

    action_entry = {
        "timestamp": datetime.now().isoformat(),
        "event_type": EVENT_USER_ACTION,
        "action": action_name,
        "page": st.session_state.current_page,
        "session_id": st.session_state.session_id,
        "action_number": st.session_state.action_count,
        "session_duration_sec": (datetime.now() - st.session_state.session_start).total_seconds(),
        **get_client_info(),
    }

    if action_details:
        action_entry["details"] = action_details

    if "action_history" not in st.session_state:
        st.session_state.action_history = []
    st.session_state.action_history.append(action_entry)

    _save_to_jsonl(action_entry, f"tracking_{datetime.now().strftime('%Y%m%d')}.jsonl")
    _save_to_navigation_log(action_entry)


def track_aoi_upload(filename: str, file_type: str, aoi_geometry, area_km2: float = None):
    """Enregistre un upload d'AOI."""
    init_navigation_tracker()

    from shapely import wkt

    entry = {
        "timestamp": datetime.now().isoformat(),
        "event_type": EVENT_AOI_UPLOAD,
        "session_id": st.session_state.session_id,
        "filename": filename,
        "file_type": file_type,
        "area_km2": area_km2,
        "aoi_wkt": wkt.dumps(aoi_geometry) if aoi_geometry else None,
        "aoi_bounds": list(aoi_geometry.bounds) if aoi_geometry else None,
        "page": st.session_state.current_page,
        **get_client_info(),
    }

    _save_to_jsonl(entry, "aoi_uploads.jsonl")
    _save_to_navigation_log(entry)
    track_user_action("aoi_upload_success", {"filename": filename, "area_km2": area_km2})


def track_country_selection(country_name: str, country_geometry):
    """Enregistre la sélection d'un pays comme AOI."""
    init_navigation_tracker()

    from shapely import wkt

    entry = {
        "timestamp": datetime.now().isoformat(),
        "event_type": EVENT_COUNTRY_SELECT,
        "session_id": st.session_state.session_id,
        "country_name": country_name,
        "country_wkt": wkt.dumps(country_geometry) if country_geometry else None,
        "country_bounds": list(country_geometry.bounds) if country_geometry else None,
        "page": st.session_state.current_page,
        **get_client_info(),
    }

    _save_to_jsonl(entry, "country_selections.jsonl")
    _save_to_navigation_log(entry)
    track_user_action("country_selected", {"country": country_name})


def track_search(search_params: Dict[str, Any]):
    """Enregistre une recherche de passes."""
    init_navigation_tracker()

    entry = {
        "timestamp": datetime.now().isoformat(),
        "event_type": EVENT_SEARCH,
        "session_id": st.session_state.session_id,
        "start_date": search_params.get("start_date"),
        "end_date": search_params.get("end_date"),
        "max_ona": search_params.get("max_ona"),
        "orbit_filter": search_params.get("orbit_filter"),
        "satellites_count": search_params.get("satellites_count", 0),
        "has_aoi": search_params.get("has_aoi", False),
        "aoi_source": search_params.get("aoi_source"),
        "page": st.session_state.current_page,
        **get_client_info(),
    }

    _save_to_jsonl(entry, "searches.jsonl")
    _save_to_navigation_log(entry)
    track_user_action("search_performed", search_params)


def track_satellites_selected(satellites_list: List[Dict[str, Any]]):
    """Enregistre les satellites sélectionnés."""
    init_navigation_tracker()

    entry = {
        "timestamp": datetime.now().isoformat(),
        "event_type": EVENT_SATELLITES_SELECT,
        "session_id": st.session_state.session_id,
        "satellites_count": len(satellites_list),
        "satellites": satellites_list,
        "page": st.session_state.current_page,
        **get_client_info(),
    }

    _save_to_jsonl(entry, "satellites_selected.jsonl")
    _save_to_navigation_log(entry)


def track_tasking_session(passes_count: int, coverage_percent: float = None, passes_used: int = None):
    """Enregistre une session de tasking."""
    init_navigation_tracker()

    entry = {
        "timestamp": datetime.now().isoformat(),
        "event_type": EVENT_TASKING,
        "session_id": st.session_state.session_id,
        "passes_count": passes_count,
        "coverage_percent": coverage_percent,
        "passes_used": passes_used,
        "page": st.session_state.current_page,
        **get_client_info(),
    }

    _save_to_jsonl(entry, "tasking_sessions.jsonl")
    _save_to_navigation_log(entry)


def track_custom_satellite(norad: int, name: str, swath_km: float, resolution_m: float):
    """Track when a user adds a custom satellite."""
    init_navigation_tracker()
    entry = {
        "timestamp": datetime.now().isoformat(),
        "event_type": "custom_satellite",
        "session_id": st.session_state.session_id,
        "norad": norad,
        "satellite_name": name,
        "swath_km": swath_km,
        "resolution_m": resolution_m,
        "page": st.session_state.current_page,
        **get_client_info(),
    }
    _save_to_jsonl(entry, "custom_satellites.jsonl")
    _save_to_navigation_log(entry)
    track_user_action("custom_satellite_added", {"norad": norad, "name": name})


def track_sasclouds_search(satellites: list, cloud_max: float, date_from: str, date_to: str,
                           scenes_found: int, aoi_filename: str = ""):
    """Track a SASClouds archive search in the unified navigation system."""
    init_navigation_tracker()
    entry = {
        "timestamp": datetime.now().isoformat(),
        "event_type": "sasclouds_search",
        "session_id": st.session_state.session_id,
        "satellites": satellites,
        "cloud_max": cloud_max,
        "date_from": date_from,
        "date_to": date_to,
        "scenes_found": scenes_found,
        "aoi_filename": aoi_filename,
        "page": st.session_state.current_page,
        **get_client_info(),
    }
    _save_to_jsonl(entry, "sasclouds_searches.jsonl")
    _save_to_navigation_log(entry)
    track_user_action("sasclouds_search_performed", {
        "satellites": satellites, "cloud_max": cloud_max,
        "scenes_found": scenes_found, "aoi": aoi_filename,
    })


# ── Compatibility wrappers ──────────────────────────────────────────────────

def track_page_view_simple(page_name, additional_data=None):
    """Simple wrapper for track_page_view for compatibility."""
    track_page_view(page_name, additional_data)


def track_user_action_simple(action, details=None):
    """Simple wrapper for track_user_action for compatibility."""
    track_user_action(action, details)


# ── Country lookup helpers ──────────────────────────────────────────────────

def load_country_geojson():
    """Load country boundaries GeoJSON for reverse geocoding (no caching)."""
    import geopandas as gpd
    base_dir = Path(__file__).parent.parent
    possible_names = ["world_countries.geojson", "world_countries.GeoJSON", "ne_110m_admin_0_countries.geojson"]
    possible_paths = [base_dir / "data" / name for name in possible_names]
    for path in possible_paths:
        if path.exists():
            try:
                gdf = gpd.read_file(path)
                name_col = None
                for col in ['CNTRY_NAME', 'NAME', 'name', 'ADMIN', 'SOVEREIGNT']:
                    if col in gdf.columns:
                        name_col = col
                        break
                if name_col:
                    gdf = gdf[[name_col, 'geometry']].rename(columns={name_col: 'country'})
                    gdf = gdf.to_crs('EPSG:4326')
                    return gdf
            except Exception:
                continue
    return None


def _get_country_from_geometry(aoi_geom):
    """Return country name from AOI geometry using GeoJSON lookup (no caching)."""
    if aoi_geom is None or aoi_geom.is_empty:
        return "Unknown"
    centroid = aoi_geom.centroid
    point = Point(centroid.x, centroid.y)
    gdf = load_country_geojson()
    if gdf is not None:
        countries = gdf[gdf.geometry.contains(point)]
        if not countries.empty:
            return countries.iloc[0]['country']
    # Fallback: approximate from longitude
    lon = centroid.x
    if -180 <= lon <= -60:
        return "Americas"
    elif -60 < lon <= -30:
        return "South America"
    elif -30 < lon <= 30:
        return "Africa/Europe"
    elif 30 < lon <= 90:
        return "Asia"
    elif 90 < lon <= 180:
        return "Asia/Pacific"
    return "Unknown"


# ── Save complete search result ─────────────────────────────────────────────

def save_search_result(session_id, ip, country, aoi, selected_sats, filters, passes, tasking_results=None):
    """
    Save a complete search record with footprints.
    """
    from shapely.geometry import mapping
    timestamp = datetime.now().isoformat()
    search_id = f"search_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"

    # Derive country from AOI if not provided
    aoi_geom = aoi
    if aoi_geom and not aoi_geom.is_empty:
        derived_country = _get_country_from_geometry(aoi_geom)
    else:
        derived_country = country or "Unknown"

    # Serialize AOI
    aoi_geojson = mapping(aoi) if aoi else None

    # Serialize passes
    passes_data = []
    for p in passes:
        pass_record = {
            "id": p.id,
            "satellite": p.satellite_name,
            "camera": p.camera_name,
            "norad": p.norad_id,
            "pass_time": p.pass_time.isoformat(),
            "min_ona": p.min_ona,
            "orbit_direction": p.orbit_direction,
            "footprint": mapping(p.footprint) if p.footprint else None,
            "tasked_footprint": mapping(p.tasked_footprint) if hasattr(p, 'tasked_footprint') and p.tasked_footprint else None,
        }
        passes_data.append(pass_record)

    # Serialize tasking results if any
    tasking_data = None
    if tasking_results:
        tasking_data = []
        for r in tasking_results:
            tr = {
                "satellite": r.get('satellite'),
                "camera": r.get('camera'),
                "required_ona": r.get('required_ona'),
                "shift_km": r.get('shift_km'),
                "coverage_pct": r.get('coverage_pct'),
                "footprint": mapping(r['footprint']) if r.get('footprint') else None,
            }
            tasking_data.append(tr)

    record = {
        "search_id": search_id,
        "timestamp": timestamp,
        "session_id": session_id,
        "ip": ip,
        "country": derived_country,
        "aoi": aoi_geojson,
        "selected_satellites": selected_sats,
        "filters": filters,
        "passes": passes_data,
        "tasking_results": tasking_data,
    }

    filepath = SEARCH_HISTORY_DIR / f"{search_id}.json"
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(record, f, indent=2, default=str)

    print(f"[SearchHistory] Saved search {search_id} with {len(passes)} passes, country={derived_country}")
