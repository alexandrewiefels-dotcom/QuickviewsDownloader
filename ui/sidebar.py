# ui/sidebar.py - Dynamic grouping: per-camera mode for uniform series, per-satellite for non-uniform
# Uses resolution_m, cameras dict, and intelligent merging.

import streamlit as st
import os
import logging
from datetime import date, timedelta
from admin_auth import is_admin
from navigation_tracker import track_user_action, display_navigation_info_sidebar
from pathlib import Path
from ui.components.map_controls import compute_zoom

# Import handlers
from ui.handlers.aoi_handler import handle_aoi_upload
from ui.handlers.live_tracking_handler import render_live_tracking_sidebar

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def _filter_satellite_cameras(sat_info):
    """
    For optical satellites, keep only the Panchromatic camera.
    For other types (SAR, etc.), keep all cameras.
    Returns a new dictionary with the filtered cameras.
    """
    sat_type = sat_info.get("type", "")
    if "Optical" in sat_type:
        cameras = sat_info.get("cameras", {})
        # Find the camera whose name contains 'Panchromatic' (case-insensitive)
        pan_cam = None
        for cam_name, cam_info in cameras.items():
            if "panchromatic" in cam_name.lower():
                pan_cam = (cam_name, cam_info)
                break
        if pan_cam:
            filtered_cameras = {pan_cam[0]: pan_cam[1]}
        else:
            # Fallback: keep all cameras (should not happen)
            filtered_cameras = cameras
        filtered = sat_info.copy()
        filtered["cameras"] = filtered_cameras
        return filtered
    else:
        # Non-optical: keep original
        return sat_info
    
def render_sidebar(satellites_db, aoi_handler):
    """Main sidebar renderer - returns selected_configs"""
    
    # CSS styles for sidebar
    st.sidebar.markdown("""
    <style>
    section[data-testid="stSidebar"] .block-container {
        padding-top: 0.5rem;
        padding-bottom: 0.5rem;
        padding-left: 0.8rem;
        padding-right: 0.8rem;
        overflow-y: auto;
        max-height: 100vh;
    }
    .stButton button { margin-bottom: 0.1rem !important; }
    .stCheckbox { margin-bottom: 0.05rem !important; }
    .streamlit-expanderHeader { font-size: 0.85rem; padding: 0.1rem 0.3rem; }
    .sidebar-logo { display: flex; align-items: center; margin-bottom: 0.5rem; }
    .sidebar-logo span { font-size: 1.2rem; font-weight: bold; color: #F8FBFF; }
    div[data-testid="stSlider"] label,
    div[data-testid="stSlider"] div[data-testid="stMarkdownContainer"] p {
        color: #F8FBFF !important;
    }
    .custom-upload-limit {
        font-size: 0.7rem;
        color: #888;
        margin-top: -5px;
        margin-bottom: 10px;
        padding: 4px 8px;
        background-color: rgba(255,255,255,0.05);
        border-radius: 4px;
    }
    </style>
    """, unsafe_allow_html=True)

    # Logo in sidebar
    logo_path = os.path.join(BASE_DIR, "logo_orbitshow.jpg")
    if os.path.exists(logo_path):
        try:
            st.sidebar.image(logo_path, width='stretch')
        except:
            st.sidebar.markdown('<div class="sidebar-logo"><span>🛰️ OrbitShow</span><br><small>Satellite passes prediction</small></div>', unsafe_allow_html=True)
    else:
        st.sidebar.markdown('<div class="sidebar-logo"><span>🛰️ OrbitShow</span><br><small>Satellite passes prediction</small></div>', unsafe_allow_html=True)

    # ── Dark mode (permanently dark) ──
    st.sidebar.markdown("""
    <style>
    .stApp { background-color: #0e1117; color: #fafafa; }
    section[data-testid="stSidebar"] { background-color: #1e1e2e; }
    </style>
    """, unsafe_allow_html=True)
    
    # ── Shared AOI Section (available in ALL tools) ──
    _render_shared_aoi_section(aoi_handler)
    
    # Tab selection in sidebar
    tab = st.sidebar.radio(
        "Select tool",
        ["📅 Pass Prediction", "🛰️ Live Tracking", "🗄️ SASClouds"],
        index=0,
        key="sidebar_tab_select"
    )

    if tab == "📅 Pass Prediction":
        return _render_pass_prediction_tab(satellites_db, aoi_handler)
    elif tab == "🛰️ Live Tracking":
        return _render_live_tracking_tab(satellites_db)
    else:
        _render_sasclouds_tab()
        return []


# ============================================================================
# Shared AOI Section — available in ALL tools (Pass Prediction, Live Tracking, SASClouds)
# ============================================================================

def _render_shared_aoi_section(aoi_handler):
    """
    Render AOI import, country selection, and status display.
    This section is shown above the tab selector so it's available in all tools.
    The AOI is stored in st.session_state.aoi and shared across all tools.
    """
    st.sidebar.markdown("### 🌍 Area of Interest")
    
    # Show current AOI status
    aoi = st.session_state.get("aoi")
    if aoi is not None and not aoi.is_empty:
        country = st.session_state.get("country_selected")
        if country:
            st.sidebar.success(f"✅ AOI set: **{country}**")
        else:
            area_km2 = aoi.area * 111.32 * 111.32  # rough deg² to km²
            st.sidebar.success(f"✅ AOI loaded ({area_km2:.0f} km²)")
    else:
        st.sidebar.info("ℹ️ No AOI set. Upload a file, select a country, or draw on the map.")
    
    # AOI upload (outside any form, so it works in all tabs)
    with st.sidebar.expander("📁 Import AOI file", expanded=False):
        st.markdown("""
        <div class="custom-upload-limit">
            📁 <strong>Supported:</strong> KML, GeoJSON, ZIP (Shapefile)<br>
            ⚠️ <strong>Max size:</strong> 1 MB
        </div>
        """, unsafe_allow_html=True)
        
        upload_key = f"shared_aoi_upload_{st.session_state.get('reset_upload_key', 0)}"
        uploaded_file = st.file_uploader(
            "Choose AOI file",
            type=["kml", "geojson", "zip"],
            key=upload_key,
            label_visibility="collapsed",
            help="Upload a KML, GeoJSON, or ZIP (Shapefile) to set the Area of Interest"
        )
        
        if uploaded_file:
            # handle_aoi_upload already detects duplicates via file hash
            # Do NOT call st.rerun() here to avoid infinite loop
            success = handle_aoi_upload(uploaded_file, aoi_handler)
            if success:
                st.success("✅ AOI loaded successfully!")
                st.session_state.passes = []
                st.session_state.displayed_passes = []
                st.session_state.tasking_results = None
            else:
                st.error("❌ Failed to load AOI. Check the file format.")
    
    # Country selector (outside any form)
    with st.sidebar.expander("🌐 Select country", expanded=False):
        _render_country_selector_sidebar_shared()
    
    # Clear AOI button
    if aoi is not None and not aoi.is_empty:
        if st.sidebar.button("🗑️ Clear AOI", key="clear_aoi_btn", use_container_width=True):
            st.session_state.aoi = None
            st.session_state.country_selected = None
            st.session_state.passes = []
            st.session_state.displayed_passes = []
            st.session_state.tasking_results = None
            st.session_state.map_key = st.session_state.get('map_key', 0) + 1
            st.rerun()
    
    st.sidebar.markdown("<hr>", unsafe_allow_html=True)


def _render_country_selector_sidebar_shared():
    """Country selector that immediately applies the selected country as AOI."""
    import geopandas as gpd
    from pathlib import Path
    from ui.components.map_controls import compute_zoom
    
    @st.cache_data
    def load_country_geojson():
        base_dir = Path(__file__).parent.parent
        possible_names = ["world_countries.geojson", "world_countries.GeoJSON", "ne_110m_admin_0_countries.geojson"]
        for name in possible_names:
            path = base_dir / "data" / name
            if path.exists():
                try:
                    gdf = gpd.read_file(path)
                    name_col = None
                    for col in ['CNTRY_NAME', 'NAME', 'name', 'ADMIN', 'SOVEREIGNT']:
                        if col in gdf.columns:
                            name_col = col
                            break
                    if name_col:
                        gdf = gdf[[name_col, 'geometry']].rename(columns={name_col: 'country'})
                        gdf = gdf.to_crs('EPSG:4326')
                        return gdf, sorted(gdf['country'].unique())
                except Exception:
                    continue
        return None, None
    
    gdf, countries = load_country_geojson()
    if gdf is None:
        st.info("Country data not available")
        return
    
    selected_country = st.selectbox(
        "Select a country",
        countries,
        index=None,
        placeholder="Choose a country...",
        key="shared_country_select",
        label_visibility="collapsed"
    )
    
    if selected_country:
        # Only apply if the country actually changed (prevents infinite rerun loop)
        if st.session_state.get("country_selected") != selected_country:
            country_poly = gdf[gdf['country'] == selected_country].geometry.iloc[0]
            st.session_state.aoi = country_poly
            st.session_state.map_center = [country_poly.centroid.y, country_poly.centroid.x]
            st.session_state.map_zoom = compute_zoom(country_poly.bounds)
            st.session_state.map_key = st.session_state.get('map_key', 0) + 1
            st.session_state.country_selected = selected_country
            # Only clear pass prediction state — do NOT touch SASClouds state
            st.session_state.passes = []
            st.session_state.displayed_passes = []
            st.session_state.tasking_results = None
            st.success(f"✅ AOI set to **{selected_country}**")
            # Use a deferred rerun flag instead of calling st.rerun() directly,
            # so the current tab state is preserved across the rerun.
            st.session_state["_deferred_rerun"] = True


# ============================================================================
# Helper functions for deferred AOI and country selection (used inside Pass Prediction form)
# ============================================================================

def _render_country_selector_sidebar_form():
    """Country selector that returns the selected country name without immediate effect."""
    import geopandas as gpd
    from pathlib import Path
    
    @st.cache_data
    def load_country_geojson():
        base_dir = Path(__file__).parent.parent
        possible_names = ["world_countries.geojson", "world_countries.GeoJSON", "ne_110m_admin_0_countries.geojson"]
        for name in possible_names:
            path = base_dir / "data" / name
            if path.exists():
                try:
                    gdf = gpd.read_file(path)
                    name_col = None
                    for col in ['CNTRY_NAME', 'NAME', 'name', 'ADMIN', 'SOVEREIGNT']:
                        if col in gdf.columns:
                            name_col = col
                            break
                    if name_col:
                        gdf = gdf[[name_col, 'geometry']].rename(columns={name_col: 'country'})
                        gdf = gdf.to_crs('EPSG:4326')
                        return gdf, name_col, sorted(gdf['country'].unique())
                except Exception:
                    continue
        return None, None, None
    
    gdf, _, countries = load_country_geojson()
    if gdf is None:
        return None
    
    selected_country = st.selectbox("Select a country", countries, index=None,
                                    placeholder="Choose a country...",
                                    key="country_select_form")
    return selected_country


def _apply_country_aoi(selected_country):
    """Apply a country polygon as the AOI (called only on form submit)."""
    import geopandas as gpd
    from pathlib import Path
    from ui.components.map_controls import compute_zoom
    
    @st.cache_data
    def load_country_geojson():
        base_dir = Path(__file__).parent.parent
        possible_names = ["world_countries.geojson", "world_countries.GeoJSON", "ne_110m_admin_0_countries.geojson"]
        for name in possible_names:
            path = base_dir / "data" / name
            if path.exists():
                try:
                    gdf = gpd.read_file(path)
                    name_col = None
                    for col in ['CNTRY_NAME', 'NAME', 'name', 'ADMIN', 'SOVEREIGNT']:
                        if col in gdf.columns:
                            name_col = col
                            break
                    if name_col:
                        gdf = gdf[[name_col, 'geometry']].rename(columns={name_col: 'country'})
                        gdf = gdf.to_crs('EPSG:4326')
                        return gdf
                except Exception:
                    continue
        return None
    
    gdf = load_country_geojson()
    if gdf is not None:
        country_poly = gdf[gdf['country'] == selected_country].geometry.iloc[0]
        st.session_state.aoi = country_poly
        st.session_state.map_center = [country_poly.centroid.y, country_poly.centroid.x]
        st.session_state.map_zoom = compute_zoom(country_poly.bounds)
        st.session_state.map_key = st.session_state.get('map_key', 0) + 1
        st.session_state.country_selected = selected_country
        st.session_state.passes = []
        st.session_state.displayed_passes = []
        st.session_state.tasking_results = None


# ============================================================================
# Helper: check if all satellites in a series have identical camera specs
# ============================================================================

def _are_cameras_identical(satellites_list):
    """
    satellites_list: list of tuples (category_name, sat_name, sat_info)
    Returns True if all satellites have exactly the same camera dict (keys + swath/resolution).
    """
    if len(satellites_list) <= 1:
        return True
    first_cameras = satellites_list[0][2]["cameras"]
    # Normalize: extract the tuple of (cam_name, resolution, swath) for each camera
    def normalize(cams):
        return tuple(sorted((name, info.get("resolution_m", info.get("resolution", 0)),
                             info.get("swath_km", 0)) for name, info in cams.items()))
    first_norm = normalize(first_cameras)
    for _, _, sat_info in satellites_list[1:]:
        if normalize(sat_info["cameras"]) != first_norm:
            return False
    return True


# ============================================================================
# Satellite selector – dynamic grouping: per-mode for uniform, per-sat for non-uniform
# ============================================================================

def _render_satellite_selector_sidebar(satellites_db):
    """
    Renders checkboxes grouped by provider and series.
    If all satellites in the series have identical camera specs:
        - Shows one checkbox per camera mode, selecting that mode for ALL satellites in the series.
    Otherwise:
        - Shows each satellite with its own per‑camera checkboxes.
    Returns a dictionary of selected keys (mode keys or camera keys).
    """
    # Build provider -> series -> list of satellites
    providers = {}
    for category_name, category in satellites_db.items():
        for sat_name, sat_info in category.items():
            provider = sat_info.get("provider", "Unknown")
            series = sat_info.get("series", "Other")
            if not isinstance(series, str):
                series = str(series)
            filtered_sat_info = _filter_satellite_cameras(sat_info)
            providers.setdefault(provider, {}).setdefault(series, []).append((category_name, sat_name, filtered_sat_info))
    
    selected = {}  # key -> bool
    st.markdown("### Satellite Selection")
    
    # Track all keys for select-all/deselect-all per provider
    _all_keys = []
    
    for provider, series_dict in providers.items():
        with st.expander(f"{provider}", expanded=False):
            # ── Select All / Deselect All for this provider ──
            provider_keys = []
            for series, satellites in series_dict.items():
                uniform = _are_cameras_identical(satellites)
                if uniform:
                    sample_cameras = satellites[0][2]["cameras"]
                    for cam_name in sample_cameras:
                        key = f"mode_{provider}_{series}_{cam_name}".replace(" ", "_")
                        provider_keys.append(key)
                else:
                    for (_, sat_name, sat_info) in satellites:
                        for cam_name in sat_info["cameras"]:
                            key = f"cam_{provider}_{series}_{sat_name}_{cam_name}".replace(" ", "_")
                            provider_keys.append(key)
            
            _all_keys.extend(provider_keys)
            
            # Render Select All / Deselect All buttons
            # NOTE: Must use form_submit_button because this is inside a st.form()
            col_sa, col_da = st.columns([1, 1])
            with col_sa:
                if st.form_submit_button(f"✅ Select all", key=f"sel_all_{provider}", use_container_width=True):
                    for k in provider_keys:
                        st.session_state[k] = True
                    st.rerun()
            with col_da:
                if st.form_submit_button(f"❌ Deselect all", key=f"desel_all_{provider}", use_container_width=True):
                    for k in provider_keys:
                        st.session_state[k] = False
                    st.rerun()
            
            for series, satellites in series_dict.items():
                # Determine if series is uniform
                uniform = _are_cameras_identical(satellites)
                
                # ---- Series info popover (always present) ----
                col1, col2 = st.columns([0.9, 0.1])
                with col1:
                    st.markdown(f"**{series}**")
                with col2:
                    with st.popover("ℹ️", use_container_width=True):
                        sat_count = len(satellites)
                        st.markdown(f"**{series}**")
                        st.markdown(f"Satellites: {sat_count}")
                        sample_sat = satellites[0][2]
                        st.markdown(f"Type: {sample_sat['type']}")
                        st.markdown(f"Provider: {provider}")
                        st.markdown("**Camera modes:**")
                        for cname, cinfo in sample_sat["cameras"].items():
                            c_res = cinfo.get("resolution_m", cinfo.get("resolution", "?"))
                            c_swath = cinfo.get("swath_km", "?")
                            st.markdown(f"- {cname}: {c_res}m / {c_swath}km")
                        norads = sorted([sat[2]["norad"] for sat in satellites])
                        norad_str = ', '.join(str(n) for n in norads[:5])
                        if len(norads) > 5:
                            norad_str += f" and {len(norads)-5} more"
                        st.markdown(f"NORAD IDs: {norad_str}")
                
                # ---- Selection UI ----
                if uniform:
                    # Uniform series: one checkbox per camera mode (applies to all satellites)
                    sample_cameras = satellites[0][2]["cameras"]
                    for cam_name, cam_info in sample_cameras.items():
                        res = cam_info.get("resolution_m", cam_info.get("resolution", 0.5))
                        swath = cam_info.get("swath_km", 0)
                        key = f"mode_{provider}_{series}_{cam_name}".replace(" ", "_")
                        label = f"🎯 {cam_name} ({res}m / {swath}km) — applies to all {len(satellites)} satellites"
                        checked = st.checkbox(label, key=key)
                        selected[key] = checked
                else:
                    # Non-uniform: per-satellite, per-camera checkboxes
                    for (category_name, sat_name, sat_info) in satellites:
                        st.markdown(f"&nbsp;&nbsp;📡 {sat_name}", unsafe_allow_html=True)
                        for cam_name, cam_info in sat_info["cameras"].items():
                            res = cam_info.get("resolution_m", cam_info.get("resolution", 0.5))
                            swath = cam_info.get("swath_km", 0)
                            key = f"cam_{provider}_{series}_{sat_name}_{cam_name}".replace(" ", "_")
                            col_cb, col_label = st.columns([0.1, 0.9])
                            with col_cb:
                                checked = st.checkbox(" ", key=key, label_visibility="collapsed")
                            with col_label:
                                st.markdown(f"&nbsp;&nbsp;&nbsp;&nbsp;🎯 {cam_name} ({res}m / {swath}km)")
                            selected[key] = checked
                st.markdown("---")  # separator between series
    return selected


# ============================================================================
# Custom satellite adder (outside form)
# ============================================================================

def _render_custom_satellite_adder_sidebar():
    """Render custom satellite addition form in sidebar – outside the main form."""
    with st.sidebar.expander("➕ Add custom satellite (NORAD)", expanded=False):
        norad_input = st.text_input("NORAD ID", key="custom_norad_input")
        sat_name_input = st.text_input("Satellite name (optional)", key="custom_name_input")
        col1, col2 = st.columns(2)
        with col1:
            swath_km = st.number_input("Swath (km)", min_value=1.0, value=15.0, step=1.0, key="custom_swath_input")
        with col2:
            resolution_m = st.number_input("Resolution (m)", min_value=0.1, value=0.5, step=0.1, key="custom_res_input")
        if st.button("Add satellite", key="add_custom_btn"):
            if norad_input.strip().isdigit():
                norad = int(norad_input.strip())
                name = sat_name_input.strip() if sat_name_input.strip() else f"Custom-{norad}"
                from config.satellites import add_custom_satellite
                cameras = {
                    "User camera": {
                        "swath_km": swath_km,
                        "resolution_m": resolution_m
                    }
                }
                add_custom_satellite(
                    norad=norad,
                    name=name,
                    cameras=cameras,
                    period_min=94.5,
                    inclination=97.5,
                    provider="User",
                    sat_type="Optical",
                    series="Custom"
                )
                from navigation_tracker import track_custom_satellite
                track_custom_satellite(norad, name, swath_km, resolution_m)
                st.success(f"✅ New satellite **{name}** (NORAD {norad}) added. Please select it below.")
                st.rerun()
            else:
                st.error("Invalid NORAD ID")


# ============================================================================
# Pass Prediction tab (all filters inside form, with error messages)
# ============================================================================

def _render_pass_prediction_tab(satellites_db, aoi_handler):
    """Render Pass Prediction tab – all filters deferred until 'Search passes' button."""
    
    if 'camera_states' not in st.session_state:
        st.session_state.camera_states = {}
    
    # ── Keyboard shortcut: Enter to submit search ──
    st.sidebar.markdown("""
    <script>
    document.addEventListener('keydown', function(e) {
        if (e.key === 'Enter' && !e.shiftKey && !e.ctrlKey && !e.metaKey) {
            // Find the search button and click it
            var buttons = document.querySelectorAll('button[kind="primary"]');
            for (var i = 0; i < buttons.length; i++) {
                if (buttons[i].innerText.includes('Search passes')) {
                    buttons[i].click();
                    break;
                }
            }
        }
    });
    </script>
    """, unsafe_allow_html=True)
    
    with st.sidebar.form(key="search_filters_form"):
        # AOI is now set via the shared section above (upload, country, or map drawing)
        # Only show a reminder if no AOI is set
        aoi = st.session_state.get("aoi")
        if aoi is None or aoi.is_empty:
            st.warning("⚠️ No AOI set. Use the section above to upload a file, select a country, or draw on the map.")
        else:
            country = st.session_state.get("country_selected")
            if country:
                st.info(f"📍 AOI: **{country}**")
            else:
                st.info(f"📍 AOI loaded ✓")
        
        st.markdown("<hr>", unsafe_allow_html=True)
        
        # --- Date range ---
        col1, col2 = st.columns(2)
        with col1:
            start_date = st.date_input(
                "Start date",
                value=st.session_state.get('start_date', date.today()),
                help="First day of the search window. Passes before this date will be excluded."
            )
        with col2:
            end_date = st.date_input(
                "End date",
                value=st.session_state.get('end_date', date.today() + timedelta(days=3)),
                help="Last day of the search window. Passes after this date will be excluded."
            )
        
        if start_date > end_date:
            st.error("Start date must be before or equal to end date.")
        
        # --- Filters ---
        orbit_filter = st.radio(
            "Orbit direction", 
            ["Both", "Ascending", "Descending"], 
            index=2 if st.session_state.get('orbit_filter', "Descending") == "Descending" 
                  else (0 if st.session_state.get('orbit_filter') == "Both" else 1),
            help="Filter passes by orbit direction. Ascending = south-to-north, Descending = north-to-south."
        )
        
        max_ona = st.slider(
            "Maximum off-nadir angle (°)", 
            0.0, 45.0, 
            value=st.session_state.get('max_ona', 15.0),
            step=1.0,
            help="Maximum allowed off-nadir angle. Higher values allow wider viewing angles but reduce image quality."
        )
        
        # NEW: Minimum ONA slider
        min_ona = st.slider(
            "Minimum off-nadir angle (°)",
            0.0, 45.0,
            value=st.session_state.get('min_ona', 0.0),
            step=1.0,
            help="Exclude passes with actual ONA below this value (useful for SAR to avoid very low ONA)."
        )
        
        if min_ona > max_ona:
            st.error("Minimum ONA cannot be greater than Maximum ONA.")
        
        daylight_filter = st.radio(
            "Pass time filter",
            ["All times", "Daylight only (9am - 3pm local time)"],
            index=1 if st.session_state.get('daylight_filter', "Daylight only (9am - 3pm local time)") == "Daylight only (9am - 3pm local time)" else 0,
            label_visibility="collapsed",
            help="Filter passes by local solar time. 'Daylight only' keeps passes between 9am and 3pm solar time."
        )
        
        ## ========== NEW: Minimum AOI coverage filter ==========
        #min_coverage = st.slider(
        #    "Minimum AOI coverage (%)",
        #    min_value=0.0,
        #    max_value=100.0,
        #    value=st.session_state.get('min_coverage', 0.0),
        #    step=5.0,
        #    help="Only show passes that cover at least this percentage of the AOI area."
        #)
        #
        ## ========== NEW: Map clipping margin (longitude) ==========
        #clip_margin_deg = st.slider(
        #    "Map clipping margin (degrees longitude)",
        #    min_value=1.0,
        #    max_value=30.0,
        #    value=st.session_state.get('clip_margin_deg', 10.0),
        #    step=1.0,
        #    help="Extends the visible area east/west of the AOI when clipping footprints on the map. Higher values show more of the footprint."
        #)
        
        st.markdown("<hr>", unsafe_allow_html=True)
        
        # ---------- SATELLITE SELECTION (dynamic grouping, filtered cameras) ----------
        selected_items = _render_satellite_selector_sidebar(satellites_db)
        
        # ---------- SEARCH SUBMIT BUTTON ----------
        submitted = st.form_submit_button("🔍 Search passes", type="primary", use_container_width=True)
        
        if submitted:
            error_occurred = False
            
            # Check if AOI is set (from shared section above)
            if st.session_state.aoi is None:
                st.sidebar.error("❌ Please load an Area of Interest (AOI) using the section above (upload a file, select a country, or draw on the map).")
                error_occurred = True
            
            # 2. Convert selected_items into selected_configs
            selected_configs = []
            # Rebuild the structure (same as in _render_satellite_selector_sidebar)
            providers = {}
            for category_name, category in satellites_db.items():
                for sat_name, sat_info in category.items():
                    provider = sat_info.get("provider", "Unknown")
                    series = sat_info.get("series", "Other")
                    if not isinstance(series, str):
                        series = str(series)
                    # Apply camera filter for optical satellites
                    filtered_sat_info = _filter_satellite_cameras(sat_info)
                    providers.setdefault(provider, {}).setdefault(series, []).append((category_name, sat_name, filtered_sat_info))
            
            for provider, series_dict in providers.items():
                for series, satellites in series_dict.items():
                    uniform = _are_cameras_identical(satellites)   # uses filtered cameras
                    
                    if uniform:
                        # Uniform series: one checkbox per camera mode, applies to all sats
                        # Use the first satellite's cameras (all identical)
                        sample_cameras = satellites[0][2]["cameras"]
                        for cam_name, cam_info in sample_cameras.items():
                            key = f"mode_{provider}_{series}_{cam_name}".replace(" ", "_")
                            if selected_items.get(key, False):
                                for (category_name, sat_name, sat_info) in satellites:
                                    cam_info_actual = sat_info["cameras"].get(cam_name)
                                    if cam_info_actual:
                                        selected_configs.append((category_name, sat_name, cam_name, cam_info_actual, sat_info))
                    else:
                        # Non-uniform: per-satellite per-camera checkboxes
                        for (category_name, sat_name, sat_info) in satellites:
                            for cam_name, cam_info in sat_info["cameras"].items():
                                key = f"cam_{provider}_{series}_{sat_name}_{cam_name}".replace(" ", "_")
                                if selected_items.get(key, False):
                                    selected_configs.append((category_name, sat_name, cam_name, cam_info, sat_info))
            
            st.session_state.selected_configs = selected_configs
            
            # 3. Check if any satellites are selected
            if not error_occurred and not st.session_state.selected_configs:
                st.sidebar.error("❌ Please select at least one satellite / tasking mode.")
                error_occurred = True
            
            # 4. If no errors, trigger detection
            if not error_occurred:
                st.session_state.start_date = start_date
                st.session_state.end_date = end_date
                st.session_state.orbit_filter = orbit_filter
                st.session_state.max_ona = max_ona
                st.session_state.min_ona = min_ona
                st.session_state.daylight_filter = daylight_filter
                #st.session_state.min_coverage = min_coverage
                #st.session_state.clip_margin_deg = clip_margin_deg
                st.session_state.run_detection = True
                st.session_state.search_performed = True
    
    # ========== OUTSIDE THE FORM ==========
    _render_custom_satellite_adder_sidebar()
    
    if st.sidebar.button("📋 Simulate Tasking", type="primary", use_container_width=True, key="simulate_tasking_btn"):
        if not st.session_state.get('search_performed', False) or not st.session_state.get('displayed_passes'):
            st.sidebar.error("❌ Please run a pass search first (click 'Search passes') before simulating tasking.")
        else:
            st.session_state.tasking_requested = True
            st.rerun()
    
    display_navigation_info_sidebar()
    return st.session_state.get('selected_configs', [])


# ============================================================================
# SASClouds Archive tab — satellites from the live SASClouds website,
# organised by sensor type (Optical / Hyperspectral / SAR).
# ============================================================================

# Lazy import to avoid polluting the sidebar module's startup time.
def _get_satellite_groups():
    from sasclouds_api_scraper import SATELLITE_GROUPS
    return SATELLITE_GROUPS


def _sat_label(entry: dict) -> str:
    """'GF7 | MUX, BWD, FWD'  or  'GF3'  for SAR with no sensor list."""
    sensors = entry.get("sensorIds") or []
    if sensors:
        return f"{entry['satelliteId']} | {', '.join(sensors)}"
    return entry["satelliteId"]


def _label_to_sat(label: str) -> dict:
    """Reverse of _sat_label — returns {satelliteId, sensorIds}."""
    if " | " in label:
        sid, sensors_str = label.split(" | ", 1)
        return {"satelliteId": sid.strip(),
                "sensorIds": [s.strip() for s in sensors_str.split(",")]}
    return {"satelliteId": label.strip(), "sensorIds": []}


def _render_sasclouds_tab():
    from shapely.geometry import mapping as _mapping

    st.sidebar.markdown("### 🗄️ SASClouds Archive")

    aoi = st.session_state.get("aoi")
    if aoi is not None and not aoi.is_empty:
        st.sidebar.caption("✅ AOI inherited from OrbitShow map")
    else:
        st.sidebar.info("ℹ️ No AOI set. You can still configure the search below — an AOI is required to search.")


    today = date.today()
    start = st.sidebar.date_input("Start date", value=today - timedelta(days=30), key="sc_start")
    end   = st.sidebar.date_input("End date",   value=today,                      key="sc_end")

    max_cloud = st.sidebar.slider("Max cloud cover %", 0, 100, 30, key="sc_cloud")

    # ── Satellite / camera selector — grouped by sensor type ──────────────
    groups = _get_satellite_groups()

    optical_entries = []
    for sats in groups.get("Optical", {}).values():
        optical_entries.extend(sats)
    optical_labels = [_sat_label(e) for e in optical_entries]

    hyper_entries = []
    for sats in groups.get("Hyperspectral", {}).values():
        hyper_entries.extend(sats)
    hyper_labels = [_sat_label(e) for e in hyper_entries]

    sar_entries = []
    for sats in groups.get("SAR", {}).values():
        sar_entries.extend(sats)
    sar_labels = [_sat_label(e) for e in sar_entries]

    st.sidebar.markdown("**Optical**")
    sel_optical = st.sidebar.multiselect(
        "Optical satellites", optical_labels,
        default=["GF1 | PMS", "GF2 | PMS", "BJ2 | PMS"],
        key="sc_sats_optical", label_visibility="collapsed",
    )

    st.sidebar.markdown("**Hyperspectral**")
    sel_hyper = st.sidebar.multiselect(
        "Hyperspectral satellites", hyper_labels,
        default=[], key="sc_sats_hyper", label_visibility="collapsed",
    )

    st.sidebar.markdown("**SAR**")
    sel_sar = st.sidebar.multiselect(
        "SAR satellites", sar_labels,
        default=[], key="sc_sats_sar", label_visibility="collapsed",
    )

    selected_satellites = [_label_to_sat(l) for l in sel_optical + sel_hyper + sel_sar]

    # ── Display mode ────────────────────────────────────────────────────────
    st.sidebar.markdown("**Map display**")
    display_mode = st.sidebar.radio(
        "Map display", ["Footprints", "Quickview"],
        horizontal=True, key="sc_display_mode", label_visibility="collapsed",
    )

    c1, c2 = st.sidebar.columns(2)
    do_search = c1.button("🔍 Search", type="primary", use_container_width=True, key="sc_btn_search")
    do_clear  = c2.button("🗑️ Clear",  use_container_width=True, key="sc_btn_clear")

    if do_search:
        if not selected_satellites:
            st.sidebar.warning("Select at least one satellite.")
        elif start > end:
            st.sidebar.error("Start date must be before end date.")
        elif aoi is None or aoi.is_empty:
            st.sidebar.error("❌ No AOI set. Draw a polygon on the map or select a country first.")
        else:
            st.session_state["sc_pending_search"] = {
                "polygon_geojson":    _mapping(aoi),
                "start_date":         start,
                "end_date":           end,
                "max_cloud":          max_cloud,
                "selected_satellites": selected_satellites,
            }

    if do_clear:
        for k in ["sc_scenes", "sc_features_download", "sc_features_map",
                  "sc_preview_indices", "sc_pending_search"]:
            st.session_state.pop(k, None)
        st.rerun()

    n = len(st.session_state.get("sc_scenes") or [])
    if n:
        mode_label = "quickview" if display_mode == "Quickview" else "footprints"
        st.sidebar.info(f"📋 {n} scenes loaded — showing {mode_label} on map")


# ============================================================================
# Live Tracking tab (unchanged)
# ============================================================================

def _render_live_tracking_tab(satellites_db):
    """Render Live Tracking tab content in sidebar"""
    render_live_tracking_sidebar(satellites_db)
    display_navigation_info_sidebar()
    return []


# ============================================================================
# Legacy functions (not used, kept for compatibility)
# ============================================================================

def _render_aoi_upload_section_sidebar(aoi_handler):
    """Legacy function – not used in the new design."""
    pass

def _render_country_selector_sidebar():
    """Legacy function – not used in the new design."""
    pass