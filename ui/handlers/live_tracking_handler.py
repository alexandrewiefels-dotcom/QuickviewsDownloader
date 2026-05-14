# ui/handlers/live_tracking_handler.py – No session state assignment conflicts

import streamlit as st
import logging
from datetime import datetime, timedelta, timezone
from skyfield.api import EarthSatellite
from geometry.utils import normalize_longitude

logger = logging.getLogger(__name__)


def render_live_tracking_sidebar(satellites_db):
    # Build unique satellites list
    satellite_list = []
    for category in satellites_db.values():
        for sat_name, sat_info in category.items():
            satellite_list.append((sat_name, sat_info["norad"], sat_info))
    
    unique_sats = {}
    for name, norad, info in satellite_list:
        if norad not in unique_sats:
            unique_sats[norad] = (name, info)
    
    sat_options = [f"{name} (NORAD {norad})" for norad, (name, info) in unique_sats.items()]

    st.sidebar.markdown("### 🛰️ Live Satellite Tracking")
    
    # Time mode radio (outside form)
    time_mode = st.sidebar.radio(
        "Time mode",
        ["Current time", "Manual range"],
        index=0 if st.session_state.get('live_time_mode', 'Current time') == 'Current time' else 1,
        key="live_time_mode",
        horizontal=True
    )
    
    # Form for all other controls
    with st.sidebar.form(key="live_tracking_form"):
        selected_sats = st.multiselect(
            "Select satellites to track",
            options=sat_options,
            default=st.session_state.get('live_selected_sats', []),
            key="live_sat_selector_form"
        )
        
        if time_mode == "Current time":
            track_hours = st.slider(
                "Track length (hours)",
                min_value=1, max_value=48,
                value=st.session_state.get('track_hours', 12),
                step=1,
                help="How many hours of past orbit to display. The satellite icon appears at the current time."
            )
            manual_start = None
            manual_end = None
        else:
            start_default = st.session_state.get('live_manual_start', datetime.now(timezone.utc))
            end_default = st.session_state.get('live_manual_end', datetime.now(timezone.utc) + timedelta(hours=12))
            col1, col2 = st.columns(2)
            with col1:
                manual_start = st.datetime_input("Start time (UTC)", value=start_default, key="live_start_input")
            with col2:
                manual_end = st.datetime_input("End time (UTC)", value=end_default, key="live_end_input")
            if manual_start and manual_end and manual_end < manual_start:
                st.error("End time must be after start time.")
            track_hours = None
        
        submitted = st.form_submit_button("🔄 Refresh satellite positions", type="primary", use_container_width=True)
    
    # Custom satellite adder (outside form)
    with st.sidebar.expander("➕ Add custom satellite (NORAD) to track", expanded=False):
        norad_live = st.text_input("NORAD ID", key="live_custom_norad")
        name_live = st.text_input("Satellite name (optional)", key="live_custom_name")
        if st.button("Add to tracking", key="add_live_custom"):
            if norad_live.strip().isdigit():
                norad = int(norad_live.strip())
                name = name_live.strip() if name_live.strip() else f"Custom-{norad}"
                from config.satellites import add_custom_satellite
                cameras = {"User camera": {"swath_km": 15.0, "resolution_m": 0.5}}
                add_custom_satellite(norad, name, cameras=cameras)
                st.success(f"✅ Satellite {name} (NORAD {norad}) added. Please select it above.")
                st.rerun()
            else:
                st.error("Invalid NORAD ID")
    
    if submitted:
        live_satellites = []
        for sat_str in selected_sats:
            norad = int(sat_str.split("NORAD ")[1].rstrip(")"))
            name = sat_str.split(" (NORAD")[0]
            info = unique_sats[norad][1]
            live_satellites.append({'norad': norad, 'name': name, 'info': info})
        
        st.session_state.live_selected_sats = selected_sats
        st.session_state.live_satellites = live_satellites
        
        if time_mode == "Current time":
            end_time = datetime.now(timezone.utc)
            start_time = end_time - timedelta(hours=track_hours)
            st.session_state.track_hours = track_hours
        else:
            start_time = manual_start.replace(tzinfo=timezone.utc) if manual_start else datetime.now(timezone.utc)
            end_time = manual_end.replace(tzinfo=timezone.utc) if manual_end else datetime.now(timezone.utc)
            # Store for later use – these keys are NOT used as widget keys (widget keys are live_start_input, live_end_input)
            st.session_state.live_manual_start = start_time
            st.session_state.live_manual_end = end_time
        
        st.session_state.live_tracking_start = start_time
        st.session_state.live_tracking_end = end_time
        st.session_state.live_tracking_mode = time_mode
        st.session_state.refresh_triggered = True
        st.rerun()
    
    # Logs display
    st.sidebar.markdown("### 📋 Logs")
    if st.session_state.get('live_tracking_log'):
        st.sidebar.info(st.session_state.live_tracking_log)
    else:
        st.sidebar.info("Select satellites and click Refresh to start tracking.")


# ============================================================================
# Core update functions (unchanged, safe)
# ============================================================================

def update_live_positions(tle_fetcher, ts, start_time, end_time, live_sats):
    """Update live satellite positions and tracks using explicit start and end times."""
    new_positions = {}
    new_tracks = {}
    
    total_seconds = (end_time - start_time).total_seconds()
    total_hours = total_seconds / 3600
    if total_hours > 24:
        step_minutes = 1.5
    elif total_hours > 12:
        step_minutes = 1.0
    else:
        step_minutes = 1.0
    
    for sat in live_sats:
        norad = sat['norad']
        name = sat['name']
        tle = tle_fetcher.fetch(norad)
        
        if not tle:
            logger.warning(f"TLE not found for {name} (NORAD {norad})")
            continue
        
        try:
            # Position at end_time (icon)
            sat_obj = EarthSatellite(tle[0], tle[1], f"SAT{norad}", ts)
            t_end = ts.from_datetime(end_time)
            geocentric = sat_obj.at(t_end)
            subpoint = geocentric.subpoint()
            lat = subpoint.latitude.degrees
            lon = subpoint.longitude.degrees
            alt = subpoint.elevation.km
            lon = normalize_longitude(lon)
            new_positions[norad] = (lat, lon, alt, end_time)
            
            # Track from start to end
            raw_track = tle_fetcher.compute_track(norad, tle, start_time, end_time, step_minutes=step_minutes)
            processed = []
            for p in raw_track:
                if len(p) >= 2:
                    lat_pt, lon_pt = p[0], p[1]
                    lon_pt = normalize_longitude(lon_pt)
                    processed.append((lat_pt, lon_pt))
            
            if len(processed) >= 2:
                new_tracks[norad] = processed
                logger.info(f"[Live Track] {name}: {len(processed)} points, {total_hours:.1f}h, step={step_minutes}min")
            else:
                new_tracks[norad] = []
                logger.warning(f"[Live Track] No valid track points for {name}")
        except Exception as e:
            logger.error(f"Error updating {name}: {e}")
    
    return new_positions, new_tracks


def handle_live_tracking_refresh(tle_fetcher, ts):
    """Handle the refresh action (called from main.py) – does NOT change map view."""
    from admin_auth import is_admin
    from navigation_tracker import track_user_action
    
    if is_admin():
        track_user_action("live_tracking_refresh_clicked", {
            "satellites_count": len(st.session_state.get('live_satellites', [])),
            "mode": st.session_state.get('live_tracking_mode', 'Unknown')
        })
    
    start_time = st.session_state.get('live_tracking_start')
    end_time = st.session_state.get('live_tracking_end')
    live_sats = st.session_state.get('live_satellites', [])
    
    if not start_time or not end_time:
        end_time = datetime.now(timezone.utc)
        start_time = end_time - timedelta(hours=12)
    
    if live_sats:
        with st.spinner(f"Updating {len(live_sats)} satellite positions..."):
            new_positions, new_tracks = update_live_positions(
                tle_fetcher, ts, start_time, end_time, live_sats
            )
            st.session_state.live_sat_positions = new_positions
            st.session_state.live_sat_tracks = new_tracks
            
            if new_tracks and len(new_positions) > 0:
                # Do NOT change map center/zoom – keep user's current view
                # Just increment map key to force a redraw (optional)
                st.session_state.map_key = st.session_state.get('map_key', 0) + 1
                st.success(f"✅ Updated {len(live_sats)} satellites")
            else:
                st.warning("⚠️ No track data generated. Check TLE availability.")
    else:
        st.info("📡 No satellites selected for tracking.")
        st.session_state.live_sat_positions = {}
        st.session_state.live_sat_tracks = {}
    
    st.session_state.refresh_triggered = False
    st.rerun()