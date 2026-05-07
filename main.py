# File: main.py
import logging
import uuid
from pathlib import Path

import streamlit as st

import os
import subprocess

from map_utils import handle_drawing, render_main_map
from sasclouds_api_scraper import (
    ensure_playwright_browser,
    load_config,
    _read_secret,
)
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

# ── Playwright browser install (once per process) ─────────────────────────────
@st.cache_resource(show_spinner=False)
def _install_playwright_browser():
    ensure_playwright_browser()

_install_playwright_browser()


# ── Daily token refresh (cached — re-runs automatically after TTL expires) ────
@st.cache_resource(ttl=3_600 * 22, show_spinner=False)   # refresh every 22 hours
def _get_token() -> str:
    """
    Returns the anonymous browsing token issued by sasclouds.com — no account
    or credentials required.  The token is scraped headlessly via Playwright
    (subprocess to avoid Windows asyncio conflicts) and cached for 22 hours.

    Fallback chain:
      1. Headless browser scrape — anonymous, works without any login
      2. Manual token from secrets (sasclouds_token) — set once in dashboard
      3. Token already in config.json from a previous scrape
    """
    import sys

    # 1. Scrape anonymously — runs as a fresh subprocess (no asyncio conflict)
    logger.info("_get_token: scraping anonymous token via headless browser…")
    try:
        script = str(Path(__file__).parent / "scrape_token.py")
        proc = subprocess.run(
            [sys.executable, script, "--headless"],
            capture_output=True, text=True, timeout=150,
            cwd=str(Path(__file__).parent),
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        )
        # Always log the full subprocess output so we can debug what happened
        sub_out = (proc.stdout + proc.stderr).strip()
        for line in sub_out.splitlines():
            logger.info(f"  [scrape_token.py] {line}")

        if proc.returncode == 0:
            token = load_config().get("token", "")
            if token:
                logger.info(f"_get_token: token scraped (length={len(token)})")
                return token
        logger.warning(f"_get_token: scrape subprocess exit {proc.returncode}")
    except Exception as exc:
        logger.error(f"_get_token: scrape error: {exc}")

    # 2. Manual override from Streamlit secrets
    try:
        static = st.secrets.get("sasclouds_token", "")
        if static:
            return static
    except Exception:
        pass

    # 3. Existing token from a previous successful scrape
    return load_config().get("token", "")

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
    if token:
        logger.info("Auth token ready")
    else:
        logger.warning("No auth token configured")

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
