#!/usr/bin/env python3
"""
tests/run_tests.py  --  Comprehensive all-in-one test runner.

Covers every layer of the SASClouds Scraper:
  config / paths, satellite groups, shapefile creation, AOI upload,
  scene search, download & georeference, version probe, AOIHandler,
  map_utils, search_logic, logging helpers
  + optional live API tests against the real sasclouds.com endpoint.

Usage:
    python tests/run_tests.py              # unit tests only
    python tests/run_tests.py --live       # unit + live API tests
    python tests/run_tests.py --live-only  # live API tests only

Report is printed to the terminal and saved to  logs/test_report.md
"""

# ── Force UTF-8 on Windows CP1252 consoles BEFORE any other imports ───────────
# Python's logging re-raises encoding errors from stream handlers, which would
# make tests ERROR instead of PASS on Windows terminals.
import sys
import io as _io
for _s_name in ("stdout", "stderr"):
    try:
        _s = getattr(sys, _s_name)
        if hasattr(_s, "reconfigure"):
            _s.reconfigure(encoding="utf-8", errors="replace")
        elif hasattr(_s, "buffer"):
            setattr(sys, _s_name,
                    _io.TextIOWrapper(_s.buffer, encoding="utf-8", errors="replace"))
    except Exception:
        pass

import argparse
import dataclasses
import json
import tempfile
import time
import traceback
import zipfile
from datetime import date, datetime
from io import BytesIO
from pathlib import Path
from typing import List, Optional
from unittest.mock import MagicMock, call, patch

# ── sys.path bootstrap ────────────────────────────────────────────────────────
_TESTS_DIR = Path(__file__).parent
_APP_DIR   = _TESTS_DIR.parent
sys.path.insert(0, str(_APP_DIR))

# ── Streamlit stub (must come before any app-module imports) ──────────────────
import streamlit as st
st._is_running_with_streamlit = False  # type: ignore[attr-defined]
st.session_state = {}  # type: ignore[assignment]


# ── App-module imports ────────────────────────────────────────────────────────
from aoi_handler import AOIHandler
from map_utils import (
    handle_drawing,
    normalize_longitude,
    split_polygon_at_antimeridian,
)
from sasclouds_api_scraper import (
    SATELLITE_GROUPS,
    SASCloudsAPIClient,
    _STRUCTURED_LOG,
    _log_event,
    _APP_DIR as _MOD_APP_DIR,
    load_config,
    log_aoi_upload,
    log_search,
    LOG_DIR,
)
from search_logic import _do_download_zip, render_results_table, run_search
from shapely.geometry import Polygon


# =============================================================================
# Test infrastructure
# =============================================================================

@dataclasses.dataclass
class TestResult:
    name: str
    category: str
    status: str          # PASS | FAIL | ERROR | SKIP
    duration_ms: int
    error: str = ""
    tb: str = ""


class Runner:
    """Lightweight test runner: each test is a plain callable."""

    def __init__(self):
        self.results: List[TestResult] = []

    def run(self, name: str, category: str, fn, *args, **kwargs):
        """Run *fn* and record the outcome."""
        t0 = time.monotonic()
        try:
            fn(*args, **kwargs)
            ms = _ms(t0)
            self.results.append(TestResult(name, category, "PASS", ms))
            _print_line("✓", name, ms)
        except AssertionError as exc:
            ms = _ms(t0)
            tb = traceback.format_exc()
            self.results.append(TestResult(name, category, "FAIL", ms, str(exc), tb))
            _print_line("✗", name, ms, str(exc))
        except Exception as exc:
            ms = _ms(t0)
            tb = traceback.format_exc()
            label = f"{type(exc).__name__}: {exc}"
            self.results.append(TestResult(name, category, "ERROR", ms, label, tb))
            _print_line("!", name, ms, label)

    def skip(self, name: str, category: str, reason: str):
        self.results.append(TestResult(name, category, "SKIP", 0, reason))
        print(f"  SKIP  {name:<60}  -- {reason}")

    # ── Counts ────────────────────────────────────────────────────────────────
    @property
    def n_pass(self): return sum(1 for r in self.results if r.status == "PASS")
    @property
    def n_fail(self): return sum(1 for r in self.results if r.status == "FAIL")
    @property
    def n_error(self): return sum(1 for r in self.results if r.status == "ERROR")
    @property
    def n_skip(self): return sum(1 for r in self.results if r.status == "SKIP")
    @property
    def total_ms(self): return sum(r.duration_ms for r in self.results)


def _ms(t0: float) -> int:
    return int((time.monotonic() - t0) * 1000)

def _print_line(icon: str, name: str, ms: int, detail: str = ""):
    detail_str = f"  -- {detail[:80]}" if detail else ""
    print(f"  {icon}  {name:<60}  {ms}ms{detail_str}")


# =============================================================================
# Helpers shared across tests
# =============================================================================

def _mock_client_config():
    """Patch load_config so SASCloudsAPIClient.__init__ skips _init_session."""
    return patch("sasclouds_api_scraper.load_config", return_value={"api_version": "v5"})

def _mock_http(status=200, json_body=None, content=b"", text=""):
    r = MagicMock()
    r.status_code = status
    r.content     = content or json.dumps(json_body or {}).encode()
    r.text        = text or json.dumps(json_body or {})
    r.raise_for_status = MagicMock()
    r.json = MagicMock(return_value=json_body or {})
    return r

def _sample_polygon():
    return {
        "type": "Polygon",
        "coordinates": [[[102.0, 10.0], [108.0, 10.0],
                         [108.0, 15.0], [102.0, 15.0], [102.0, 10.0]]]
    }

def _make_scene(prod_id="prod123"):
    return {
        "satelliteId": "ZY3-1",
        "sensorId": "MUX",
        "acquisitionTime": 1609459200000,
        "cloudPercent": 5,
        "productId": prod_id,
        "boundary": json.dumps({
            "type": "Polygon",
            "coordinates": [[[105, 12], [106, 12], [106, 13], [105, 13], [105, 12]]],
        }),
        "quickViewUri": "http://quickview.sasclouds.com/img.jpg",
    }

def _mock_streamlit_ui():
    """Return a combined patch context for all Streamlit UI calls in run_search."""
    status_ctx = MagicMock()
    status_ctx.__enter__ = MagicMock(return_value=status_ctx)
    status_ctx.__exit__  = MagicMock(return_value=False)
    return (
        patch("streamlit.status",          return_value=status_ctx),
        patch("streamlit.progress",        return_value=MagicMock()),
        patch("streamlit.subheader"),
        patch("streamlit.markdown"),
        patch("streamlit.warning"),
        patch("streamlit.error"),
        patch("streamlit.button",          return_value=False),
        patch("streamlit.download_button"),
    )

def _apply_patches(patches):
    cms = [p.start() for p in patches]
    return cms, patches

def _stop_patches(patches):
    for p in patches:
        try:
            p.stop()
        except RuntimeError:
            pass

def _run_search_with_client(mock_client, polygon=None):
    """Run search_logic.run_search fully mocked."""
    polygon = polygon or _sample_polygon()
    patches = list(_mock_streamlit_ui())
    _apply_patches(patches)
    try:
        st.session_state = {}
        run_search(
            polygon_geojson   = polygon,
            aoi_filename      = "test.geojson",
            start_date        = date(2025, 1, 1),
            end_date          = date(2025, 6, 30),
            max_cloud         = 50,
            selected_satellites = [{"satelliteId": "ZY3-1", "sensorIds": ["MUX"]}],
            session_id        = "test-session",
            log_container     = MagicMock(),
        )
    finally:
        _stop_patches(patches)


# =============================================================================
# CATEGORY 1 — Config & Paths
# =============================================================================

def _reg_config_paths(r: Runner):
    cat = "Config & Paths"

    def config_json_exists():
        p = _APP_DIR / "config.json"
        assert p.exists(), f"config.json not found at {p}"

    def config_api_version_is_v5():
        cfg = load_config()
        v = cfg.get("api_version", "")
        assert v == "v5", f"api_version should be 'v5', got '{v}'"

    def module_app_dir_is_absolute():
        assert _MOD_APP_DIR.is_absolute(), \
            f"_APP_DIR in sasclouds_api_scraper is not absolute: {_MOD_APP_DIR}"

    def log_dir_exists():
        assert LOG_DIR.exists(), f"logs/ directory missing at {LOG_DIR}"

    def structured_log_path_absolute():
        assert _STRUCTURED_LOG.is_absolute(), \
            f"_STRUCTURED_LOG is not absolute: {_STRUCTURED_LOG}"

    for name, fn in [
        ("config_json_exists",          config_json_exists),
        ("config_api_version_is_v5",    config_api_version_is_v5),
        ("module_app_dir_is_absolute",  module_app_dir_is_absolute),
        ("log_dir_exists",              log_dir_exists),
        ("structured_log_path_absolute",structured_log_path_absolute),
    ]:
        r.run(name, cat, fn)


# =============================================================================
# CATEGORY 2 — Satellite Groups
# =============================================================================

def _reg_satellite_groups(r: Runner):
    cat = "Satellite Groups"

    def groups_not_empty():
        assert SATELLITE_GROUPS, "SATELLITE_GROUPS is empty"
        total = sum(
            len(sats)
            for cats in SATELLITE_GROUPS.values()
            for sats in cats.values()
            if isinstance(sats, list)
        )
        assert total > 10, f"Only {total} satellite entries — expected >10"

    def all_entries_have_satellite_id():
        missing = []
        for group, cats in SATELLITE_GROUPS.items():
            for cat_name, sats in cats.items():
                if not isinstance(sats, list):
                    continue
                for s in sats:
                    if not isinstance(s, dict) or "satelliteId" not in s:
                        missing.append(f"{group}/{cat_name}: {s!r}")
        assert not missing, f"Entries missing satelliteId: {missing}"

    def all_entries_have_sensor_ids_key():
        missing = []
        for group, cats in SATELLITE_GROUPS.items():
            for cat_name, sats in cats.items():
                if not isinstance(sats, list):
                    continue
                for s in sats:
                    if isinstance(s, dict) and "sensorIds" not in s:
                        missing.append(s.get("satelliteId", "unknown"))
        assert not missing, f"Entries missing sensorIds: {missing}"

    for name, fn in [
        ("groups_not_empty",             groups_not_empty),
        ("all_entries_have_satellite_id", all_entries_have_satellite_id),
        ("all_entries_have_sensor_ids",  all_entries_have_sensor_ids_key),
    ]:
        r.run(name, cat, fn)


# =============================================================================
# CATEGORY 3 — Shapefile Creation
# =============================================================================

def _reg_shapefile_creation(r: Runner):
    cat = "Shapefile Creation"

    def _create_shp(polygon=None):
        """Helper: create a shapefile via the private method and return the shp path."""
        polygon = polygon or _sample_polygon()
        with _mock_client_config():
            client = SASCloudsAPIClient()
        tmp = Path(tempfile.mkdtemp(prefix="shp_test_"))
        shp_path = client._create_shapefile(polygon, tmp)
        return shp_path, tmp

    def creates_three_sidecar_files():
        shp_path, tmp = _create_shp()
        for ext in (".shp", ".shx", ".dbf"):
            p = shp_path.with_suffix(ext)
            assert p.exists(), f"Shapefile component missing: {p.name}"

    def all_three_files_nonempty():
        shp_path, tmp = _create_shp()
        for ext in (".shp", ".shx", ".dbf"):
            p = shp_path.with_suffix(ext)
            assert p.stat().st_size > 0, f"{p.name} is empty (0 bytes)"

    def outer_ring_is_clockwise():
        """After _create_shapefile, the exterior ring on disk must be CW (ESRI convention).
        The SASClouds server uses ESRI convention: CW = outer ring, CCW = inner ring.
        A CCW outer ring is interpreted as a hole → empty geometry → 0 search results."""
        import shapefile as pyshp
        shp_path, _ = _create_shp()
        sf = pyshp.Reader(str(shp_path))
        shape = sf.shapes()[0]
        sf.close()
        coords = shape.points
        # Shoelace formula — negative area = clockwise (ESRI convention for outer rings)
        area2 = sum(
            (coords[i][0] * coords[(i+1) % len(coords)][1]
             - coords[(i+1) % len(coords)][0] * coords[i][1])
            for i in range(len(coords))
        )
        assert area2 < 0, (
            f"Exterior ring is CCW (shoelace area={area2:.4f}). "
            "Server uses ESRI convention: CW = outer ring. CCW = hole → empty geometry."
        )

    def simplifies_dense_polygon():
        """A 300-vertex polygon should be simplified to ≤200 vertices."""
        import math
        n = 300
        coords = [
            [105.0 + 1.5 * math.cos(2 * math.pi * i / n),
             12.0  + 1.5 * math.sin(2 * math.pi * i / n)]
            for i in range(n)
        ]
        coords.append(coords[0])
        dense = {"type": "Polygon", "coordinates": [coords]}
        shp_path, _ = _create_shp(dense)
        import shapefile as pyshp
        sf = pyshp.Reader(str(shp_path))
        n_after = len(sf.shapes()[0].points)
        sf.close()
        assert n_after <= 200, \
            f"Dense polygon not simplified: {n_after} vertices remain (max 200)"

    def rejects_multipolygon_with_no_parts():
        """An empty FeatureCollection must raise ValueError, not silently succeed."""
        empty_fc = {"type": "FeatureCollection", "features": []}
        with _mock_client_config():
            client = SASCloudsAPIClient()
        tmp = Path(tempfile.mkdtemp(prefix="shp_test_"))
        try:
            client._create_shapefile(empty_fc, tmp)
            raise AssertionError("Expected ValueError for empty FeatureCollection — none raised")
        except ValueError:
            pass  # correct

    for name, fn in [
        ("creates_three_sidecar_files",        creates_three_sidecar_files),
        ("all_three_files_nonempty",           all_three_files_nonempty),
        ("outer_ring_is_clockwise",            outer_ring_is_clockwise),
        ("simplifies_dense_polygon",           simplifies_dense_polygon),
        ("rejects_empty_feature_collection",   rejects_multipolygon_with_no_parts),
    ]:
        r.run(name, cat, fn)


# =============================================================================
# CATEGORY 4 — Upload AOI
# =============================================================================

def _reg_upload_aoi(r: Runner):
    cat = "Upload AOI"
    polygon = _sample_polygon()

    def _mock_upload_response(json_body, **extra):
        resp = _mock_http(json_body=json_body, text=json.dumps(json_body), **extra)
        return resp

    def upload_sends_single_file_field():
        """Must send a single 'file' field (only the .shp).
        CW winding (ESRI convention) allows the server to parse the shape with no .shx.
        Extra fields (file_shx, file_dbf) cause server errors."""
        captured = {}

        def _fake_request(method, url, **kwargs):
            if method == "POST" and "files" in kwargs:
                captured.update(kwargs["files"])
            return _mock_upload_response({"code": 0, "data": {"uploadId": "u1"}})

        with _mock_client_config(), \
             patch("requests.Session.request", side_effect=_fake_request):
            SASCloudsAPIClient().upload_aoi(polygon)

        assert "file" in captured, "Multipart field 'file' missing"
        for unexpected in ("file_shx", "file_dbf"):
            assert unexpected not in captured, \
                f"Unexpected multipart field '{unexpected}'"
        _, shp_bytes, _ = captured["file"]
        assert len(shp_bytes) > 0, "Field 'file' has 0 bytes"

    def upload_shp_is_clockwise():
        """The uploaded .shp must use CW (ESRI convention) winding.
        CCW winding is treated as an inner ring (hole) by the server → empty geometry."""
        import struct
        captured = {}

        def _fake_request(method, url, **kwargs):
            if method == "POST" and "files" in kwargs:
                captured.update(kwargs["files"])
            return _mock_upload_response({"code": 0, "data": {"uploadId": "u2"}})

        with _mock_client_config(), \
             patch("requests.Session.request", side_effect=_fake_request):
            SASCloudsAPIClient().upload_aoi(polygon)

        _, shp_bytes, _ = captured["file"]
        # Read points from the .shp shape record (offset 100 = first record)
        num_parts = struct.unpack("<I", shp_bytes[144:148])[0]
        num_points = struct.unpack("<I", shp_bytes[148:152])[0]
        pts_offset = 152 + num_parts * 4
        pts = [struct.unpack("<dd", shp_bytes[pts_offset+i*16:pts_offset+i*16+16])
               for i in range(num_points)]
        area2 = sum(
            pts[i][0]*pts[(i+1)%len(pts)][1] - pts[(i+1)%len(pts)][0]*pts[i][1]
            for i in range(len(pts))
        )
        assert area2 < 0, (
            f"Exterior ring is CCW (shoelace area={area2:.4f}). "
            "Server uses ESRI convention: CW = outer ring. CCW = hole → empty geometry."
        )

    def upload_returns_upload_id_on_success():
        resp = _mock_upload_response({"code": 0, "data": {"uploadId": "uid_success"}})
        with _mock_client_config(), \
             patch("requests.Session.request", return_value=resp):
            uid = SASCloudsAPIClient().upload_aoi(polygon)
        assert uid == "uid_success", f"Got upload_id={uid!r}, expected 'uid_success'"

    def upload_raises_on_api_error():
        resp = _mock_upload_response({"code": 1, "message": "Bad polygon"})
        with _mock_client_config(), \
             patch("requests.Session.request", return_value=resp):
            try:
                SASCloudsAPIClient().upload_aoi(polygon)
                raise AssertionError("Expected exception for code=1 — none raised")
            except Exception as exc:
                assert "Bad polygon" in str(exc), \
                    f"Exception doesn't mention 'Bad polygon': {exc}"

    def upload_out_of_range_raises_helpful_message():
        resp = _mock_upload_response({"code": 1, "message": "region out-of-range detected"})
        with _mock_client_config(), \
             patch("requests.Session.request", return_value=resp):
            try:
                SASCloudsAPIClient().upload_aoi(polygon)
                raise AssertionError("Expected out-of-range exception — none raised")
            except Exception as exc:
                msg = str(exc)
                assert "AOI is outside the SASClouds archive coverage" in msg, \
                    f"Helpful out-of-range message missing.\nGot: {msg[:200]}"

    for name, fn in [
        ("upload_sends_single_file_field",         upload_sends_single_file_field),
        ("upload_shp_is_clockwise",                upload_shp_is_clockwise),
        ("upload_returns_upload_id_on_success",    upload_returns_upload_id_on_success),
        ("upload_raises_on_api_error",             upload_raises_on_api_error),
        ("upload_out_of_range_raises_helpful_msg", upload_out_of_range_raises_helpful_message),
    ]:
        r.run(name, cat, fn)


# =============================================================================
# CATEGORY 5 — Search Scenes
# =============================================================================

def _reg_search_scenes(r: Runner):
    cat = "Search Scenes"

    def _client_with_mock():
        with _mock_client_config():
            return SASCloudsAPIClient()

    def search_returns_data_dict():
        body = {"code": 0, "data": [_make_scene()], "pageInfo": {"total": 1}}
        resp = _mock_http(json_body=body)
        with _mock_client_config(), \
             patch("requests.Session.request", return_value=resp):
            result = SASCloudsAPIClient().search_scenes(
                "uid", 0, 1, 20, [{"satelliteId": "ZY3-1", "sensorIds": []}], 1, 50
            )
        assert result["data"][0]["satelliteId"] == "ZY3-1"
        assert result["pageInfo"]["total"] == 1

    def search_payload_has_shp_upload_id():
        """shpUploadId must be the exact string passed to search_scenes."""
        body = {"code": 0, "data": [], "pageInfo": {"total": 0}}
        captured_payload = {}

        def _fake(method, url, **kwargs):
            if kwargs.get("json"):
                captured_payload.update(kwargs["json"])
            return _mock_http(json_body=body)

        with _mock_client_config(), \
             patch("requests.Session.request", side_effect=_fake):
            SASCloudsAPIClient().search_scenes(
                "MY_UPLOAD_ID", 0, 1, 20, [], 1, 50
            )
        assert captured_payload.get("shpUploadId") == "MY_UPLOAD_ID", \
            f"shpUploadId={captured_payload.get('shpUploadId')!r}, expected 'MY_UPLOAD_ID'"

    def search_payload_null_time_fields():
        """Four *Time fields must be present and None (confirmed from live HAR)."""
        body = {"code": 0, "data": [], "pageInfo": {"total": 0}}
        captured = {}

        def _fake(method, url, **kwargs):
            if kwargs.get("json"):
                captured.update(kwargs["json"])
            return _mock_http(json_body=body)

        with _mock_client_config(), \
             patch("requests.Session.request", side_effect=_fake):
            SASCloudsAPIClient().search_scenes("uid", 0, 1, 20, [], 1, 50)

        for field in ("tarInputTimeStart", "tarInputTimeEnd", "inputTimeStart", "inputTimeEnd"):
            assert field in captured, f"Payload missing field: {field}"
            assert captured[field] is None, \
                f"Field {field} should be None, got {captured[field]!r}"

    def search_payload_cloud_max():
        body = {"code": 0, "data": [], "pageInfo": {"total": 0}}
        captured = {}

        def _fake(method, url, **kwargs):
            if kwargs.get("json"):
                captured.update(kwargs["json"])
            return _mock_http(json_body=body)

        with _mock_client_config(), \
             patch("requests.Session.request", side_effect=_fake):
            SASCloudsAPIClient().search_scenes("uid", 0, 1, 37, [], 1, 50)

        assert captured.get("cloudPercentMax") == 37, \
            f"cloudPercentMax={captured.get('cloudPercentMax')}, expected 37"

    def search_raises_on_api_error():
        body = {"code": 2, "message": "Upstream unavailable"}
        resp = _mock_http(json_body=body)
        with _mock_client_config(), \
             patch("requests.Session.request", return_value=resp):
            try:
                SASCloudsAPIClient().search_scenes("uid", 0, 1, 20, [], 1, 50)
                raise AssertionError("Expected exception for code=2 — none raised")
            except Exception as exc:
                assert "Upstream unavailable" in str(exc)

    for name, fn in [
        ("search_returns_data_dict",        search_returns_data_dict),
        ("search_payload_shp_upload_id",    search_payload_has_shp_upload_id),
        ("search_payload_null_time_fields", search_payload_null_time_fields),
        ("search_payload_cloud_max",        search_payload_cloud_max),
        ("search_raises_on_api_error",      search_raises_on_api_error),
    ]:
        r.run(name, cat, fn)


# =============================================================================
# CATEGORY 6 — Download & Georeference
# =============================================================================

def _reg_download(r: Runner):
    cat = "Download & Georeference"
    footprint = {
        "type": "Polygon",
        "coordinates": [[[105, 12], [106, 12], [106, 13], [105, 13], [105, 12]]],
    }

    def download_creates_jpg_jgw_prj(tmp_path=None):
        tmp = Path(tempfile.mkdtemp(prefix="dl_test_"))
        out = tmp / "scene.jpg"
        mock_img = MagicMock()
        mock_img.size = (100, 200)

        with _mock_client_config(), \
             patch("requests.Session.request",
                   return_value=_mock_http(content=b"fake-image")), \
             patch("PIL.Image.open", return_value=mock_img):
            ok = SASCloudsAPIClient().download_and_georeference(
                "https://example.com/img.jpg", footprint, out
            )
        assert ok is True, "download_and_georeference returned False"
        assert out.exists(), "JPEG not written"
        assert out.with_suffix(".jgw").exists(), ".jgw not written"
        assert out.with_suffix(".prj").exists(), ".prj not written"

    def jgw_has_six_float_lines():
        tmp = Path(tempfile.mkdtemp(prefix="dl_test_"))
        out = tmp / "scene.jpg"
        mock_img = MagicMock()
        mock_img.size = (100, 100)

        with _mock_client_config(), \
             patch("requests.Session.request",
                   return_value=_mock_http(content=b"img")), \
             patch("PIL.Image.open", return_value=mock_img):
            SASCloudsAPIClient().download_and_georeference(
                "https://example.com/img.jpg", footprint, out
            )
        lines = out.with_suffix(".jgw").read_text().splitlines()
        assert len(lines) == 6, f".jgw has {len(lines)} lines, expected 6"
        for i, line in enumerate(lines):
            try:
                float(line)
            except ValueError:
                raise AssertionError(f".jgw line {i+1} is not a float: {line!r}")

    def prj_contains_wgs84():
        tmp = Path(tempfile.mkdtemp(prefix="dl_test_"))
        out = tmp / "s.jpg"
        mock_img = MagicMock()
        mock_img.size = (50, 50)

        with _mock_client_config(), \
             patch("requests.Session.request",
                   return_value=_mock_http(content=b"img")), \
             patch("PIL.Image.open", return_value=mock_img):
            SASCloudsAPIClient().download_and_georeference(
                "https://example.com/s.jpg", footprint, out
            )
        prj = out.with_suffix(".prj").read_text()
        assert "WGS 84" in prj and "EPSG" in prj, \
            f".prj missing WGS84/EPSG content: {prj[:100]}"

    def download_returns_false_on_http_error():
        tmp = Path(tempfile.mkdtemp(prefix="dl_test_"))
        out = tmp / "missing.jpg"
        resp = _mock_http(status=404, content=b"")
        with _mock_client_config(), \
             patch("requests.Session.request", return_value=resp):
            ok = SASCloudsAPIClient().download_and_georeference(
                "https://example.com/missing.jpg", footprint, out
            )
        assert ok is False, f"Expected False for HTTP 404, got {ok!r}"

    for name, fn in [
        ("download_creates_jpg_jgw_prj",    download_creates_jpg_jgw_prj),
        ("jgw_has_six_float_lines",         jgw_has_six_float_lines),
        ("prj_contains_wgs84",              prj_contains_wgs84),
        ("download_returns_false_on_404",   download_returns_false_on_http_error),
    ]:
        r.run(name, cat, fn)


# =============================================================================
# CATEGORY 7 — Version Probe
# =============================================================================

def _reg_version_probe(r: Runner):
    cat = "Version Probe"

    def uniform_204_falls_back_to_v5():
        """When WAF returns 204 for all OPTIONS, _probe_api_version must return 'v5'."""
        resp_204 = _mock_http(status=204, content=b"")
        with patch("requests.Session.request", return_value=resp_204):
            # Create client with no api_version in config so _init_session runs
            with patch("sasclouds_api_scraper.load_config", return_value={}), \
                 patch.object(SASCloudsAPIClient, "_scan_js_bundles", return_value=None), \
                 patch.object(SASCloudsAPIClient, "_init_session",
                              wraps=lambda self, url: "v5"):
                client = SASCloudsAPIClient.__new__(SASCloudsAPIClient)
                client.session = __import__("requests").Session()
                client.session.headers.update(SASCloudsAPIClient._BROWSER_HEADERS)
                result = client._probe_api_version("https://www.sasclouds.com")
        assert result == "v5", \
            f"Expected 'v5' from WAF-uniform probe, got {result!r}"

    def version_in_config_skips_probe():
        """When config.json has api_version, __init__ must not call _init_session."""
        init_session_called = []

        def _fake_init(self, url):
            init_session_called.append(url)
            return "v5"

        with patch("sasclouds_api_scraper.load_config",
                   return_value={"api_version": "v5"}), \
             patch.object(SASCloudsAPIClient, "_init_session", _fake_init):
            SASCloudsAPIClient()

        assert not init_session_called, \
            "_init_session was called even though config.json had api_version"

    for name, fn in [
        ("uniform_204_falls_back_to_v5", uniform_204_falls_back_to_v5),
        ("version_in_config_skips_probe", version_in_config_skips_probe),
    ]:
        r.run(name, cat, fn)


# =============================================================================
# CATEGORY 8 — AOIHandler
# =============================================================================

def _reg_aoi_handler(r: Runner):
    cat = "AOIHandler"

    def _write_geojson(tmp: Path, geojson: dict) -> str:
        p = tmp / "aoi.geojson"
        p.write_text(json.dumps(geojson))
        return str(p)

    def _write_kml(tmp: Path) -> str:
        kml = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<kml xmlns="http://www.opengis.net/kml/2.2">'
            "<Placemark><Polygon><outerBoundaryIs><LinearRing>"
            "<coordinates>102,10 108,10 108,15 102,15 102,10</coordinates>"
            "</LinearRing></outerBoundaryIs></Polygon></Placemark></kml>"
        )
        p = tmp / "aoi.kml"
        p.write_text(kml)
        return str(p)

    def _write_zip_shp(tmp: Path) -> str:
        import shapefile as pyshp
        shp_dir = tmp / "shp"
        shp_dir.mkdir()
        w = pyshp.Writer(shp_dir / "test", pyshp.POLYGON)
        w.field("ID", "N", 10)
        w.poly([[[102, 10], [108, 10], [108, 15], [102, 15], [102, 10]]])
        w.record(1)
        w.close()
        zip_path = tmp / "aoi.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            for ext in (".shp", ".shx", ".dbf"):
                p = shp_dir / f"test{ext}"
                if p.exists():
                    zf.write(p, arcname=f"test{ext}")
        return str(zip_path)

    def load_geojson_returns_polygon():
        tmp = Path(tempfile.mkdtemp(prefix="aoi_test_"))
        p = _write_geojson(tmp, {
            "type": "Polygon",
            "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]],
        })
        poly = AOIHandler.load_from_filepath(p)
        assert isinstance(poly, Polygon), f"Expected Polygon, got {type(poly)}"
        assert poly.area > 0, "Polygon area is 0"

    def load_kml_returns_polygon():
        tmp = Path(tempfile.mkdtemp(prefix="aoi_test_"))
        p = _write_kml(tmp)
        poly = AOIHandler.load_from_filepath(p)
        assert isinstance(poly, Polygon), f"Expected Polygon from KML, got {type(poly)}"
        assert poly.area > 0

    def load_shapefile_zip_returns_polygon():
        tmp = Path(tempfile.mkdtemp(prefix="aoi_test_"))
        p = _write_zip_shp(tmp)
        poly = AOIHandler.load_from_filepath(p)
        assert isinstance(poly, Polygon), f"Expected Polygon from ZIP, got {type(poly)}"

    def unsupported_format_returns_none():
        tmp = Path(tempfile.mkdtemp(prefix="aoi_test_"))
        p = tmp / "data.csv"
        p.write_text("lat,lon\n1,2")
        result = AOIHandler.load_from_filepath(str(p))
        assert result is None, f"Expected None for .csv, got {type(result)}"

    def calculate_area_polygon_is_positive():
        poly = Polygon([[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]])
        area, unit = AOIHandler.calculate_area(poly)
        assert area > 0, "Area is 0 or negative"
        assert unit in ("km²", "m²", "ha"), f"Unknown unit: {unit!r}"

    def calculate_area_none_returns_zero():
        area, unit = AOIHandler.calculate_area(None)
        assert area == 0
        assert unit == "km²"

    for name, fn in [
        ("load_geojson_returns_polygon",       load_geojson_returns_polygon),
        ("load_kml_returns_polygon",           load_kml_returns_polygon),
        ("load_shapefile_zip_returns_polygon", load_shapefile_zip_returns_polygon),
        ("unsupported_format_returns_none",    unsupported_format_returns_none),
        ("calculate_area_polygon_positive",    calculate_area_polygon_is_positive),
        ("calculate_area_none_returns_zero",   calculate_area_none_returns_zero),
    ]:
        r.run(name, cat, fn)


# =============================================================================
# CATEGORY 9 — map_utils
# =============================================================================

def _reg_map_utils(r: Runner):
    cat = "map_utils"

    def norm_overflow_pos():
        assert normalize_longitude(190) == -170

    def norm_overflow_neg():
        assert normalize_longitude(-190) == 170

    def norm_at_180():
        assert normalize_longitude(180) == -180

    def norm_normal_values():
        assert normalize_longitude(0) == 0
        assert normalize_longitude(90) == 90
        assert normalize_longitude(-90) == -90

    def split_no_cross():
        poly = Polygon([(105, 10), (108, 10), (108, 15), (105, 15), (105, 10)])
        parts = split_polygon_at_antimeridian(poly)
        assert len(parts) == 1

    def split_empty_polygon():
        assert split_polygon_at_antimeridian(Polygon()) == []

    def split_regular_polygon_valid():
        poly = Polygon([(105, 10), (108, 10), (108, 15), (105, 15), (105, 10)])
        parts = split_polygon_at_antimeridian(poly)
        assert len(parts) == 1
        assert parts[0].is_valid

    def split_spanning_180_returns_normalised():
        poly = Polygon([(170, 10), (-170, 10), (-170, 20), (170, 20), (170, 10)])
        parts = split_polygon_at_antimeridian(poly)
        assert len(parts) == 1
        mn, _, mx, _ = parts[0].bounds
        assert -180 <= mn and mx <= 180

    def handle_drawing_valid_polygon():
        data = {"last_active_drawing": {
            "geometry": {"type": "Polygon",
                         "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]]}}}
        result = handle_drawing(data)
        assert result is not None
        assert result["type"] == "Polygon"
        assert len(result["coordinates"][0]) == 5

    def handle_drawing_empty_dict():
        assert handle_drawing({}) is None

    def handle_drawing_none():
        assert handle_drawing(None) is None

    def handle_drawing_wrong_geometry_type():
        data = {"last_active_drawing": {
            "geometry": {"type": "LineString", "coordinates": [[0, 0], [1, 1]]}}}
        assert handle_drawing(data) is None

    for name, fn in [
        ("normalize_longitude_overflow_positive", norm_overflow_pos),
        ("normalize_longitude_overflow_negative", norm_overflow_neg),
        ("normalize_longitude_at_180",            norm_at_180),
        ("normalize_longitude_normal_values",     norm_normal_values),
        ("split_no_cross",                        split_no_cross),
        ("split_empty_polygon",                   split_empty_polygon),
        ("split_regular_polygon_valid",           split_regular_polygon_valid),
        ("split_spanning_180_normalised",         split_spanning_180_returns_normalised),
        ("handle_drawing_valid_polygon",          handle_drawing_valid_polygon),
        ("handle_drawing_empty_dict",             handle_drawing_empty_dict),
        ("handle_drawing_none",                   handle_drawing_none),
        ("handle_drawing_wrong_geometry_type",    handle_drawing_wrong_geometry_type),
    ]:
        r.run(name, cat, fn)


# =============================================================================
# CATEGORY 10 — search_logic / run_search
# =============================================================================

def _reg_run_search(r: Runner):
    cat = "search_logic / run_search"

    def sets_features_for_map():
        with patch("search_logic.SASCloudsAPIClient") as MockClient:
            MockClient.return_value.upload_aoi.return_value = "uid"
            MockClient.return_value.search_scenes.return_value = {
                "code": 0, "data": [_make_scene()], "pageInfo": {"total": 1},
            }
            _run_search_with_client(MockClient)
        assert len(st.session_state.get("features_for_map", [])) == 1, \
            "features_for_map not set after successful search"

    def sets_scenes_for_download():
        with patch("search_logic.SASCloudsAPIClient") as MockClient:
            MockClient.return_value.upload_aoi.return_value = "uid"
            MockClient.return_value.search_scenes.return_value = {
                "code": 0, "data": [_make_scene()], "pageInfo": {"total": 1},
            }
            _run_search_with_client(MockClient)
        assert st.session_state.get("scenes_for_download") is not None
        assert st.session_state.get("temp_dir_ready") is True

    def paginates_until_total():
        with patch("search_logic.SASCloudsAPIClient") as MockClient:
            MockClient.return_value.upload_aoi.return_value = "uid"
            MockClient.return_value.search_scenes.side_effect = [
                {"code": 0, "data": [_make_scene("p1s1"), _make_scene("p1s2")],
                 "pageInfo": {"total": 4}},
                {"code": 0, "data": [_make_scene("p2s1"), _make_scene("p2s2")],
                 "pageInfo": {"total": 4}},
            ]
            _run_search_with_client(MockClient)
        assert MockClient.return_value.search_scenes.call_count == 2
        assert len(st.session_state.get("scenes_for_download", [])) == 4

    def stops_on_empty_page():
        with patch("search_logic.SASCloudsAPIClient") as MockClient:
            MockClient.return_value.upload_aoi.return_value = "uid"
            MockClient.return_value.search_scenes.side_effect = [
                {"code": 0, "data": [_make_scene()], "pageInfo": {"total": 99}},
                {"code": 0, "data": [],               "pageInfo": {"total": 99}},
            ]
            _run_search_with_client(MockClient)
        assert len(st.session_state.get("scenes_for_download", [])) == 1, \
            "Pagination did not stop on empty page"

    def skips_scene_with_invalid_boundary():
        bad = _make_scene("bad")
        bad["boundary"] = "NOT_VALID_JSON"
        with patch("search_logic.SASCloudsAPIClient") as MockClient:
            MockClient.return_value.upload_aoi.return_value = "uid"
            MockClient.return_value.search_scenes.return_value = {
                "code": 0, "data": [bad, _make_scene("good")], "pageInfo": {"total": 2},
            }
            _run_search_with_client(MockClient)
        assert len(st.session_state.get("features_for_map", [])) == 1, \
            "Scene with invalid boundary should have been skipped"

    def rewrites_quickview_domain():
        scene = _make_scene()
        scene["quickViewUri"] = "http://quickview.sasclouds.com/path/thumb.jpg"
        with patch("search_logic.SASCloudsAPIClient") as MockClient:
            MockClient.return_value.upload_aoi.return_value = "uid"
            MockClient.return_value.search_scenes.return_value = {
                "code": 0, "data": [scene], "pageInfo": {"total": 1},
            }
            _run_search_with_client(MockClient)
        qv = st.session_state["features_for_map"][0]["properties"]["quickview"]
        assert "quickview.obs.cn-north-10.myhuaweicloud.com" in qv, \
            f"Quickview URL not rewritten to Huawei Cloud CDN: {qv}"
        assert "quickview.sasclouds.com" not in qv, \
            "Old sasclouds.com domain still present in quickview URL"

    def no_scenes_leaves_state_clean():
        with patch("search_logic.SASCloudsAPIClient") as MockClient:
            MockClient.return_value.upload_aoi.return_value = "uid"
            MockClient.return_value.search_scenes.return_value = {
                "code": 0, "data": [], "pageInfo": {"total": 0},
            }
            _run_search_with_client(MockClient)
        assert "features_for_map" not in st.session_state, \
            "features_for_map set even though 0 scenes returned"

    for name, fn in [
        ("sets_features_for_map",           sets_features_for_map),
        ("sets_scenes_for_download",        sets_scenes_for_download),
        ("paginates_until_total",           paginates_until_total),
        ("stops_on_empty_page",             stops_on_empty_page),
        ("skips_scene_with_invalid_boundary",skips_scene_with_invalid_boundary),
        ("rewrites_quickview_domain",       rewrites_quickview_domain),
        ("no_scenes_leaves_state_clean",    no_scenes_leaves_state_clean),
    ]:
        r.run(name, cat, fn)


# =============================================================================
# CATEGORY 11 — search_logic / _do_download_zip
# =============================================================================

def _reg_download_zip(r: Runner):
    cat = "search_logic / create_download_zip"

    def _make_feature():
        return {
            "geometry": {"type": "Polygon",
                         "coordinates": [[[105, 12], [106, 12], [106, 13],
                                          [105, 13], [105, 12]]]},
            "properties": {"quickview": "https://example.com/img.jpg"},
        }

    def _status_ctx():
        ctx = MagicMock()
        ctx.__enter__ = MagicMock(return_value=ctx)
        ctx.__exit__  = MagicMock(return_value=False)
        return ctx

    def preserves_features_for_map():
        """features_for_map in session_state must not be cleared after download."""
        features = [_make_feature()]
        st.session_state["features_for_map"] = features
        tmp = Path(tempfile.mkdtemp(prefix="zip_test_"))
        with patch("search_logic.SASCloudsAPIClient") as MockClient, \
             patch("streamlit.download_button"), \
             patch("streamlit.status", return_value=_status_ctx()), \
             patch("tempfile.mkdtemp", return_value=str(tmp)):
            MockClient.return_value.download_and_georeference.return_value = True
            _do_download_zip([_make_scene()], features)
        assert st.session_state.get("features_for_map") == features, \
            "features_for_map was cleared — footprints will disappear from map"

    def skips_when_no_scenes():
        """_do_download_zip with empty lists shows a warning, does not call the API."""
        warned = []
        with patch("search_logic.SASCloudsAPIClient") as MockClient, \
             patch("streamlit.warning", side_effect=lambda m: warned.append(m)):
            _do_download_zip([], [])
        MockClient.assert_not_called()
        assert warned, "Expected st.warning for empty scene list"

    def skips_when_button_not_clicked():
        """render_results_table returns immediately when session has no scenes."""
        st.session_state = {}
        with patch("search_logic.SASCloudsAPIClient") as MockClient:
            render_results_table()
        MockClient.assert_not_called()

    for name, fn in [
        ("preserves_features_for_map",     preserves_features_for_map),
        ("skips_when_no_scenes",           skips_when_no_scenes),
        ("skips_when_button_not_clicked",  skips_when_button_not_clicked),
    ]:
        r.run(name, cat, fn)


# =============================================================================
# CATEGORY 12 — Logging helpers
# =============================================================================

def _reg_logging_helpers(r: Runner):
    cat = "Logging helpers"
    import sasclouds_api_scraper as _mod

    def log_search_writes_correct_fields():
        tmp = Path(tempfile.mkdtemp(prefix="log_test_"))
        orig, _mod.LOG_DIR = _mod.LOG_DIR, tmp
        try:
            log_search("sess_a", {"type": "Polygon"}, {"cloud": 20}, 7)
            record = json.loads((tmp / "search_history.jsonl").read_text().strip())
            assert record["session_id"] == "sess_a"
            assert record["num_scenes"] == 7
            assert record["type"] == "search"
        finally:
            _mod.LOG_DIR = orig

    def log_search_appends_multiple():
        tmp = Path(tempfile.mkdtemp(prefix="log_test_"))
        orig, _mod.LOG_DIR = _mod.LOG_DIR, tmp
        try:
            log_search("s1", {}, {}, 3)
            log_search("s2", {}, {}, 9)
            lines = (tmp / "search_history.jsonl").read_text().strip().splitlines()
            assert len(lines) == 2, f"Expected 2 JSONL lines, got {len(lines)}"
        finally:
            _mod.LOG_DIR = orig

    def log_aoi_upload_writes_correct_fields():
        tmp = Path(tempfile.mkdtemp(prefix="log_test_"))
        orig, _mod.LOG_DIR = _mod.LOG_DIR, tmp
        try:
            log_aoi_upload("sess_b", "my.geojson", {"type": "Polygon"})
            record = json.loads((tmp / "aoi_history.jsonl").read_text().strip())
            assert record["session_id"] == "sess_b"
            assert record["filename"] == "my.geojson"
            assert record["type"] == "aoi_upload"
        finally:
            _mod.LOG_DIR = orig

    def structured_log_appends_jsonl():
        tmp_log = Path(tempfile.mkdtemp(prefix="log_test_")) / "events.jsonl"
        orig = _mod._STRUCTURED_LOG
        _mod._STRUCTURED_LOG = tmp_log
        try:
            _log_event("test_event", field_a="hello", field_b=42)
            record = json.loads(tmp_log.read_text().strip())
            assert record["event"] == "test_event"
            assert record["field_a"] == "hello"
            assert record["field_b"] == 42
            assert "ts" in record
        finally:
            _mod._STRUCTURED_LOG = orig

    for name, fn in [
        ("log_search_writes_correct_fields",   log_search_writes_correct_fields),
        ("log_search_appends_multiple",        log_search_appends_multiple),
        ("log_aoi_upload_writes_correct_fields",log_aoi_upload_writes_correct_fields),
        ("structured_log_appends_jsonl",       structured_log_appends_jsonl),
    ]:
        r.run(name, cat, fn)


# =============================================================================
# CATEGORY 13 — Live API tests  (requires --live flag + network)
# =============================================================================

def _reg_live_tests(r: Runner):
    cat = "Live API"
    import requests as _req

    # Beijing suburbs — guaranteed within SASClouds archive (Chinese territory)
    LIVE_POLYGON = {
        "type": "Polygon",
        "coordinates": [[[116.0, 39.5], [117.0, 39.5],
                         [117.0, 40.5], [116.0, 40.5], [116.0, 39.5]]],
    }
    # Satellite set confirmed to return results from HAR analysis (2026-05-08).
    # Hyperspectral satellites (GF5A/B AHSI) have the broadest archive coverage.
    LIVE_SATS = [
        {"satelliteId": "ZY3-1",  "sensorIds": ["MUX"]},
        {"satelliteId": "ZY3-2",  "sensorIds": ["MUX"]},
        {"satelliteId": "ZY3-3",  "sensorIds": ["MUX"]},
        {"satelliteId": "ZY02C",  "sensorIds": ["HRC"]},
        {"satelliteId": "ZY1F",   "sensorIds": ["VNIC"]},
        {"satelliteId": "ZY1E",   "sensorIds": ["AHSI"]},
        {"satelliteId": "ZY1F",   "sensorIds": ["AHSI"]},
        {"satelliteId": "GF5",    "sensorIds": ["AHSI"]},
        {"satelliteId": "GF5A",   "sensorIds": ["AHSI"]},
        {"satelliteId": "GF5B",   "sensorIds": ["AHSI"]},
    ]
    # Date range from HAR confirmed to return results: 2021-02-01 → now
    START_MS = int(datetime(2021, 2, 1).timestamp() * 1000)
    END_MS   = int(datetime(2026, 12, 31).timestamp() * 1000)

    # Shared state across live tests
    _live_state = {"upload_id": None, "scenes": []}

    def homepage_reachable():
        resp = _req.get(
            "https://www.sasclouds.com/english/normal/",
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=15,
        )
        assert resp.status_code == 200, \
            f"Homepage returned HTTP {resp.status_code} — server may be down"

    def upload_vietnam_aoi():
        client = SASCloudsAPIClient()
        uid = client.upload_aoi(LIVE_POLYGON)
        assert uid, "upload_aoi returned empty uploadId"
        _live_state["upload_id"] = uid
        _live_state["client"]    = client

    def search_returns_scenes():
        if not _live_state.get("upload_id"):
            raise AssertionError("Skipping — upload_vietnam_aoi must pass first")
        client   = _live_state["client"]
        upload_id = _live_state["upload_id"]
        result = client.search_scenes(
            upload_id, START_MS, END_MS, 50, LIVE_SATS, 1, 20
        )
        assert result.get("code") == 0, \
            f"Search API returned code={result.get('code')}: {result.get('message')}"
        scenes = result.get("data", [])
        total  = result.get("pageInfo", {}).get("total", 0)
        assert total > 0, (
            f"API returned 0 scenes for Beijing bbox 2021–2026 with ZY3/ZY1/GF5 satellites.\n"
            f"Response: {json.dumps(result)[:300]}"
        )
        _live_state["scenes"] = scenes
        print(f"\n       → {total} total scenes, {len(scenes)} on page 1")

    def quickview_cdn_url_accessible():
        scenes = _live_state.get("scenes", [])
        if not scenes:
            raise AssertionError("Skipping — search_returns_scenes must pass first")
        raw_qv = scenes[0].get("quickViewUri", "")
        cdn_qv = raw_qv.replace(
            "http://quickview.sasclouds.com",
            "https://quickview.obs.cn-north-10.myhuaweicloud.com",
        )
        if not cdn_qv:
            raise AssertionError("First scene has no quickViewUri")
        resp = _req.head(cdn_qv, timeout=15, allow_redirects=True)
        assert resp.status_code < 400, \
            f"Quickview CDN URL returned HTTP {resp.status_code}: {cdn_qv}"

    for name, fn in [
        ("homepage_reachable",         homepage_reachable),
        ("upload_vietnam_aoi",         upload_vietnam_aoi),
        ("search_returns_scenes",      search_returns_scenes),
        ("quickview_cdn_url_accessible", quickview_cdn_url_accessible),
    ]:
        r.run(name, cat, fn)


# =============================================================================
# Report generation
# =============================================================================

_STATUS_ICON = {"PASS": "OK  ", "FAIL": "FAIL", "ERROR": "ERR ", "SKIP": "SKIP"}
_STATUS_MD   = {"PASS": "PASS", "FAIL": "**FAIL**", "ERROR": "**ERROR**", "SKIP": "SKIP"}


def _build_report(runner: Runner, run_live: bool) -> str:
    now    = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    total  = len(runner.results)
    lines  = []

    lines.append(f"# SASClouds Scraper — Test Report")
    lines.append(f"Generated: {now}  |  Live tests: {'yes' if run_live else 'no'}")
    lines.append("")

    # Summary table
    lines.append("## Summary")
    lines.append(f"| Status | Count |")
    lines.append(f"|--------|-------|")
    lines.append(f"| ✓ PASS  | {runner.n_pass} |")
    lines.append(f"| ✗ FAIL  | {runner.n_fail} |")
    lines.append(f"| ! ERROR | {runner.n_error} |")
    lines.append(f"| ~ SKIP  | {runner.n_skip} |")
    lines.append(f"| **Total** | **{total}** |")
    lines.append("")
    elapsed = runner.total_ms / 1000
    lines.append(f"Total elapsed: {elapsed:.1f}s")
    lines.append("")

    # Failures & errors detail
    bad = [r for r in runner.results if r.status in ("FAIL", "ERROR")]
    if bad:
        lines.append("---")
        lines.append(f"## Failures & Errors ({len(bad)})")
        lines.append("")
        for res in bad:
            icon = _STATUS_ICON[res.status]
            lines.append(f"### [{res.status}] {res.category} / {res.name}")
            lines.append(f"```")
            lines.append(res.error)
            if res.tb:
                lines.append("")
                lines.append(res.tb.strip())
            lines.append(f"```")
            lines.append("")

    # Full results table per category
    lines.append("---")
    lines.append("## Full Results by Category")
    lines.append("")

    current_cat = None
    for res in runner.results:
        if res.category != current_cat:
            current_cat = res.category
            lines.append(f"### {res.category}")
            lines.append(f"| Test | Status | ms |")
            lines.append(f"|------|--------|----|")
        icon = _STATUS_ICON[res.status]
        status_str = _STATUS_MD[res.status]
        lines.append(f"| {res.name} | {icon} {status_str} | {res.duration_ms} |")

    lines.append("")
    return "\n".join(lines)


def _print_banner(text: str, width: int = 70):
    bar = "=" * width
    print(f"\n{bar}")
    print(f"  {text}")
    print(bar)


def _print_summary(runner: Runner):
    print()
    print("  Summary")
    print(f"  OK   {runner.n_pass:3d}  passed")
    print(f"  FAIL {runner.n_fail:3d}  failed")
    print(f"  ERR  {runner.n_error:3d}  errors")
    print(f"  SKIP {runner.n_skip:3d}  skipped")
    print(f"  Total: {len(runner.results)} tests  ({runner.total_ms/1000:.1f}s)")
    if runner.n_fail + runner.n_error > 0:
        print()
        print("  -- Failures --------------------------------------------------")
        for res in runner.results:
            if res.status in ("FAIL", "ERROR"):
                print(f"  {_STATUS_ICON[res.status]}  [{res.category}] {res.name}")
                if res.error:
                    for line in res.error.splitlines()[:2]:
                        print(f"       {line}")


# =============================================================================
# Main entry point
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="SASClouds comprehensive test runner"
    )
    parser.add_argument("--live",      action="store_true",
                        help="Also run live API tests (requires network)")
    parser.add_argument("--live-only", action="store_true",
                        help="Run only live API tests")
    args = parser.parse_args()

    runner = Runner()

    if not args.live_only:
        _print_banner("Unit Tests")

        print("\nConfig & Paths")
        _reg_config_paths(runner)

        print("\nSatellite Groups")
        _reg_satellite_groups(runner)

        print("\nShapefile Creation")
        _reg_shapefile_creation(runner)

        print("\nUpload AOI")
        _reg_upload_aoi(runner)

        print("\nSearch Scenes")
        _reg_search_scenes(runner)

        print("\nDownload & Georeference")
        _reg_download(runner)

        print("\nVersion Probe")
        _reg_version_probe(runner)

        print("\nAOIHandler")
        _reg_aoi_handler(runner)

        print("\nmap_utils")
        _reg_map_utils(runner)

        print("\nsearch_logic / run_search")
        _reg_run_search(runner)

        print("\nsearch_logic / create_download_zip")
        _reg_download_zip(runner)

        print("\nLogging helpers")
        _reg_logging_helpers(runner)

    if args.live or args.live_only:
        _print_banner("Live API Tests  (hitting real sasclouds.com)")
        print()
        _reg_live_tests(runner)

    # Print summary
    _print_banner("Results")
    _print_summary(runner)

    # Save report
    report_md = _build_report(runner, run_live=args.live or args.live_only)
    report_path = _APP_DIR / "logs" / "test_report.md"
    report_path.parent.mkdir(exist_ok=True)
    report_path.write_text(report_md, encoding="utf-8")
    print(f"\n  Full report saved → {report_path}")
    print()

    sys.exit(0 if runner.n_fail + runner.n_error == 0 else 1)


if __name__ == "__main__":
    main()
