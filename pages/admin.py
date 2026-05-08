# pages/admin.py - Admin dashboard for SASClouds API Scraper
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

# set_page_config must be the first Streamlit call
st.set_page_config(page_title="Admin Dashboard", layout="wide")

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

st.title("📊 Admin Dashboard – SASClouds API Scraper")

# Absolute paths so the admin page works regardless of the shell CWD
# (pages/ is one level below the project root)
_APP_DIR = Path(__file__).parent.parent
_LOG_DIR = _APP_DIR / "logs"

# ----------------------------------------------------------------------
# Data loading functions
# ----------------------------------------------------------------------
@st.cache_data(ttl=300)
def load_search_logs():
    log_file = _LOG_DIR / "search_history.jsonl"
    entries = []
    if not log_file.exists():
        return entries
    with open(log_file, "r") as f:
        for line in f:
            try:
                entries.append(json.loads(line))
            except Exception:
                continue
    return entries


@st.cache_data(ttl=300)
def load_aoi_logs():
    log_file = _LOG_DIR / "aoi_history.jsonl"
    entries = []
    if not log_file.exists():
        return entries
    with open(log_file, "r") as f:
        for line in f:
            try:
                entries.append(json.loads(line))
            except Exception:
                continue
    return entries


@st.cache_data(ttl=300)
def load_error_logs():
    log_file = _LOG_DIR / "api_errors.log"
    if log_file.exists():
        with open(log_file, "r") as f:
            return f.readlines()
    return []


# ----------------------------------------------------------------------
# Helper functions
# ----------------------------------------------------------------------
@st.cache_data
def load_country_geojson():
    data_dir = _APP_DIR / "data"
    possible_names = [
        "world_countries.geojson",
        "world_countries.GeoJSON",
        "ne_110m_admin_0_countries.geojson",
    ]
    for name in possible_names:
        path = data_dir / name
        if path.exists():
            try:
                gdf = gpd.read_file(path)
                name_col = None
                for col in ["CNTRY_NAME", "NAME", "name", "ADMIN", "SOVEREIGNT"]:
                    if col in gdf.columns:
                        name_col = col
                        break
                if name_col:
                    gdf = gdf[[name_col, "geometry"]].rename(columns={name_col: "country"})
                    gdf = gdf.to_crs("EPSG:4326")
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
            return countries.iloc[0]["country"]
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


def generate_kml_from_search_record(record):
    kml = simplekml.Kml()
    aoi_data = record.get("aoi")
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
            if geom["type"] == "Polygon":
                pol = aoi_folder.newpolygon(name="Area of Interest")
                coords = [(lon, lat) for lon, lat, *_ in geom["coordinates"][0]]
                pol.outerboundaryis = coords
                pol.style.polystyle.color = simplekml.Color.changealpha("33", "0000FF")
            elif geom["type"] == "MultiPolygon":
                for idx, poly_coords in enumerate(geom["coordinates"]):
                    pol = aoi_folder.newpolygon(name=f"Area of Interest part {idx + 1}")
                    coords = [(lon, lat) for lon, lat, *_ in poly_coords[0]]
                    pol.outerboundaryis = coords
                    pol.style.polystyle.color = simplekml.Color.changealpha("33", "0000FF")
        except Exception:
            pass
    return kml.kml()


# ----------------------------------------------------------------------
# Tab renderers
# ----------------------------------------------------------------------
def render_dashboard_tab():
    searches = load_search_logs()
    aois = load_aoi_logs()
    st.subheader("Dashboard Overview")
    col1, col2, col3 = st.columns(3)
    col1.metric("Total Searches", len(searches))
    col2.metric("Total AOI Uploads", len(aois))
    col3.metric("Total Scenes Found", sum(s.get("num_scenes", 0) for s in searches))

    st.subheader("📐 Recent AOI Records")
    aoi_records = []
    for aoi in aois[-20:]:
        name = aoi.get("filename", "Upload")
        geom = aoi.get("geometry")
        area = "Unknown"
        if geom:
            try:
                area_km2 = shape(geom).area * 111.0 * 111.0
                area = f"{area_km2:.2f} km²"
            except Exception:
                pass
        aoi_records.append({
            "Timestamp": aoi.get("timestamp", ""),
            "Name": name,
            "Area": area,
            "Session": str(aoi.get("session_id", ""))[:8],
        })
    if aoi_records:
        st.dataframe(pd.DataFrame(aoi_records), use_container_width=True)
    else:
        st.info("No AOI records yet.")


def render_messages_tab():
    st.subheader("📨 User Messages")
    st.info("Messages are not collected in this version.")


def render_analytics_tab():
    st.subheader("📈 Search Analytics")
    searches = load_search_logs()
    if not searches:
        st.info("No search data yet.")
        return
    df = pd.DataFrame(searches)
    df["date"] = pd.to_datetime(df["timestamp"]).dt.date
    daily = df.groupby("date").size().reset_index(name="count")
    fig = px.line(daily, x="date", y="count", title="Daily Searches")
    st.plotly_chart(fig, use_container_width=True)

    sat_counts: dict = {}
    for s in searches:
        for sat in s.get("filters", {}).get("satellites", []):
            sid = sat.get("satelliteId", "")
            if sid:
                sat_counts[sid] = sat_counts.get(sid, 0) + 1
    if sat_counts:
        st.subheader("Most Searched Satellites")
        st.bar_chart(pd.Series(sat_counts).sort_values(ascending=False))


def render_activity_history_tab():
    st.subheader("📋 Unified Activity History")
    searches = load_search_logs()
    aois = load_aoi_logs()
    activities = []
    for a in aois:
        activities.append({**a, "type": "aoi_upload"})
    for s in searches:
        activities.append({**s, "type": "search"})
    activities.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
    if not activities:
        st.info("No activities.")
        return
    tz = st.session_state.get("admin_timezone", "UTC")
    for act in activities[:50]:
        timestamp_utc = act.get("timestamp")
        try:
            dt_utc = datetime.fromisoformat(timestamp_utc) if isinstance(timestamp_utc, str) else datetime.now(pytz.UTC)
        except Exception:
            dt_utc = datetime.now(pytz.UTC)
        timestamp_local = utc_to_local(dt_utc, tz).strftime("%Y-%m-%d %H:%M:%S")

        if act["type"] == "search":
            with st.expander(f"🔍 Satellite Search – {timestamp_local}"):
                st.write(f"**Session ID:** `{act.get('session_id')}`")
                st.write(f"**Filters:** {act.get('filters', {})}")
                st.write(f"**Scenes found:** {act.get('num_scenes', 0)}")
                if act.get("aoi"):
                    st.json(act["aoi"])
        else:
            with st.expander(f"📁 AOI Upload: {act.get('filename', 'unknown')} – {timestamp_local}"):
                st.write(f"**Session ID:** `{act.get('session_id')}`")
                if act.get("geometry"):
                    st.json(act["geometry"])


def render_logs_management_tab():
    st.subheader("📁 Logs Management")
    error_logs = load_error_logs()
    st.metric("Error log lines", len(error_logs))
    if st.button("🗑️ Clear API error logs"):
        (_LOG_DIR / "api_errors.log").write_text("")
        st.cache_data.clear()
        st.rerun()
    if error_logs:
        st.code("".join(error_logs[-50:]), language="bash")


def render_active_users_tab():
    st.subheader("👥 Active Users")
    st.info("Active session tracking requires additional setup. Showing distinct sessions from logs.")
    searches = load_search_logs()
    sessions = {s.get("session_id") for s in searches if s.get("session_id")}
    st.metric("Distinct user sessions", len(sessions))


def render_system_health_tab():
    st.subheader("🖥️ System Health")
    try:
        import psutil
        st.metric("CPU Usage", f"{psutil.cpu_percent()}%")
        mem = psutil.virtual_memory()
        st.metric("Memory Usage", f"{mem.percent}% ({mem.used // (1024**3)} GB / {mem.total // (1024**3)} GB)")
        disk = psutil.disk_usage("/")
        st.metric("Disk Usage", f"{disk.percent}% ({disk.used // (1024**3)} GB / {disk.total // (1024**3)} GB)")
    except ImportError:
        st.info("Install `psutil` for system metrics: `pip install psutil`")
    except Exception as e:
        st.error(f"Could not retrieve metrics: {e}")


def render_cache_management_tab():
    st.subheader("🗄️ Cache Management")
    if st.button("Clear Streamlit cache"):
        st.cache_data.clear()
        st.success("Cache cleared.")


def render_session_management_tab():
    st.subheader("Session Management")
    st.info("Killing individual user sessions is not implemented in this version.")


def render_backup_restore_tab():
    st.subheader("Backup & Restore")
    backup_dir = _APP_DIR / "admin_backups"
    backup_dir.mkdir(exist_ok=True)
    if st.button("Create backup ZIP"):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_zip = backup_dir / f"admin_backup_{timestamp}.zip"
        with zipfile.ZipFile(backup_zip, "w", zipfile.ZIP_DEFLATED) as zf:
            for target in [_LOG_DIR, _APP_DIR / "config.json"]:
                if target.exists():
                    if target.is_dir():
                        for f in target.rglob("*"):
                            if f.is_file():
                                zf.write(f, f.relative_to(_APP_DIR))
                    else:
                        zf.write(target, target.relative_to(_APP_DIR))
        with open(backup_zip, "rb") as f:
            st.download_button(
                "📥 Download backup",
                f,
                file_name=backup_zip.name,
                mime="application/zip",
            )

    existing = sorted(backup_dir.glob("admin_backup_*.zip"), reverse=True)
    if existing:
        st.subheader("Existing backups")
        for bk in existing[:10]:
            size_kb = bk.stat().st_size // 1024
            st.text(f"{bk.name}  ({size_kb} KB)")


def render_api_status_tab():
    st.subheader("API Status")
    st.write("SASClouds API version: auto-detected at runtime (v5 confirmed via HAR 2026-05-06).")
    st.write("Check `logs/api_errors.log` and `logs/api_interactions.jsonl` for detailed API activity.")

    jsonl_path = _LOG_DIR / "api_interactions.jsonl"
    if jsonl_path.exists():
        try:
            df = pd.read_json(jsonl_path, lines=True)
            st.subheader("Recent API interactions")
            st.dataframe(df.tail(30)[["ts", "event", "url", "status", "duration_ms"]].fillna(""), use_container_width=True)
        except Exception as e:
            st.warning(f"Could not parse api_interactions.jsonl: {e}")


def render_custom_satellites_tab():
    st.subheader("User-Added Satellites")
    st.info("Custom satellite management is not used in this version.")


def render_tle_stats_tab():
    st.subheader("🛰️ TLE Statistics")
    st.info("TLE tracking is not used in this version.")


# ----------------------------------------------------------------------
# Main layout — 13 tabs
# ----------------------------------------------------------------------
(tab1, tab2, tab3, tab4, tab5,
 tab6, tab7, tab8, tab9, tab10,
 tab11, tab12, tab13) = st.tabs([
    "Dashboard", "Messages", "Analytics", "Activity History", "Logs Management",
    "Active Users", "System Health", "Cache Management", "Session Management",
    "Backup & Restore", "API Status", "Custom Satellites", "TLE Stats",
])

with tab1:
    render_dashboard_tab()
with tab2:
    render_messages_tab()
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
