# main.py - Complete with min ONA, min coverage, adjustable clipping margin

import streamlit as st
import sys
import traceback
import hashlib
import json
import time
import math
import threading
from datetime import datetime, timedelta
from pathlib import Path
from skyfield.api import load
from shapely.geometry import Polygon
from streamlit.runtime.scriptrunner import add_script_run_ctx

# UI components
from ui.components.popup import render_how_it_works_popup
from ui.components.footer import render_footer, render_acknowledgments
from ui.components.map_controls import render_zoom_to_aoi_button, compute_zoom
from ui.sidebar import render_sidebar
from ui.pages.faq import render_faq_page
from ui.pages.contact import render_contact_page
from ui.handlers.live_tracking_handler import handle_live_tracking_refresh

# Core functionality
from config.satellites import SATELLITES
from data.tle_fetcher import TLEFetcher, get_tle_fetcher, CACHE_FILE, save_last_refresh, get_pending_missing_norads, background_download_missing
from data.aoi_handler import AOIHandler
from detection.pass_detector import PassDetector
from visualization.map_renderer import MapRenderer
from core.state_manager import init_session_state
from core.pass_runner import run_pass_detection
from core.tasking_runner import run_tasking
from geometry.calculations import great_circle_distance, calculate_bearing
from navigation_tracker import init_navigation_tracker, track_page_view, track_user_action, save_search_result, get_user_ip, get_user_country
from config.satellites import get_satellite_count
from navigation_tracker import cleanup_old_logs

# TLE management
from prefetch_all_tles import (
    is_cache_populated, 
    prefetch_all_tles_silent,
    background_refresh_if_needed
)

# PDF export configuration
from visualization.pdf_exporter import PDFExporter

# SASClouds integration
from sasclouds_search_logic import run_search as sc_run_search, render_results_table as sc_render_results_table

import os
os.environ['STREAMLIT_SERVER_MAX_UPLOAD_SIZE'] = '5'

# ============================================================================
# Simple overlay helper functions
# ============================================================================
def show_progress_overlay():
    overlay = st.empty()
    overlay_css = """
    <style>
    .progress-overlay {
        position: fixed;
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        background: rgba(0,0,0,0.7);
        backdrop-filter: blur(4px);
        z-index: 9999;
        display: flex;
        justify-content: center;
        align-items: center;
        pointer-events: none;
        font-family: system-ui, -apple-system, sans-serif;
    }
    .progress-card {
        background: #1e1e2e;
        border-radius: 16px;
        padding: 24px 32px;
        min-width: 300px;
        text-align: center;
        border: 1px solid #2ecc71;
        box-shadow: 0 8px 32px rgba(0,0,0,0.3);
    }
    .progress-message {
        color: white;
        margin-bottom: 16px;
        font-size: 16px;
    }
    .progress-bar-container {
        width: 100%;
        height: 8px;
        background: #333;
        border-radius: 4px;
        overflow: hidden;
        margin: 16px 0;
    }
    .progress-bar {
        height: 100%;
        background: #2ecc71;
        width: 0%;
        transition: width 0.2s ease;
        border-radius: 4px;
    }
    .progress-widget {
        display: inline-block;
        width: 20px;
        height: 20px;
        border: 2px solid #2ecc71;
        border-top-color: transparent;
        border-radius: 50%;
        animation: spin 0.8s linear infinite;
        margin-right: 8px;
        vertical-align: middle;
    }
    @keyframes spin {
        to { transform: rotate(360deg); }
    }
    .progress-time {
        font-size: 12px;
        color: #aaa;
        margin-top: 12px;
    }
    </style>
    """
    st.markdown(overlay_css, unsafe_allow_html=True)
    
    start_time = datetime.now()
    
    def update(progress: int, message: str):
        elapsed = (datetime.now() - start_time).total_seconds()
        html = f"""
        <div class="progress-overlay">
            <div class="progress-card">
                <div class="progress-message">
                    <span class="progress-widget"></span> {message}
                </div>
                <div class="progress-bar-container">
                    <div class="progress-bar" style="width: {progress}%;"></div>
                </div>
                <div class="progress-time">⏱️ {elapsed:.0f} sec</div>
            </div>
        </div>
        """
        overlay.markdown(html, unsafe_allow_html=True)
    
    return overlay, update

def clear_progress_overlay(container):
    if container is not None:
        container.empty()

# ============================================================================
# PDF EXPORT CONFIGURATION
# ============================================================================
PDFExporter.set_map_size(width_inch=10.0, height_inch=7.0)
PDFExporter.set_map_padding(padding=0.3)

# ============================================================================
# TLE MANAGEMENT FUNCTIONS (unchanged)
# ============================================================================
def ensure_tle_cache_populated():
    """
    Ensure TLE cache is populated on first run.
    Uses total satellite count to decide if cache is complete.
    If less than 50% of satellites have valid TLEs, trigger a full Space‑Track download.
    """
    total_satellites = get_satellite_count()
    fetcher = get_tle_fetcher()
    valid_tles = 0
    for norad in fetcher.tles:
        if fetcher._is_valid_tle(fetcher.tles[norad]):
            valid_tles += 1

    # If less than half of the satellites have valid TLEs, start background download
    if valid_tles < total_satellites * 0.5:
        print(f"[TLE] Cache has {valid_tles}/{total_satellites} valid TLEs – starting background full download (Space‑Track primary)")
        def download_in_background():
            try:
                print("[TLE] Starting background force download (Space‑Track bulk for all NORADs)...")
                from force_download_tles import force_download_all_tls
                force_download_all_tls()   # No cooldown, uses Space‑Track first
                print("[TLE] Background force download complete")
            except Exception as e:
                print(f"[TLE] Background force download error: {e}")
        thread = threading.Thread(target=download_in_background, daemon=True)
        thread.start()
        return True
    return False

def handle_map_drawing(map_data, current_aoi, all_passes):
    from shapely.geometry import Polygon, Point
    import hashlib
    import json

    if not map_data or not map_data.get("last_active_drawing"):
        return None, False

    drawing = map_data["last_active_drawing"]
    if not drawing or drawing.get("geometry", {}).get("type") != "Polygon":
        return None, False

    coords = drawing["geometry"]["coordinates"][0]
    drawing_str = json.dumps(coords, sort_keys=True)
    drawing_hash = hashlib.md5(drawing_str.encode()).hexdigest()

    if st.session_state.last_drawing_hash == drawing_hash:
        return None, False

    st.session_state.last_drawing_hash = drawing_hash
    new_aoi = Polygon(coords)

    # Check if drawn polygon is actually a footprint
    is_footprint = False
    for p in all_passes:
        fp = getattr(p, 'display_footprint', None) or getattr(p, 'footprint', None)
        if fp is None or fp.is_empty:
            continue

        area_diff = abs(fp.area - new_aoi.area) / max(fp.area, 1e-6)
        centroid_dist = fp.centroid.distance(new_aoi.centroid)
        intersection_area = fp.intersection(new_aoi).area
        overlap_ratio = intersection_area / max(fp.area, new_aoi.area, 1e-6)

        if area_diff < 0.05 and centroid_dist < 0.01 and overlap_ratio > 0.9:
            is_footprint = True
            break

    if is_footprint:
        st.info("🛰️ Clicked on a satellite footprint. Use the drawing tool to define a new AOI, or click the Zoom button.")
        return None, False

    if current_aoi is not None and current_aoi.equals_exact(new_aoi, 0.0001):
        return None, False

    return new_aoi, True

def show_upload_overlay(message="Uploading, please wait..."):
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

def hide_overlay(placeholder):
    if placeholder is not None:
        placeholder.empty()
        
def check_and_download_missing_tles():
    missing = get_pending_missing_norads()
    if missing:
        print(f"[Main] {len(missing)} NORADs used generated TLEs. Downloading in background...")
        thread = threading.Thread(target=background_download_missing, daemon=True)
        thread.start()

def check_tle_freshness_and_update():
    fetcher = get_tle_fetcher()
    age_hours = fetcher.get_cache_age_hours()
    total_satellites = get_satellite_count()
    valid_tles = 0
    for norad in fetcher.tles:
        if fetcher._is_valid_tle(fetcher.tles[norad]):
            valid_tles += 1

    if age_hours >= 48 or valid_tles < total_satellites:
        print(f"[TLE Check] Triggering update: age={age_hours:.1f}h, valid={valid_tles}/{total_satellites}")
        def download_in_background():
            try:
                from force_download_tles import force_download_all_tls
                force_download_all_tls()
                print("[TLE Check] Background download complete")
            except Exception as e:
                print(f"[TLE Check] Background download error: {e}")
        thread = threading.Thread(target=download_in_background, daemon=True)
        thread.start()
        return True
    else:
        print(f"[TLE Check] Cache OK: age={age_hours:.1f}h, valid={valid_tles}/{total_satellites}")
        return False

def show_spinner(message):
    spinner_html = f"""
    <div style="position: fixed; top: 50%; left: 50%; transform: translate(-50%, -50%);
                background: rgba(0,0,0,0.7); color: white; padding: 20px; border-radius: 10px;
                z-index: 1000; text-align: center;">
        <div style="font-size: 24px;">⏳</div>
        <div>{message}</div>
    </div>
    """
    return st.markdown(spinner_html, unsafe_allow_html=True)

def handle_drag_drop(detector, aoi):
    if not st.session_state.get('pending_drag_pass_id') or not st.session_state.get('drag_click_position'):
        return False

    pass_id = st.session_state.pending_drag_pass_id
    click_lat, click_lon = st.session_state.drag_click_position
    aoi_centroid = aoi.centroid

    for p in st.session_state.passes:
        if p.id == pass_id and hasattr(p, 'tasked_footprint') and p.tasked_footprint:
            track_user_action("drag_drop_start", {"pass_id": pass_id, "satellite": p.satellite_name})
            
            perp_bearing = (p.track_azimuth + 90) % 360
            dist_km = great_circle_distance(aoi_centroid.y, aoi_centroid.x, click_lat, click_lon)
            bearing_click = calculate_bearing(aoi_centroid.y, aoi_centroid.x, click_lat, click_lon)
            diff = (bearing_click - perp_bearing + 360) % 360
            if diff > 180:
                diff -= 360
            new_offset = dist_km * math.cos(math.radians(diff))
            max_shift_km = detector.ground_range_from_ona(550.0, st.session_state.max_ona)
            new_offset = max(-max_shift_km, min(max_shift_km, new_offset))
            shift = p.original_offset_km - new_offset
            required_ona = detector.ona_from_distance(550.0, abs(shift))
            
            if required_ona > st.session_state.max_ona + 0.1:
                st.warning(f"Cannot move {p.satellite_name}: required ONA {required_ona:.1f}° exceeds max {st.session_state.max_ona}°")
                break

            track_coords = list(p.ground_track.coords)
            new_footprint = detector.create_shifted_footprint_from_coords(track_coords, p.swath_km, shift)
            if new_footprint and not new_footprint.is_empty:
                p.tasked_footprint = new_footprint
                p.tasked_ona = required_ona
                p.current_offset_km = new_offset
                p.display_footprint = new_footprint
                if st.session_state.tasking_results:
                    for r in st.session_state.tasking_results:
                        if r['id'] == p.id:
                            r['footprint'] = new_footprint
                            r['required_ona'] = required_ona
                            r['offset_km'] = shift
                            r['y_center'] = new_offset
                            break
                st.success(f"Moved {p.satellite_name} to offset {new_offset:.1f} km (ONA: {required_ona:.1f}°)")
                st.session_state.map_key += 1
            else:
                st.error("Failed to create shifted footprint")
            break

    st.session_state.pending_drag_pass_id = None
    st.session_state.drag_click_position = None
    return True

# ============================================================================
# Main App
# ============================================================================
try:
    print("Starting main.py")
    st.set_page_config(
        layout="wide", 
        page_title="OrbitShow", 
        page_icon="🛰️", 
        initial_sidebar_state="expanded",
        menu_items={'Get Help': None, 'Report a bug': None, 'About': None}
    )

    init_navigation_tracker()
    cleanup_old_logs(max_age_hours=48)
    track_page_view("main", {"app_start": True})
    
    st.markdown("""
    <style>
    .stApp header { display: none !important; }
    section[data-testid="stSidebarNav"] { display: none !important; }
    .main > div { padding-top: 0rem !important; }
    .stProgress > div > div > div > div { background-color: #2ecc71 !important; }
    .leaflet-tooltip {
        background-color: rgba(0,0,0,0.85) !important;
        color: white !important;
        font-family: monospace !important;
        font-size: 11px !important;
        border: 1px solid #2ecc71 !important;
        border-radius: 5px !important;
        padding: 8px !important;
        max-width: 280px !important;
    }
    div[data-testid="stDialog"] {
        background: linear-gradient(135deg, #1a2a4a 0%, #0f1a2e 100%);
        border: 1px solid #2ecc71;
        border-radius: 20px;
    }
    </style>
    """, unsafe_allow_html=True)

    print("Imports successful")

    try:
        ts = load.timescale()
        st.session_state.ts = ts
    except Exception as e:
        print(f"Error loading timescale: {e}")
        ts = load.timescale()
        st.session_state.ts = ts

    def main():
        init_session_state()
        
        st.toast("🔄 Updating... Please wait", icon="⏳")

        ensure_tle_cache_populated()
        background_refresh_if_needed()
        
        if not is_cache_populated():
            threading.Thread(target=prefetch_all_tles_silent, daemon=True).start()
        
        if st.session_state.get("show_faq", False):
            render_faq_page()
            if st.button("← Back to Main App", key="back_from_faq_main"):
                st.session_state.show_faq = False
                st.rerun()
            return
        
        if st.session_state.get("show_contact", False):
            render_contact_page()
            if st.button("← Back to Main App", key="back_from_contact_main"):
                st.session_state.show_contact = False
                st.rerun()
            return
        
        if st.session_state.get("show_howto", False):
            render_how_it_works_popup()
        
        tle_fetcher = TLEFetcher()
        ts = st.session_state.ts
        aoi_handler = AOIHandler()
        detector = PassDetector(tle_fetcher, ts, coarse_step=1.0, fine_step=0.5)
        detector.window_merge_gap_minutes = 2
        map_renderer = MapRenderer()
        
        selected_configs = render_sidebar(SATELLITES, aoi_handler)
        if selected_configs is None:
            selected_configs = []

        # ── SASClouds: run search when sidebar triggers it ─────────────────────
        _sc_pending = st.session_state.pop("sc_pending_search", None)
        if _sc_pending:
            _sc_log = st.empty()
            sc_run_search(
                polygon_geojson    = _sc_pending["polygon_geojson"],
                aoi_filename       = "OrbitShow AOI",
                start_date         = _sc_pending["start_date"],
                end_date           = _sc_pending["end_date"],
                max_cloud          = _sc_pending["max_cloud"],
                selected_satellites= _sc_pending["selected_satellites"],
                session_id         = st.session_state.get("session_id", "main"),
                log_container      = _sc_log,
                state_prefix       = "sc",
            )
            _sc_log.empty()
            st.rerun()

        if st.session_state.get('refresh_triggered', False):
            handle_live_tracking_refresh(tle_fetcher, ts)
        
        center = st.session_state.get('map_center', [30, 0])
        zoom = st.session_state.get('map_zoom', 2)
        aoi = st.session_state.get('aoi')
        
        # ========== TASKING ==========
        if st.session_state.get('tasking_requested', False) and st.session_state.get('displayed_passes') and aoi is not None:
            track_user_action("tasking_started", {"passes_count": len(st.session_state.displayed_passes)})
            
            overlay_container, update_progress = show_progress_overlay()
            
            tasking_mode = "one_coverage"
            overlap_km = 0.0
            print(f"[Main] Tasking mode: {tasking_mode}, Overlap: {overlap_km} km")
            
            tasking_results = None
            
            def detection_progress_callback(progress, message):
                update_progress(progress, message)
            
            with st.spinner("Simulating tasking..."):
                from core.tasking_runner import run_tasking
                tasking_results = run_tasking(
                    st.session_state.displayed_passes, aoi, st.session_state.max_ona,
                    detector, sat_alt_km=550.0,
                    fetch_weather=True,
                    mode=tasking_mode,
                    overlap_km=overlap_km
                )
            
            clear_progress_overlay(overlay_container)
            
            if tasking_results:
                print(f"[Main] Tasking complete: {len(tasking_results)} results")
                tasked_map = {}
                for r in tasking_results:
                    tasked_map[r.get('id')] = r
                
                for p in st.session_state.passes:
                    if p.id in tasked_map:
                        r = tasked_map[p.id]
                        if r.get('footprint') and not r['footprint'].is_empty:
                            p.tasked_footprint = r['footprint']
                            p.display_footprint = r['footprint']
                            p.tasked_ona = r.get('required_ona')
                            p.current_offset_km = r.get('offset_km', 0)
                            p.y_center = r.get('y_center', 0)
                            p.is_central = r.get('is_central', False)
                            p.coverage_pct = r.get('coverage_pct', 0)
                            print(f"[Main] Updated pass {p.satellite_name} with tasked footprint")
                
                for p in st.session_state.displayed_passes:
                    if p.id in tasked_map:
                        r = tasked_map[p.id]
                        if r.get('footprint') and not r['footprint'].is_empty:
                            p.tasked_footprint = r['footprint']
                            p.display_footprint = r['footprint']
                            p.tasked_ona = r.get('required_ona')
                            p.current_offset_km = r.get('offset_km', 0)
                            p.y_center = r.get('y_center', 0)
                            p.is_central = r.get('is_central', False)
                            p.coverage_pct = r.get('coverage_pct', 0)
                
                st.session_state.tasking_results = tasking_results
                st.session_state.highlighted_pass_id = None
                st.session_state.map_key = st.session_state.get('map_key', 0) + 1
                
                if aoi:
                    bounds = aoi.bounds
                    new_zoom = compute_zoom(bounds)
                    st.session_state.map_center = [aoi.centroid.y, aoi.centroid.x]
                    st.session_state.map_zoom = new_zoom
                
                st.success(f"✅ Tasking complete! {len(tasking_results)} passes tasked")
            
            st.session_state.tasking_requested = False
            st.rerun()
        
        if st.session_state.get('pending_drag_pass_id') and aoi is not None:
            if handle_drag_drop(detector, aoi):
                st.rerun()
        
        live_satellites_list = []
        for norad, (lat, lon, alt, sat_time) in st.session_state.get('live_sat_positions', {}).items():
            sat_info = next((s for s in st.session_state.get('live_satellites', []) if s['norad'] == norad), None)
            if sat_info:
                live_satellites_list.append({
                    'norad': norad,
                    'name': sat_info['name'],
                    'info': sat_info['info'],
                    'lat': lat, 'lon': lon, 'alt': alt,
                    'time': sat_time,
                    'track': st.session_state.get('live_sat_tracks', {}).get(norad, [])
                })
        
        if st.session_state.get('tasking_results'):
            passes_to_display = []
            for p in st.session_state.passes:
                if hasattr(p, 'tasked_footprint') and p.tasked_footprint is not None:
                    p.display_footprint = p.tasked_footprint
                    passes_to_display.append(p)
                elif hasattr(p, 'display_footprint') and p.display_footprint is not None:
                    passes_to_display.append(p)
                elif p.footprint is not None:
                    passes_to_display.append(p)
            print(f"[Main] Displaying {len(passes_to_display)} tasked passes on map")
            show_tracks = False
        else:
            passes_to_display = st.session_state.get('displayed_passes', [])
            show_tracks = True
            print(f"[Main] Displaying {len(passes_to_display)} regular passes on map")
        
        highlighted_pass_id = st.session_state.get('highlighted_pass_id')
        
        sat_names = list(set([sat_name for (_, sat_name, _, _, _) in selected_configs]))
        filters = {
            "Dates": f"{st.session_state.start_date} → {st.session_state.end_date}",
            "Max ONA (Filter)": f"{st.session_state.max_ona}°",
            "Orbit direction": st.session_state.get('orbit_filter', 'Both'),
            "Satellites": ", ".join(sat_names) if len(sat_names) <= 3 else f"{len(sat_names)} satellites"
        }
        # Add min ONA to filter display
        min_ona_val = st.session_state.get('min_ona', 0.0)
        if min_ona_val > 0:
            filters["Min ONA"] = f"{min_ona_val}°"
        
        selected_satellite_names = []
        if st.session_state.get('selected_configs'):
            for (_, sat_name, _, _, _) in st.session_state.selected_configs:
                if sat_name not in selected_satellite_names:
                    selected_satellite_names.append(sat_name)
        
        col_zoom, col_progress = st.columns([1, 4])
        with col_zoom:
            render_zoom_to_aoi_button(aoi)
        with col_progress:
            progress_placeholder = st.empty()
        
        # ── Gather SASClouds data for map overlay ─────────────────────────────
        _sc_features_map = st.session_state.get("sc_features_map")
        _sc_dl           = st.session_state.get("sc_features_download") or []
        _sc_preview_idx  = st.session_state.get("sc_preview_indices") or set()
        # Quickview images are only passed to the renderer when the user has
        # explicitly chosen "Quickview" display mode in the SASClouds sidebar.
        _sc_display_mode = st.session_state.get("sc_display_mode", "Footprints")
        if _sc_display_mode == "Quickview":
            _sc_preview = [_sc_dl[i] for i in sorted(_sc_preview_idx) if 0 <= i < len(_sc_dl)]
        else:
            _sc_preview = []

        map_data = map_renderer.render(
            center=center, zoom=zoom, aoi=aoi,
            passes=passes_to_display,
            opportunities=st.session_state.get('opportunities', []),
            map_key=st.session_state.map_key,
            height=700,
            live_satellites=live_satellites_list,
            show_tracks=show_tracks,
            highlighted_pass_id=highlighted_pass_id,
            filters=filters,
            selected_satellites=selected_satellite_names,
            sasclouds_features=_sc_features_map,
            sasclouds_preview_scenes=_sc_preview,
        )
        
        # Handle AOI drawing
        if map_data and map_data.get("last_active_drawing"):
            drawing = map_data["last_active_drawing"]
            if drawing and drawing.get("geometry") and drawing["geometry"]["type"] == "Polygon":
                coords = drawing["geometry"]["coordinates"][0]
                drawing_str = json.dumps(coords, sort_keys=True)
                drawing_hash = hashlib.md5(drawing_str.encode()).hexdigest()
                if st.session_state.last_drawing_hash != drawing_hash:
                    st.session_state.last_drawing_hash = drawing_hash
                    new_aoi, aoi_changed = handle_map_drawing(map_data, st.session_state.aoi, st.session_state.passes)
                    if aoi_changed and new_aoi is not None:
                        track_user_action("aoi_drawn", {"area": new_aoi.area})
                        st.session_state.aoi = new_aoi
                        st.session_state.map_center = [new_aoi.centroid.y, new_aoi.centroid.x]
                        st.session_state.passes = []
                        st.session_state.opportunities = []
                        st.session_state.displayed_passes = []
                        st.session_state.tasking_results = None
                        st.session_state.tasking_requested = False
                        st.session_state.highlighted_pass_id = None
                        st.session_state.country_selected = None
                        st.session_state.country_select_key_counter = st.session_state.get('country_select_key_counter', 0) + 1
                        st.session_state.aoi_just_drawn = True
                        st.rerun()
        
        # ========== PASS DETECTION ==========
        if st.session_state.get('run_detection', False) and not st.session_state.get('processing', False):
            print("[DEBUG] Starting pass detection...")
            check_tle_freshness_and_update()
            st.session_state.processing = True
            st.session_state.run_detection = False
            st.rerun()
        
        if st.session_state.get('processing', False):
            print("[DEBUG] Processing detection...")
            if aoi is None:
                st.error("❌ Please load an Area of Interest (AOI) via the sidebar or by drawing on the map.")
                st.session_state.processing = False
                st.rerun()
            elif not selected_configs:
                st.error("❌ Please select at least one satellite and camera in the sidebar.")
                st.session_state.processing = False
                st.rerun()
            else:
                st.session_state.tasking_results = None
                st.session_state.highlighted_pass_id = None
                
                overlay_container, update_progress = show_progress_overlay()
                
                def detection_progress_callback(progress, message):
                    update_progress(progress, message)
                
                progress_bar = progress_placeholder.progress(0, text="Initialization...")
                start_time = time.time()
                
                all_passes = run_pass_detection(
                    detector, selected_configs, aoi, ts,
                    st.session_state.start_date, st.session_state.end_date,
                    st.session_state.max_ona,
                    progress_bar=progress_bar, start_time=start_time,
                    fetch_weather=False,
                    progress_callback=detection_progress_callback
                )
                progress_bar.empty()
                clear_progress_overlay(overlay_container)
                
                st.session_state.passes = all_passes
                st.session_state.opportunities = []
                
                # ========== NEW: Apply minimum AOI coverage filter ==========
                min_cov = st.session_state.get('min_coverage', 0.0)
                if min_cov > 0 and aoi and aoi.area > 0:
                    coverage_filtered = []
                    for p in all_passes:
                        if p.footprint and not p.footprint.is_empty:
                            try:
                                intersection = p.footprint.intersection(aoi)
                                coverage_pct = (intersection.area / aoi.area) * 100
                                if coverage_pct >= min_cov:
                                    coverage_filtered.append(p)
                            except Exception:
                                coverage_filtered.append(p)
                        else:
                            coverage_filtered.append(p)
                    all_passes = coverage_filtered
                    print(f"[Main] Kept {len(all_passes)} passes with coverage >= {min_cov}%")
                
                # ========== NEW: Apply ONA range filter (min and max) ==========
                min_ona_filter = st.session_state.get('min_ona', 0.0)
                max_ona_filter = st.session_state.max_ona
                if min_ona_filter > 0 or max_ona_filter < 45:
                    ona_filtered = []
                    for p in all_passes:
                        if min_ona_filter <= p.min_ona <= max_ona_filter:
                            ona_filtered.append(p)
                    all_passes = ona_filtered
                    print(f"[Main] Kept {len(all_passes)} passes with ONA between {min_ona_filter}° and {max_ona_filter}°")
                
                check_and_download_missing_tles()
                
                orbit_filter = st.session_state.get('orbit_filter', 'Both')
                if orbit_filter != 'Both':
                    filtered_passes = [p for p in all_passes if p.orbit_direction == orbit_filter]
                else:
                    filtered_passes = all_passes
                
                if not filtered_passes:
                    if all_passes:
                        message = f"No passes found with orbit direction '{orbit_filter}'."
                        if st.session_state.daylight_filter != "All times":
                            message += f" Also, the daylight filter '{st.session_state.daylight_filter}' removed passes with local solar time outside 9:00–15:00."
                            message += " Try changing the 'Pass time filter' to 'All times' in the sidebar."
                        st.warning(message)
                    else:
                        st.warning("No passes found. Try adjusting the date range, max ONA, or selecting different satellites.")
                
                st.session_state.displayed_passes = filtered_passes
                st.session_state.processing = False
                st.session_state.map_key += 1
                
                if filtered_passes:
                    save_search_result(
                        session_id=st.session_state.session_id,
                        ip=get_user_ip(),
                        country=get_user_country(),
                        aoi=aoi,
                        selected_sats=[(cat, name, cam) for (cat, name, cam, _, _) in selected_configs],
                        filters={
                            "start_date": st.session_state.start_date.isoformat(),
                            "end_date": st.session_state.end_date.isoformat(),
                            "max_ona": st.session_state.max_ona,
                            "min_ona": min_ona_filter,
                            "orbit_filter": st.session_state.orbit_filter,
                            "daylight_filter": st.session_state.daylight_filter
                        },
                        passes=filtered_passes,
                        tasking_results=None
                    )
                
                print(f"[DEBUG] Displaying {len(filtered_passes)} passes, rerunning...")
                st.rerun()
        
        # ========== REAPPLY FILTERS WHEN CHANGED ==========
        if st.session_state.get('filters_changed', False) and st.session_state.get('passes'):
            print("[DEBUG] Reapplying filters to existing passes...")
            all_passes = st.session_state.passes
            orbit_filter = st.session_state.orbit_filter
            daylight_filter = st.session_state.daylight_filter
            max_ona = st.session_state.max_ona
            min_ona = st.session_state.get('min_ona', 0.0)

            if orbit_filter != 'Both':
                filtered = [p for p in all_passes if p.orbit_direction == orbit_filter]
            else:
                filtered = all_passes

            # Apply ONA range filter (min and max)
            filtered = [p for p in filtered if min_ona <= p.min_ona <= max_ona]

            if daylight_filter == "Daylight only (9am - 3pm local time)":
                from detection.daylight_filter import filter_daylight_passes
                filtered = filter_daylight_passes(filtered, aoi)

            st.session_state.displayed_passes = filtered
            st.session_state.filters_changed = False
            st.rerun()
        
        # Results tables
        if st.session_state.get('tasking_results'):
            from ui.tasking_table import render_tasking_table
            render_tasking_table(st.session_state.tasking_results, aoi)
        elif st.session_state.get('displayed_passes'):
            from ui.results_table import render_passes_table, render_passes_summary
            max_ona = st.session_state.get('max_ona', 15)
            min_ona = st.session_state.get('min_ona', 0)
            filtered_passes = [p for p in st.session_state.displayed_passes if min_ona <= p.min_ona <= max_ona]
            if filtered_passes:
                render_passes_summary(filtered_passes, aoi)
                render_passes_table(filtered_passes, aoi, st.session_state.get('weather_api_exhausted', False))
            else:
                st.info(f"No passes with actual ONA between {min_ona}° and {max_ona}°. Try adjusting the ONA range.")
        
        # ── SASClouds results table ────────────────────────────────────────────
        if st.session_state.get("sc_scenes"):
            st.divider()
            with st.expander(
                f"🗄️ SASClouds Archive — {len(st.session_state['sc_scenes'])} scenes",
                expanded=True,
            ):
                sc_render_results_table(state_prefix="sc")

        render_footer()
        render_acknowledgments()
    
    if __name__ == "__main__":
        main()

except Exception as e:
    print("Fatal error in main.py :")
    traceback.print_exc()
    st.error(f"Error: {e}")