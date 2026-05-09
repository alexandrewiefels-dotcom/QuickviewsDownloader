# ui/components/map_controls.py
import streamlit as st
import math


def compute_zoom(bounds):
    """Compute appropriate zoom level from bounds"""
    width_deg = bounds[2] - bounds[0]
    height_deg = bounds[3] - bounds[1]
    
    if width_deg <= 0 or height_deg <= 0:
        return 10
    
    max_dim_deg = max(width_deg, height_deg)
    zoom = math.log2(360 / max_dim_deg)
    zoom = max(3, min(15, int(zoom)))
    return zoom


def render_zoom_to_aoi_button(aoi):
    """Render zoom to AOI button"""
    if aoi and not aoi.is_empty:
        if st.button("🎯 Zoom to AOI", key="zoom_to_aoi_btn", use_container_width=True):
            bounds = aoi.bounds
            new_zoom = compute_zoom(bounds)
            st.session_state.map_center = [aoi.centroid.y, aoi.centroid.x]
            st.session_state.map_zoom = new_zoom
            st.session_state.map_key += 1
            st.rerun()
