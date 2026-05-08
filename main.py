# File: main.py
import hashlib
import json
import logging
import uuid
from pathlib import Path

import streamlit as st

from map_utils import handle_drawing, render_main_map
from sasclouds_api_scraper import (
    ensure_playwright_browser,
    load_config,
)
from search_logic import render_results_table, run_search
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
# Use absolute path — Streamlit runs with the user's shell CWD, not the script directory.
_LOG_DIR = Path(__file__).parent / "logs"
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

# ── Playwright browser install (once per process) ─────────────────────────────
@st.cache_resource(show_spinner=False)
def _install_playwright_browser():
    ensure_playwright_browser()

_install_playwright_browser()


# ── Token lookup (no scraping — v5 API is anonymous, confirmed from HAR) ─────
@st.cache_resource(show_spinner=False)
def _get_token() -> str:
    """
    Returns a manually configured token if one exists, otherwise empty string.
    The SASClouds v5 API works without a token for anonymous browsing
    (confirmed from live HAR capture 2026-05-06). Headless scraping is not
    attempted — it never succeeded and blocked startup for 2 minutes.

    To set a token manually, add to .streamlit/secrets.toml:
      sasclouds_token = "<value>"
    """
    # 1. Manual override from Streamlit secrets
    try:
        static = st.secrets.get("sasclouds_token", "")
        if static:
            logger.info(f"_get_token: token from secrets (length={len(static)})")
            return static
    except Exception:
        pass

    # 2. Token saved from a previous manual capture
    token = load_config().get("token", "")
    if token:
        logger.info(f"_get_token: token from config.json (length={len(token)})")
    else:
        logger.info("_get_token: no token configured — using anonymous v5 API")
    return token

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

# ── Auth token check (once per session, daily auto-refresh) ───────────────────
if "token_ready" not in st.session_state:
    token = _get_token()
    st.session_state.token_ready = bool(token)
    logger.info(f"Token status: {'configured' if token else 'none — anonymous v5 API'}")

# ── Page header ───────────────────────────────────────────────────────────────
st.title("🛰️ SASClouds API Scraper")
st.markdown("Fast, cloud-compatible search using the official API. No browser needed.")

# No token warning: the API is public — anonymous browsing works without a token
# (confirmed from live HAR capture 2026-05-06). Token is only needed if the
# server starts enforcing auth for anonymous users.

# ── Sidebar ───────────────────────────────────────────────────────────────────
sidebar_params = render_sidebar()
logger.debug(
    f"Sidebar | satellites={len(sidebar_params.get('selected_satellites', []))} | "
    f"cloud≤{sidebar_params.get('max_cloud')}% | "
    f"search_clicked={sidebar_params.get('search_clicked')}"
)

# ── Resolve AOI: drawn polygon > sidebar file upload ─────────────────────────
polygon_geojson = st.session_state.get("polygon_geojson") or sidebar_params["polygon_geojson"]
aoi_filename    = st.session_state.get("aoi_filename")    or sidebar_params["aoi_filename"]

# ── Auto-zoom: reset stored map position whenever the AOI changes ─────────────
_aoi_hash = (
    hashlib.md5(json.dumps(polygon_geojson, sort_keys=True).encode()).hexdigest()
    if polygon_geojson else ""
)
if st.session_state.get("_aoi_hash") != _aoi_hash:
    st.session_state["_aoi_hash"] = _aoi_hash
    st.session_state.pop("map_center", None)
    st.session_state.pop("map_zoom", None)

# ── Search (runs BEFORE the map so footprints are in session_state when the
#    map renders, making them visible without needing a second rerun) ──────────
if sidebar_params["search_clicked"]:
    if not polygon_geojson:
        st.error("Please provide an AOI — upload a file or draw a polygon on the map.")
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

# ── Results table (left) + Map (right) side-by-side ──────────────────────────
left_col, right_col = st.columns([2, 3])

with left_col:
    render_results_table()

with right_col:
    st.subheader("🗺️ Map – Draw AOI · View Footprints & Quickviews")

    features_for_map      = st.session_state.get("features_for_map")
    features_for_download = st.session_state.get("features_for_download") or []

    # Resolve which scenes the eye buttons are pointing at (set of indices)
    preview_indices = st.session_state.get("preview_indices") or set()
    preview_scenes = [
        features_for_download[i]
        for i in sorted(preview_indices)
        if 0 <= i < len(features_for_download)
    ]

    stored_center = st.session_state.get("map_center")
    stored_zoom   = st.session_state.get("map_zoom")

    logger.debug(
        f"Rendering map | AOI={'set' if polygon_geojson else 'none'} | "
        f"footprints={len(features_for_map) if features_for_map else 0} | "
        f"previews={len(preview_scenes)}"
    )

    map_data = render_main_map(
        polygon_geojson=polygon_geojson,
        features_for_map=features_for_map,
        preview_scenes=preview_scenes,
        stored_center=stored_center,
        stored_zoom=stored_zoom,
    )

    # Persist pan/zoom so the map doesn't reset on every rerun
    if map_data:
        if map_data.get("center"):
            st.session_state["map_center"] = [
                map_data["center"]["lat"],
                map_data["center"]["lng"],
            ]
        if map_data.get("zoom"):
            st.session_state["map_zoom"] = map_data["zoom"]

    # Handle new drawing events
    new_aoi = handle_drawing(map_data)
    if new_aoi:
        st.session_state.polygon_geojson = new_aoi
        st.session_state.aoi_filename = "map_drawn"
        logger.info(f"New AOI drawn on map: {len(new_aoi['coordinates'][0])} vertices")
        st.success("✅ AOI captured from drawing.")
        st.rerun()

