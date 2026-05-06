# File: sidebar.py
import streamlit as st
from datetime import datetime
from sasclouds_api_scraper import convert_uploaded_file_to_geojson, SATELLITE_GROUPS

def render_sidebar():
    """Render all sidebar filters and return the selected parameters."""
    with st.sidebar:
        st.header("🔍 Search Parameters")
        
        # AOI input method
        aoi_method = st.radio("AOI input method", ["Bounding box", "Upload file (GeoJSON, Shapefile ZIP, KML, KMZ)"])
        
        if aoi_method == "Bounding box":
            col1, col2 = st.columns(2)
            with col1:
                min_lon = st.number_input("West (min lon)", value=-73.0, format="%.6f")
                min_lat = st.number_input("South (min lat)", value=8.0, format="%.6f")
            with col2:
                max_lon = st.number_input("East (max lon)", value=-72.0, format="%.6f")
                max_lat = st.number_input("North (max lat)", value=9.0, format="%.6f")
            polygon_geojson = {
                "type": "Polygon",
                "coordinates": [[[min_lon, min_lat], [max_lon, min_lat],
                                 [max_lon, max_lat], [min_lon, max_lat], [min_lon, min_lat]]]
            }
            aoi_filename = "bbox"
        else:
            uploaded_file = st.file_uploader(
                "Upload AOI file",
                type=["geojson", "zip", "kml", "kmz"],
                help="Supported: GeoJSON (.geojson), Shapefile (.zip containing .shp), KML (.kml), KMZ (.kmz)"
            )
            if uploaded_file:
                try:
                    polygon_geojson = convert_uploaded_file_to_geojson(uploaded_file)
                    aoi_filename = uploaded_file.name
                    st.success(f"File loaded: {aoi_filename}")
                    st.info(f"Geometry type: {polygon_geojson.get('type')}")
                except Exception as e:
                    st.error(f"Failed to parse file: {e}")
                    polygon_geojson = None
                    aoi_filename = None
            else:
                polygon_geojson = None
                aoi_filename = None
        
        # Date range and cloud cover
        st.subheader("Temporal & Cloud Filters")
        start_date = st.date_input("Start date", value=datetime(2025, 1, 1))
        end_date = st.date_input("End date", value=datetime(2026, 4, 11))
        max_cloud = st.slider("Maximum cloud cover (%)", 0, 100, 20)
        
        # Satellite selection (grouped expanders)
        st.subheader("🛰️ Satellites and sensors")
        selected_satellites = []
        for group_name, categories in SATELLITE_GROUPS.items():
            with st.expander(group_name):
                for cat_name, sats in categories.items():
                    if not isinstance(sats, list):
                        st.warning(f"Skipping category '{cat_name}': not a list")
                        continue
                    labels = []
                    for sat in sats:
                        if not isinstance(sat, dict):
                            continue
                        sensor_str = ', '.join(sat.get('sensorIds', [])) if sat.get('sensorIds') else 'All sensors'
                        labels.append(f"{sat['satelliteId']} ({sensor_str})")
                    chosen = st.multiselect(cat_name, labels, key=f"{group_name}_{cat_name}")
                    for label in chosen:
                        for sat in sats:
                            if label.startswith(sat['satelliteId']):
                                selected_satellites.append({
                                    "satelliteId": sat['satelliteId'],
                                    "sensorIds": sat.get('sensorIds', [])
                                })
                                break
        
        search_clicked = st.button("🔍 Search", type="primary", use_container_width=True)
        
        return {
            "polygon_geojson": polygon_geojson,
            "aoi_filename": aoi_filename,
            "start_date": start_date,
            "end_date": end_date,
            "max_cloud": max_cloud,
            "selected_satellites": selected_satellites,
            "search_clicked": search_clicked
        }