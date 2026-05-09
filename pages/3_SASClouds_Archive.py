"""
SASClouds Archive — satellite imagery search tool integrated into OrbitShow.

Search the SASClouds public API for historical satellite scenes:
  - Upload or draw an AOI (or inherit from OrbitShow's main map)
  - Filter by date range, cloud cover, and satellite/sensor
  - Browse results with per-scene quickview overlays on a Folium map
  - Download selected scenes as a georeferenced ZIP
"""

import hashlib
import json
import logging
import sys
import uuid
from pathlib import Path

import streamlit as st

# ── Path bootstrap: ensure project root is importable ─────────────────────────
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# ── Logging ───────────────────────────────────────────────────────────────────
_LOG_DIR = _ROOT / "logs"
_LOG_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)-8s] %(name)s – %(message)s",
    datefmt="%H:%M:%S",
    force=True,
)
_fh = logging.FileHandler(_LOG_DIR / "sasclouds_archive.log", encoding="utf-8")
_fh.setFormatter(logging.Formatter(
    "%(asctime)s [%(levelname)-8s] %(name)s – %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
))
logging.getLogger().addHandler(_fh)
for _noisy in ("urllib3", "httpx", "httpcore", "streamlit", "watchdog"):
    logging.getLogger(_noisy).setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

# ── Imports from SASClouds modules ────────────────────────────────────────────
from sasclouds_api_scraper import ensure_playwright_browser, load_config
from sasclouds_sidebar import render_sasclouds_sidebar
from sasclouds_search_logic import run_search, render_results_table
from sasclouds_map_utils import render_sasclouds_map, handle_drawing

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="SASClouds Archive — OrbitShow",
    page_icon="🛰️",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
.stApp header { display: none !important; }
section[data-testid="stSidebarNav"] { display: none !important; }
.main > div { padding-top: 0rem !important; }
</style>
""", unsafe_allow_html=True)

# ── Playwright (optional — gracefully skipped if not installed) ───────────────
@st.cache_resource(show_spinner=False)
def _ensure_browser():
    ensure_playwright_browser()

_ensure_browser()

# ── Token (anonymous API — token optional) ────────────────────────────────────
@st.cache_resource(show_spinner=False)
def _get_token() -> str:
    try:
        static = st.secrets.get("sasclouds_token", "")
        if static:
            return static
    except Exception:
        pass
    return load_config().get("token", "")

# ── Session init ──────────────────────────────────────────────────────────────
_SP = "sc"   # state_prefix — all SASClouds session keys are namespaced under "sc_"

if f"{_SP}_session_id" not in st.session_state:
    st.session_state[f"{_SP}_session_id"] = str(uuid.uuid4())

session_id = st.session_state[f"{_SP}_session_id"]

# ── Page header ───────────────────────────────────────────────────────────────
st.title("🛰️ SASClouds Archive")
st.caption("Search historical satellite imagery via the SASClouds public API.")

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    sidebar_params = render_sasclouds_sidebar(key_prefix=_SP)

logger.debug(
    f"Sidebar | sats={len(sidebar_params.get('selected_satellites', []))} | "
    f"cloud≤{sidebar_params.get('max_cloud')}% | "
    f"search_clicked={sidebar_params.get('search_clicked')}"
)

# ── Resolve AOI: drawn polygon > sidebar ──────────────────────────────────────
polygon_geojson = (
    st.session_state.get(f"{_SP}_polygon_geojson")
    or sidebar_params["polygon_geojson"]
)
aoi_filename = (
    st.session_state.get(f"{_SP}_aoi_filename")
    or sidebar_params["aoi_filename"]
)

# Reset map position when AOI changes
_aoi_hash = (
    hashlib.md5(json.dumps(polygon_geojson, sort_keys=True).encode()).hexdigest()
    if polygon_geojson else ""
)
if st.session_state.get(f"{_SP}_aoi_hash") != _aoi_hash:
    _from_draw = aoi_filename == "map_drawn"
    if not _from_draw:
        st.session_state.pop(f"{_SP}_map_center", None)
        st.session_state.pop(f"{_SP}_map_zoom", None)
    st.session_state[f"{_SP}_aoi_hash"] = _aoi_hash

# ── Search ────────────────────────────────────────────────────────────────────
if sidebar_params["search_clicked"]:
    if not polygon_geojson:
        st.error("Please provide an AOI — upload a file or draw a polygon on the map.")
    elif not sidebar_params["selected_satellites"]:
        st.warning("No satellites selected. Choose at least one in the sidebar.")
    else:
        logger.info(
            f"Search | AOI={aoi_filename!r} | "
            f"{sidebar_params['start_date']} → {sidebar_params['end_date']} | "
            f"cloud≤{sidebar_params['max_cloud']}% | "
            f"sats={[s['satelliteId'] for s in sidebar_params['selected_satellites']]}"
        )
        run_search(
            polygon_geojson=polygon_geojson,
            aoi_filename=aoi_filename,
            start_date=sidebar_params["start_date"],
            end_date=sidebar_params["end_date"],
            max_cloud=sidebar_params["max_cloud"],
            selected_satellites=sidebar_params["selected_satellites"],
            session_id=session_id,
            log_container=st.empty(),
            state_prefix=_SP,
        )

# ── Main layout: results table (left) + map (right) ──────────────────────────
left_col, right_col = st.columns([2, 3])

with left_col:
    render_results_table(state_prefix=_SP)

with right_col:
    st.subheader("🗺️ Map — Draw AOI · View Footprints & Quickviews")

    features_for_map      = st.session_state.get(f"{_SP}_features_map")
    features_for_download = st.session_state.get(f"{_SP}_features_download") or []

    # Resolve quickview previews
    preview_indices = st.session_state.get(f"{_SP}_preview_indices") or set()
    preview_scenes = [
        features_for_download[i]
        for i in sorted(preview_indices)
        if 0 <= i < len(features_for_download)
    ]

    # Reset map position when preview selection changes
    _preview_hash = (
        hashlib.md5(json.dumps(sorted(preview_indices)).encode()).hexdigest()
        if preview_indices else ""
    )
    if st.session_state.get(f"{_SP}_preview_hash") != _preview_hash:
        st.session_state[f"{_SP}_preview_hash"] = _preview_hash
        st.session_state.pop(f"{_SP}_map_center", None)
        st.session_state.pop(f"{_SP}_map_zoom", None)

    stored_center = st.session_state.get(f"{_SP}_map_center")
    stored_zoom   = st.session_state.get(f"{_SP}_map_zoom")

    map_data = render_sasclouds_map(
        polygon_geojson=polygon_geojson,
        features_for_map=features_for_map,
        preview_scenes=preview_scenes,
        stored_center=stored_center,
        stored_zoom=stored_zoom,
        map_key=f"{_SP}_main_map",
    )

    # Persist pan/zoom
    if map_data:
        _ret_center = map_data.get("center")
        _ret_zoom   = map_data.get("zoom")
        if _ret_center:
            st.session_state[f"{_SP}_map_center"] = [_ret_center["lat"], _ret_center["lng"]]
        if _ret_zoom:
            st.session_state[f"{_SP}_map_zoom"] = _ret_zoom

    # Handle new drawing
    new_aoi = handle_drawing(map_data)
    if new_aoi:
        st.session_state[f"{_SP}_polygon_geojson"] = new_aoi
        st.session_state[f"{_SP}_aoi_filename"] = "map_drawn"
        logger.info(f"New AOI drawn: {len(new_aoi['coordinates'][0])} vertices")
        st.success("✅ AOI captured from drawing.")
        st.rerun()

# ── Footer ────────────────────────────────────────────────────────────────────
st.divider()
st.caption(
    "SASClouds Archive uses the public SASClouds v5 API (anonymous access). "
    "Quickviews are served directly from the SASClouds CDN."
)
