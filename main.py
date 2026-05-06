import streamlit as st
import json
import tempfile
import zipfile
import io
import shutil
from pathlib import Path
from datetime import datetime

from sasclouds_api_scraper import SASCloudsAPIClient, logger

st.set_page_config(page_title="SASClouds API Scraper", layout="wide")

# ----------------------------------------------------------------------
# Authentication
# ----------------------------------------------------------------------
PASSWORD = st.secrets.get("PASSWORD", "default_fallback")
if PASSWORD == "default_fallback":
    st.error("No PASSWORD found in secrets.")
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
# Satellite groups (same as before, but ensure sensorIds are lists)
# ----------------------------------------------------------------------
SATELLITE_GROUPS = {
    "Optical": {
        "2-meter": [
            {"satelliteId": "ZY3-1", "sensorIds": ["MUX"]},
            # ... (full list as before)
        ],
        # ... rest of groups
    },
    "Hyperspectral": {...},
    "SAR": {...},
    "Other": {...}
}

def flatten_satellites():
    options = []
    for group, cats in SATELLITE_GROUPS.items():
        for cat_name, sats in cats.items():
            for sat in sats:
                options.append({
                    "label": f"{sat['satelliteId']} ({', '.join(sat['sensorIds']) if sat['sensorIds'] else 'All'})",
                    "satelliteId": sat["satelliteId"],
                    "sensorIds": sat["sensorIds"]
                })
    return options

# ----------------------------------------------------------------------
# Helper: date to ms
# ----------------------------------------------------------------------
def date_to_ms(dt):
    return int(dt.timestamp() * 1000)

# ----------------------------------------------------------------------
# Main UI
# ----------------------------------------------------------------------
st.title("🛰️ SASClouds Resilient Scraper")
st.markdown("Uses the official API; auto‑detects version, validates schema, logs changes.")

# AOI input (simplified)
aoi_method = st.radio("AOI", ["Bounding box", "GeoJSON"])
if aoi_method == "Bounding box":
    col1, col2 = st.columns(2)
    with col1:
        min_lon = st.number_input("West", value=-73.0, format="%.6f")
        min_lat = st.number_input("South", value=8.0, format="%.6f")
    with col2:
        max_lon = st.number_input("East", value=-72.0, format="%.6f")
        max_lat = st.number_input("North", value=9.0, format="%.6f")
    polygon = {
        "type": "Polygon",
        "coordinates": [[[min_lon, min_lat], [max_lon, min_lat],
                         [max_lon, max_lat], [min_lon, max_lat], [min_lon, min_lat]]]
    }
else:
    uploaded = st.file_uploader("Upload GeoJSON", type=["geojson"])
    if uploaded:
        polygon = json.load(uploaded)
    else:
        polygon = None

# Filters
col1, col2 = st.columns(2)
with col1:
    start = st.date_input("Start", datetime(2025, 1, 1))
    end = st.date_input("End", datetime(2026, 4, 11))
with col2:
    cloud_max = st.slider("Max cloud %", 0, 100, 20)

# Satellite selection (grouped expanders – same as before)
st.subheader("Satellites & Sensors")
selected_satellites = []
for group_name, cats in SATELLITE_GROUPS.items():
    with st.expander(group_name):
        for cat_name, sats in cats.items():
            labels = [f"{s['satelliteId']} ({', '.join(s['sensorIds']) if s['sensorIds'] else 'All'})" for s in sats]
            chosen = st.multiselect(cat_name, labels, key=f"{group_name}_{cat_name}")
            for label in chosen:
                for s in sats:
                    if label.startswith(s["satelliteId"]):
                        selected_satellites.append({"satelliteId": s["satelliteId"], "sensorIds": s["sensorIds"]})
                        break

# ----------------------------------------------------------------------
# Search and download
# ----------------------------------------------------------------------
if st.button("🔍 Search and Download", type="primary"):
    if not polygon:
        st.error("Please provide an AOI.")
        st.stop()

    with st.status("Connecting to SASClouds API...", expanded=True) as status:
        try:
            client = SASCloudsAPIClient()
            status.write("Uploading AOI...")
            upload_id = client.upload_aoi(polygon)
            status.write(f"AOI uploaded, ID: {upload_id}")

            start_ms = date_to_ms(start)
            end_ms = date_to_ms(end)
            all_scenes = []
            page = 1
            while True:
                status.write(f"Fetching page {page}...")
                result = client.search_scenes(upload_id, start_ms, end_ms, cloud_max,
                                               selected_satellites, page, page_size=50)
                scenes = result.get("data", [])
                if not scenes:
                    break
                # Validate schema for first scene of first page
                if page == 1:
                    for s in scenes:
                        if not client.validate_scene(s):
                            st.error("API schema changed. Please contact the developer. Check logs for details.")
                            st.stop()
                all_scenes.extend(scenes)
                total = result["pageInfo"]["total"]
                if len(all_scenes) >= total:
                    break
                page += 1
            status.write(f"Total scenes found: {len(all_scenes)}")

            if not all_scenes:
                st.warning("No scenes found.")
                st.stop()

            temp_dir = Path(tempfile.mkdtemp(prefix="sasclouds_"))
            features = []
            for idx, scene in enumerate(all_scenes):
                status.write(f"Processing {idx+1}/{len(all_scenes)}...")
                footprint = json.loads(scene["boundary"])
                img_url = scene["quickViewUri"].replace("http://quickview.sasclouds.com",
                                                        "https://quickview.obs.cn-north-10.myhuaweicloud.com")
                img_name = f"{scene['satelliteId']}_{scene['sensorId']}_{datetime.fromtimestamp(scene['acquisitionTime']/1000).strftime('%Y%m%d')}_{scene['productId']}.jpg"
                img_path = temp_dir / img_name
                if client.download_and_georeference(img_url, footprint, img_path):
                    status.write(f"  Downloaded {img_name}")
                else:
                    status.write(f"  Failed {img_name}")
                features.append({
                    "type": "Feature",
                    "geometry": footprint,
                    "properties": {
                        "satellite": scene["satelliteId"],
                        "sensor": scene["sensorId"],
                        "date": datetime.fromtimestamp(scene["acquisitionTime"]/1000).strftime("%Y-%m-%d"),
                        "cloud_cover": scene["cloudPercent"],
                        "product_id": scene["productId"],
                        "image": img_name
                    }
                })

            geojson_path = temp_dir / "footprints.geojson"
            with open(geojson_path, "w") as f:
                json.dump({"type": "FeatureCollection", "features": features}, f, indent=2)

            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
                for f in temp_dir.rglob("*"):
                    zf.write(f, arcname=f.relative_to(temp_dir))
            zip_buffer.seek(0)
            shutil.rmtree(temp_dir, ignore_errors=True)

            status.update(label="✅ Done", state="complete")
            st.success(f"Found {len(all_scenes)} scenes. Download below.")
            st.download_button(
                label="📥 Download ZIP",
                data=zip_buffer.getvalue(),
                file_name=f"sasclouds_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip",
                mime="application/zip",
                use_container_width=True
            )
        except Exception as e:
            st.error(f"Error: {e}")
            logger.exception("Critical error in search pipeline")
            status.update(label="❌ Failed", state="error")