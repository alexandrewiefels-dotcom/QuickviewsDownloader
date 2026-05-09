# ============================================================================
# FILE: ui/results_table.py – Results table for detected passes
# FIXED: Local time display now uses get_local_time_str() for correct timezone
# ============================================================================
import streamlit as st
import pandas as pd
from datetime import datetime
from detection.daylight_filter import get_local_time_str
from detection.daylight_filter import get_local_time_political


def render_passes_table(passes, aoi, weather_exhausted=False):
    """
    Render the detected passes table with export buttons.
    
    Args:
        passes: List of SatellitePass objects
        aoi: Area of Interest polygon (for local time calculation)
        weather_exhausted: Whether weather API quota is exhausted
    """
    if not passes:
        st.info("No passes detected. Try adjusting the search parameters.")
        return

    if weather_exhausted:
        st.warning("⚠️ OpenWeatherMap API quota exceeded. Cloud cover data temporarily unavailable.")

    st.markdown("### 📊 Detected Passes")
    st.caption(f"Showing {len(passes)} passes | ONA values shown are the actual footprint ONA (not the filter limit)")

    # Create columns for header
    cols = st.columns([0.5, 0.5, 1.5, 1.5, 1.5, 1.5, 1.5, 1.5, 1.5, 1.5, 1.5])
    headers = ["🔍", "#", "Satellite", "Camera", "Date (UTC)", "Time (UTC)", "Local Date", "Local Time", "ONA (°)", "Direction", "Clouds"]
    for i, header in enumerate(headers):
        cols[i].write(f"**{header}**")

    # Display each pass
    for idx, p in enumerate(passes, start=1):
        cols = st.columns([0.5, 0.5, 1.5, 1.5, 1.5, 1.5, 1.5, 1.5, 1.5, 1.5, 1.5])
        
        with cols[0]:
            if st.button("🔍", key=f"highlight_pass_{p.id}"):
                st.session_state.highlighted_pass_id = p.id
                st.rerun()
        
        with cols[1]:
            st.write(idx)
        
        with cols[2]:
            st.write(p.satellite_name)
        
        with cols[3]:
            st.write(p.camera_name)
        
        with cols[4]:
            st.write(p.date_utc)
        
        with cols[5]:
            st.write(p.time_utc)
        
        # FIXED: Use get_local_time_str for correct local time display
        local_time_str = get_local_time_political(p.pass_time, aoi)
        local_parts = local_time_str.split()
        
        with cols[6]:
            st.write(local_parts[0] if len(local_parts) > 0 else "")
        
        with cols[7]:
            st.write(local_parts[1] if len(local_parts) > 1 else "")
        
        with cols[8]:
            st.write(f"{p.min_ona:.1f}°")
        
        with cols[9]:
            st.write(p.orbit_direction)
        
        with cols[10]:
            if hasattr(p, 'mean_cloud_cover') and p.mean_cloud_cover is not None:
                cloud = p.mean_cloud_cover
                if cloud <= 30:
                    st.write(f"🟢 {cloud:.0f}%")
                elif cloud <= 70:
                    st.write(f"🟡 {cloud:.0f}%")
                else:
                    st.write(f"🔴 {cloud:.0f}%")
            else:
                st.write("—")

    # Export buttons row
    st.markdown("---")
    col_btn1, col_btn2, col_btn3, col_btn4 = st.columns([1, 1, 1, 3])
    
    # ========== KML EXPORT ==========
    with col_btn1:
        from visualization.kml_exporter import KMLExporter
        kml_str = KMLExporter.export_passes(passes, aoi=aoi)
        
        st.download_button(
            label="📥 Export to KML",
            data=kml_str,
            file_name=f"passes_{datetime.now().strftime('%Y%m%d_%H%M%S')}.kml",
            mime="application/vnd.google-earth.kml+xml",
            key="download_kml_passes_oneclick",
            use_container_width=True
        )
    
    # ========== CSV EXPORT ==========
    with col_btn2:
        from visualization.csv_exporter import CSVExporter
        csv_content = CSVExporter.export_passes_to_csv(passes, aoi)
        
        st.download_button(
            label="📊 Export to CSV",
            data=csv_content,
            file_name=f"passes_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            mime="text/csv",
            key="download_csv_passes_oneclick",
            use_container_width=True
        )
    
    # ========== PDF EXPORT ==========
    with col_btn3:
        from visualization.pdf_exporter import PDFExporter
        
        filters = {
            "Dates": f"{st.session_state.get('start_date', 'N/A')} → {st.session_state.get('end_date', 'N/A')}",
            "Max ONA (Filter)": f"{st.session_state.get('max_ona', 15)}°",
            "Orbit direction": st.session_state.get('orbit_filter', 'Both'),
        }
        
        tasking_results = st.session_state.get('tasking_results', None)
        
        pdf_buffer = PDFExporter.create_full_report(
            passes=passes,
            tasking_results=st.session_state.get('tasking_results', None),  # Les résultats taskés
            aoi=aoi,
            filters=filters
        )
        
        st.download_button(
            label="📄 Export to PDF",
            data=pdf_buffer,
            file_name=f"orbitshow_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf",
            mime="application/pdf",
            key="download_pdf_passes_oneclick",
            use_container_width=True
        )
    
    # ========== CLEAR HIGHLIGHT BUTTON ==========
    with col_btn4:
        if st.button("Clear highlight", key="clear_highlight_passes", use_container_width=True):
            st.session_state.highlighted_pass_id = None
            st.rerun()


def render_passes_summary(passes, aoi=None):
    """
    Render a compact summary of detected passes.
    
    Args:
        passes: List of SatellitePass objects
        aoi: Optional AOI for statistics
    """
    if not passes:
        return
    
    st.markdown("### 📈 Passes Summary")
    
    # Calculate statistics
    total_passes = len(passes)
    satellites = list(set([p.satellite_name for p in passes]))
    avg_ona = sum([p.min_ona for p in passes]) / total_passes if total_passes > 0 else 0
    min_ona = min([p.min_ona for p in passes]) if passes else 0
    max_ona = max([p.min_ona for p in passes]) if passes else 0
    
    # Count by direction
    asc_count = sum(1 for p in passes if p.orbit_direction == "Ascending")
    desc_count = sum(1 for p in passes if p.orbit_direction == "Descending")
    
    col1, col2, col3, col4, col5 = st.columns(5)
    with col1:
        st.metric("Total Passes", total_passes)
    with col2:
        st.metric("Satellites", len(satellites))
    with col3:
        st.metric("Avg ONA", f"{avg_ona:.1f}°")
    with col4:
        st.metric("Min ONA", f"{min_ona:.1f}°")
    with col5:
        st.metric("Max ONA", f"{max_ona:.1f}°")
    
    col6, col7 = st.columns(2)
    with col6:
        st.metric("Ascending Passes", asc_count)
    with col7:
        st.metric("Descending Passes", desc_count)
    
    # Show satellite breakdown
    if len(satellites) > 1:
        st.markdown("#### 🛰️ Passes by Satellite")
        sat_counts = {}
        for p in passes:
            sat_counts[p.satellite_name] = sat_counts.get(p.satellite_name, 0) + 1
        
        for sat, count in sorted(sat_counts.items(), key=lambda x: x[1], reverse=True):
            st.progress(count / total_passes, text=f"{sat}: {count} passes")


def render_pass_details(p, aoi=None):
    """
    Render detailed information for a single pass.
    
    Args:
        p: SatellitePass object
        aoi: Optional AOI for local time calculation
    """
    from detection.daylight_filter import get_local_time_str
    
    st.markdown(f"### 🛰️ {p.satellite_name}")
    st.markdown(f"**Camera:** {p.camera_name}")
    st.markdown(f"**Provider:** {p.provider}")
    st.markdown(f"**NORAD ID:** {p.norad_id}")
    
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**Pass Time:**")
        st.write(f"UTC: {p.datetime_utc}")
        if aoi:
            local_time_str = get_local_time_str(p.pass_time, aoi)
            st.write(f"Local: {local_time_str}")
        else:
            st.write(f"Local: {p.local_time_approx}")
        st.write(f"CET: {p.datetime_cet}")
    
    with col2:
        st.markdown("**Geometry:**")
        st.write(f"Min ONA: {p.min_ona:.1f}°")
        st.write(f"Max ONA: {p.max_ona:.1f}°")
        st.write(f"Direction: {p.orbit_direction}")
        st.write(f"Swath: {p.swath_km:.0f} km")
        st.write(f"Resolution: {p.resolution_m:.1f} m")
    
    if hasattr(p, 'mean_cloud_cover') and p.mean_cloud_cover is not None:
        cloud = p.mean_cloud_cover
        if cloud <= 30:
            cloud_icon = "🟢"
        elif cloud <= 70:
            cloud_icon = "🟡"
        else:
            cloud_icon = "🔴"
        st.markdown(f"**Cloud Cover:** {cloud_icon} {cloud:.0f}%")
    
    if hasattr(p, 'tle_age_days') and p.tle_age_days is not None:
        st.caption(f"TLE age: {p.tle_age_days:.1f} days")
