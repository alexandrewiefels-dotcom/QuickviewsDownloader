# pages/admin_dashboard.py - No external dependency on navigation_tracker
import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime, timedelta
import pytz
from pathlib import Path
import json
import folium
from streamlit_folium import st_folium
from shapely.geometry import shape, mapping, Point
import base64
import simplekml
import geopandas as gpd
import shutil
import zipfile
import tempfile

# ---------- ADMIN AUTHENTICATION ----------
ADMIN_PASSWORD = st.secrets.get("ADMIN_PASSWORD", None)
if ADMIN_PASSWORD is None:
    st.error("ADMIN_PASSWORD not found in secrets. Please set it in .streamlit/secrets.toml")
    st.stop()

if "admin_authenticated" not in st.session_state:
    st.session_state.admin_authenticated = False

if not st.session_state.admin_authenticated:
    st.title("🔐 Admin Authentication Required")
    admin_pass_input = st.text_input("Enter Admin Password", type="password")
    if st.button("Login as Admin"):
        if admin_pass_input == ADMIN_PASSWORD:
            st.session_state.admin_authenticated = True
            st.rerun()
        else:
            st.error("Incorrect admin password")
    st.stop()

st.set_page_config(page_title="Admin Dashboard", layout="wide")
st.title("📊 Admin Dashboard – SASClouds Scraper")

# ---------- Fallback for missing navigation_tracker ----------
def get_active_sessions_fallback(minutes_active=15):
    return {"count": 0, "sessions": []}

# We'll just use the fallback directly (no import)
get_active_sessions = get_active_sessions_fallback
SEARCH_HISTORY_DIR = Path("navigation_history")  # fallback – can be changed later

# ----------------------------------------------------------------------
# Helper functions (unchanged)
# ----------------------------------------------------------------------
@st.cache_data
def load_country_geojson():
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

def utc_to_local(utc_dt: datetime, tz_str: str) -> datetime:
    if utc_dt.tzinfo is None:
        utc_dt = utc_dt.replace(tzinfo=pytz.UTC)
    local_tz = pytz.timezone(tz_str)
    return utc_dt.astimezone(local_tz)

def get_country_from_aoi(aoi_geom):
    if aoi_geom is None or aoi_geom.is_empty:
        return "Unknown"
    centroid = aoi_geom.centroid
    point = Point(centroid.x, centroid.y)
    gdf = load_country_geojson()
    if gdf is not None:
        countries = gdf[gdf.geometry.contains(point)]
        if not countries.empty:
            return countries.iloc[0]['country']
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

def generate_kml_from_record(record):
    kml = simplekml.Kml()
    aoi_data = record.get('aoi')
    aoi_geom = None
    if aoi_data:
        try:
            if isinstance(aoi_data, dict):
                aoi_geom = shape(aoi_data)
            elif isinstance(aoi_data, str):
                from shapely import wkt
                aoi_geom = wkt.loads(aoi_data)
        except Exception:
            aoi_geom = None
    if aoi_geom and not aoi_geom.is_empty:
        try:
            aoi_folder = kml.newfolder(name="AOI")
            geom = mapping(aoi_geom)
            if geom['type'] == 'Polygon':
                pol = aoi_folder.newpolygon(name="Area of Interest")
                coords = [(lon, lat) for lon, lat, *_ in geom['coordinates'][0]]
                pol.outerboundaryis = coords
                pol.style.polystyle.color = simplekml.Color.changealpha("33", "0000FF")
            elif geom['type'] == 'MultiPolygon':
                for idx, poly_coords in enumerate(geom['coordinates']):
                    pol = aoi_folder.newpolygon(name=f"Area of Interest part {idx+1}")
                    coords = [(lon, lat) for lon, lat, *_ in poly_coords[0]]
                    pol.outerboundaryis = coords
                    pol.style.polystyle.color = simplekml.Color.changealpha("33", "0000FF")
        except Exception:
            pass
    passes_folder = kml.newfolder(name="Passes")
    for p in record.get('passes', []):
        if p.get('footprint'):
            try:
                fp = shape(p['footprint'])
                if fp and not fp.is_empty:
                    parts = [fp] if fp.geom_type == 'Polygon' else list(fp.geoms)
                    for part in parts:
                        pol = passes_folder.newpolygon(name=f"{p['satellite']} - {p['camera']} - {p['pass_time'][:19]}")
                        coords = [(lon, lat) for lon, lat, *_ in part.exterior.coords]
                        pol.outerboundaryis = coords
                        pol.style.polystyle.color = simplekml.Color.changealpha("44", "FF0000")
                        pol.extendeddata.newdata('Satellite', p['satellite'])
                        pol.extendeddata.newdata('ONA', str(p.get('min_ona', 'N/A')))
            except Exception:
                pass
    return kml.kml()

@st.cache_data(ttl=300)
def load_aoi_uploads_cached():
    aoi_dir = Path("aoi_history")
    entries = []
    if not aoi_dir.exists():
        return entries
    for file in aoi_dir.glob("aoi_*.json"):
        try:
            with open(file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                data['type'] = 'aoi_upload'
                data['source_file'] = str(file)
                entries.append(data)
        except Exception:
            continue
    return entries

@st.cache_data(ttl=300)
def load_country_selections_cached():
    entries = []
    filepath = Path("admin_data/country_selections.jsonl")
    if not filepath.exists():
        return entries
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            for line in f:
                data = json.loads(line)
                data['type'] = 'country_select'
                entries.append(data)
    except Exception:
        pass
    return entries

@st.cache_data(ttl=300)
def load_search_history_cached():
    entries = []
    search_dir = SEARCH_HISTORY_DIR
    if not search_dir.exists():
        return entries
    for file in search_dir.glob("search_*.json"):
        try:
            with open(file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                data['type'] = 'search'
                data['source_file'] = str(file)
                entries.append(data)
        except Exception:
            continue
    return entries

@st.cache_data(ttl=300)
def load_custom_satellites_cached():
    entries = []
    filepath = Path("admin_data/custom_satellites.jsonl")
    if not filepath.exists():
        return entries
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            for line in f:
                data = json.loads(line)
                data['type'] = 'custom_satellite'
                entries.append(data)
    except Exception:
        pass
    return entries

def load_all_activities():
    activities = []
    activities.extend(load_aoi_uploads_cached())
    activities.extend(load_country_selections_cached())
    activities.extend(load_search_history_cached())
    activities.extend(load_custom_satellites_cached())
    activities.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
    return activities

def get_log_stats():
    logs = {
        "navigation_logs.json": {"path": Path("navigation_logs.json")},
        "admin_data/user_sessions.jsonl": {"path": Path("admin_data/user_sessions.jsonl")},
        "admin_data/tasking_sessions.jsonl": {"path": Path("admin_data/tasking_sessions.jsonl")},
        "admin_data/searches.jsonl": {"path": Path("admin_data/searches.jsonl")},
        "admin_data/aoi_uploads.jsonl": {"path": Path("admin_data/aoi_uploads.jsonl")},
    }
    stats = {}
    for name, info in logs.items():
        path = info["path"]
        if path.exists():
            size_bytes = path.stat().st_size
            size_mb = size_bytes / (1024 * 1024)
            if path.suffix == ".jsonl":
                try:
                    with open(path, 'r', encoding='utf-8') as f:
                        count = sum(1 for _ in f)
                except:
                    count = 0
            else:
                try:
                    with open(path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        count = len(data) if isinstance(data, list) else 0
                except:
                    count = 0
            stats[name] = {
                "size_mb": round(size_mb, 2),
                "entries": count,
                "path": str(path),
                "missing": False
            }
        else:
            stats[name] = {"size_mb": None, "entries": None, "path": str(path), "missing": True}
    return stats

def truncate_navigation_log(keep_last=10000, create_backup=True):
    log_file = Path("navigation_logs.json")
    if not log_file.exists():
        return f"❌ Log file not found: {log_file}"
    backup_path = None
    if create_backup:
        backup_path = log_file.with_suffix(".json.bak")
        shutil.copy2(log_file, backup_path)
    try:
        with open(log_file, 'r', encoding='utf-8') as f:
            logs = json.load(f)
        if not isinstance(logs, list):
            logs = []
        original_count = len(logs)
        if original_count <= keep_last:
            if backup_path:
                backup_path.unlink()
            return f"ℹ️ Log has {original_count} entries, no truncation needed (limit = {keep_last})."
        logs = logs[-keep_last:]
        with open(log_file, 'w', encoding='utf-8') as f:
            json.dump(logs, f, indent=2)
        msg = f"✅ Truncated log from {original_count} to {len(logs)} entries."
        if backup_path:
            msg += f" Backup saved as {backup_path.name}"
        return msg
    except Exception as e:
        return f"❌ Error truncating log: {e}"

def truncate_jsonl_file(filepath, keep_last=10000, create_backup=True):
    path = Path(filepath)
    if not path.exists():
        return f"❌ File not found: {path}"
    if create_backup:
        backup_path = path.with_suffix(".jsonl.bak")
        shutil.copy2(path, backup_path)
    try:
        with open(path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        original_count = len(lines)
        if original_count <= keep_last:
            if create_backup:
                backup_path.unlink()
            return f"ℹ️ File has {original_count} entries, no truncation needed."
        with open(path, 'w', encoding='utf-8') as f:
            f.writelines(lines[-keep_last:])
        msg = f"✅ Truncated {path.name} from {original_count} to {keep_last} entries."
        if create_backup:
            msg += f" Backup saved as {backup_path.name}"
        return msg
    except Exception as e:
        return f"❌ Error truncating {path.name}: {e}"

# ----------------------------------------------------------------------
# Tabs rendering (all without navigation_tracker)
# ----------------------------------------------------------------------
def render_dashboard_tab(messages, aoi_history):
    st.subheader("Dashboard Overview")
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Total AOI Uploads", len(aoi_history))
    with col2:
        st.metric("Country Selections", len(load_country_selections_cached()))
    with col3:
        st.metric("Search Activities", len(load_search_history_cached()))
    st.subheader("📐 Recent AOI Records")
    aoi_records = []
    for aoi in aoi_history[-20:]:
        name = aoi.get('filename', 'Unknown')
        area = aoi.get('area_km2', None)
        if area is None and aoi.get('geometry'):
            try:
                geom = shape(aoi['geometry'])
                area_km2 = geom.area * 111.0 * 111.0
                area = f"{area_km2:.2f} km²"
            except:
                area = "N/A"
        else:
            area = f"{area:.2f} km²" if area else "N/A"
        timestamp = aoi.get('timestamp', '')
        source = "Upload"
        aoi_records.append({"Timestamp": timestamp, "Name": name, "Area": area, "Source": source})
    country_selections = load_country_selections_cached()
    for cs in country_selections[-20:]:
        name = cs.get('country_name', 'Unknown')
        area = "Country boundary"
        timestamp = cs.get('timestamp', '')
        source = "Country Select"
        aoi_records.append({"Timestamp": timestamp, "Name": name, "Area": area, "Source": source})
    if aoi_records:
        df_aoi = pd.DataFrame(aoi_records)
        df_aoi = df_aoi.sort_values('Timestamp', ascending=False)
        st.dataframe(df_aoi, use_container_width=True)
    else:
        st.info("No AOI records found.")

def render_messages_tab(messages):
    st.subheader("📨 User Messages")
    if not messages:
        st.info("No messages yet. (Feature not implemented in this version)")
    else:
        for msg in messages[-20:]:
            with st.expander(f"{msg.get('subject', 'No Subject')} – {msg.get('timestamp', 'unknown date')}"):
                st.write(f"**From:** {msg.get('name', 'Unknown')} ({msg.get('email', 'no email')})")
                st.write(msg.get('message', ''))
                st.caption(f"Session ID: {msg.get('session_id', 'unknown')}")

def render_analytics_tab():
    st.subheader("📈 User Analytics")
    st.info("Detailed analytics can be added by parsing navigation_logs.json")

def render_activity_history_tab():
    st.subheader("📋 Unified Activity History")
    activities = load_all_activities()
    if not activities:
        st.info("No activities recorded yet.")
        return
    tz = st.session_state.get('admin_timezone', 'UTC')
    for act in activities[:50]:
        timestamp_utc = act.get('timestamp')
        if isinstance(timestamp_utc, str):
            try:
                dt_utc = datetime.fromisoformat(timestamp_utc)
            except:
                dt_utc = datetime.now(pytz.UTC)
        else:
            dt_utc = timestamp_utc or datetime.now(pytz.UTC)
        dt_local = utc_to_local(dt_utc, tz)
        timestamp_local = dt_local.strftime('%Y-%m-%d %H:%M:%S')
        activity_type = act.get('type')
        if activity_type == 'search':
            icon = "🔍"
            title = f"Satellite Search"
            with st.expander(f"{icon} {title} – {timestamp_local}"):
                st.write(f"**Session ID:** `{act.get('session_id')}`")
                st.write(f"**Filters:** {act.get('filters', {})}")
                st.write(f"**Selected Satellites:** {act.get('selected_satellites', [])}")
                st.write(f"**Passes found:** {len(act.get('passes', []))}")
                if act.get('aoi'):
                    st.json(act['aoi'])
        elif activity_type == 'custom_satellite':
            icon = "🛰️➕"
            sat_name = act.get('satellite_name', 'Unknown')
            title = f"Custom Satellite: {sat_name}"
            with st.expander(f"{icon} {title} – {timestamp_local}"):
                st.write(f"**Session ID:** `{act.get('session_id')}`")
                st.write(f"**NORAD ID:** {act.get('norad')}")
                st.write(f"**Swath:** {act.get('swath_km')} km | **Resolution:** {act.get('resolution_m')} m")
        elif activity_type == 'aoi_upload':
            icon = "📁"
            title = f"AOI Upload: {act.get('filename', 'unknown')}"
            with st.expander(f"{icon} {title} – {timestamp_local}"):
                st.write(f"**Session ID:** `{act.get('user_id') or act.get('session_id')}`")
                if act.get('geometry'):
                    st.json(act['geometry'])
        elif activity_type == 'country_select':
            icon = "🌍"
            title = f"Country Selection: {act.get('country_name', 'Unknown')}"
            with st.expander(f"{icon} {title} – {timestamp_local}"):
                st.write(f"**Session ID:** `{act.get('session_id')}`")
                if act.get('country_wkt'):
                    st.text(act['country_wkt'][:200] + "...")

def render_logs_management_tab():
    st.subheader("📁 Logs Management")
    stats = get_log_stats()
    st.dataframe(pd.DataFrame(stats).T, use_container_width=True)
    if st.button("🧹 Truncate navigation_logs.json (keep 10,000 entries)"):
        result = truncate_navigation_log(keep_last=10000)
        st.success(result)
        st.rerun()
    for name, info in stats.items():
        if not info["missing"] and "jsonl" in name:
            if st.button(f"Truncate {name} (keep 10,000 lines)"):
                result = truncate_jsonl_file(info["path"], keep_last=10000)
                st.success(result)
                st.rerun()

def render_active_users_tab():
    st.subheader("👥 Active Users")
    active = get_active_sessions(minutes_active=15)
    st.metric("Active sessions", active["count"])
    if active["sessions"]:
        df = pd.DataFrame(active["sessions"])
        df["last_seen"] = pd.to_datetime(df["last_seen"]).dt.strftime("%Y-%m-%d %H:%M:%S")
        st.dataframe(df, use_container_width=True)
    else:
        st.info("No active sessions. (session tracking not implemented)")

def render_system_health_tab():
    st.subheader("🖥️ System Health")
    try:
        import psutil
        cpu = psutil.cpu_percent()
        mem = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        st.metric("CPU Usage", f"{cpu}%")
        st.metric("Memory Usage", f"{mem.percent}% ({mem.used//(1024**3)} GB / {mem.total//(1024**3)} GB)")
        st.metric("Disk Usage", f"{disk.percent}% ({disk.used//(1024**3)} GB / {disk.total//(1024**3)} GB)")
    except ImportError:
        st.info("Install `psutil` to see system metrics: `pip install psutil`")
    except Exception as e:
        st.error(f"Could not retrieve metrics: {e}")

def render_cache_management_tab():
    st.subheader("🗄️ Cache Management")
    if Path("tle_cache.json").exists():
        st.write("TLE cache file size:", Path("tle_cache.json").stat().st_size / 1024, "KB")
        if st.button("Clear TLE cache"):
            Path("tle_cache.json").unlink()
            st.success("TLE cache cleared.")
    if Path("aoi_history").exists():
        st.write("AOI history files:", len(list(Path("aoi_history").glob("*.json"))))
        if st.button("Clear AOI history"):
            for f in Path("aoi_history").glob("*.json"):
                f.unlink()
            st.success("AOI history cleared.")

def render_session_management_tab():
    st.subheader("Session Management")
    st.info("This tab would allow killing user sessions – requires navigation_tracker module.")

def render_backup_restore_tab():
    st.subheader("Backup & Restore")
    backup_dir = Path("admin_backups")
    backup_dir.mkdir(exist_ok=True)
    if st.button("Create backup ZIP"):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_zip = backup_dir / f"admin_backup_{timestamp}.zip"
        with zipfile.ZipFile(backup_zip, "w") as zf:
            for p in ["admin_data", "aoi_history", "navigation_logs.json"]:
                if Path(p).exists():
                    if Path(p).is_dir():
                        for f in Path(p).rglob("*"):
                            zf.write(f, f.relative_to("."))
                    else:
                        zf.write(p, p)
        with open(backup_zip, "rb") as f:
            st.download_button("Download backup", f, file_name=backup_zip.name)

def render_api_status_tab():
    st.subheader("API Status")
    st.info("Check Space-Track, N2YO, OpenWeatherMap keys from secrets (configure in .streamlit/secrets.toml).")

def render_custom_satellites_tab():
    st.subheader("User‑Added Satellites")
    sats = load_custom_satellites_cached()
    if not sats:
        st.info("No custom satellites yet.")
    for sat in sats:
        st.write(f"- {sat.get('satellite_name')} (NORAD {sat.get('norad')}) added by {sat.get('session_id')}")

def render_tle_stats_tab():
    st.subheader("🛰️ TLE Statistics")
    st.info("Integrate with your TLE fetcher module to display supplier success rates, last update, etc.")

# ----------------------------------------------------------------------
# Main tabs layout
# ----------------------------------------------------------------------
tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8, tab9, tab10, tab11, tab12, tab13 = st.tabs([
    "Dashboard", "Messages", "Analytics", "Activity History", "Logs Management",
    "Active Users", "System Health", "Cache Management", "Session Management",
    "Backup & Restore", "API Status", "Custom Satellites", "TLE Stats"
])

# Load data
all_messages = []
aoi_uploads = load_aoi_uploads_cached()

with tab1:
    render_dashboard_tab(all_messages, aoi_uploads)
with tab2:
    render_messages_tab(all_messages)
with tab3:
    render_analytics_tab()
with tab4:
    render_activity_history_tab()
with tab5:
    render_logs_management_tab()
with tab6:
    render_active_users_tab()
with tab7:
    render_system_health_tab()
with tab8:
    render_cache_management_tab()
with tab9:
    render_session_management_tab()
with tab10:
    render_backup_restore_tab()
with tab11:
    render_api_status_tab()
with tab12:
    render_custom_satellites_tab()
with tab13:
    render_tle_stats_tab()