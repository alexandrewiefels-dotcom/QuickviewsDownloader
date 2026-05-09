# core/state_manager.py - OPTIMIZED with lazy loading
import streamlit as st
from datetime import date, timedelta, datetime, timezone
from skyfield.api import load
import hashlib
import uuid


def init_session_state():
    """Initialize all session state variables with lazy loading"""
    
    # Core state - NO widget keys here!
    if 'ts' not in st.session_state:
        st.session_state.ts = load.timescale()
    
    if 'session_id' not in st.session_state:
        st.session_state.session_id = str(uuid.uuid4())[:8]
    
    if 'user_ip' not in st.session_state:
        st.session_state.user_ip = "unknown"
    
    if 'country' not in st.session_state:
        st.session_state.country = "unknown"
    
    # AOI state
    if 'aoi' not in st.session_state:
        st.session_state.aoi = None
    
    if 'map_center' not in st.session_state:
        st.session_state.map_center = [30, 0]
    
    if 'map_zoom' not in st.session_state:
        st.session_state.map_zoom = 2
    
    if 'map_key' not in st.session_state:
        st.session_state.map_key = 0
    
    if 'last_drawing_hash' not in st.session_state:
        st.session_state.last_drawing_hash = ""
    
    # Date range state
    if 'start_date' not in st.session_state:
        st.session_state.start_date = date.today() + timedelta(days=1)
    
    if 'end_date' not in st.session_state:
        st.session_state.end_date = date.today() + timedelta(days=3)
    
    # Filter state
    if 'max_ona' not in st.session_state:
        st.session_state.max_ona = 15.0
    
    if 'min_ona' not in st.session_state:
        st.session_state.min_ona = 0.0

    if 'orbit_filter' not in st.session_state:
        st.session_state.orbit_filter = "Descending"
    
    if 'daylight_filter' not in st.session_state:
        st.session_state.daylight_filter = "Daylight only (9am - 3pm local time)"
    
    # Previous values for tracking changes
    if 'previous_orbit_filter' not in st.session_state:
        st.session_state.previous_orbit_filter = "Descending"
    
    if 'previous_max_ona' not in st.session_state:
        st.session_state.previous_max_ona = 15.0
    
    if 'previous_daylight_filter' not in st.session_state:
        st.session_state.previous_daylight_filter = "Daylight only (9am - 3pm local time)"
    
    # Satellite selection state
    if 'camera_states' not in st.session_state:
        st.session_state.camera_states = {}
    
    if 'selected_configs' not in st.session_state:
        st.session_state.selected_configs = []
    
    # Results state
    if 'passes' not in st.session_state:
        st.session_state.passes = []
    
    if 'opportunities' not in st.session_state:
        st.session_state.opportunities = []
    
    if 'displayed_passes' not in st.session_state:
        st.session_state.displayed_passes = []
    
    if 'tasking_results' not in st.session_state:
        st.session_state.tasking_results = None
    
    if 'highlighted_pass_id' not in st.session_state:
        st.session_state.highlighted_pass_id = None
    
    # Processing state
    if 'processing' not in st.session_state:
        st.session_state.processing = False
    
    if 'run_detection' not in st.session_state:
        st.session_state.run_detection = False
    
    if 'search_triggered' not in st.session_state:
        st.session_state.search_triggered = False
    
    if 'search_performed' not in st.session_state:
        st.session_state.search_performed = False
    
    if 'tasking_requested' not in st.session_state:
        st.session_state.tasking_requested = False
    
    # Live tracking state
    if 'live_satellites' not in st.session_state:
        st.session_state.live_satellites = []
    
    if 'live_sat_positions' not in st.session_state:
        st.session_state.live_sat_positions = {}
    
    if 'live_sat_tracks' not in st.session_state:
        st.session_state.live_sat_tracks = {}
    
    if 'refresh_triggered' not in st.session_state:
        st.session_state.refresh_triggered = False
    
    if 'time_mode' not in st.session_state:
        st.session_state.time_mode = "Current time"
    
    if 'manual_time' not in st.session_state:
        st.session_state.manual_time = datetime.now(timezone.utc)
    
    # NEW: Track length for live tracking
    if 'track_hours' not in st.session_state:
        st.session_state.track_hours = 12
    
    if 'build_track' not in st.session_state:
        st.session_state.build_track = True
    
    # Drag and drop state
    if 'pending_drag_pass_id' not in st.session_state:
        st.session_state.pending_drag_pass_id = None
    
    if 'drag_click_position' not in st.session_state:
        st.session_state.drag_click_position = None
    
    # UI state
    if 'show_faq' not in st.session_state:
        st.session_state.show_faq = False
    
    if 'show_contact' not in st.session_state:
        st.session_state.show_contact = False
    
    if 'show_howto' not in st.session_state:
        st.session_state.show_howto = False
    
    if 'sidebar_tab' not in st.session_state:
        st.session_state.sidebar_tab = "📅 Pass Prediction"
    
    # Upload state
    if 'reset_upload_key' not in st.session_state:
        st.session_state.reset_upload_key = 0
    
    if 'uploaded_file_hash' not in st.session_state:
        st.session_state.uploaded_file_hash = None
    
    if 'country_selected' not in st.session_state:
        st.session_state.country_selected = None
    
    # Weather state
    if 'weather_api_exhausted' not in st.session_state:
        st.session_state.weather_api_exhausted = False
    
    # NEW: Flag to indicate AOI was just drawn (to override country selection)
    if 'aoi_just_drawn' not in st.session_state:
        st.session_state.aoi_just_drawn = False

    #Add counter
    if 'country_select_key_counter' not in st.session_state:
        st.session_state.country_select_key_counter = 0
    
    # Minimum coverage and clipping margin
    if 'min_coverage' not in st.session_state:
        st.session_state.min_coverage = 0.0
    if 'clip_margin_deg' not in st.session_state:
        st.session_state.clip_margin_deg = 10.0

