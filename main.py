# File: main.py
import logging
import uuid
from pathlib import Path

import streamlit as st

from map_utils import handle_drawing, render_main_map
from search_logic import create_download_zip, run_search
from sidebar import render_sidebar

# ── Logging ───────────────────────────────────────────────────────────────────
# force=True clears any handlers left over from the previous Streamlit rerun,
# then we attach a fresh console handler (via basicConfig) plus a file handler.
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)-8s] %(name)s – %(message)s",
    datefmt="%H:%M:%S",
    force=True,
)

# Persist all log output to a rolling text file so nothing is lost between reruns.
_LOG_DIR = Path("./logs")
_LOG_DIR.mkdir(exist_ok=True)
_file_handler = logging.FileHandler(_LOG_DIR / "app.log", encoding="utf-8")
_file_handler.setLevel(logging.DEBUG)
_file_handler.setFormatter(logging.Formatter(
    "%(asctime)s [%(levelname)-8s] %(name)s – %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
))
logging.getLogger().addHandler(_file_handler)

# Keep third-party chatter manageable
for _noisy in ("urllib3", "httpx", "httpcore", "streamlit", "watchdog"):
    logging.getLogger(_noisy).setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

st.set_page_config(page_title="SASClouds API Scraper", layout="wide")

# ── Authentication ────────────────────────────────────────────────────────────
PASSWORD = st.secrets.get("PASSWORD", "default_fallback")
if PASSWORD == "default_fallback":
    st.error("No PASSWORD found in secrets. Please set .streamlit/secrets.toml")
    st.stop()

if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

if not st.session_state.authenticated:
    st.title("🔐 Authentication Required")
    pwd = st.text_input("Enter Password", type="password")
    if st.button("Login"):
        if pwd == PASSWORD:
            st.session_state.authenticated = True
            logger.info("User authenticated successfully")
            st.rerun()
        else:
            st.error("Incorrect password")
            logger.warning("Failed login attempt")
    st.stop()

# ── Session init ──────────────────────────────────────────────────────────────
if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())
    logger.info(f"New session started: {st.session_state.session_id[:8]}…")

if "polygon_geojson" not in st.session_state:
    st.session_state.polygon_geojson = None
if "aoi_filename" not in st.session_state:
    st.session_state.aoi_filename = None

# ── Page header ───────────────────────────────────────────────────────────────
st.title("🛰️ SASClouds API Scraper")
st.markdown("Fast, cloud-compatible search using the official API. No browser needed.")

# ── Sidebar ───────────────────────────────────────────────────────────────────
sidebar_params = render_sidebar()
logger.debug(
    f"Sidebar | satellites={len(sidebar_params.get('selected_satellites', []))} | "
    f"cloud≤{sidebar_params.get('max_cloud')}% | "
    f"search_clicked={sidebar_params.get('search_clicked')}"
)

# ── Resolve AOI: drawn polygon > sidebar file upload > sidebar bbox ───────────
polygon_geojson = st.session_state.polygon_geojson or sidebar_params["polygon_geojson"]
aoi_filename    = st.session_state.aoi_filename    or sidebar_params["aoi_filename"]

# ── Search (runs BEFORE the map so footprints are in session_state when the
#    map renders, making them visible without needing a second rerun) ──────────
if sidebar_params["search_clicked"]:
    if not polygon_geojson:
        st.error("Please provide an AOI (draw on map, use bounding box, or upload a file).")
        logger.warning("Search attempted without AOI")
    elif not sidebar_params["selected_satellites"]:
        st.warning("No satellites selected. Please choose at least one.")
        logger.warning("Search attempted with no satellites selected")
    else:
        logger.info(
            f"Search requested | AOI={aoi_filename!r} | "
            f"{sidebar_params['start_date']} → {sidebar_params['end_date']} | "
            f"cloud≤{sidebar_params['max_cloud']}% | "
            f"satellites={[s['satelliteId'] for s in sidebar_params['selected_satellites']]}"
        )
        run_search(
            polygon_geojson=polygon_geojson,
            aoi_filename=aoi_filename,
            start_date=sidebar_params["start_date"],
            end_date=sidebar_params["end_date"],
            max_cloud=sidebar_params["max_cloud"],
            selected_satellites=sidebar_params["selected_satellites"],
            session_id=st.session_state.session_id,
            log_container=st.empty(),
        )

# ── Single map: drawing tools + AOI overlay + footprints ─────────────────────
st.subheader("🗺️ Map – Draw AOI · View Footprints & Quickviews")
features_for_map = st.session_state.get("features_for_map")
logger.debug(
    f"Rendering map | AOI={'set' if polygon_geojson else 'none'} | "
    f"footprints={len(features_for_map) if features_for_map else 0}"
)
map_data = render_main_map(polygon_geojson=polygon_geojson, features_for_map=features_for_map)

# Handle new drawing events
new_aoi = handle_drawing(map_data)
if new_aoi:
    st.session_state.polygon_geojson = new_aoi
    st.session_state.aoi_filename = "map_drawn"
    logger.info(f"New AOI drawn on map: {len(new_aoi['coordinates'][0])} vertices")
    st.success("✅ AOI captured from drawing.")
    st.rerun()

# ── Download ──────────────────────────────────────────────────────────────────
create_download_zip()
