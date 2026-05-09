# ============================================================================
# FILE: navigation_tracker.py – Suivi de navigation des utilisateurs
# VERSION ADMIN - Stocke toutes les actions pour l'admin
# + Stockage structuré des AOI, pays, recherches, satellites sélectionnés
# + Compatible avec l'interface admin moderne
# + Added save_search_result for complete search history
# ============================================================================
import streamlit as st
from datetime import datetime, timedelta
import pandas as pd
import hashlib
import json
import uuid
from typing import Dict, Any, Optional, List
from pathlib import Path
import os
import base64
import requests
from functools import lru_cache
import time
# Added for country lookup
import geopandas as gpd
from shapely.geometry import Point

# ============================================================================
# CONSTANTES
# ============================================================================
ADMIN_DATA_DIR = Path("admin_data")
ADMIN_DATA_DIR.mkdir(exist_ok=True)

SEARCH_HISTORY_DIR = ADMIN_DATA_DIR / "search_history"
SEARCH_HISTORY_DIR.mkdir(exist_ok=True)

# Types d'événements
EVENT_PAGE_VIEW = "page_view"
EVENT_USER_ACTION = "user_action"
EVENT_AOI_UPLOAD = "aoi_upload"
EVENT_COUNTRY_SELECT = "country_select"
EVENT_SEARCH = "search"
EVENT_SATELLITES_SELECT = "satellites_select"
EVENT_TASKING = "tasking"
EVENT_SESSION_START = "session_start"
EVENT_SESSION_END = "session_end"

# Fichiers de stockage
NAVIGATION_LOG_FILE = Path("navigation_logs.json")
MAX_LOG_ENTRIES = 10000


# ============================================================================
# FONCTIONS D'INITIALISATION
# ============================================================================
def init_navigation_tracker():
    """Initialise le tracker de navigation dans session_state"""
    if "navigation_history" not in st.session_state:
        st.session_state.navigation_history = []
    if "current_page" not in st.session_state:
        st.session_state.current_page = "main"
    if "session_start" not in st.session_state:
        st.session_state.session_start = datetime.now()
    if "session_id" not in st.session_state:
        session_str = f"{datetime.now().isoformat()}{st.session_state.get('user_id', 'anonymous')}"
        st.session_state.session_id = hashlib.md5(session_str.encode()).hexdigest()[:8]
    if "action_count" not in st.session_state:
        st.session_state.action_count = 0
    if "all_sessions" not in st.session_state:
        st.session_state.all_sessions = []
    
    # Enregistrer le début de session
    if "session_started" not in st.session_state:
        st.session_state.session_started = True
        _save_session_start()
    
    # Ensure log file exists
    if not NAVIGATION_LOG_FILE.exists():
        with open(NAVIGATION_LOG_FILE, 'w', encoding='utf-8') as f:
            json.dump([], f)

# Add to navigation_tracker.py



def get_active_sessions(minutes_active: int = 5) -> dict:
    """
    Count active sessions based on recent log entries.
    Returns dict with 'count' and list of 'sessions'.
    """
    from datetime import datetime, timedelta
    import json
    from pathlib import Path

    cutoff = datetime.now() - timedelta(minutes=minutes_active)
    log_file = Path("navigation_logs.json")
    if not log_file.exists():
        return {"count": 0, "sessions": []}
    
    try:
        with open(log_file, 'r', encoding='utf-8') as f:
            events = json.load(f)
    except:
        return {"count": 0, "sessions": []}
    
    sessions = {}
    for ev in events:
        sid = ev.get("session_id")
        if not sid:
            continue
        ts_str = ev.get("timestamp")
        if not ts_str:
            continue
        try:
            ts = datetime.fromisoformat(ts_str)
        except:
            continue
        if sid not in sessions or ts > sessions[sid]["last_seen"]:
            sessions[sid] = {
                "session_id": sid,
                "last_seen": ts,
                "last_page": ev.get("page", "unknown"),
                "last_action": ev.get("action", ev.get("event_type", "unknown")),
                "ip": ev.get("ip", "unknown"),
                "country": ev.get("country", "unknown")
            }
    
    active_list = [data for data in sessions.values() if data["last_seen"] >= cutoff]
    active_list.sort(key=lambda x: x["last_seen"], reverse=True)
    return {"count": len(active_list), "sessions": active_list}

def cleanup_old_logs(max_age_hours: int = 48):
    """
    Remove log entries older than max_age_hours from all log files.
    This includes navigation_logs.json and all JSONL files in admin_data.
    Also deletes old daily tracking files older than max_age_hours.
    """
    cutoff_time = datetime.now() - timedelta(hours=max_age_hours)
    cutoff_ts = cutoff_time.isoformat()

    # 1. Clean navigation_logs.json
    logs = []
    if NAVIGATION_LOG_FILE.exists():
        try:
            with open(NAVIGATION_LOG_FILE, 'r', encoding='utf-8') as f:
                logs = json.load(f)
                if not isinstance(logs, list):
                    logs = []
        except (json.JSONDecodeError, IOError):
            logs = []
    
    # Filter by timestamp
    new_logs = []
    for entry in logs:
        ts_str = entry.get('timestamp')
        if ts_str:
            try:
                ts = datetime.fromisoformat(ts_str)
                if ts >= cutoff_time:
                    new_logs.append(entry)
            except:
                # keep if timestamp invalid (avoid data loss)
                new_logs.append(entry)
        else:
            new_logs.append(entry)
    
    # Write back if changed
    if len(new_logs) != len(logs):
        with open(NAVIGATION_LOG_FILE, 'w', encoding='utf-8') as f:
            json.dump(new_logs, f, indent=2, default=str)
        print(f"[LogCleanup] Removed {len(logs)-len(new_logs)} old entries from navigation_logs.json")

    # 2. Clean JSONL files in admin_data
    jsonl_files = [
        ADMIN_DATA_DIR / "user_sessions.jsonl",
        ADMIN_DATA_DIR / "tasking_sessions.jsonl",
        ADMIN_DATA_DIR / "searches.jsonl",
        ADMIN_DATA_DIR / "aoi_uploads.jsonl",
        ADMIN_DATA_DIR / "country_selections.jsonl",
        ADMIN_DATA_DIR / "satellites_selected.jsonl",
        ADMIN_DATA_DIR / "custom_satellites.jsonl",
    ]
    for filepath in jsonl_files:
        if not filepath.exists():
            continue
        # Read all lines, filter by timestamp
        lines = []
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                lines = f.readlines()
        except Exception as e:
            print(f"[LogCleanup] Error reading {filepath}: {e}")
            continue
        
        new_lines = []
        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                ts_str = data.get('timestamp')
                if ts_str:
                    ts = datetime.fromisoformat(ts_str)
                    if ts >= cutoff_time:
                        new_lines.append(line + '\n')
                else:
                    # keep if no timestamp
                    new_lines.append(line + '\n')
            except:
                # keep line if malformed (avoid data loss)
                new_lines.append(line + '\n')
        
        if len(new_lines) != len(lines):
            with open(filepath, 'w', encoding='utf-8') as f:
                f.writelines(new_lines)
            print(f"[LogCleanup] Removed {len(lines)-len(new_lines)} old entries from {filepath.name}")

    # 3. Delete old daily tracking files (tracking_YYYYMMDD.jsonl)
    tracking_files = list(ADMIN_DATA_DIR.glob("tracking_*.jsonl"))
    deleted = 0
    for file in tracking_files:
        # extract date from filename: tracking_20241225.jsonl
        try:
            date_str = file.stem.split('_')[1]
            file_date = datetime.strptime(date_str, '%Y%m%d')
            if file_date < cutoff_time:
                file.unlink()
                deleted += 1
        except Exception:
            continue
    if deleted:
        print(f"[LogCleanup] Deleted {deleted} old daily tracking files")

@lru_cache(maxsize=1000)
def get_ip_geolocation(ip: str) -> dict:
    """Get country and city from IP using ip-api.com."""
    if ip == "unknown" or ip.startswith("127.") or ip.startswith("192.168."):
        return {"country": "Local", "city": "Local"}
    try:
        response = requests.get(f"http://ip-api.com/json/{ip}", timeout=3)
        if response.status_code == 200:
            data = response.json()
            if data.get('status') == 'success':
                return {
                    "country": data.get('country', 'Unknown'),
                    "city": data.get('city', 'Unknown')
                }
    except Exception:
        pass
    return {"country": "Unknown", "city": "Unknown"}

def get_session_id():
    """Get or create a unique session ID for the user"""
    if 'session_id' not in st.session_state:
        st.session_state.session_id = str(uuid.uuid4())[:8]
    return st.session_state.session_id


def get_user_ip():
    """Get user IP address from Streamlit (if available)"""
    try:
        if hasattr(st, 'context') and hasattr(st.context, 'headers'):
            headers = st.context.headers
            if 'X-Forwarded-For' in headers:
                return headers['X-Forwarded-For'].split(',')[0].strip()
            if 'Remote-Addr' in headers:
                return headers['Remote-Addr']
    except Exception:
        pass
    return "unknown"


def get_user_country(ip_address=None):
    """Get user country based on IP address or browser language"""
    if ip_address:
        geo = get_ip_geolocation(ip_address)
        return geo["country"]
    try:
        if hasattr(st, 'context') and hasattr(st.context, 'headers'):
            accept_language = st.context.headers.get('Accept-Language', '')
            if 'fr' in accept_language.lower():
                return "France"
            elif 'es' in accept_language.lower():
                return "Spain"
            elif 'de' in accept_language.lower():
                return "Germany"
            elif 'en-us' in accept_language.lower():
                return "United States"
            elif 'en-gb' in accept_language.lower():
                return "United Kingdom"
    except Exception:
        pass
    return "unknown"


def get_client_info() -> Dict[str, str]:
    client_info = {
        "ip": "unknown",
        "user_agent": "unknown",
        "platform": "unknown",
        "browser": "unknown",
        "country": "unknown",
        "city": "unknown"
    }
    try:
        if hasattr(st, 'context') and hasattr(st.context, 'headers'):
            user_agent = st.context.headers.get("User-Agent", "unknown")
            client_info["user_agent"] = user_agent
            client_info["ip"] = st.context.headers.get("X-Forwarded-For", "unknown")
            # ... browser/platform detection ...
            # Get geolocation from IP
            geo = get_ip_geolocation(client_info["ip"])
            client_info["country"] = geo["country"]
            client_info["city"] = geo["city"]
    except:
        pass
    return client_info


def _save_session_start():
    entry = {
        "timestamp": datetime.now().isoformat(),
        "event_type": EVENT_SESSION_START,
        "session_id": st.session_state.session_id,
        "page": "session_start",
        "client_info": get_client_info()
    }
    _save_to_jsonl(entry, "user_sessions.jsonl")
    _save_to_navigation_log(entry)


def _save_to_jsonl(entry: Dict[str, Any], filename: str):
    """Sauvegarde une entrée dans un fichier JSONL"""
    try:
        filepath = ADMIN_DATA_DIR / filename
        with open(filepath, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")
    except Exception as e:
        print(f"Erreur sauvegarde {filename}: {e}")

def _save_to_navigation_log(entry: Dict[str, Any]):
    """Sauvegarde une entrée dans le fichier de log principal"""
    try:
        logs = []
        if NAVIGATION_LOG_FILE.exists():
            try:
                with open(NAVIGATION_LOG_FILE, 'r', encoding='utf-8') as f:
                    logs = json.load(f)
                    if not isinstance(logs, list):
                        logs = []
            except (json.JSONDecodeError, IOError):
                logs = []
        
        logs.append(entry)
        
        if len(logs) > MAX_LOG_ENTRIES:
            logs = logs[-MAX_LOG_ENTRIES:]
        
        with open(NAVIGATION_LOG_FILE, 'w', encoding='utf-8') as f:
            json.dump(logs, f, indent=2, default=str)
    except Exception as e:
        print(f"Erreur sauvegarde log: {e}")


def _ensure_datetime(value):
    """Convertit une chaîne ISO en datetime si nécessaire"""
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value)
        except:
            return datetime.now()
    return value if isinstance(value, datetime) else datetime.now()


def track_page_view(page_name: str, extra_data: Optional[Dict[str, Any]] = None):
    """Enregistre une visite de page"""
    init_navigation_tracker()
    
    # Calculer le temps passé sur la page précédente
    time_on_previous_page = None
    if st.session_state.navigation_history:
        last_entry = st.session_state.navigation_history[-1]
        if last_entry.get("page") != page_name:
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
        **get_client_info()   # includes 'ip', 'country', 'city', etc.

    }
    
    if extra_data:
        entry.update(extra_data)
    
    if time_on_previous_page is not None and st.session_state.navigation_history:
        entry["arrived_from"] = st.session_state.navigation_history[-1].get("page") if st.session_state.navigation_history else None
    
    st.session_state.navigation_history.append(entry)
    st.session_state.current_page = page_name
    
    # Sauvegarder
    _save_to_jsonl(entry, f"tracking_{datetime.now().strftime('%Y%m%d')}.jsonl")
    _save_to_navigation_log(entry)


def track_user_action(action_name: str, action_details: Optional[Dict[str, Any]] = None):
    """Enregistre une action utilisateur"""
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
        **get_client_info()
    }
    
    if action_details:
        action_entry["details"] = action_details
    
    if "action_history" not in st.session_state:
        st.session_state.action_history = []
    st.session_state.action_history.append(action_entry)
    
    # Sauvegarder
    _save_to_jsonl(action_entry, f"tracking_{datetime.now().strftime('%Y%m%d')}.jsonl")
    _save_to_navigation_log(action_entry)


def track_aoi_upload(filename: str, file_type: str, aoi_geometry, area_km2: float = None):
    """Enregistre un upload d'AOI"""
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
        **get_client_info()
    }
    
    _save_to_jsonl(entry, "aoi_uploads.jsonl")
    _save_to_navigation_log(entry)
    track_user_action("aoi_upload_success", {"filename": filename, "area_km2": area_km2})


def track_country_selection(country_name: str, country_geometry):
    """Enregistre la sélection d'un pays comme AOI"""
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
        **get_client_info()
    }
    
    _save_to_jsonl(entry, "country_selections.jsonl")
    _save_to_navigation_log(entry)
    track_user_action("country_selected", {"country": country_name})


def track_search(search_params: Dict[str, Any]):
    """Enregistre une recherche de passes"""
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
        **get_client_info()
    }
    
    _save_to_jsonl(entry, "searches.jsonl")
    _save_to_navigation_log(entry)
    track_user_action("search_performed", search_params)


def track_satellites_selected(satellites_list: List[Dict[str, Any]]):
    """Enregistre les satellites sélectionnés"""
    init_navigation_tracker()
    
    entry = {
        "timestamp": datetime.now().isoformat(),
        "event_type": EVENT_SATELLITES_SELECT,
        "session_id": st.session_state.session_id,
        "satellites_count": len(satellites_list),
        "satellites": satellites_list,
        "page": st.session_state.current_page,
        **get_client_info()
    }
    
    _save_to_jsonl(entry, "satellites_selected.jsonl")
    _save_to_navigation_log(entry)


def track_tasking_session(passes_count: int, coverage_percent: float = None, passes_used: int = None):
    """Enregistre une session de tasking"""
    init_navigation_tracker()
    
    entry = {
        "timestamp": datetime.now().isoformat(),
        "event_type": EVENT_TASKING,
        "session_id": st.session_state.session_id,
        "passes_count": passes_count,
        "coverage_percent": coverage_percent,
        "passes_used": passes_used,
        "page": st.session_state.current_page,
        **get_client_info()
    }
    
    _save_to_jsonl(entry, "tasking_sessions.jsonl")
    _save_to_navigation_log(entry)


# ============================================================================
# COUNTRY LOOKUP HELPERS (no caching, to avoid hashing issues)
# ============================================================================
def load_country_geojson():
    """Load country boundaries GeoJSON for reverse geocoding (no caching)."""
    base_dir = Path(__file__).parent
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


# ============================================================================
# SAVE COMPLETE SEARCH RESULT (for admin search history)
# ============================================================================
def save_search_result(session_id, ip, country, aoi, selected_sats, filters, passes, tasking_results=None):
    """
    Save a complete search record with footprints.
    """
    from shapely.geometry import mapping
    timestamp = datetime.now().isoformat()
    search_id = f"search_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"
    
    # Derive country from AOI if not provided or if we want to override
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
            "tasked_footprint": mapping(p.tasked_footprint) if hasattr(p, 'tasked_footprint') and p.tasked_footprint else None
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
                "footprint": mapping(r['footprint']) if r.get('footprint') else None
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
        "tasking_results": tasking_data
    }
    
    filepath = SEARCH_HISTORY_DIR / f"{search_id}.json"
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(record, f, indent=2, default=str)
    
    print(f"[SearchHistory] Saved search {search_id} with {len(passes)} passes, country={derived_country}")


# ============================================================================
# FONCTIONS DE LECTURE DES DONNÉES POUR L'ADMIN
# ============================================================================
def load_all_tracking_data(days: int = 30) -> pd.DataFrame:
    """Charge toutes les données de tracking des derniers jours"""
    all_entries = []
    cutoff_date = datetime.now() - timedelta(days=days)
    
    for file in ADMIN_DATA_DIR.glob("tracking_*.jsonl"):
        try:
            with open(file, "r", encoding="utf-8") as f:
                for line in f:
                    entry = json.loads(line)
                    entry_time = datetime.fromisoformat(entry["timestamp"])
                    if entry_time >= cutoff_date:
                        all_entries.append(entry)
        except Exception as e:
            print(f"Erreur lecture {file}: {e}")
    
    return pd.DataFrame(all_entries) if all_entries else pd.DataFrame()


def load_aoi_uploads(days: int = 30) -> pd.DataFrame:
    """Charge l'historique des uploads AOI"""
    entries = []
    cutoff_date = datetime.now() - timedelta(days=days)
    
    filepath = ADMIN_DATA_DIR / "aoi_uploads.jsonl"
    if filepath.exists():
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                for line in f:
                    entry = json.loads(line)
                    entry_time = datetime.fromisoformat(entry["timestamp"])
                    if entry_time >= cutoff_date:
                        entries.append(entry)
        except Exception as e:
            print(f"Erreur lecture aoi_uploads: {e}")
    
    return pd.DataFrame(entries) if entries else pd.DataFrame()


def load_country_selections(days: int = 30) -> pd.DataFrame:
    """Charge l'historique des sélections de pays"""
    entries = []
    cutoff_date = datetime.now() - timedelta(days=days)
    
    filepath = ADMIN_DATA_DIR / "country_selections.jsonl"
    if filepath.exists():
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                for line in f:
                    entry = json.loads(line)
                    entry_time = datetime.fromisoformat(entry["timestamp"])
                    if entry_time >= cutoff_date:
                        entries.append(entry)
        except Exception as e:
            print(f"Erreur lecture country_selections: {e}")
    
    return pd.DataFrame(entries) if entries else pd.DataFrame()


def load_searches(days: int = 30) -> pd.DataFrame:
    """Charge l'historique des recherches"""
    entries = []
    cutoff_date = datetime.now() - timedelta(days=days)
    
    filepath = ADMIN_DATA_DIR / "searches.jsonl"
    if filepath.exists():
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                for line in f:
                    entry = json.loads(line)
                    entry_time = datetime.fromisoformat(entry["timestamp"])
                    if entry_time >= cutoff_date:
                        entries.append(entry)
        except Exception as e:
            print(f"Erreur lecture searches: {e}")
    
    return pd.DataFrame(entries) if entries else pd.DataFrame()


def load_satellites_selected(days: int = 30) -> pd.DataFrame:
    """Charge l'historique des sélections de satellites"""
    entries = []
    cutoff_date = datetime.now() - timedelta(days=days)
    
    filepath = ADMIN_DATA_DIR / "satellites_selected.jsonl"
    if filepath.exists():
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                for line in f:
                    entry = json.loads(line)
                    entry_time = datetime.fromisoformat(entry["timestamp"])
                    if entry_time >= cutoff_date:
                        entries.append(entry)
        except Exception as e:
            print(f"Erreur lecture satellites_selected: {e}")
    
    return pd.DataFrame(entries) if entries else pd.DataFrame()


def load_tasking_sessions(days: int = 30) -> pd.DataFrame:
    """Charge l'historique des sessions de tasking"""
    entries = []
    cutoff_date = datetime.now() - timedelta(days=days)
    
    filepath = ADMIN_DATA_DIR / "tasking_sessions.jsonl"
    if filepath.exists():
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                for line in f:
                    entry = json.loads(line)
                    entry_time = datetime.fromisoformat(entry["timestamp"])
                    if entry_time >= cutoff_date:
                        entries.append(entry)
        except Exception as e:
            print(f"Erreur lecture tasking_sessions: {e}")
    
    return pd.DataFrame(entries) if entries else pd.DataFrame()


def load_user_sessions(days: int = 30) -> pd.DataFrame:
    """Charge l'historique des sessions utilisateur"""
    entries = []
    cutoff_date = datetime.now() - timedelta(days=days)
    
    filepath = ADMIN_DATA_DIR / "user_sessions.jsonl"
    if filepath.exists():
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                for line in f:
                    entry = json.loads(line)
                    entry_time = datetime.fromisoformat(entry["timestamp"])
                    if entry_time >= cutoff_date:
                        entries.append(entry)
        except Exception as e:
            print(f"Erreur lecture user_sessions: {e}")
    
    return pd.DataFrame(entries) if entries else pd.DataFrame()


def load_messages() -> List[Dict]:
    """Charge les messages de contact"""
    messages = []
    messages_dir = Path("messages")
    if not messages_dir.exists():
        return []
    
    for file in sorted(messages_dir.glob("message_*.json"), reverse=True):
        try:
            with open(file, "r", encoding="utf-8") as f:
                msg = json.load(f)
                msg["filename"] = str(file)
                messages.append(msg)
        except Exception as e:
            print(f"Erreur lecture {file}: {e}")
    
    return messages


def get_navigation_stats() -> Dict[str, Any]:
    """Retourne les statistiques de navigation de la session courante"""
    init_navigation_tracker()
    
    if not st.session_state.navigation_history:
        return {
            "total_views": 0,
            "unique_pages": 0,
            "most_viewed": None,
            "session_duration_min": 0,
            "page_breakdown": {},
            "total_actions": 0
        }
    
    df = pd.DataFrame(st.session_state.navigation_history)
    action_count = len(st.session_state.get("action_history", []))
    
    return {
        "total_views": len(df),
        "unique_pages": df['page'].nunique() if 'page' in df.columns else 0,
        "most_viewed": df['page'].mode().iloc[0] if not df.empty and 'page' in df.columns else None,
        "session_duration_min": (datetime.now() - st.session_state.session_start).total_seconds() / 60,
        "page_breakdown": df['page'].value_counts().to_dict() if 'page' in df.columns else {},
        "total_actions": action_count,
        "last_page": df['page'].iloc[-1] if not df.empty and 'page' in df.columns else None,
        "session_id": st.session_state.session_id
    }


def get_user_analytics():
    """Get analytics data for admin dashboard"""
    if not NAVIGATION_LOG_FILE.exists():
        return []
    
    try:
        with open(NAVIGATION_LOG_FILE, 'r', encoding='utf-8') as f:
            logs = json.load(f)
            return logs if isinstance(logs, list) else []
    except Exception:
        return []


def export_all_data(format: str = "csv") -> Dict[str, bytes]:
    """Exporte toutes les données pour téléchargement"""
    exports = {}
    
    data_sources = {
        "tracking": load_all_tracking_data,
        "aoi_uploads": load_aoi_uploads,
        "country_selections": load_country_selections,
        "searches": load_searches,
        "satellites_selected": load_satellites_selected,
        "tasking_sessions": load_tasking_sessions,
        "user_sessions": load_user_sessions
    }
    
    for name, loader in data_sources.items():
        df = loader(days=365)
        if not df.empty:
            if format == "csv":
                exports[f"{name}.csv"] = df.to_csv(index=False).encode('utf-8')
            elif format == "json":
                exports[f"{name}.json"] = df.to_json(orient="records", indent=2).encode('utf-8')
    
    return exports


def get_user_statistics() -> Dict[str, Any]:
    """Retourne des statistiques globales sur les utilisateurs"""
    df_tracking = load_all_tracking_data(days=30)
    df_aoi = load_aoi_uploads(days=30)
    df_searches = load_searches(days=30)
    
    return {
        "total_events": len(df_tracking),
        "unique_sessions": df_tracking['session_id'].nunique() if not df_tracking.empty else 0,
        "total_aoi_uploads": len(df_aoi),
        "total_searches": len(df_searches),
        "unique_browsers": df_tracking['browser'].nunique() if not df_tracking.empty and 'browser' in df_tracking.columns else 0,
        "unique_platforms": df_tracking['platform'].nunique() if not df_tracking.empty and 'platform' in df_tracking.columns else 0,
    }


def get_top_countries(limit: int = 10) -> pd.DataFrame:
    """Retourne les pays les plus sélectionnés"""
    df_countries = load_country_selections(days=90)
    if df_countries.empty:
        return pd.DataFrame()
    
    top_countries = df_countries['country_name'].value_counts().reset_index()
    top_countries.columns = ['Country', 'Selections']
    return top_countries.head(limit)


def get_top_satellites(limit: int = 15) -> pd.DataFrame:
    """Retourne les satellites les plus sélectionnés"""
    df_sats = load_satellites_selected(days=90)
    if df_sats.empty:
        return pd.DataFrame()
    
    all_sats = []
    for sats in df_sats['satellites']:
        if isinstance(sats, list):
            for sat in sats:
                if isinstance(sat, dict) and 'name' in sat:
                    all_sats.append(sat['name'])
    
    if not all_sats:
        return pd.DataFrame()
    
    sat_counts = pd.Series(all_sats).value_counts().reset_index()
    sat_counts.columns = ['Satellite', 'Selections']
    return sat_counts.head(limit)


def get_daily_activity(days: int = 30) -> pd.DataFrame:
    """Retourne l'activité quotidienne"""
    df_tracking = load_all_tracking_data(days=days)
    if df_tracking.empty:
        return pd.DataFrame()
    
    df_tracking['date'] = pd.to_datetime(df_tracking['timestamp']).dt.date
    daily_activity = df_tracking.groupby('date').size().reset_index(name='count')
    return daily_activity


def get_user_stats_by_ip(days=30) -> pd.DataFrame:
    """Return statistics grouped by IP address."""
    df = load_all_tracking_data(days)
    if df.empty:
        return pd.DataFrame()
    stats = df.groupby('ip').agg({
        'session_id': 'nunique',
        'timestamp': 'count',
        'country': 'first'
    }).rename(columns={'session_id': 'sessions', 'timestamp': 'actions'})
    return stats


def display_navigation_info_sidebar():
    """
    Affiche les informations de navigation dans la sidebar
    UNIQUEMENT POUR ADMIN
    """
    from admin_auth import is_admin
    
    if not is_admin():
        return
    
    init_navigation_tracker()
    
    st.sidebar.markdown("---")
    st.sidebar.markdown("### 🧭 Navigation Info (Admin)")
    
    stats = get_navigation_stats()
    
    col1, col2 = st.sidebar.columns(2)
    with col1:
        st.metric("Pages visitées", stats['total_views'])
    with col2:
        st.metric("Session", f"{stats['session_duration_min']:.0f} min")
    
    st.sidebar.markdown(f"**Page actuelle:** `{st.session_state.current_page}`")
    st.sidebar.markdown(f"**Session ID:** `{st.session_state.session_id}`")
    st.sidebar.markdown(f"**IP:** `{get_user_ip()}`")
    st.sidebar.markdown(f"**Country:** `{get_user_country()}`")
    
    if st.sidebar.button("📊 Voir l'historique", key="show_history_btn"):
        st.session_state.show_history = not st.session_state.get("show_history", False)
    
    if st.session_state.get("show_history", False):
        st.sidebar.markdown("#### Historique récent")
        if st.session_state.navigation_history:
            recent = st.session_state.navigation_history[-5:]
            for entry in recent:
                timestamp = entry.get("timestamp")
                if isinstance(timestamp, str):
                    try:
                        timestamp = datetime.fromisoformat(timestamp)
                    except:
                        timestamp = datetime.now()
                elif not isinstance(timestamp, datetime):
                    timestamp = datetime.now()
                time_str = timestamp.strftime("%H:%M:%S")
                st.sidebar.markdown(f"- {time_str} → **{entry.get('page', 'unknown')}**")
        
        if st.sidebar.button("📥 Exporter", key="export_history_btn"):
            export_navigation_history()


def export_navigation_history():
    """Exporte l'historique de navigation en CSV"""
    init_navigation_tracker()
    
    if not st.session_state.navigation_history:
        st.warning("Aucun historique à exporter")
        return
    
    df_history = pd.DataFrame(st.session_state.navigation_history)
    export_df = df_history.copy()
    
    if 'timestamp' in export_df.columns:
        export_df['timestamp'] = pd.to_datetime(export_df['timestamp']).dt.strftime('%Y-%m-%d %H:%M:%S')
    
    csv = export_df.to_csv(index=False)
    
    st.download_button(
        label="📥 Télécharger (CSV)",
        data=csv,
        file_name=f"navigation_history_{st.session_state.session_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
        mime="text/csv",
        key="download_history_btn"
    )


def track_page_view_simple(page_name, additional_data=None):
    """Simple wrapper for track_page_view for compatibility"""
    track_page_view(page_name, additional_data)

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
        **get_client_info()
    }
    _save_to_jsonl(entry, "custom_satellites.jsonl")
    _save_to_navigation_log(entry)
    track_user_action("custom_satellite_added", {"norad": norad, "name": name})

def track_user_action_simple(action, details=None):
    """Simple wrapper for track_user_action for compatibility"""
    track_user_action(action, details)
