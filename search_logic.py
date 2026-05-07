# File: search_logic.py
import io
import json
import logging
import shutil
import tempfile
import time
import traceback
import zipfile
from datetime import date as _date, datetime
from pathlib import Path

import pandas as pd
import streamlit as st

from sasclouds_api_scraper import SASCloudsAPIClient, log_aoi_upload, log_search, _log_event

logger = logging.getLogger(__name__)


def _date_to_ms(dt) -> int:
    """Convert date or datetime to Unix milliseconds."""
    if isinstance(dt, _date) and not isinstance(dt, datetime):
        dt = datetime(dt.year, dt.month, dt.day)
    return int(dt.timestamp() * 1000)


# ── Search ────────────────────────────────────────────────────────────────────

def run_search(polygon_geojson, aoi_filename, start_date, end_date,
               max_cloud, selected_satellites, session_id, log_container):
    """
    Execute a full search against the SASClouds API:
      1. Upload AOI shapefile → get uploadId
      2. Paginate through scene results
      3. Build results table + map features
      4. Store everything in session_state for the map and download

    Progress is logged to the terminal (via logging) AND shown in the Streamlit
    UI log container for live feedback.
    """
    t0 = time.time()
    log_lines: list[str] = []

    def add_log(msg: str, level: str = "info"):
        """Append to the UI log pane and emit to the Python logger."""
        log_lines.append(msg)
        log_container.code("\n".join(log_lines[-40:]), language="bash")
        getattr(logger, level)(msg)

    with st.status("Searching…", expanded=True) as status:
        try:
            client = SASCloudsAPIClient()

            # ── 1. Upload AOI ─────────────────────────────────────────
            add_log("▶ [1/4] Uploading AOI shapefile…")
            status.write("Uploading AOI…")
            t1 = time.time()
            upload_id = client.upload_aoi(polygon_geojson)
            add_log(f"  ✓ AOI uploaded in {time.time()-t1:.2f}s → uploadId={upload_id}")
            status.write(f"AOI uploaded (ID: {upload_id})")
            log_aoi_upload(session_id, aoi_filename, polygon_geojson)

            # ── 2. Search params summary ──────────────────────────────
            start_ms = _date_to_ms(start_date)
            end_ms   = _date_to_ms(end_date)
            sat_names = [s["satelliteId"] for s in selected_satellites]
            add_log(f"▶ [2/4] Search parameters:")
            add_log(f"  Date range : {start_date} → {end_date}")
            add_log(f"  Cloud cover: ≤ {max_cloud}%")
            add_log(f"  Satellites : {len(selected_satellites)} selected")
            add_log(f"  {', '.join(sat_names)}")
            logger.info(
                f"Search params | uploadId={upload_id} | "
                f"{start_date}→{end_date} | cloud≤{max_cloud}% | "
                f"satellites({len(selected_satellites)})={sat_names}"
            )

            # ── 3. Paginate scenes ────────────────────────────────────
            add_log("▶ [3/4] Fetching scenes (paginated)…")
            status.write("Fetching scenes…")
            all_scenes: list = []
            page = 1
            page_size = 50
            total_expected = None

            while True:
                add_log(f"  → Page {page} (page_size={page_size}, fetched so far={len(all_scenes)})…")
                status.write(f"Fetching page {page}…")
                t_page = time.time()

                result = client.search_scenes(
                    upload_id, start_ms, end_ms, max_cloud,
                    selected_satellites, page, page_size,
                )
                elapsed_page = time.time() - t_page

                if result.get("code") != 0:
                    msg = result.get("message", "Unknown API error")
                    add_log(f"  ✗ API error on page {page}: {msg}", "error")
                    raise Exception(f"API returned error: {msg}")

                scenes = result.get("data", [])
                page_info = result.get("pageInfo", {})
                if total_expected is None:
                    total_expected = page_info.get("total", 0)
                    add_log(f"  Total scenes reported by API: {total_expected}")

                add_log(
                    f"  ✓ Page {page}: {len(scenes)} scenes returned | "
                    f"cumulative={len(all_scenes)+len(scenes)}/{total_expected} | "
                    f"{elapsed_page:.2f}s"
                )
                logger.info(
                    f"Page {page}: {len(scenes)} scenes | "
                    f"cumulative={len(all_scenes)+len(scenes)}/{total_expected} | "
                    f"{elapsed_page:.2f}s"
                )

                if not scenes:
                    add_log(f"  Empty page {page} – stopping pagination")
                    break

                all_scenes.extend(scenes)

                if len(all_scenes) >= (total_expected or 0):
                    add_log(f"  All {total_expected} scenes fetched after {page} page(s)")
                    break

                page += 1

            total_search_time = time.time() - t0
            add_log(
                f"▶ Pagination complete: {len(all_scenes)} scenes | "
                f"{page} page(s) | {total_search_time:.1f}s total"
            )
            status.write(f"Found {len(all_scenes)} scenes.")
            logger.info(
                f"Search complete | {len(all_scenes)} scenes | "
                f"{page} pages | {total_search_time:.2f}s"
            )

            if not all_scenes:
                st.warning("No scenes found. Try adjusting date range, cloud cover, or AOI.")
                logger.warning("Search returned 0 scenes")
                status.update(label="⚠ No scenes found", state="complete")
                return

            log_search(
                session_id,
                polygon_geojson,
                {
                    "satellites": selected_satellites,
                    "cloud_max": max_cloud,
                    "date_range": [start_date.isoformat(), end_date.isoformat()],
                },
                len(all_scenes),
            )

            # ── 4. Build table + map features ─────────────────────────
            add_log(f"▶ [4/4] Processing {len(all_scenes)} scenes…")
            features_for_map: list = []
            table_data: list = []
            parse_errors = 0

            for idx, scene in enumerate(all_scenes):
                sat     = scene.get("satelliteId", "")
                sensor  = scene.get("sensorId", "")
                acq_ms  = scene.get("acquisitionTime", 0)
                cloud   = scene.get("cloudPercent", 0)
                prod_id = scene.get("productId", "")
                qv_raw  = scene.get("quickViewUri", "")

                date_str = datetime.fromtimestamp(acq_ms / 1000).strftime("%Y-%m-%d")

                try:
                    footprint = json.loads(scene.get("boundary", "{}"))
                except json.JSONDecodeError:
                    logger.warning(
                        f"Scene {idx+1}/{len(all_scenes)}: invalid boundary JSON "
                        f"for {prod_id} – skipping"
                    )
                    parse_errors += 1
                    continue

                quickview_url = qv_raw.replace(
                    "http://quickview.sasclouds.com",
                    "https://quickview.obs.cn-north-10.myhuaweicloud.com",
                )
                logger.debug(
                    f"  Scene {idx+1}/{len(all_scenes)}: {sat}/{sensor} | "
                    f"{date_str} | cloud={cloud}% | prod={prod_id}"
                )

                table_data.append({
                    "Satellite/Sensor": f"{sat} {sensor}",
                    "Date": date_str,
                    "Cloud (%)": cloud,
                    "Product ID": prod_id,
                    "Quickview": f'<a href="{quickview_url}" target="_blank">🔗 View</a>',
                })
                features_for_map.append({
                    "geometry": footprint,
                    "properties": {
                        "satellite":  sat,
                        "sensor":     sensor,
                        "date":       date_str,
                        "cloud":      cloud,
                        "product_id": prod_id,
                        "quickview":  quickview_url,
                    },
                })

            if parse_errors:
                add_log(f"  ⚠ {parse_errors} scene(s) skipped (boundary JSON error)", "warning")

            add_log(
                f"  Built table: {len(table_data)} rows | "
                f"map features: {len(features_for_map)} polygons | "
                f"parse errors: {parse_errors}"
            )
            logger.info(
                f"Results built | table_rows={len(table_data)} | "
                f"map_features={len(features_for_map)} | parse_errors={parse_errors}"
            )
            _log_event(
                "search_complete",
                session_id=session_id,
                upload_id=upload_id,
                aoi_filename=aoi_filename,
                date_start=str(start_date),
                date_end=str(end_date),
                cloud_max=max_cloud,
                satellite_ids=[s["satelliteId"] for s in selected_satellites],
                pages_fetched=page,
                total_scenes=len(all_scenes),
                table_rows=len(table_data),
                parse_errors=parse_errors,
                elapsed_s=round(time.time() - t0, 2),
            )

            # ── Display results table ─────────────────────────────────
            st.subheader(f"📋 Search Results ({len(table_data)} scenes)")
            df = pd.DataFrame(table_data)
            st.markdown(df.to_html(escape=False, index=False), unsafe_allow_html=True)

            # ── Persist in session_state ──────────────────────────────
            st.session_state["scenes_for_download"]   = all_scenes
            st.session_state["features_for_download"] = features_for_map
            st.session_state["features_for_map"]      = features_for_map  # read by main map
            st.session_state["temp_dir_ready"]        = True

            add_log(f"✅ Search done. {len(all_scenes)} scenes ready. Scroll down to see footprints on the map.")
            status.update(
                label=f"✅ {len(all_scenes)} scenes found in {total_search_time:.1f}s",
                state="complete",
            )

        except Exception as exc:
            status.update(label="✗ Search failed", state="error")
            add_log(f"✗ EXCEPTION: {exc}", "error")
            logger.error(f"Search failed: {exc}", exc_info=True)
            st.error(f"Search failed: {exc}\n\n{traceback.format_exc()}")


# ── Download ──────────────────────────────────────────────────────────────────

def create_download_zip():
    """Download all quickview images, georeference them, and bundle as a ZIP."""
    if not st.session_state.get("temp_dir_ready") or not st.session_state.get("scenes_for_download"):
        return

    all_scenes            = st.session_state["scenes_for_download"]
    features_for_download = st.session_state["features_for_download"]

    if not st.button("📥 Prepare & Download ZIP", type="primary"):
        return

    with st.status("Creating download package…", expanded=True) as status:
        try:
            temp_dir = Path(tempfile.mkdtemp(prefix="sasclouds_"))
            logger.info(f"Download package: {len(all_scenes)} scenes → {temp_dir}")
            client = SASCloudsAPIClient()
            features_out: list = []
            ok = 0
            fail = 0

            for idx, (scene, feat) in enumerate(zip(all_scenes, features_for_download)):
                sat      = scene["satelliteId"]
                sensor   = scene["sensorId"]
                date_str = datetime.fromtimestamp(scene["acquisitionTime"] / 1000).strftime("%Y-%m-%d")
                cloud    = scene["cloudPercent"]
                prod_id  = scene["productId"]
                footprint = feat["geometry"]
                qv_url   = feat["properties"]["quickview"]
                img_name = f"{sat}_{sensor}_{date_str}_{prod_id}.jpg"
                img_path = temp_dir / img_name

                status.write(f"[{idx+1}/{len(all_scenes)}] {img_name}")
                logger.info(f"[{idx+1}/{len(all_scenes)}] Downloading {img_name}")

                if client.download_and_georeference(qv_url, footprint, img_path):
                    ok += 1
                    logger.debug(f"  ✓ {img_name}")
                else:
                    fail += 1
                    logger.warning(f"  ✗ Failed to download/georeference {img_name}")

                features_out.append({
                    "type": "Feature",
                    "geometry": footprint,
                    "properties": {
                        "satellite":   sat,
                        "sensor":      sensor,
                        "date":        date_str,
                        "cloud_cover": cloud,
                        "product_id":  prod_id,
                        "image":       img_name,
                    },
                })

            logger.info(f"Downloads complete: {ok} ok, {fail} failed")
            _log_event(
                "download_batch_complete",
                total=len(all_scenes),
                ok=ok,
                failed=fail,
            )

            geojson_path = temp_dir / "footprints.geojson"
            with open(geojson_path, "w") as f:
                json.dump({"type": "FeatureCollection", "features": features_out}, f, indent=2)
            logger.info(f"footprints.geojson written ({len(features_out)} features)")

            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
                for file in temp_dir.rglob("*"):
                    zf.write(file, arcname=file.relative_to(temp_dir))
            zip_buffer.seek(0)
            shutil.rmtree(temp_dir, ignore_errors=True)

            status.update(
                label=f"✅ Package ready – {ok} images downloaded, {fail} failed",
                state="complete",
            )
            logger.info("ZIP package ready for download")

            st.download_button(
                label="📥 Download ZIP",
                data=zip_buffer.getvalue(),
                file_name=f"sasclouds_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip",
                mime="application/zip",
                use_container_width=True,
            )

            # Clear download state but keep footprints on the map
            st.session_state["temp_dir_ready"]        = False
            st.session_state["scenes_for_download"]   = None
            st.session_state["features_for_download"] = None

        except Exception as exc:
            logger.error(f"ZIP creation failed: {exc}", exc_info=True)
            st.error(f"Failed to create ZIP: {exc}")
