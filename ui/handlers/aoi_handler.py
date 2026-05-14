# ui/handlers/aoi_handler.py – corrected for form usage

import streamlit as st
import hashlib
import os
import tempfile
import logging
import json
from datetime import datetime
from pathlib import Path
from shapely.geometry import mapping
from admin_auth import is_admin
from navigation_tracker import track_user_action

logger = logging.getLogger(__name__)

MAX_AOI_FILE_SIZE_MB = 1
MAX_AOI_FILE_SIZE_BYTES = MAX_AOI_FILE_SIZE_MB * 1024 * 1024

MAX_VERTICES_WARNING = 30000
MAX_VERTICES_ERROR = 50000


# ============================================================================
# CENTERED OVERLAY HELPERS
# ============================================================================
def _show_upload_overlay(message="Uploading, please wait..."):
    overlay_html = f"""
    <div id="upload-overlay" style="
        position: fixed;
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        background: rgba(0,0,0,0.75);
        backdrop-filter: blur(4px);
        z-index: 9999;
        display: flex;
        justify-content: center;
        align-items: center;
        font-family: system-ui, sans-serif;
    ">
        <div style="
            background: #1e1e2e;
            border-radius: 16px;
            padding: 32px 48px;
            text-align: center;
            border: 1px solid #2ecc71;
            box-shadow: 0 8px 32px rgba(0,0,0,0.3);
        ">
            <div style="font-size: 48px; margin-bottom: 20px;">⏳</div>
            <div style="color: white; font-size: 18px; margin-bottom: 16px;">{message}</div>
            <div style="display: inline-block; width: 20px; height: 20px; border: 2px solid #2ecc71; border-top-color: transparent; border-radius: 50%; animation: spin 0.8s linear infinite;"></div>
        </div>
    </div>
    <style>
        @keyframes spin {{
            to {{ transform: rotate(360deg); }}
        }}
    </style>
    """
    overlay_placeholder = st.empty()
    overlay_placeholder.markdown(overlay_html, unsafe_allow_html=True)
    return overlay_placeholder

def _hide_overlay(placeholder):
    if placeholder is not None:
        placeholder.empty()


# ============================================================================
# AOI HANDLING FUNCTIONS
# ============================================================================
def compute_zoom_from_bounds(bounds, zoom_offset=2):
    import math
    min_lon, min_lat, max_lon, max_lat = bounds
    width_deg = max_lon - min_lon
    height_deg = max_lat - min_lat
    if width_deg <= 0 or height_deg <= 0:
        return 10
    max_dim_deg = max(width_deg, height_deg)
    zoom = math.log2(360 / max_dim_deg)
    zoom = int(zoom) + zoom_offset
    zoom = max(3, min(15, zoom))
    return zoom

def zoom_to_aoi(aoi, zoom_offset=2):
    if aoi is not None and not aoi.is_empty:
        bounds = aoi.bounds
        new_zoom = compute_zoom_from_bounds(bounds, zoom_offset=zoom_offset)
        st.session_state.map_center = [aoi.centroid.y, aoi.centroid.x]
        st.session_state.map_zoom = new_zoom
        st.session_state.map_key = st.session_state.get('map_key', 0) + 1
        logger.info(f"Zoom to AOI: center=({aoi.centroid.y:.2f}, {aoi.centroid.x:.2f}), zoom={new_zoom}")

def simplify_aoi(aoi, tolerance_degrees=0.02):
    from shapely.geometry import Polygon
    if aoi is None or aoi.is_empty:
        return aoi
    simplified = aoi.simplify(tolerance_degrees, preserve_topology=True)
    if simplified.is_empty or not isinstance(simplified, Polygon):
        return aoi
    if simplified.geom_type == 'MultiPolygon':
        from shapely.geometry import MultiPolygon
        largest = max(simplified.geoms, key=lambda p: p.area)
        return largest
    return simplified

def count_vertices(geometry):
    if geometry is None or geometry.is_empty:
        return 0
    if geometry.geom_type == 'Polygon':
        return len(geometry.exterior.coords)
    elif geometry.geom_type == 'MultiPolygon':
        count = 0
        for poly in geometry.geoms:
            count += len(poly.exterior.coords)
        return count
    return 0

def track_aoi_selection(aoi_type, source, geometry, country=None, area=None, ip=None, session_id=None):
    aoi_dir = Path("aoi_history")
    aoi_dir.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    filename = aoi_dir / f"aoi_{timestamp}.json"
    if session_id is None:
        session_id = st.session_state.get('session_id', 'unknown')
    aoi_data = {
        "timestamp": datetime.now().isoformat(),
        "user_id": session_id,
        "type": aoi_type,
        "source": source,
        "country": country,
        "area_km2": area,
        "geometry": geometry,
        "ip": ip or st.session_state.get('user_ip', 'unknown')
    }
    try:
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(aoi_data, f, indent=2, default=str)
    except Exception as e:
        logger.error(f"Failed to track AOI: {e}")

# ============================================================================
# handle_aoi_upload – returns True on success, False on failure
# ============================================================================
def handle_aoi_upload(uploaded_file, aoi_handler):
    from shapely.geometry import Polygon, MultiPolygon
    
    # --- File size validation ---
    file_bytes = uploaded_file.getvalue()
    file_size_mb = len(file_bytes) / (1024 * 1024)
    if file_size_mb > MAX_AOI_FILE_SIZE_MB:
        st.error(
            f"❌ File too large: {file_size_mb:.1f} MB. "
            f"Maximum allowed: {MAX_AOI_FILE_SIZE_MB} MB."
        )
        logger.warning(f"[AOI Upload] Rejected oversized file: {uploaded_file.name} ({file_size_mb:.1f} MB)")
        return False
    
    # --- Extension validation ---
    allowed_extensions = {'.geojson', '.json', '.kml', '.kmz', '.gpkg', '.shp', '.zip'}
    suffix = os.path.splitext(uploaded_file.name)[1].lower()
    if suffix not in allowed_extensions:
        st.error(
            f"❌ Unsupported file format: '{suffix}'. "
            f"Allowed: {', '.join(sorted(allowed_extensions))}"
        )
        logger.warning(f"[AOI Upload] Rejected unsupported format: {uploaded_file.name} ({suffix})")
        return False
    
    overlay = _show_upload_overlay("Processing AOI file, please wait...")
    
    try:
        logger.info(f"[AOI Upload] Processing {uploaded_file.name} ({file_size_mb:.2f} MB)")
        file_hash = hashlib.md5(file_bytes).hexdigest()
        if st.session_state.get('uploaded_file_hash') == file_hash:
            logger.info("[AOI Upload] Duplicate file, already loaded – consider success")
            return True
        st.session_state.uploaded_file_hash = file_hash
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(file_bytes)
            tmp_path = tmp.name
        try:
            aoi = aoi_handler.load_from_filepath(tmp_path)
            if not aoi:
                st.error(f"❌ Failed to load AOI from {uploaded_file.name}")
                return False
            if isinstance(aoi, MultiPolygon):
                largest_polygon = max(aoi.geoms, key=lambda p: p.area)
                aoi = largest_polygon
            if not isinstance(aoi, Polygon):
                st.error(f"❌ Unsupported geometry type: {type(aoi)}. Please use a single polygon.")
                return False
            vertex_count = count_vertices(aoi)
            if vertex_count > MAX_VERTICES_ERROR:
                return _handle_complex_aoi(aoi, vertex_count, uploaded_file.name)
            elif vertex_count > MAX_VERTICES_WARNING:
                return _handle_warning_aoi(aoi, vertex_count, uploaded_file.name)
            else:
                result = _save_aoi(aoi, vertex_count, uploaded_file.name)
                logger.info(f"[AOI Upload] _save_aoi returned {result}")
                return result
        finally:
            os.unlink(tmp_path)
    finally:
        _hide_overlay(overlay)

# ----------------------------------------------------------------------------
# Helper sub-functions for saving / handling complex AOIs
# ----------------------------------------------------------------------------
def _save_aoi(aoi, vertex_count, filename):
    from data.aoi_handler import AOIHandler
    from shapely.geometry import mapping
    st.session_state.aoi = aoi
    st.session_state.passes = []
    st.session_state.opportunities = []
    st.session_state.displayed_passes = []
    st.session_state.tasking_results = None
    st.session_state.country_selected = None
    st.session_state.country_select_key_counter = st.session_state.get('country_select_key_counter', 0) + 1

    try:
        area_value, area_unit = AOIHandler.calculate_area(aoi)
        st.success(f"✅ AOI loaded from {filename}")
        st.info(f"📐 Area: {area_value:,.2f} {area_unit} | Vertices: {vertex_count}")
    except Exception:
        logger.warning(f"Could not calculate area for AOI from {filename}")
        st.success(f"✅ AOI loaded from {filename} ({vertex_count} vertices)")
    try:
        track_aoi_selection(
            aoi_type="Polygon",
            source="upload",
            geometry=mapping(aoi),
            area=aoi.area
        )
    except Exception as e:
        logger.error(f"Failed to track AOI: {e}")
    zoom_to_aoi(aoi)
    # DO NOT call st.rerun() – the form will handle the rerun
    return True

def _handle_warning_aoi(aoi, vertex_count, filename):
    st.warning(f"⚠️ Your AOI has {vertex_count} vertices. For better performance, consider simplifying it.")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("🔄 Simplify AOI", key="simplify_warning_btn"):
            with st.spinner("Simplifying AOI..."):
                simplified = simplify_aoi(aoi, tolerance_degrees=0.02)
                new_count = count_vertices(simplified)
                st.session_state.aoi = simplified
                st.session_state.passes = []
                st.session_state.opportunities = []
                st.session_state.displayed_passes = []
                st.session_state.tasking_results = None
                st.success(f"✅ AOI simplified from {vertex_count} to {new_count} vertices")
                zoom_to_aoi(simplified)
                return True
    with col2:
        if st.button("Keep original", key="keep_original_warning_btn"):
            st.session_state.aoi = aoi
            st.session_state.passes = []
            st.session_state.opportunities = []
            st.session_state.displayed_passes = []
            st.session_state.tasking_results = None
            zoom_to_aoi(aoi)
            return True
    return False

def _handle_complex_aoi(aoi, vertex_count, filename):
    st.error(f"⚠️ Your AOI is very complex with {vertex_count} vertices. This may cause performance issues.")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("🔄 Simplify AOI", key="simplify_error_btn"):
            with st.spinner("Simplifying AOI..."):
                simplified = simplify_aoi(aoi, tolerance_degrees=0.05)
                new_count = count_vertices(simplified)
                st.session_state.aoi = simplified
                st.session_state.passes = []
                st.session_state.opportunities = []
                st.session_state.displayed_passes = []
                st.session_state.tasking_results = None
                st.success(f"✅ AOI simplified from {vertex_count} to {new_count} vertices")
                zoom_to_aoi(simplified)
                return True
    with col2:
        if st.button("Use original AOI", key="use_original_error_btn"):
            st.session_state.aoi = aoi
            st.session_state.passes = []
            st.session_state.opportunities = []
            st.session_state.displayed_passes = []
            st.session_state.tasking_results = None
            st.warning(f"⚠️ Using original AOI with {vertex_count} vertices. Map performance may be affected.")
            zoom_to_aoi(aoi)
            return True
    return False


# ============================================================================
# RENDER FUNCTION FOR SIDEBAR (legacy, not used)
# ============================================================================
def render_aoi_upload_section(aoi_handler):
    pass