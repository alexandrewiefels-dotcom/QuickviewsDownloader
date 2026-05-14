# SASClouds search logic — API search, results table, download.
# Renamed from search_logic.py to avoid naming conflicts.
import io
import json
import logging
import re
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
    if isinstance(dt, _date) and not isinstance(dt, datetime):
        dt = datetime(dt.year, dt.month, dt.day)
    return int(dt.timestamp() * 1000)


# ── Search ────────────────────────────────────────────────────────────────────

def run_search(polygon_geojson, aoi_filename, start_date, end_date,
               max_cloud, selected_satellites, session_id, log_container,
               state_prefix: str = "sc"):
    """
    Execute a full search against the SASClouds API.
    Results stored in session_state with the given state_prefix.
    """
    t0 = time.time()
    log_lines: list[str] = []

    def _ts():
        return datetime.now().strftime("%H:%M:%S")

    def add_log(msg, level="info"):
        stamped = f"[{_ts()}] {msg}"
        log_lines.append(stamped)
        log_container.code("\n".join(log_lines[-60:]), language="bash")
        getattr(logger, level)(msg)

    progress = st.progress(0, text="Initialising…")

    for key in list(st.session_state.keys()):
        if key.startswith(f"{state_prefix}_chk_") or key.startswith(f"{state_prefix}_eye_"):
            del st.session_state[key]
    st.session_state.pop(f"{state_prefix}_results_page", None)
    st.session_state.pop(f"{state_prefix}_preview_indices", None)

    with st.status("Searching…", expanded=True) as status:
        try:
            add_log("▶ [1/4] Building and uploading AOI shapefile…")
            progress.progress(5, text="Uploading AOI shapefile…")
            t1 = time.time()
            client = SASCloudsAPIClient()
            upload_id = client.upload_aoi(polygon_geojson)
            elapsed1 = time.time() - t1
            add_log(f"  ✓ Uploaded in {elapsed1:.2f}s  →  uploadId={upload_id}")
            progress.progress(15, text=f"AOI uploaded ({elapsed1:.1f}s) — querying scenes…")
            log_aoi_upload(session_id, aoi_filename, polygon_geojson)

            start_ms = _date_to_ms(start_date)
            end_ms = _date_to_ms(end_date)
            sat_names = [s["satelliteId"] for s in selected_satellites]
            add_log(f"▶ [2/4] Date range: {start_date} → {end_date}  |  cloud ≤ {max_cloud}%  |  {len(sat_names)} satellites")

            add_log("▶ [3/4] Fetching scenes (paginated)…")
            all_scenes = []
            page = 1
            page_size = 50
            total_expected = None

            while True:
                add_log(f"  → Page {page}  ({len(all_scenes)} so far)…")
                progress.progress(
                    15 if total_expected is None else min(15 + int(70 * len(all_scenes) / max(total_expected, 1)), 85),
                    text=f"Fetching page {page}…  ({len(all_scenes)}/{total_expected or '?'} scenes)",
                )
                t_page = time.time()
                result = client.search_scenes(
                    upload_id, start_ms, end_ms, max_cloud,
                    selected_satellites, page, page_size,
                )
                elapsed_page = time.time() - t_page
                api_code = result.get("code")
                if api_code != 0:
                    msg = result.get("message", "Unknown API error")
                    add_log(f"  ✗ API code={api_code}: {msg}", "error")
                    raise Exception(f"API error (code {api_code}): {msg}")
                scenes = result.get("data", [])
                page_info = result.get("pageInfo", {})
                if total_expected is None:
                    total_expected = page_info.get("total", 0)
                    add_log(f"  Total scenes: {total_expected}")
                all_scenes.extend(scenes)
                fetched = len(all_scenes)
                add_log(f"  ✓ Page {page}: {len(scenes)} scenes  |  {fetched}/{total_expected}  |  {elapsed_page:.2f}s")
                if not scenes or fetched >= (total_expected or 0):
                    break
                page += 1

            total_time = time.time() - t0
            add_log(f"▶ Done: {len(all_scenes)} scenes  |  {page} page(s)  |  {total_time:.1f}s")

            if not all_scenes:
                progress.progress(100, text="No scenes found")
                st.warning("No scenes found. Try a wider date range, higher cloud limit, or a different AOI.")
                status.update(label="No scenes found", state="complete")
                return

            log_search(session_id, polygon_geojson,
                       {"satellites": selected_satellites, "cloud_max": max_cloud,
                        "date_range": [start_date.isoformat(), end_date.isoformat()]},
                       len(all_scenes))

            add_log(f"▶ [4/4] Processing {len(all_scenes)} scenes…")
            progress.progress(88, text=f"Processing {len(all_scenes)} scenes…")
            features_for_map = []
            parse_errors = 0

            for idx, scene in enumerate(all_scenes):
                sat = scene.get("satelliteId", "")
                sensor = scene.get("sensorId", "")
                acq_ms = scene.get("acquisitionTime", 0)
                cloud = scene.get("cloudPercent", 0)
                prod_id = scene.get("productId", "")
                qv_raw = scene.get("quickViewUri", "")
                date_str = datetime.fromtimestamp(acq_ms / 1000).strftime("%Y-%m-%d")
                try:
                    footprint = json.loads(scene.get("boundary", "{}"))
                except json.JSONDecodeError:
                    parse_errors += 1
                    continue
                quickview_url = qv_raw.replace(
                    "http://quickview.sasclouds.com",
                    "https://quickview.obs.cn-north-10.myhuaweicloud.com",
                )
                # Build a meaningful scene name from productId or fallback
                pid_str = (prod_id or "").strip()
                scene_name = pid_str if pid_str and pid_str.lower() != "none" else f"{sat}_{sensor}_{date_str}"
                features_for_map.append({
                    "geometry": footprint,
                    "properties": {
                        "satellite": sat, "sensor": sensor,
                        "date": date_str, "cloud": cloud,
                        "product_id": prod_id, "quickview": quickview_url,
                        "scene_name": scene_name,
                    },
                })

            if parse_errors:
                add_log(f"  ⚠ {parse_errors} scenes skipped (bad boundary JSON)", "warning")

            _log_event("search_complete", session_id=session_id, upload_id=upload_id,
                       aoi_filename=aoi_filename, date_start=str(start_date),
                       date_end=str(end_date), cloud_max=max_cloud,
                       satellite_ids=sat_names, pages_fetched=page,
                       total_scenes=len(all_scenes), parse_errors=parse_errors,
                       elapsed_s=round(time.time() - t0, 2))

            st.session_state[f"{state_prefix}_scenes"]              = all_scenes
            st.session_state[f"{state_prefix}_features_download"]   = features_for_map
            st.session_state[f"{state_prefix}_features_map"]        = features_for_map

            # Show all quickviews by default when the map loads
            st.session_state[f"{state_prefix}_preview_indices"] = set(range(len(features_for_map)))

            # Track this SASClouds search in the unified navigation system
            try:
                from navigation.tracker import track_sasclouds_search
                track_sasclouds_search(
                    satellites=sat_names,
                    cloud_max=max_cloud,
                    date_from=str(start_date),
                    date_to=str(end_date),
                    scenes_found=len(all_scenes),
                    aoi_filename=aoi_filename,
                )
            except Exception:
                pass

            progress.progress(100, text=f"Done — {len(all_scenes)} scenes")
            add_log(f"✅ Complete. {len(all_scenes)} scenes ready.")
            status.update(label=f"✅ {len(all_scenes)} scenes in {total_time:.1f}s", state="complete")

        except Exception as exc:
            elapsed = time.time() - t0
            progress.progress(100, text="Search failed")
            status.update(label="Search failed", state="error")
            add_log(f"✗ FAILED after {elapsed:.1f}s: {exc}", "error")
            logger.error(f"Search failed: {exc}", exc_info=True)
            st.error(f"**Search failed:** {exc}")


# ── Results table ─────────────────────────────────────────────────────────────

def render_results_table(state_prefix: str = "sc"):
    all_scenes = st.session_state.get(f"{state_prefix}_scenes") or []
    features   = st.session_state.get(f"{state_prefix}_features_download") or []
    if not all_scenes:
        return

    n = len(all_scenes)
    n_pages = max(1, (n + _TABLE_PAGE_SIZE - 1) // _TABLE_PAGE_SIZE)
    page = max(0, min(st.session_state.get(f"{state_prefix}_results_page", 0), n_pages - 1))

    sel_indices = [i for i in range(n) if st.session_state.get(f"{state_prefix}_chk_{i}", False)]
    n_sel = len(sel_indices)

    st.subheader(f"📋 Results — {n} scenes")

    ctl = st.columns([1, 1, 3, 1, 1, 1])
    if ctl[0].button("Select All", key=f"{state_prefix}_sel_all", use_container_width=True):
        for i in range(n):
            st.session_state[f"{state_prefix}_chk_{i}"] = True
        st.rerun()
    if ctl[1].button("Deselect All", key=f"{state_prefix}_desel_all", use_container_width=True):
        for i in range(n):
            st.session_state[f"{state_prefix}_chk_{i}"] = False
        st.rerun()
    ctl[2].caption(f"{n_sel} of {n} selected")
    if n_pages > 1:
        if ctl[3].button("◀", key=f"{state_prefix}_prev", disabled=page == 0):
            st.session_state[f"{state_prefix}_results_page"] = page - 1
            st.rerun()
        ctl[4].caption(f"p. {page + 1}/{n_pages}")
        if ctl[5].button("▶", key=f"{state_prefix}_next", disabled=page >= n_pages - 1):
            st.session_state[f"{state_prefix}_results_page"] = page + 1
            st.rerun()

    W = [0.35, 1.2, 1.0, 2.5, 1.2, 0.65, 0.55]
    hdr = st.columns(W)
    for col, label in zip(hdr, ["", "Satellite", "Sensor", "Scene Name", "Date", "Cloud %", ""]):
        col.markdown(f"**{label}**")
    st.divider()

    start = page * _TABLE_PAGE_SIZE
    end = min(start + _TABLE_PAGE_SIZE, n)

    for idx in range(start, end):
        scene = all_scenes[idx]
        sat = scene.get("satelliteId", "")
        sen = scene.get("sensorId", "")
        dt = datetime.fromtimestamp(scene.get("acquisitionTime", 0) / 1000).strftime("%Y-%m-%d")
        cld = scene.get("cloudPercent", 0)
        prod_id = scene.get("productId", "") or ""
        # Build a meaningful scene name from productId or fallback
        scene_name = prod_id.strip() if prod_id.strip() and prod_id.strip().lower() != "none" else f"{sat}_{sen}_{dt}"

        row = st.columns(W)
        row[0].checkbox("Select", key=f"{state_prefix}_chk_{idx}", label_visibility="collapsed")
        row[1].write(sat)
        row[2].write(sen)
        row[3].write(scene_name)
        row[4].write(dt)
        row[5].write(f"{cld:.1f}")

        preview_indices = st.session_state.get(f"{state_prefix}_preview_indices") or set()
        preview_active = idx in preview_indices
        eye_label = "🔍" if preview_active else "👁️"
        if row[6].button(eye_label, key=f"{state_prefix}_eye_{idx}", help="Show quickview on map"):
            pset = set(st.session_state.get(f"{state_prefix}_preview_indices") or set())
            pset.discard(idx) if idx in pset else pset.add(idx)
            st.session_state[f"{state_prefix}_preview_indices"] = pset
            st.rerun()

    st.divider()
    bc = st.columns(4)

    with bc[0]:
        if st.button(
            f"📥 Download Selected ({n_sel})",
            type="primary", disabled=n_sel == 0,
            use_container_width=True, key=f"{state_prefix}_dl_sel",
        ):
            _do_download_zip(
                [all_scenes[i] for i in sel_indices],
                [features[i] for i in sel_indices],
            )

    with bc[1]:
        if st.button(
            "🗺️ Show Selected on Map",
            disabled=n_sel == 0,
            use_container_width=True, key=f"{state_prefix}_show_sel",
        ):
            st.session_state[f"{state_prefix}_features_map"] = [features[i] for i in sel_indices]
            st.rerun()

    with bc[2]:
        if st.button(
            "👁️ Quickviews for Selected",
            disabled=n_sel == 0,
            use_container_width=True, key=f"{state_prefix}_qv_sel",
            help="Show quickviews for all selected scenes on the map",
        ):
            pset = set(st.session_state.get(f"{state_prefix}_preview_indices") or set())
            for i in sel_indices:
                pset.add(i)
            st.session_state[f"{state_prefix}_preview_indices"] = pset
            st.rerun()

    with bc[3]:
        if st.button("📥 Download All", use_container_width=True, key=f"{state_prefix}_dl_all"):
            _do_download_zip(all_scenes, features)


# ── Download ──────────────────────────────────────────────────────────────────

_FS_UNSAFE = re.compile(r'[\\/:*?"<>|\x00-\x1f]')


def _fs_safe(name: str) -> str:
    """Replace filesystem-illegal characters with underscores."""
    return _FS_UNSAFE.sub("_", name).strip("_") or "scene"


def _scene_basename(sat: str, sensor: str, date_str: str,
                    prod_id, qv_url: str, idx: int) -> str:
    """
    Build a clean, non-None base name (no extension) for a scene file.

    Priority:
      1. Filename extracted from the quickview URL path (most descriptive)
      2. productId from the API response, if present and not 'None'
      3. Sequential fallback:  <sat>_<sensor>_<date>_<idx:04d>

    The quickview URL contains the most meaningful filename, e.g.:
      .../zy302a_mux_054103_299099_20260225190937_01_sec_0004_2603023712.jpg
    """
    # Priority 1: extract filename from quickview URL
    if qv_url:
        url_path = qv_url.split("?")[0].rstrip("/")
        basename = url_path.rsplit("/", 1)[-1]
        stem = basename.rsplit(".", 1)[0]
        if len(stem) > 4:
            return _fs_safe(stem)

    # Priority 2: productId from the API response
    pid = str(prod_id or "").strip()
    if pid and pid.lower() != "none":
        return _fs_safe(f"{sat}_{sensor}_{date_str}_{pid}")

    # Priority 3: fallback using satellite + sensor + date + index
    return _fs_safe(f"{sat}_{sensor}_{date_str}_{idx:04d}")


def _do_download_zip(scenes: list, features: list):
    if not scenes:
        st.warning("No scenes to download.")
        return

    with st.status(f"Creating package — {len(scenes)} scenes…", expanded=True) as status:
        try:
            temp_dir = Path(tempfile.mkdtemp(prefix="sasclouds_"))
            client = SASCloudsAPIClient()
            features_out = []
            ok = fail = 0

            for idx, (scene, feat) in enumerate(zip(scenes, features)):
                sat = scene.get("satelliteId") or "SAT"
                sensor = scene.get("sensorId") or "SENSOR"
                date_str = datetime.fromtimestamp(
                    scene.get("acquisitionTime", 0) / 1000
                ).strftime("%Y-%m-%d")
                cloud = scene.get("cloudPercent", 0)
                prod_id = scene.get("productId")
                footprint = feat["geometry"]
                qv_url = feat["properties"]["quickview"]
                img_name = _scene_basename(sat, sensor, date_str, prod_id, qv_url, idx) + ".jpg"
                img_path = temp_dir / img_name

                status.write(f"[{idx + 1}/{len(scenes)}] {img_name}")
                status.write(f"   URL: {qv_url[:120]}")
                if client.download_and_georeference(qv_url, footprint, img_path):
                    ok += 1
                else:
                    fail += 1

                features_out.append({
                    "type": "Feature",
                    "geometry": footprint,
                    "properties": {
                        "satellite": sat, "sensor": sensor,
                        "date": date_str, "cloud_cover": cloud,
                        "product_id": prod_id, "image": img_name,
                    },
                })

            geojson_path = temp_dir / "footprints.geojson"
            with open(geojson_path, "w") as f:
                json.dump({"type": "FeatureCollection", "features": features_out}, f, indent=2)

            zip_buf = io.BytesIO()
            with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
                for file in temp_dir.rglob("*"):
                    zf.write(file, arcname=file.relative_to(temp_dir))
            zip_buf.seek(0)
            shutil.rmtree(temp_dir, ignore_errors=True)

            status.update(label=f"✅ {ok} images, {fail} failed", state="complete")
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
