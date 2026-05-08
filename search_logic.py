# File: search_logic.py
import io
import json
import logging
import shutil
import tempfile
import time
import zipfile
from datetime import date as _date, datetime
from pathlib import Path

import pandas as pd
import streamlit as st

from sasclouds_api_scraper import SASCloudsAPIClient, log_aoi_upload, log_search, _log_event

logger = logging.getLogger(__name__)

_TABLE_PAGE_SIZE = 20


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
      4. Store everything in session_state for the table and map
    """
    t0 = time.time()
    log_lines: list[str] = []

    def _ts() -> str:
        return datetime.now().strftime("%H:%M:%S")

    def add_log(msg: str, level: str = "info"):
        stamped = f"[{_ts()}] {msg}"
        log_lines.append(stamped)
        log_container.code("\n".join(log_lines[-60:]), language="bash")
        getattr(logger, level)(msg)

    progress = st.progress(0, text="Initialising…")

    # Clear table state from any previous search
    for key in list(st.session_state.keys()):
        if key.startswith("chk_") or key.startswith("eye_"):
            del st.session_state[key]
    st.session_state.pop("results_page", None)
    st.session_state.pop("preview_indices", None)

    with st.status("Searching…", expanded=True) as status:
        try:
            # ── 1. Upload AOI ─────────────────────────────────────────
            add_log("▶ [1/4] Building and uploading AOI shapefile…")
            progress.progress(5, text="Uploading AOI shapefile…")
            t1 = time.time()

            try:
                client = SASCloudsAPIClient()
                upload_id = client.upload_aoi(polygon_geojson)
            except Exception as exc:
                add_log(f"  ✗ Upload failed: {exc}", "error")
                raise

            elapsed1 = time.time() - t1
            add_log(f"  ✓ Uploaded in {elapsed1:.2f}s  →  uploadId={upload_id}")
            progress.progress(15, text=f"AOI uploaded ({elapsed1:.1f}s) — querying scenes…")
            log_aoi_upload(session_id, aoi_filename, polygon_geojson)

            # ── 2. Log search parameters ──────────────────────────────
            start_ms  = _date_to_ms(start_date)
            end_ms    = _date_to_ms(end_date)
            sat_names = [s["satelliteId"] for s in selected_satellites]
            add_log(f"▶ [2/4] Search parameters:")
            add_log(f"  Date range : {start_date}  →  {end_date}")
            add_log(f"  Cloud cover: ≤ {max_cloud}%")
            add_log(f"  Satellites : {len(sat_names)}  —  {', '.join(sat_names)}")
            logger.info(
                f"Search | uploadId={upload_id} | "
                f"{start_date}→{end_date} | cloud≤{max_cloud}% | sats={sat_names}"
            )

            # ── 3. Paginate scenes ────────────────────────────────────
            add_log("▶ [3/4] Fetching scenes (paginated)…")
            all_scenes: list = []
            page = 1
            page_size = 50
            total_expected = None

            while True:
                add_log(f"  → Requesting page {page}  (have {len(all_scenes)} scenes so far)…")
                progress.progress(
                    15 if total_expected is None else min(15 + int(70 * len(all_scenes) / max(total_expected, 1)), 85),
                    text=f"Fetching page {page}…  ({len(all_scenes)}/{total_expected or '?'} scenes)",
                )
                t_page = time.time()

                try:
                    result = client.search_scenes(
                        upload_id, start_ms, end_ms, max_cloud,
                        selected_satellites, page, page_size,
                    )
                except Exception as exc:
                    add_log(f"  ✗ Network error on page {page}: {exc}", "error")
                    raise

                elapsed_page = time.time() - t_page
                api_code = result.get("code")

                if api_code != 0:
                    msg = result.get("message", "Unknown API error")
                    add_log(
                        f"  ✗ API returned code={api_code} on page {page}: {msg}",
                        "error",
                    )
                    raise Exception(f"API error (code {api_code}): {msg}")

                scenes    = result.get("data", [])
                page_info = result.get("pageInfo", {})

                if total_expected is None:
                    total_expected = page_info.get("total", 0)
                    add_log(f"  Total scenes reported by API: {total_expected}")

                all_scenes.extend(scenes)
                fetched = len(all_scenes)

                add_log(
                    f"  ✓ Page {page}: {len(scenes)} scenes  |  "
                    f"cumulative {fetched}/{total_expected}  |  {elapsed_page:.2f}s"
                )
                logger.info(
                    f"Page {page}: {len(scenes)} scenes | cumulative {fetched}/{total_expected} | {elapsed_page:.2f}s"
                )

                if not scenes or fetched >= (total_expected or 0):
                    reason = "empty page" if not scenes else f"all {total_expected} scenes fetched"
                    add_log(f"  Stopping pagination — {reason} (page {page})")
                    break

                page += 1

            total_search_time = time.time() - t0
            add_log(
                f"▶ Pagination done: {len(all_scenes)} scenes  |  "
                f"{page} page(s)  |  {total_search_time:.1f}s total"
            )
            logger.info(
                f"Search complete | {len(all_scenes)} scenes | {page} pages | {total_search_time:.2f}s"
            )

            if not all_scenes:
                progress.progress(100, text="No scenes found")
                st.warning("No scenes found. Try a wider date range, higher cloud limit, or a different AOI.")
                logger.warning("Search returned 0 scenes")
                status.update(label="No scenes found", state="complete")
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

            # ── 4. Build features ─────────────────────────────────────
            add_log(f"▶ [4/4] Processing {len(all_scenes)} scenes…")
            progress.progress(88, text=f"Processing {len(all_scenes)} scenes…")
            features_for_map: list = []
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
                        f"Scene {idx+1}/{len(all_scenes)}: invalid boundary JSON for {prod_id} — skipping"
                    )
                    parse_errors += 1
                    continue

                quickview_url = qv_raw.replace(
                    "http://quickview.sasclouds.com",
                    "https://quickview.obs.cn-north-10.myhuaweicloud.com",
                )

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
                add_log(f"  ⚠ {parse_errors} scene(s) skipped — invalid boundary JSON", "warning")

            add_log(
                f"  map features: {len(features_for_map)}  |  parse errors: {parse_errors}"
            )
            logger.info(
                f"Results built | features={len(features_for_map)} | parse_errors={parse_errors}"
            )
            _log_event(
                "search_complete",
                session_id=session_id,
                upload_id=upload_id,
                aoi_filename=aoi_filename,
                date_start=str(start_date),
                date_end=str(end_date),
                cloud_max=max_cloud,
                satellite_ids=sat_names,
                pages_fetched=page,
                total_scenes=len(all_scenes),
                parse_errors=parse_errors,
                elapsed_s=round(time.time() - t0, 2),
            )

            # ── Persist in session_state ──────────────────────────────
            st.session_state["scenes_for_download"]   = all_scenes
            st.session_state["features_for_download"] = features_for_map
            st.session_state["features_for_map"]      = features_for_map
            st.session_state["temp_dir_ready"]        = True

            progress.progress(100, text=f"Done — {len(all_scenes)} scenes ready")
            add_log(f"✅ Complete. {len(all_scenes)} scenes ready. Footprints visible on the map below.")
            status.update(
                label=f"✅ {len(all_scenes)} scenes found in {total_search_time:.1f}s",
                state="complete",
            )

        except Exception as exc:
            elapsed = time.time() - t0
            progress.progress(100, text="Search failed")
            status.update(label="Search failed", state="error")
            add_log(f"✗ FAILED after {elapsed:.1f}s: {exc}", "error")
            logger.error(f"Search failed after {elapsed:.1f}s: {exc}", exc_info=True)
            st.error(f"**Search failed:** {exc}")


# ── Results table ─────────────────────────────────────────────────────────────

def render_results_table():
    """Interactive results table: per-scene selection, quickview preview, download."""
    all_scenes = st.session_state.get("scenes_for_download") or []
    features   = st.session_state.get("features_for_download") or []
    if not all_scenes:
        return

    n       = len(all_scenes)
    n_pages = max(1, (n + _TABLE_PAGE_SIZE - 1) // _TABLE_PAGE_SIZE)
    page    = max(0, min(st.session_state.get("results_page", 0), n_pages - 1))

    # Collect current selection from Streamlit checkbox widget state
    sel_indices = [i for i in range(n) if st.session_state.get(f"chk_{i}", False)]
    n_sel = len(sel_indices)

    # ── Header + controls ─────────────────────────────────────────────────────
    st.subheader(f"📋 Results — {n} scenes")

    ctl = st.columns([1, 1, 3, 1, 1, 1])
    if ctl[0].button("Select All", use_container_width=True):
        for i in range(n):
            st.session_state[f"chk_{i}"] = True
        st.rerun()
    if ctl[1].button("Deselect All", use_container_width=True):
        for i in range(n):
            st.session_state[f"chk_{i}"] = False
        st.rerun()
    ctl[2].caption(f"{n_sel} of {n} selected")
    if n_pages > 1:
        if ctl[3].button("◀", disabled=page == 0):
            st.session_state.results_page = page - 1
            st.rerun()
        ctl[4].caption(f"p. {page + 1}/{n_pages}")
        if ctl[5].button("▶", disabled=page >= n_pages - 1):
            st.session_state.results_page = page + 1
            st.rerun()

    # ── Column headers ────────────────────────────────────────────────────────
    W = [0.35, 1.4, 1.1, 1.5, 0.75, 0.55]
    hdr = st.columns(W)
    for col, label in zip(hdr, ["", "Satellite", "Sensor", "Date", "Cloud %", ""]):
        col.markdown(f"**{label}**")
    st.divider()

    # ── Data rows ─────────────────────────────────────────────────────────────
    start = page * _TABLE_PAGE_SIZE
    end   = min(start + _TABLE_PAGE_SIZE, n)

    for idx in range(start, end):
        scene = all_scenes[idx]
        sat   = scene.get("satelliteId", "")
        sen   = scene.get("sensorId", "")
        dt    = datetime.fromtimestamp(scene.get("acquisitionTime", 0) / 1000).strftime("%Y-%m-%d")
        cld   = scene.get("cloudPercent", 0)

        row = st.columns(W)
        row[0].checkbox("Select", key=f"chk_{idx}", label_visibility="collapsed")
        row[1].write(sat)
        row[2].write(sen)
        row[3].write(dt)
        row[4].write(f"{cld:.1f}")

        preview_indices = st.session_state.get("preview_indices") or set()
        preview_active = idx in preview_indices
        eye_label = "🔍" if preview_active else "👁️"
        if row[5].button(eye_label, key=f"eye_{idx}", help="Show quickview on map"):
            pset = set(st.session_state.get("preview_indices") or set())
            pset.discard(idx) if idx in pset else pset.add(idx)
            st.session_state["preview_indices"] = pset
            st.rerun()

    # ── Action buttons ────────────────────────────────────────────────────────
    st.divider()
    bc = st.columns(3)

    with bc[0]:
        if st.button(
            f"📥 Download Selected ({n_sel})",
            type="primary",
            disabled=n_sel == 0,
            use_container_width=True,
        ):
            _do_download_zip(
                [all_scenes[i] for i in sel_indices],
                [features[i] for i in sel_indices],
            )

    with bc[1]:
        if st.button(
            "🗺️ Show Selected on Map",
            disabled=n_sel == 0,
            use_container_width=True,
        ):
            st.session_state["features_for_map"] = [features[i] for i in sel_indices]
            st.rerun()

    with bc[2]:
        if st.button("📥 Download All", use_container_width=True):
            _do_download_zip(all_scenes, features)


# ── Download ──────────────────────────────────────────────────────────────────

def _do_download_zip(scenes: list, features: list):
    """Download quickviews for the given scenes and serve a ZIP."""
    if not scenes:
        st.warning("No scenes to download.")
        return

    with st.status(f"Creating download package — {len(scenes)} scenes…", expanded=True) as status:
        try:
            temp_dir = Path(tempfile.mkdtemp(prefix="sasclouds_"))
            logger.info(f"Download package: {len(scenes)} scenes → {temp_dir}")
            client = SASCloudsAPIClient()
            features_out: list = []
            ok = fail = 0

            for idx, (scene, feat) in enumerate(zip(scenes, features)):
                sat      = scene["satelliteId"]
                sensor   = scene["sensorId"]
                date_str = datetime.fromtimestamp(scene["acquisitionTime"] / 1000).strftime("%Y-%m-%d")
                cloud    = scene["cloudPercent"]
                prod_id  = scene["productId"]
                footprint = feat["geometry"]
                qv_url   = feat["properties"]["quickview"]
                img_name = f"{sat}_{sensor}_{date_str}_{prod_id}.jpg"
                img_path = temp_dir / img_name

                status.write(f"[{idx + 1}/{len(scenes)}] {img_name}")
                logger.info(f"[{idx + 1}/{len(scenes)}] Downloading {img_name}")

                if client.download_and_georeference(qv_url, footprint, img_path):
                    ok += 1
                else:
                    fail += 1
                    logger.warning(f"  ✗ Failed: {img_name}")

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
            _log_event("download_batch_complete", total=len(scenes), ok=ok, failed=fail)

            geojson_path = temp_dir / "footprints.geojson"
            with open(geojson_path, "w") as f:
                json.dump({"type": "FeatureCollection", "features": features_out}, f, indent=2)

            zip_buf = io.BytesIO()
            with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
                for file in temp_dir.rglob("*"):
                    zf.write(file, arcname=file.relative_to(temp_dir))
            zip_buf.seek(0)
            shutil.rmtree(temp_dir, ignore_errors=True)

            status.update(
                label=f"✅ Package ready — {ok} images, {fail} failed",
                state="complete",
            )
            logger.info("ZIP ready for download")

            st.download_button(
                label=f"📥 Download ZIP ({ok} images)",
                data=zip_buf.getvalue(),
                file_name=f"sasclouds_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip",
                mime="application/zip",
                use_container_width=True,
            )

        except Exception as exc:
            logger.error(f"ZIP creation failed: {exc}", exc_info=True)
            st.error(f"Failed to create ZIP: {exc}")


def create_download_zip():
    """Legacy entry point — kept for backward compatibility."""
    pass
