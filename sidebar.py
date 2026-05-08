# File: sidebar.py
import os
import tempfile
from datetime import datetime

import streamlit as st
from shapely.geometry import mapping

from aoi_handler import AOIHandler
from sasclouds_api_scraper import SATELLITE_GROUPS

MAX_AOI_FILE_SIZE_MB = 10
MAX_AOI_FILE_SIZE_BYTES = MAX_AOI_FILE_SIZE_MB * 1024 * 1024


def _sat_label(sat: dict) -> str:
    sensor_str = ", ".join(sat.get("sensorIds", [])) if sat.get("sensorIds") else "All sensors"
    return f"{sat['satelliteId']} ({sensor_str})"


def render_sidebar():
    """Render sidebar filters (bounding box & file upload only)."""
    with st.sidebar:
        st.header("🔍 Search Parameters")

        aoi_method = st.radio("AOI input method", ["Bounding box", "Upload file"])

        polygon_geojson = None
        aoi_filename = None

        if aoi_method == "Bounding box":
            # Clear any cached uploaded AOI when switching to bbox mode
            st.session_state.pop("_aoi_cache_key", None)
            st.session_state.pop("_aoi_geojson", None)
            st.session_state.pop("_aoi_filename", None)

            col1, col2 = st.columns(2)
            with col1:
                min_lon = st.number_input("West (min lon)", value=116.0, format="%.6f")
                min_lat = st.number_input("South (min lat)", value=39.5, format="%.6f")
            with col2:
                max_lon = st.number_input("East (max lon)", value=117.0, format="%.6f")
                max_lat = st.number_input("North (max lat)", value=40.5, format="%.6f")
            polygon_geojson = {
                "type": "Polygon",
                "coordinates": [[[min_lon, min_lat], [max_lon, min_lat],
                                  [max_lon, max_lat], [min_lon, max_lat], [min_lon, min_lat]]],
            }
            aoi_filename = "bbox"

        else:  # Upload file
            uploaded_file = st.file_uploader(
                "Upload AOI file",
                type=["geojson", "zip", "kml", "kmz"],
                help="Supported: GeoJSON (.geojson), Shapefile (.zip containing .shp), KML (.kml), KMZ (.kmz)",
            )
            if uploaded_file:
                if uploaded_file.size > MAX_AOI_FILE_SIZE_BYTES:
                    st.error(f"❌ File too large! Max size is {MAX_AOI_FILE_SIZE_MB} MB.")
                else:
                    # Cache by (filename, size) so re-runs don't re-parse the file
                    cache_key = (uploaded_file.name, uploaded_file.size)
                    if st.session_state.get("_aoi_cache_key") != cache_key:
                        suffix = os.path.splitext(uploaded_file.name)[1].lower()
                        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                            tmp.write(uploaded_file.getvalue())
                            tmp_path = tmp.name
                        try:
                            aoi_polygon = AOIHandler.load_from_filepath(tmp_path)
                            if aoi_polygon is not None:
                                st.session_state["_aoi_cache_key"] = cache_key
                                st.session_state["_aoi_geojson"]   = mapping(aoi_polygon)
                                st.session_state["_aoi_filename"]  = uploaded_file.name
                            else:
                                st.error("Failed to load AOI. Check file format.")
                        finally:
                            os.unlink(tmp_path)

                    if st.session_state.get("_aoi_geojson"):
                        polygon_geojson = st.session_state["_aoi_geojson"]
                        aoi_filename    = st.session_state["_aoi_filename"]
                        st.success(f"File loaded: {aoi_filename}")

        # ── Temporal & Cloud Filters ──────────────────────────────────────────
        st.subheader("Temporal & Cloud Filters")
        start_date = st.date_input("Start date", value=datetime(2025, 1, 1))
        end_date   = st.date_input("End date",   value=datetime(2026, 4, 11))
        max_cloud  = st.slider("Maximum cloud cover (%)", 0, 100, 20)

        # ── Satellite selection ───────────────────────────────────────────────
        st.subheader("🛰️ Satellites and sensors")
        selected_satellites = []

        # Build a lookup: exact label → satellite dict, so matching is unambiguous
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
                    chosen = st.multiselect(cat_name, labels, key=f"{group_name}_{cat_name}")
                    for label in chosen:
                        sat = label_to_sat.get(label)
                        if sat:
                            selected_satellites.append({
                                "satelliteId": sat["satelliteId"],
                                "sensorIds":   sat.get("sensorIds", []),
                            })

        search_clicked = st.button("🔍 Search", type="primary", use_container_width=True)

        return {
            "polygon_geojson":    polygon_geojson,
            "aoi_filename":       aoi_filename,
            "start_date":         start_date,
            "end_date":           end_date,
            "max_cloud":          max_cloud,
            "selected_satellites": selected_satellites,
            "search_clicked":     search_clicked,
        }
