# ============================================================================
# FILE: ui/tasking_table.py – Tasking results display
# FIXED: Local time uses political timezone (round(lon/15)) matching CSV
# ============================================================================
import streamlit as st
import pandas as pd
from shapely.ops import unary_union
from datetime import datetime
from detection.daylight_filter import get_local_time_political


def render_tasking_table(tasking_results, aoi):
    """Render the tasking simulation results table"""
    if not tasking_results:
        st.info("No tasking results available. Please run a search first.")
        return

    st.markdown("### 📊 Tasking Simulation Results")
    
    # Display coverage summary if AOI exists
    if aoi and aoi.area > 0:
        valid_footprints = []
        for r in tasking_results:
            if 'footprint' in r and r['footprint'] and not r['footprint'].is_empty:
                intersection = r['footprint'].intersection(aoi)
                if not intersection.is_empty and intersection.area > 0:
                    valid_footprints.append(r['footprint'])
        
        if valid_footprints:
            total_coverage = unary_union(valid_footprints)
            coverage_area = total_coverage.intersection(aoi).area
            coverage_pct = (coverage_area / aoi.area) * 100
            
            from data.aoi_handler import AOIHandler
            aoi_area_km2, aoi_unit = AOIHandler.calculate_area(aoi)
            covered_km2_approx = coverage_area * 111.0 * 111.0
            
            st.success(f"✅ **Coverage achieved:** {coverage_pct:.1f}% of AOI")
            st.info(f"📐 **AOI area:** {aoi_area_km2:.2f} {aoi_unit} | **Covered area:** {covered_km2_approx:.2f} km² (approx.)")
        else:
            st.warning("No footprints intersect the AOI")

    # Create columns for header
    cols = st.columns([0.5, 0.5, 1.5, 1.5, 1.5, 1.5, 1.5, 1.5, 1.5, 1.5, 1.5, 1.5])
    headers = ["🔍", "#", "Satellite", "Camera", "Date/Time UTC", "Date/Time local", "ONA used", "Offset", "Swath (km)", "GSD (m)", "Weather", "Coverage"]
    for i, header in enumerate(headers):
        cols[i].write(f"**{header}**")

    for idx, r in enumerate(tasking_results, start=1):
        # Récupération sécurisée de pass_time
        pass_time = r.get('pass_time')
        if pass_time is None:
            if 'pass' in r and hasattr(r['pass'], 'pass_time'):
                pass_time = r['pass'].pass_time
            else:
                st.warning(f"Missing pass_time for task {idx}")
                continue

        # Get UTC date and time
        date_utc = pass_time.strftime("%Y-%m-%d")
        time_utc = pass_time.strftime("%H:%M:%S")
        
        # Get local political time
        local_time_str = get_local_time_political(pass_time, aoi)
        # Extract date and time (format: "YYYY-MM-DD HH:MM:SS")
        if " " in local_time_str:
            local_date, local_time_display = local_time_str.split(" ", 1)
        else:
            local_date = local_time_str
            local_time_display = ""

        # Get ONA value
        ona_value = r.get('required_ona', 0)
        if ona_value is None:
            ona_value = 0
        
        # Get coverage value
        coverage_value = r.get('coverage_pct', r.get('cumulative_coverage_pct', 0))
        if coverage_value is None:
            coverage_value = 0

        cols = st.columns([0.5, 0.5, 1.5, 1.5, 1.5, 1.5, 1.5, 1.5, 1.5, 1.5, 1.5, 1.5])
        
        with cols[0]:
            unique_key = f"highlight_tasking_{r.get('id', idx)}_{idx}"
            if st.button("🔍", key=unique_key):
                st.session_state.highlighted_pass_id = r.get('id')
                st.rerun()
        
        with cols[1]:
            st.write(idx)
        
        with cols[2]:
            st.write(r.get('satellite', 'N/A'))
        
        with cols[3]:
            st.write(r.get('camera', 'N/A'))
        
        with cols[4]:
            st.write(f"{date_utc} {time_utc}")
        
        with cols[5]:
            st.write(f"{local_date} {local_time_display}")
        
        with cols[6]:
            # Color code based on ONA value
            if ona_value <= 10:
                st.write(f"🟢 {ona_value:.1f}°")
            elif ona_value <= 25:
                st.write(f"🟡 {ona_value:.1f}°")
            else:
                st.write(f"🔴 {ona_value:.1f}°")
        
        with cols[7]:
            shift = abs(r.get('shift_km', r.get('offset_km', 0)))
            if shift is None:
                shift = 0
            if r.get('shift_km', 0) > 0:
                st.write(f"→ {shift:.1f} km")
            elif r.get('shift_km', 0) < 0:
                st.write(f"← {shift:.1f} km")
            else:
                st.write(f"{shift:.1f} km")
        
        with cols[8]:
            swath = r.get('swath_km', 0)
            st.write(f"{swath:.0f} km")
        
        with cols[9]:
            resolution = r.get('resolution_m', 0)
            st.write(f"{resolution:.1f} m")
        
        with cols[10]:
            # Weather info with icon
            cloud = r.get('cloud_cover')
            if cloud is not None:
                if cloud <= 30:
                    st.write(f"☀️ {cloud:.0f}%")
                elif cloud <= 70:
                    st.write(f"⛅ {cloud:.0f}%")
                else:
                    st.write(f"☁️ {cloud:.0f}%")
            else:
                st.write("🌤️ N/A")
        
        with cols[11]:
            # Coverage percentage with color coding
            if coverage_value >= 80:
                st.write(f"🟢 {coverage_value:.1f}%")
            elif coverage_value >= 50:
                st.write(f"🟡 {coverage_value:.1f}%")
            elif coverage_value >= 20:
                st.write(f"🟠 {coverage_value:.1f}%")
            else:
                st.write(f"🔴 {coverage_value:.1f}%")

    # Export buttons row
    st.markdown("---")
    
    col_btn1, col_btn2, col_btn3, col_btn4 = st.columns([1, 1, 1, 2])
    
    # ========== KML EXPORT ==========
    with col_btn1:
        passes_with_task = [p for p in st.session_state.get('passes', []) if hasattr(p, 'tasked_footprint') and p.tasked_footprint]
        if passes_with_task:
            from visualization.kml_exporter import KMLExporter
            kml_str = KMLExporter.export_tasked_passes(passes_with_task, aoi=st.session_state.get('aoi'))
            
            st.download_button(
                label="📥 Export to KML",
                data=kml_str,
                file_name=f"tasking_passes_{datetime.now().strftime('%Y%m%d_%H%M%S')}.kml",
                mime="application/vnd.google-earth.kml+xml",
                key="download_kml_tasking_oneclick",
                use_container_width=True
            )
        else:
            st.button("📥 Export to KML", disabled=True, use_container_width=True, help="No tasked passes available")
    
    # ========== CSV EXPORT ==========
    with col_btn2:
        from visualization.csv_exporter import CSVExporter
        csv_content = CSVExporter.export_tasking_to_csv(tasking_results, aoi)
        
        st.download_button(
            label="📊 Export to CSV",
            data=csv_content,
            file_name=f"tasking_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            mime="text/csv",
            key="download_csv_tasking_oneclick",
            use_container_width=True
        )
    
    # ========== PDF EXPORT ==========
# ========== PDF EXPORT ==========
    with col_btn3:
        from visualization.pdf_exporter import PDFExporter
        passes_list = st.session_state.get('displayed_passes', [])
        
        # Prepare filters for PDF
        filters = {}
        if st.session_state.get('start_date') and st.session_state.get('end_date'):
            filters["Dates"] = f"{st.session_state.start_date} → {st.session_state.end_date}"
        if st.session_state.get('max_ona'):
            filters["Max ONA"] = f"{st.session_state.max_ona}°"
        if st.session_state.get('orbit_filter'):
            filters["Orbit direction"] = st.session_state.get('orbit_filter', 'Both')
        
        # Try to generate PDF buffer
        pdf_buffer = None
        error_msg = None
        try:
            # Try to capture map image (optional, may fail if cartopy missing)
            map_image = None
            try:
                from visualization.map_renderer import MapRenderer
                map_renderer = MapRenderer()
                center = st.session_state.get('map_center', [30, 0])
                zoom = st.session_state.get('map_zoom', 2)
                aoi_geom = st.session_state.get('aoi')
                map_image = PDFExporter.capture_map_as_image(
                    map_renderer, center, zoom, aoi_geom,
                    passes_list,
                    st.session_state.get('opportunities', []),
                    highlighted_pass_id=st.session_state.get('highlighted_pass_id'),
                    filters=filters
                )
            except Exception as e:
                print(f"Map capture failed: {e}")
            
            pdf_buffer = PDFExporter.create_simple_report(
                passes_list,
                tasking_results=tasking_results,
                aoi=st.session_state.get('aoi'),
                filters=filters,
                map_image=map_image,
                center=st.session_state.get('map_center', [30, 0]),
                zoom=st.session_state.get('map_zoom', 2)
            )
        except Exception as e:
            error_msg = str(e)
            print(f"PDF generation error: {error_msg}")
            # Create a simple text fallback buffer
            from io import BytesIO
            pdf_buffer = BytesIO()
            pdf_buffer.write(f"PDF generation failed: {error_msg}\nPlease install reportlab and cartopy.".encode())
            pdf_buffer.seek(0)
        
        # Always show the download button
        st.download_button(
            label="📄 Export to PDF",
            data=pdf_buffer,
            file_name=f"orbitshow_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf",
            mime="application/pdf",
            key="download_pdf_tasking_oneclick",
            use_container_width=True
        )
        
        if error_msg:
            st.warning(f"PDF export limited: {error_msg}. Install reportlab and cartopy for full PDF features.")
    
    # ========== CLEAR HIGHLIGHT BUTTON ==========
    with col_btn4:
        if st.button("Clear highlight", key="clear_highlight_tasking", use_container_width=True):
            st.session_state.highlighted_pass_id = None
            st.rerun()


def render_tasking_summary(tasking_results, aoi):
    """Render a compact summary of tasking results"""
    if not tasking_results:
        return
    
    st.markdown("### 📈 Tasking Summary")
    
    # Calculate statistics
    total_passes = len(tasking_results)
    total_coverage = max([r.get('coverage_pct', 0) for r in tasking_results]) if tasking_results else 0
    if 'total_coverage_pct' in tasking_results[0]:
        total_coverage = tasking_results[0].get('total_coverage_pct', total_coverage)
    
    avg_ona = sum([r.get('required_ona', 0) or 0 for r in tasking_results]) / total_passes if total_passes > 0 else 0
    best_coverage = max([r.get('coverage_pct', 0) or 0 for r in tasking_results]) if tasking_results else 0
    
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Total Passes", total_passes)
    with col2:
        st.metric("Total Coverage", f"{total_coverage:.1f}%")
    with col3:
        st.metric("Avg ONA", f"{avg_ona:.1f}°")
    with col4:
        st.metric("Best Coverage", f"{best_coverage:.1f}%")
    
    # Show best passes
    st.markdown("#### 🏆 Best Passes")
    best_passes = sorted(tasking_results, key=lambda x: x.get('coverage_pct', 0) or 0, reverse=True)[:5]
    
    for i, p in enumerate(best_passes, 1):
        coverage = p.get('coverage_pct', 0) or 0
        ona = p.get('required_ona', 0) or 0
        sat = p.get('satellite', 'Unknown')
        
        if coverage >= 80:
            emoji = "🟢"
        elif coverage >= 50:
            emoji = "🟡"
        else:
            emoji = "🔴"
        
        st.write(f"{emoji} **{i}. {sat}** – Coverage: {coverage:.1f}%, ONA: {ona:.1f}°")
