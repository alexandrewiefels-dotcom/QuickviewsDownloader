# File: search_logic.py
import json
import tempfile
import zipfile
import io
import shutil
import traceback
from pathlib import Path
from datetime import datetime
import streamlit as st
import pandas as pd
from sasclouds_api_scraper import SASCloudsAPIClient, log_search, log_aoi_upload
from map_utils import show_footprints_map

def date_to_ms(dt):
    return int(dt.timestamp() * 1000)

def run_search(polygon_geojson, aoi_filename, start_date, end_date, max_cloud, selected_satellites, session_id, log_container):
    """Execute the search, display results (table, map), and store data for download."""
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
            log_aoi_upload(session_id, aoi_filename, polygon_geojson)

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
                return

            add_log("Logging search...")
            log_search(
                session_id,
                polygon_geojson,
                {
                    "satellites": selected_satellites,
                    "cloud_max": max_cloud,
                    "date_range": [start_date.isoformat(), end_date.isoformat()]
                },
                len(all_scenes)
            )

            # Build table and map data
            features_for_map = []
            table_data = []
            for scene in all_scenes:
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
                table_data.append({
                    "Name": f"{sat} {sensor}",
                    "Date": date_str,
                    "Cloud (%)": cloud,
                    "Product ID": prod_id,
                    "Quickview": f'<a href="{quickview_url}" target="_blank">🔗</a>'
                })
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
            st.markdown(df.to_html(escape=False, index=False), unsafe_allow_html=True)
            
            # Display map
            st.subheader("🗺️ Footprint Map")
            show_footprints_map(features_for_map)
            
            # Store data for download
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

def create_download_zip():
    """Create a ZIP file from stored scenes and provide download button."""
    if not st.session_state.get("temp_dir_ready") or not st.session_state.get("scenes_for_download"):
        return
    
    all_scenes = st.session_state.scenes_for_download
    features_for_download = st.session_state.features_for_download
    
    if st.button("📥 Download ZIP", type="primary"):
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
                # Clear session state after download
                st.session_state.temp_dir_ready = False
                st.session_state.scenes_for_download = None
                st.session_state.features_for_download = None
            except Exception as e:
                st.error(f"Failed to create ZIP: {e}")