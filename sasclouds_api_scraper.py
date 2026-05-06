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

from sasclouds_api_scraper import SASCloudsAPIClient, log_search, log_aoi_upload

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
# Satellite and sensor definitions (same as before – keep it correct)
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
    1. Draw your AOI (bounding box or upload a GeoJSON polygon).
    2. Select date range, cloud cover, and satellites/sensors.
    3. Click **Search and Download** – the API will return all scenes.
    4. Results are zipped and downloaded (images + world files + GeoJSON).
    """)

# ----------------------------------------------------------------------
# AOI input
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
    aoi_filename = "bbox"
else:
    uploaded_geo = st.file_uploader("Upload GeoJSON polygon", type=["geojson"])
    if uploaded_geo:
        polygon_geojson = json.load(uploaded_geo)
        aoi_filename = uploaded_geo.name
        st.success("Polygon loaded")
    else:
        polygon_geojson = None
        aoi_filename = None

# ----------------------------------------------------------------------
# Filters
# ----------------------------------------------------------------------
col1, col2 = st.columns(2)
with col1:
    start_date = st.date_input("Start date", value=datetime(2025, 1, 1))
    end_date = st.date_input("End date", value=datetime(2026, 4, 11))
with col2:
    max_cloud = st.slider("Maximum cloud cover (%)", 0, 100, 20)

# ----------------------------------------------------------------------
# Satellite selection
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
# Search and download with detailed logging
# ----------------------------------------------------------------------
if st.button("🔍 Search and Download", type="primary"):
    if not polygon_geojson:
        st.error("Please provide an AOI (bounding box or GeoJSON polygon).")
        st.stop()

    if not selected_satellites:
        st.warning("No satellites selected. Please choose at least one.")
        st.stop()

    # Create a container to capture logs
    log_container = st.empty()
    log_lines = []

    def add_log(msg):
        log_lines.append(msg)
        log_container.code("\n".join(log_lines[-30:]), language="bash")

    with st.status("Processing...", expanded=True) as status:
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

            temp_dir = Path(tempfile.mkdtemp(prefix="sasclouds_"))
            add_log(f"Created temporary directory: {temp_dir}")
            features = []

            for idx, scene in enumerate(all_scenes):
                status.write(f"Processing scene {idx+1}/{len(all_scenes)}...")
                add_log(f"Processing scene {idx+1}/{len(all_scenes)}...")
                sat = scene["satelliteId"]
                sensor = scene["sensorId"]
                date_str = datetime.fromtimestamp(scene["acquisitionTime"]/1000).strftime("%Y-%m-%d")
                cloud = scene["cloudPercent"]
                prod_id = scene["productId"]
                footprint = json.loads(scene["boundary"])
                quickview_url = scene["quickViewUri"].replace(
                    "http://quickview.sasclouds.com",
                    "https://quickview.obs.cn-north-10.myhuaweicloud.com"
                )
                img_name = f"{sat}_{sensor}_{date_str}_{prod_id}.jpg"
                img_path = temp_dir / img_name

                add_log(f"  Downloading {img_name} from {quickview_url[:80]}...")
                if client.download_and_georeference(quickview_url, footprint, img_path):
                    add_log(f"  ✅ Downloaded {img_name}")
                else:
                    add_log(f"  ❌ Failed {img_name}")

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
            add_log(f"GeoJSON saved: {geojson_path}")

            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
                for file in temp_dir.rglob("*"):
                    zf.write(file, arcname=file.relative_to(temp_dir))
            zip_buffer.seek(0)
            add_log(f"ZIP created, size: {len(zip_buffer.getvalue())} bytes")

            shutil.rmtree(temp_dir, ignore_errors=True)
            add_log("Temporary directory cleaned up")

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
            error_details = traceback.format_exc()
            status.write(f"❌ Error: {e}")
            status.write(f"Details:\n{error_details}")
            add_log(f"❌ EXCEPTION: {e}")
            add_log(error_details)
            status.update(label="❌ Failed", state="error")
            st.error(f"Search failed: {e}\n\nCheck the log above for details.")