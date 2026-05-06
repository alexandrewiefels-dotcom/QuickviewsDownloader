# File: main.py
import streamlit as st
import json
import tempfile
import zipfile
import io
import shutil
import uuid
import traceback
from pathlib import Path
from datetime import datetime

import folium
from streamlit_folium import st_folium
from folium.plugins import MarkerCluster
import pandas as pd

from sasclouds_api_scraper import (
    SASCloudsAPIClient,
    log_search,
    log_aoi_upload,
    convert_uploaded_file_to_geojson
)

st.set_page_config(page_title="SASClouds API Scraper", layout="wide")

# ----------------------------------------------------------------------
# Authentication (app password)
# ----------------------------------------------------------------------
PASSWORD = st.secrets.get("PASSWORD", "default_fallback")
if PASSWORD == "default_fallback":
    st.error("No PASSWORD found in secrets. Please set .streamlit/secrets.toml")
    st.stop()

if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

if not st.session_state.authenticated:
    st.title("🔐 Authentication Required")
    password_input = st.text_input("Enter Password", type="password")
    if st.button("Login"):
        if password_input == PASSWORD:
            st.session_state.authenticated = True
            st.rerun()
        else:
            st.error("Incorrect password")
    st.stop()

# ----------------------------------------------------------------------
# Session ID for logging
# ----------------------------------------------------------------------
if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())

# ----------------------------------------------------------------------
# Satellite and sensor definitions (full list)
# ----------------------------------------------------------------------
SATELLITE_GROUPS = {
    "Optical": {
        "2-meter": [
            {"satelliteId": "ZY3-1", "sensorIds": ["MUX"]},
            {"satelliteId": "ZY3-2", "sensorIds": ["MUX"]},
            {"satelliteId": "ZY3-3", "sensorIds": ["MUX"]},
            {"satelliteId": "ZY02C", "sensorIds": ["HRC"]},
            {"satelliteId": "ZY1-02D", "sensorIds": ["VNIC"]},
            {"satelliteId": "ZY1-02E", "sensorIds": ["VNIC"]},
            {"satelliteId": "2m8m", "sensorIds": ["PMS"]},
            {"satelliteId": "GF1", "sensorIds": ["PMS"]},
            {"satelliteId": "GF6", "sensorIds": ["PMS"]},
            {"satelliteId": "CBERS-04A", "sensorIds": ["WPM"]},
            {"satelliteId": "CM1", "sensorIds": ["DMC"]},
            {"satelliteId": "TH01", "sensorIds": ["GFB", "DGP"]},
            {"satelliteId": "SPOT6/7", "sensorIds": ["PMS"]},
        ],
        "Sub-meter": [
            {"satelliteId": "GF2", "sensorIds": ["PMS"]},
            {"satelliteId": "GF7", "sensorIds": ["MUX", "BWD", "FWD"]},
            {"satelliteId": "GFDM01", "sensorIds": ["PMS"]},
            {"satelliteId": "JL1", "sensorIds": ["PMS"]},
            {"satelliteId": "BJ2", "sensorIds": ["PMS"]},
            {"satelliteId": "BJ3", "sensorIds": ["PMS"]},
            {"satelliteId": "SV1", "sensorIds": ["PMS"]},
            {"satelliteId": "SV2", "sensorIds": ["PMS"]},
            {"satelliteId": "LJ3-2", "sensorIds": ["PMS"]},
            {"satelliteId": "GeoEye-1", "sensorIds": ["PMS"]},
            {"satelliteId": "WorldView-2", "sensorIds": ["PMS"]},
            {"satelliteId": "WorldView-3", "sensorIds": ["PMS"]},
            {"satelliteId": "WorldView-4", "sensorIds": ["PMS"]},
            {"satelliteId": "Pleiades", "sensorIds": ["PMS"]},
            {"satelliteId": "DEIMOS", "sensorIds": ["PMS"]},
            {"satelliteId": "KOMPSAT-2", "sensorIds": ["PMS"]},
            {"satelliteId": "KOMPSAT-3", "sensorIds": ["PMS"]},
            {"satelliteId": "KOMPSAT-3A", "sensorIds": ["PMS"]},
        ],
        "Other (wide‑angle)": [
            {"satelliteId": "GF1", "sensorIds": ["WFV"]},
            {"satelliteId": "GF6", "sensorIds": ["WFV"]},
            {"satelliteId": "GF4", "sensorIds": ["PMI", "IRS"]},
        ]
    },
    "Hyperspectral": {
        "Hyperspectral": [
            {"satelliteId": "ZY1-02D", "sensorIds": ["AHSI"]},
            {"satelliteId": "ZY1-02E", "sensorIds": ["AHSI"]},
            {"satelliteId": "GF5", "sensorIds": ["AHSI"]},
            {"satelliteId": "GF5A", "sensorIds": ["AHSI"]},
            {"satelliteId": "GF5B", "sensorIds": ["AHSI"]},
            {"satelliteId": "GF5", "sensorIds": ["VIMS"]},
            {"satelliteId": "LJ3-2", "sensorIds": ["HSI"]},
            {"satelliteId": "OHS-2/3", "sensorIds": ["MSS"]},
        ]
    },
    "SAR": {
        "SAR": [
            {"satelliteId": "GF3", "sensorIds": []},
            {"satelliteId": "CSAR", "sensorIds": []},
            {"satelliteId": "LSAR", "sensorIds": []},
        ]
    },
    "Other": {
        "Other sensors": [
            {"satelliteId": "JL-1GP", "sensorIds": ["PMS"]},
        ]
    }
}

# ----------------------------------------------------------------------
# Helper: date to milliseconds
# ----------------------------------------------------------------------
def date_to_ms(dt):
    return int(dt.timestamp() * 1000)

# ----------------------------------------------------------------------
# Main UI
# ----------------------------------------------------------------------
st.title("🛰️ SASClouds API Scraper")
st.markdown("Fast, cloud‑compatible search using the official API. No browser needed.")

with st.expander("How to use", expanded=False):
    st.markdown("""
    1. Draw your AOI (bounding box or upload a GeoJSON, Shapefile ZIP, KML, KMZ).
    2. Select date range, cloud cover, and satellites/sensors.
    3. Click **Search** – results will appear on a map and in a table.
    4. Then click **Download ZIP** to save all images + world files + GeoJSON.
    """)

# ----------------------------------------------------------------------
# AOI input (bounding box or file upload)
# ----------------------------------------------------------------------
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
            geom_type = polygon_geojson.get("type")
            st.info(f"Geometry type: {geom_type}")
        except Exception as e:
            st.error(f"Failed to parse file: {e}")
            polygon_geojson = None
            aoi_filename = None
    else:
        polygon_geojson = None
        aoi_filename = None

# ----------------------------------------------------------------------
# Filters: date range, cloud cover
# ----------------------------------------------------------------------
col1, col2 = st.columns(2)
with col1:
    start_date = st.date_input("Start date", value=datetime(2025, 1, 1))
    end_date = st.date_input("End date", value=datetime(2026, 4, 11))
with col2:
    max_cloud = st.slider("Maximum cloud cover (%)", 0, 100, 20)

# ----------------------------------------------------------------------
# Satellite selection (grouped expanders with safety checks)
# ----------------------------------------------------------------------
st.subheader("Satellites and sensors")
selected_satellites = []

for group_name, categories in SATELLITE_GROUPS.items():
    if not isinstance(categories, dict):
        st.warning(f"Skipping group '{group_name}': invalid structure")
        continue
    with st.expander(group_name):
        for cat_name, sats in categories.items():
            if not isinstance(sats, list):
                st.warning(f"Skipping category '{cat_name}' in '{group_name}': not a list")
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

# ----------------------------------------------------------------------
# Search button and results handling
# ----------------------------------------------------------------------
if st.button("🔍 Search", type="primary"):
    if not polygon_geojson:
        st.error("Please provide an AOI (bounding box or valid file).")
        st.stop()

    if not selected_satellites:
        st.warning("No satellites selected. Please choose at least one.")
        st.stop()

    # Placeholders for logs and results
    log_container = st.empty()
    log_lines = []

    def add_log(msg):
        log_lines.append(msg)
        log_container.code("\n".join(log_lines[-30:]), language="bash")

    with st.status("Searching...", expanded=True) as status:
        try:
            client = SASCloudsAPIClient()
            status.write("Uploading AOI...")
            add_log("Starting AOI upload...")
            upload_id = client.upload_aoi(polygon_geojson)
            status.write(f"AOI uploaded, ID: {upload_id}")
            add_log(f"AOI upload successful, ID: {upload_id}")

            add_log("Logging AOI upload...")
            log_aoi_upload(st.session_state.session_id, aoi_filename, polygon_geojson)

            start_ms = date_to_ms(start_date)
            end_ms = date_to_ms(end_date)
            add_log(f"Date range: {start_date} to {end_date} (ms: {start_ms} - {end_ms})")
            add_log(f"Cloud cover max: {max_cloud}%")
            add_log(f"Selected satellites: {json.dumps(selected_satellites, indent=2)}")

            all_scenes = []
            page = 1
            page_size = 50
            while True:
                status.write(f"Fetching page {page}...")
                add_log(f"Fetching page {page}...")
                result = client.search_scenes(upload_id, start_ms, end_ms, max_cloud,
                                              selected_satellites, page, page_size)
                if result.get("code") != 0:
                    error_msg = result.get("message", "Unknown API error")
                    add_log(f"API error: {error_msg}")
                    raise Exception(f"API returned error: {error_msg}")
                scenes = result.get("data", [])
                add_log(f"Page {page} returned {len(scenes)} scenes")
                if not scenes:
                    break
                all_scenes.extend(scenes)
                total = result.get("pageInfo", {}).get("total", 0)
                add_log(f"Total scenes so far: {len(all_scenes)} / {total}")
                if len(all_scenes) >= total:
                    break
                page += 1

            status.write(f"Found {len(all_scenes)} scenes.")
            add_log(f"Total scenes found: {len(all_scenes)}")

            if not all_scenes:
                st.warning("No scenes found. Adjust your filters.")
                st.stop()

            add_log("Logging search...")
            log_search(
                st.session_state.session_id,
                polygon_geojson,
                {
                    "satellites": selected_satellites,
                    "cloud_max": max_cloud,
                    "date_range": [start_date.isoformat(), end_date.isoformat()]
                },
                len(all_scenes)
            )

            # ----------------------------------------------------------
            # Build table and map from all_scenes
            # ----------------------------------------------------------
            features_for_map = []
            table_data = []
            for idx, scene in enumerate(all_scenes):
                sat = scene["satelliteId"]
                sensor = scene["sensorId"]
                date_str = datetime.fromtimestamp(scene["acquisitionTime"]/1000).strftime("%Y-%m-%d")
                cloud = scene["cloudPercent"]
                prod_id = scene["productId"]
                footprint = json.loads(scene["boundary"])  # GeoJSON polygon
                quickview_url = scene["quickViewUri"].replace(
                    "http://quickview.sasclouds.com",
                    "https://quickview.obs.cn-north-10.myhuaweicloud.com"
                )
                # For table
                table_data.append({
                    "Name": f"{sat} {sensor}",
                    "Date": date_str,
                    "Cloud (%)": cloud,
                    "Product ID": prod_id,
                    "Quickview": f'<a href="{quickview_url}" target="_blank">🔗</a>'
                })
                # For map: store feature
                features_for_map.append({
                    "geometry": footprint,
                    "properties": {
                        "satellite": sat,
                        "sensor": sensor,
                        "date": date_str,
                        "cloud": cloud,
                        "product_id": prod_id,
                        "quickview": quickview_url
                    }
                })
            
            # Display table
            st.subheader("📋 Search Results")
            df = pd.DataFrame(table_data)
            # Convert Quickview column to HTML for clickable links
            df_html = df.to_html(escape=False, index=False)
            st.markdown(df_html, unsafe_allow_html=True)
            
            # Create Folium map
            st.subheader("🗺️ Footprint Map")
            # Determine map center from first polygon centroid
            if features_for_map:
                first_geom = features_for_map[0]["geometry"]
                # Extract centroid quickly
                if first_geom["type"] == "Polygon":
                    coords = first_geom["coordinates"][0]
                    lons = [c[0] for c in coords]
                    lats = [c[1] for c in coords]
                    center_lat = sum(lats) / len(lats)
                    center_lon = sum(lons) / len(lons)
                else:
                    center_lat, center_lon = 9.0, -73.0  # fallback
                m = folium.Map(location=[center_lat, center_lon], zoom_start=8)
                # Add each footprint as GeoJSON with popup
                for feat in features_for_map:
                    popup_html = f"""
                    <b>{feat['properties']['satellite']} {feat['properties']['sensor']}</b><br>
                    Date: {feat['properties']['date']}<br>
                    Cloud: {feat['properties']['cloud']}%<br>
                    <img src="{feat['properties']['quickview']}" width="200"><br>
                    <a href="{feat['properties']['quickview']}" target="_blank">Open full image</a>
                    """
                    folium.GeoJson(
                        feat["geometry"],
                        popup=folium.Popup(popup_html, max_width=300),
                        style_function=lambda x: {"color": "red", "weight": 2, "fillOpacity": 0.1}
                    ).add_to(m)
                # Display map using streamlit-folium
                st_folium(m, width=800, height=500)
            else:
                st.info("No footprints to display.")
            
            # Provide download button (after map)
            st.subheader("💾 Download All Data")
            # Store scenes and features in session state so download can reuse
            st.session_state.scenes_for_download = all_scenes
            st.session_state.features_for_download = features_for_map
            st.session_state.temp_dir_ready = True
            
        except Exception as e:
            error_details = traceback.format_exc()
            status.write(f"❌ Error: {e}")
            status.write(f"Details:\n{error_details}")
            add_log(f"❌ EXCEPTION: {e}")
            add_log(error_details)
            status.update(label="❌ Search failed", state="error")
            st.error(f"Search failed: {e}\n\nCheck the log above for details.")

# ----------------------------------------------------------------------
# Download button (appears after search)
# ----------------------------------------------------------------------
if st.session_state.get("temp_dir_ready") and st.session_state.get("scenes_for_download"):
    if st.button("📥 Download ZIP", type="primary"):
        all_scenes = st.session_state.scenes_for_download
        features_for_download = st.session_state.features_for_download
        
        with st.status("Creating download package...", expanded=True) as status:
            try:
                temp_dir = Path(tempfile.mkdtemp(prefix="sasclouds_"))
                features = []
                for idx, (scene, feat) in enumerate(zip(all_scenes, features_for_download)):
                    status.write(f"Processing scene {idx+1}/{len(all_scenes)}...")
                    sat = scene["satelliteId"]
                    sensor = scene["sensorId"]
                    date_str = datetime.fromtimestamp(scene["acquisitionTime"]/1000).strftime("%Y-%m-%d")
                    cloud = scene["cloudPercent"]
                    prod_id = scene["productId"]
                    footprint = feat["geometry"]
                    quickview_url = feat["properties"]["quickview"]
                    img_name = f"{sat}_{sensor}_{date_str}_{prod_id}.jpg"
                    img_path = temp_dir / img_name
                    
                    client = SASCloudsAPIClient()
                    if client.download_and_georeference(quickview_url, footprint, img_path):
                        status.write(f"  Downloaded {img_name}")
                    else:
                        status.write(f"  Failed {img_name}")
                    
                    features.append({
                        "type": "Feature",
                        "geometry": footprint,
                        "properties": {
                            "satellite": sat,
                            "sensor": sensor,
                            "date": date_str,
                            "cloud_cover": cloud,
                            "product_id": prod_id,
                            "image": img_name
                        }
                    })
                
                geojson_path = temp_dir / "footprints.geojson"
                with open(geojson_path, "w") as f:
                    json.dump({"type": "FeatureCollection", "features": features}, f, indent=2)
                
                zip_buffer = io.BytesIO()
                with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
                    for file in temp_dir.rglob("*"):
                        zf.write(file, arcname=file.relative_to(temp_dir))
                zip_buffer.seek(0)
                
                shutil.rmtree(temp_dir, ignore_errors=True)
                status.update(label="✅ Package ready", state="complete")
                st.download_button(
                    label="📥 Download ZIP",
                    data=zip_buffer.getvalue(),
                    file_name=f"sasclouds_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip",
                    mime="application/zip",
                    use_container_width=True
                )
                # Clear session state to avoid re-downloading the same data
                st.session_state.temp_dir_ready = False
                st.session_state.scenes_for_download = None
                st.session_state.features_for_download = None
            except Exception as e:
                st.error(f"Failed to create ZIP: {e}")