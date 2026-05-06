import streamlit as st
import json
import tempfile
import zipfile
import io
import shutil
from pathlib import Path
from datetime import datetime
import requests

from sasclouds_api_scraper import (
    date_to_ms, upload_aoi, search_scenes, download_and_georeference
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
# Satellite and sensor definitions (based on website UI)
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
            {"satelliteId": "GF3", "sensorIds": []},  # SAR sensors not listed
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

# Flatten for selection widget
def get_all_satellite_options():
    options = []
    for group, categories in SATELLITE_GROUPS.items():
        for cat_name, sats in categories.items():
            for sat in sats:
                options.append({
                    "label": f"{sat['satelliteId']} ({', '.join(sat['sensorIds']) if sat['sensorIds'] else '?'})",
                    "satelliteId": sat["satelliteId"],
                    "sensorIds": sat["sensorIds"]
                })
    return options

# ----------------------------------------------------------------------
# Main UI
# ----------------------------------------------------------------------
st.title("🛰️ SASClouds API Scraper")
st.markdown("Fast, cloud‑compatible search using the official API. No browser needed.")

with st.expander("How to use", expanded=False):
    st.markdown("""
    1. Draw your AOI on a map (or upload a GeoJSON polygon).
    2. Select date range, cloud cover, and satellites.
    3. Click **Search and Download** – the API will return all scenes.
    4. Results are zipped and downloaded (images + world files + GeoJSON).
    """)

# ----------------------------------------------------------------------
# AOI input (bbox or GeoJSON)
# ----------------------------------------------------------------------
aoi_method = st.radio("AOI input method", ["Bounding box", "GeoJSON polygon"])

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
else:
    uploaded_file = st.file_uploader("Upload GeoJSON polygon", type=["geojson"])
    if uploaded_file:
        polygon_geojson = json.load(uploaded_file)
        st.success("Polygon loaded")
    else:
        polygon_geojson = None

# ----------------------------------------------------------------------
# Filters
# ----------------------------------------------------------------------
col1, col2 = st.columns(2)
with col1:
    start_date = st.date_input("Start date", value=datetime(2025, 1, 1))
    end_date = st.date_input("End date", value=datetime(2026, 4, 11))
with col2:
    max_cloud = st.slider("Maximum cloud cover (%)", 0, 100, 20)

# Satellite selection (grouped by categories)
st.subheader("Satellites and sensors")
selected_satellites = []

# We'll build a multiselect per category for clarity
for group_name, categories in SATELLITE_GROUPS.items():
    with st.expander(group_name):
        for cat_name, sats in categories.items():
            options = [f"{s['satelliteId']} ({', '.join(s['sensorIds']) if s['sensorIds'] else 'any'})" for s in sats]
            selected = st.multiselect(cat_name, options, key=f"{group_name}_{cat_name}")
            for sel in selected:
                # Find the corresponding satellite dict
                for sat in sats:
                    label = f"{sat['satelliteId']} ({', '.join(sat['sensorIds']) if sat['sensorIds'] else 'any'})"
                    if label == sel:
                        selected_satellites.append({
                            "satelliteId": sat["satelliteId"],
                            "sensorIds": sat["sensorIds"]
                        })
                        break

# ----------------------------------------------------------------------
# Search and download
# ----------------------------------------------------------------------
if st.button("🔍 Search and Download", type="primary"):
    if not polygon_geojson:
        st.error("Please provide an AOI (bounding box or GeoJSON).")
        st.stop()

    with st.status("Processing...", expanded=True) as status:
        try:
            # 1. Upload AOI
            status.write("Uploading AOI...")
            upload_id = upload_aoi(polygon_geojson)
            status.write(f"AOI uploaded, ID: {upload_id}")

            # 2. Search all pages
            start_ms = date_to_ms(start_date.year, start_date.month, start_date.day)
            end_ms = date_to_ms(end_date.year, end_date.month, end_date.day)
            all_scenes = []
            page = 1
            page_size = 50
            while True:
                status.write(f"Fetching page {page}...")
                result = search_scenes(upload_id, start_ms, end_ms, max_cloud,
                                       selected_satellites, page, page_size)
                scenes = result.get("data", [])
                if not scenes:
                    break
                all_scenes.extend(scenes)
                total = result["pageInfo"]["total"]
                if len(all_scenes) >= total:
                    break
                page += 1
            status.write(f"Found {len(all_scenes)} scenes.")

            if not all_scenes:
                st.warning("No scenes found. Adjust your filters.")
                st.stop()

            # 3. Download images and create world files
            temp_dir = Path(tempfile.mkdtemp(prefix="sasclouds_"))
            features = []
            for idx, scene in enumerate(all_scenes):
                status.write(f"Processing scene {idx+1}/{len(all_scenes)}...")
                # Extract data
                sat = scene["satelliteId"]
                sensor = scene["sensorId"]
                date_str = datetime.fromtimestamp(scene["acquisitionTime"]/1000).strftime("%Y-%m-%d")
                cloud = scene["cloudPercent"]
                prod_id = scene["productId"]
                footprint = json.loads(scene["boundary"])  # GeoJSON
                quickview_url = scene["quickViewUri"].replace("http://quickview.sasclouds.com",
                                                              "https://quickview.obs.cn-north-10.myhuaweicloud.com")
                # Image name
                img_name = f"{sat}_{sensor}_{date_str}_{prod_id}.jpg"
                img_path = temp_dir / img_name
                if download_and_georeference(quickview_url, footprint, img_path):
                    status.write(f"  Downloaded {img_name}")
                else:
                    status.write(f"  Failed to download {img_name}")

                # Add to GeoJSON
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

            # 4. Create GeoJSON
            geojson_path = temp_dir / "footprints.geojson"
            with open(geojson_path, "w") as f:
                json.dump({"type": "FeatureCollection", "features": features}, f, indent=2)

            # 5. Zip results
            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
                for file in temp_dir.rglob("*"):
                    zf.write(file, arcname=file.relative_to(temp_dir))
            zip_buffer.seek(0)

            # Cleanup temp dir
            shutil.rmtree(temp_dir, ignore_errors=True)

            status.update(label="✅ Search complete", state="complete")
            st.success(f"Found {len(all_scenes)} scenes. Click below to download.")
            st.download_button(
                label="📥 Download ZIP",
                data=zip_buffer.getvalue(),
                file_name=f"sasclouds_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip",
                mime="application/zip",
                use_container_width=True
            )
        except Exception as e:
            st.error(f"Error: {e}")
            status.update(label="❌ Failed", state="error")