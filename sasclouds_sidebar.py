# SASClouds sidebar — satellite selection, AOI upload, date/cloud filters.
# Renamed from sidebar.py to avoid collision with OrbitShow's ui/sidebar.py.
import os
import tempfile
from datetime import datetime

import streamlit as st
from shapely.geometry import mapping

try:
    from data.aoi_handler import AOIHandler
except ImportError:
    from aoi_handler import AOIHandler

from sasclouds_api_scraper import SATELLITE_GROUPS

MAX_AOI_FILE_SIZE_MB = 10
MAX_AOI_FILE_SIZE_BYTES = MAX_AOI_FILE_SIZE_MB * 1024 * 1024


def _sat_label(sat: dict) -> str:
    sensor_str = ", ".join(sat.get("sensorIds", [])) if sat.get("sensorIds") else "All sensors"
    return f"{sat['satelliteId']} ({sensor_str})"


def render_sasclouds_sidebar(key_prefix: str = "sc"):
    """
    Render SASClouds search parameters inside st.sidebar.
    Returns a dict with: polygon_geojson, aoi_filename, start_date, end_date,
    max_cloud, selected_satellites, search_clicked.
    key_prefix avoids Streamlit widget-key collisions when embedded in OrbitShow.
    """
    st.header("🛰️ SASClouds Archive Search")

    # ── AOI: file upload ──────────────────────────────────────────────────────
    st.subheader("📍 Area of Interest")
    st.caption("Upload a file below, or draw a polygon directly on the map.")

    polygon_geojson = None
    aoi_filename = None

    # If OrbitShow has an AOI loaded, offer to use it
    orbitshow_aoi = st.session_state.get("aoi")
    if orbitshow_aoi is not None:
        from shapely.geometry import mapping as _mapping
        use_os_aoi = st.checkbox(
            "Use AOI from OrbitShow main map",
            value=True,
            key=f"{key_prefix}_use_os_aoi",
        )
        if use_os_aoi:
            polygon_geojson = _mapping(orbitshow_aoi)
            aoi_filename = "orbitshow_aoi"
            st.success("Using OrbitShow AOI")

    if polygon_geojson is None:
        uploaded_file = st.file_uploader(
            "Upload AOI file",
            type=["geojson", "zip", "kml", "kmz"],
            key=f"{key_prefix}_aoi_upload",
            help="Supported: GeoJSON, Shapefile (ZIP), KML, KMZ",
        )

        if uploaded_file:
            if uploaded_file.size > MAX_AOI_FILE_SIZE_BYTES:
                st.error(f"File too large (max {MAX_AOI_FILE_SIZE_MB} MB).")
            else:
                cache_key = (uploaded_file.name, uploaded_file.size)
                if st.session_state.get(f"{key_prefix}_aoi_cache_key") != cache_key:
                    suffix = os.path.splitext(uploaded_file.name)[1].lower()
                    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                        tmp.write(uploaded_file.getvalue())
                        tmp_path = tmp.name
                    try:
                        aoi_polygon = AOIHandler.load_from_filepath(tmp_path)
                        if aoi_polygon is not None:
                            st.session_state[f"{key_prefix}_aoi_cache_key"] = cache_key
                            st.session_state[f"{key_prefix}_aoi_geojson"] = mapping(aoi_polygon)
                            st.session_state[f"{key_prefix}_aoi_filename"] = uploaded_file.name
                            st.session_state.pop(f"{key_prefix}_polygon_geojson", None)
                        else:
                            st.error("Failed to load AOI. Check file format.")
                    except Exception as exc:
                        st.error(f"Error loading file: {exc}")
                    finally:
                        os.unlink(tmp_path)

                if st.session_state.get(f"{key_prefix}_aoi_geojson"):
                    polygon_geojson = st.session_state[f"{key_prefix}_aoi_geojson"]
                    aoi_filename = st.session_state[f"{key_prefix}_aoi_filename"]
                    st.success(f"✅ {aoi_filename}")

        elif st.session_state.get(f"{key_prefix}_aoi_geojson"):
            st.session_state.pop(f"{key_prefix}_aoi_cache_key", None)
            st.session_state.pop(f"{key_prefix}_aoi_geojson", None)
            st.session_state.pop(f"{key_prefix}_aoi_filename", None)

    # Fall back to drawn polygon from the SASClouds map
    if polygon_geojson is None:
        drawn = st.session_state.get(f"{key_prefix}_polygon_geojson")
        if drawn:
            polygon_geojson = drawn
            aoi_filename = "map_drawn"
            st.info("Using polygon drawn on the map below.")

    # ── Temporal & Cloud Filters ──────────────────────────────────────────────
    st.subheader("Temporal & Cloud Filters")
    start_date = st.date_input(
        "Start date", value=datetime(2025, 1, 1), key=f"{key_prefix}_start"
    )
    end_date = st.date_input(
        "End date", value=datetime(2026, 4, 11), key=f"{key_prefix}_end"
    )
    max_cloud = st.slider(
        "Maximum cloud cover (%)", 0, 100, 20, key=f"{key_prefix}_cloud"
    )

    # ── Satellite selection ───────────────────────────────────────────────────
    st.subheader("🛰️ Satellites and sensors")
    selected_satellites = []

    label_to_sat: dict = {}
    for categories in SATELLITE_GROUPS.values():
        for sats in categories.values():
            if not isinstance(sats, list):
                continue
            for sat in sats:
                if isinstance(sat, dict):
                    label_to_sat[_sat_label(sat)] = sat

    for group_name, categories in SATELLITE_GROUPS.items():
        with st.expander(group_name):
            for cat_name, sats in categories.items():
                if not isinstance(sats, list):
                    continue
                labels = [_sat_label(s) for s in sats if isinstance(s, dict)]
                chosen = st.multiselect(
                    cat_name, labels,
                    key=f"{key_prefix}_{group_name}_{cat_name}",
                )
                for label in chosen:
                    sat = label_to_sat.get(label)
                    if sat:
                        selected_satellites.append({
                            "satelliteId": sat["satelliteId"],
                            "sensorIds": sat.get("sensorIds", []),
                        })

    search_clicked = st.button(
        "🔍 Search Archive",
        type="primary",
        use_container_width=True,
        key=f"{key_prefix}_search",
    )

    return {
        "polygon_geojson": polygon_geojson,
        "aoi_filename": aoi_filename,
        "start_date": start_date,
        "end_date": end_date,
        "max_cloud": max_cloud,
        "selected_satellites": selected_satellites,
        "search_clicked": search_clicked,
    }
