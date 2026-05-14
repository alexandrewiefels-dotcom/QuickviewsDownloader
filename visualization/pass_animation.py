"""
Satellite pass animation with time slider (3.21).

Provides an interactive time slider that animates satellite passes
over time, showing how footprints and ground tracks evolve.

Usage:
    from visualization.pass_animation import render_pass_animation
    render_pass_animation(passes, aoi, center, zoom)
"""

import logging
from datetime import datetime, timedelta
from typing import List, Optional

import streamlit as st
import folium
from streamlit_folium import st_folium
from shapely.geometry import mapping

from config.constants import MAP_TILES
from geometry.utils import split_polygon_at_antimeridian, split_line_at_antimeridian, shapely_coords_to_folium

logger = logging.getLogger(__name__)


def _get_pass_time(p) -> datetime:
    """Extract datetime from a pass object."""
    if hasattr(p, 'datetime') and p.datetime:
        return p.datetime
    if hasattr(p, 'start_time') and p.start_time:
        return p.start_time
    # Fallback: parse from date_utc8 + time_utc8
    try:
        date_str = getattr(p, 'date_utc8', '')
        time_str = getattr(p, 'time_utc8', '')
        if date_str and time_str:
            return datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M:%S")
    except (ValueError, TypeError):
        pass
    return datetime.now()


def render_pass_animation(passes: List, aoi, center: tuple, zoom: int,
                          map_key: int = 0, height: int = 600):
    """
    Render an interactive pass animation with a time slider.
    
    Args:
        passes: List of pass objects
        aoi: AOI geometry (Shapely)
        center: Map center (lat, lon)
        zoom: Initial zoom level
        map_key: Unique key for Streamlit
        height: Map height in pixels
    """
    if not passes:
        st.info("No passes to animate.")
        return

    # Sort passes by time
    sorted_passes = sorted(passes, key=_get_pass_time)

    # Get time range
    start_time = _get_pass_time(sorted_passes[0])
    end_time = _get_pass_time(sorted_passes[-1])
    total_seconds = max((end_time - start_time).total_seconds(), 1)

    # Time slider
    st.markdown("### ⏱️ Pass Animation")
    st.markdown(f"**Time range:** {start_time.strftime('%Y-%m-%d %H:%M')} → "
                f"{end_time.strftime('%Y-%m-%d %H:%M')} UTC")

    col1, col2 = st.columns([3, 1])
    with col1:
        # Slider as fraction of time range
        time_fraction = st.slider(
            "Time",
            min_value=0.0,
            max_value=1.0,
            value=0.0,
            step=0.01,
            key=f"anim_slider_{map_key}",
            label_visibility="collapsed",
        )
    with col2:
        play = st.button("▶️ Play", key=f"anim_play_{map_key}")

    # Calculate current time from fraction
    current_time = start_time + timedelta(seconds=total_seconds * time_fraction)

    # Filter passes visible at current time
    visible_window = timedelta(minutes=30)  # Show passes within 30 min of current time
    visible_passes = [
        p for p in sorted_passes
        if abs((_get_pass_time(p) - current_time).total_seconds()) < visible_window.total_seconds()
    ]

    # Show count
    st.caption(f"Showing {len(visible_passes)} of {len(passes)} passes at "
               f"{current_time.strftime('%Y-%m-%d %H:%M')} UTC")

    # Render map
    m = folium.Map(location=center, zoom_start=zoom, tiles=MAP_TILES)

    # Add AOI
    if aoi is not None and not aoi.is_empty:
        from data.aoi_handler import AOIHandler
        area_value, area_unit = AOIHandler.calculate_area(aoi)
        gdf = __import__('geopandas', fromlist=['GeoDataFrame']).GeoDataFrame(
            [{"geometry": aoi}], crs="EPSG:4326"
        )
        folium.GeoJson(
            gdf.__geo_interface__,
            name="AOI",
            style_function=lambda x: {"fillColor": "#00FFFF", "color": "#006666",
                                      "weight": 3, "fillOpacity": 0.2},
        ).add_to(m)

    # Render visible passes
    for p in visible_passes:
        footprint = getattr(p, 'display_footprint', None) or p.footprint
        ground_track = getattr(p, 'display_ground_track', None) or p.ground_track

        if footprint is None or footprint.is_empty:
            continue

        # Split at antimeridian
        parts = split_polygon_at_antimeridian(footprint)
        pass_time = _get_pass_time(p)
        is_current = abs((pass_time - current_time).total_seconds()) < 60  # Within 1 min

        for part in parts:
            if part.is_empty:
                continue
            geojson = mapping(part)
            style = {
                "fillColor": "#00FF00" if is_current else p.color,
                "color": "#00AA00" if is_current else "#333333",
                "weight": 3 if is_current else 1,
                "fillOpacity": 0.5 if is_current else 0.15,
            }
            tooltip = f"{p.satellite_name}<br>{pass_time.strftime('%H:%M')} UTC"
            folium.GeoJson(
                geojson,
                style_function=lambda x, s=style: s,
                tooltip=tooltip,
            ).add_to(m)

        # Ground track
        if ground_track and not ground_track.is_empty:
            track_segments = split_line_at_antimeridian(ground_track)
            for seg in track_segments:
                if seg.is_empty or len(seg.coords) < 2:
                    continue
                coords = shapely_coords_to_folium(list(seg.coords))
                folium.PolyLine(
                    locations=coords,
                    color="#00FF00" if is_current else p.color,
                    weight=2 if is_current else 1,
                    opacity=0.5,
                ).add_to(m)

    # Time indicator
    time_html = f"""
    <div style="position:absolute;top:10px;left:50%;transform:translateX(-50%);
                background:rgba(0,0,0,0.8);color:white;padding:8px 16px;
                border-radius:8px;font-size:14px;z-index:1000;
                border:1px solid #2ecc71;">
        🕐 {current_time.strftime('%Y-%m-%d %H:%M:%S')} UTC
    </div>
    """
    m.get_root().html.add_child(folium.Element(time_html))

    # Render map
    st_folium(m, key=f"anim_map_{map_key}", width="100%", height=height)

    # Auto-play logic
    if play:
        st.markdown("""
        <script>
        (function() {
            var slider = document.querySelector('[data-testid="stSlider"] input[type="range"]');
            if (slider) {
                var playInterval = setInterval(function() {
                    var val = parseFloat(slider.value);
                    if (val >= 1.0) {
                        clearInterval(playInterval);
                        return;
                    }
                    slider.value = Math.min(val + 0.01, 1.0);
                    slider.dispatchEvent(new Event('input', {bubbles: true}));
                }, 200);
            }
        })();
        </script>
        """, unsafe_allow_html=True)
