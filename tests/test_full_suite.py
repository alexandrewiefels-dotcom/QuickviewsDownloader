"""
Complete test suite for the SASClouds + OrbitShow fusion app.

Run all unit tests (no network):
    pytest tests/test_full_suite.py -v

Run including live API tests (requires internet):
    pytest tests/test_full_suite.py -v -m live

Run a single section:
    pytest tests/test_full_suite.py -v -k "shapefile"
"""

import json
import math
import sys
import tempfile
import types
from datetime import date, datetime
from io import BytesIO
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import shapefile
from shapely.geometry import Polygon, mapping, shape as shapely_shape

# ── path bootstrap ─────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# ── shared fixtures ────────────────────────────────────────────────────────────

# Simple Beijing-area polygon (CCW, right-hand rule — standard GeoJSON convention)
BEIJING_GEOJSON = {
    "type": "Polygon",
    "coordinates": [[
        [116.2, 39.8],
        [116.6, 39.8],
        [116.6, 40.1],
        [116.2, 40.1],
        [116.2, 39.8],
    ]],
}

# Same polygon wrapped as FeatureCollection
BEIJING_FC = {
    "type": "FeatureCollection",
    "features": [{
        "type": "Feature",
        "geometry": BEIJING_GEOJSON,
        "properties": {},
    }],
}

# Polygon that crosses the antimeridian (Pacific Ocean)
ANTIMERIDIAN_GEOJSON = {
    "type": "Polygon",
    "coordinates": [[
        [175.0, 10.0],
        [-175.0, 10.0],
        [-175.0, -10.0],
        [175.0, -10.0],
        [175.0, 10.0],
    ]],
}

# A realistic scene feature dict
SAMPLE_SCENE = {
    "satelliteId": "GF2",
    "sensorId": "PMS",
    "acquisitionTime": 1735689600000,  # 2025-01-01 00:00:00 UTC
    "cloudPercent": 5.0,
    "quickViewUri": "http://quickview.sasclouds.com/GF2/test/img.jpg",
    "boundary": json.dumps(BEIJING_GEOJSON),
    "productId": "PROD-TEST-001",
}

# ── pytest marker ──────────────────────────────────────────────────────────────
def pytest_configure(config):
    config.addinivalue_line("markers", "live: tests that make real network calls")


# =============================================================================
# 1. MODULE IMPORTS
# =============================================================================

class TestImports:
    """All project modules must import without errors."""

    def test_sasclouds_api_scraper(self):
        import sasclouds_api_scraper  # noqa: F401

    def test_sasclouds_sidebar(self):
        import sasclouds_sidebar  # noqa: F401

    def test_sasclouds_map_utils(self):
        import sasclouds_map_utils  # noqa: F401

    def test_sasclouds_search_logic(self):
        import sasclouds_search_logic  # noqa: F401

    def test_config_satellites(self):
        from config.satellites import SATELLITES, get_satellite_count  # noqa: F401

    def test_config_constants(self):
        from config.constants import EARTH_RADIUS_KM, DEFAULT_CENTER  # noqa: F401

    def test_models_satellite_pass(self):
        from models.satellite_pass import SatellitePass  # noqa: F401

    def test_data_aoi_handler(self):
        from data.aoi_handler import AOIHandler  # noqa: F401

    def test_navigation_tracker(self):
        import navigation_tracker  # noqa: F401

    def test_prefetch_all_tles(self):
        import prefetch_all_tles  # noqa: F401

    def test_page_compiles(self):
        """SASClouds Archive page must compile without syntax errors."""
        import py_compile
        page = ROOT / "pages" / "3_SASClouds_Archive.py"
        py_compile.compile(str(page), doraise=True)


# =============================================================================
# 2. SATELLITE GROUPS (sasclouds_api_scraper)
# =============================================================================

class TestSatelliteGroups:
    from sasclouds_api_scraper import SATELLITE_GROUPS as _SG

    def test_top_level_categories_exist(self):
        from sasclouds_api_scraper import SATELLITE_GROUPS as SG
        for cat in ("Optical", "Hyperspectral", "SAR"):
            assert cat in SG, f"Expected category {cat!r} in SATELLITE_GROUPS"

    def test_satellite_entries_have_required_fields(self):
        from sasclouds_api_scraper import SATELLITE_GROUPS as SG
        for group, categories in SG.items():
            for cat, sats in categories.items():
                assert isinstance(sats, list), f"{group}/{cat} is not a list"
                for sat in sats:
                    assert "satelliteId" in sat, f"Missing satelliteId in {sat}"
                    assert "sensorIds" in sat, f"Missing sensorIds in {sat}"
                    assert isinstance(sat["satelliteId"], str) and sat["satelliteId"]

    def test_known_satellites_present(self):
        from sasclouds_api_scraper import SATELLITE_GROUPS as SG
        all_ids = {
            s["satelliteId"]
            for cats in SG.values()
            for sats in cats.values()
            if isinstance(sats, list)
            for s in sats
        }
        for expected in ("GF2", "GF5B", "GF3", "ZY3-1", "GF1"):
            assert expected in all_ids, f"{expected} not found in SATELLITE_GROUPS"

    def test_no_empty_satellite_id(self):
        from sasclouds_api_scraper import SATELLITE_GROUPS as SG
        for cats in SG.values():
            for sats in cats.values():
                if not isinstance(sats, list):
                    continue
                for sat in sats:
                    assert sat["satelliteId"].strip(), f"Empty satelliteId: {sat}"


# =============================================================================
# 3. CONFIG / LOAD_CONFIG
# =============================================================================

class TestLoadConfig:
    def test_returns_dict_for_missing_file(self):
        from sasclouds_api_scraper import load_config
        result = load_config(config_path=Path("/nonexistent/path/config.json"))
        assert result == {}

    def test_reads_existing_json(self, tmp_path):
        from sasclouds_api_scraper import load_config
        cfg = {"api_version": "v5", "token": "abc123"}
        p = tmp_path / "config.json"
        p.write_text(json.dumps(cfg))
        result = load_config(config_path=p)
        assert result["api_version"] == "v5"
        assert result["token"] == "abc123"

    def test_returns_empty_for_empty_file(self, tmp_path):
        from sasclouds_api_scraper import load_config
        p = tmp_path / "config.json"
        p.write_text("{}")
        assert load_config(config_path=p) == {}


# =============================================================================
# 4. STRUCTURED LOGGER (_log_event)
# =============================================================================

class TestLogEvent:
    def test_writes_jsonl_record(self, tmp_path):
        import sasclouds_api_scraper as mod
        original = mod._STRUCTURED_LOG
        try:
            mod._STRUCTURED_LOG = tmp_path / "test_events.jsonl"
            mod._log_event("test_event", foo="bar", count=42)
            lines = mod._STRUCTURED_LOG.read_text().strip().splitlines()
            assert len(lines) == 1
            rec = json.loads(lines[0])
            assert rec["event"] == "test_event"
            assert rec["foo"] == "bar"
            assert rec["count"] == 42
            assert "ts" in rec
        finally:
            mod._STRUCTURED_LOG = original

    def test_multiple_events_append(self, tmp_path):
        import sasclouds_api_scraper as mod
        original = mod._STRUCTURED_LOG
        try:
            mod._STRUCTURED_LOG = tmp_path / "multi.jsonl"
            for i in range(3):
                mod._log_event("evt", i=i)
            lines = mod._STRUCTURED_LOG.read_text().strip().splitlines()
            assert len(lines) == 3
        finally:
            mod._STRUCTURED_LOG = original


# =============================================================================
# 5. ACTIVITY LOGGERS (log_search, log_aoi_upload)
# =============================================================================

class TestActivityLoggers:
    def test_log_search_writes_jsonl(self, tmp_path):
        import sasclouds_api_scraper as mod
        orig = mod.LOG_DIR
        mod.LOG_DIR = tmp_path
        try:
            mod.log_search("sess-001", BEIJING_GEOJSON,
                           {"cloud_max": 20}, 42)
            log_file = tmp_path / "search_history.jsonl"
            assert log_file.exists()
            rec = json.loads(log_file.read_text().strip())
            assert rec["type"] == "search"
            assert rec["num_scenes"] == 42
            assert rec["session_id"] == "sess-001"
        finally:
            mod.LOG_DIR = orig

    def test_log_aoi_upload_writes_jsonl(self, tmp_path):
        import sasclouds_api_scraper as mod
        orig = mod.LOG_DIR
        mod.LOG_DIR = tmp_path
        try:
            mod.log_aoi_upload("sess-002", "test.geojson", BEIJING_GEOJSON)
            log_file = tmp_path / "aoi_history.jsonl"
            assert log_file.exists()
            rec = json.loads(log_file.read_text().strip())
            assert rec["type"] == "aoi_upload"
            assert rec["filename"] == "test.geojson"
        finally:
            mod.LOG_DIR = orig


# =============================================================================
# 6. SHAPEFILE BUILDER (_create_shapefile)
# =============================================================================

class TestCreateShapefile:
    """The shapefile builder is the most critical internal function —
    wrong winding = 'Out-of-range error' from the API server."""

    @pytest.fixture
    def client(self):
        from sasclouds_api_scraper import SASCloudsAPIClient
        with patch.object(SASCloudsAPIClient, "_init_session", return_value="v5"):
            c = SASCloudsAPIClient.__new__(SASCloudsAPIClient)
            c.base_url = "https://www.sasclouds.com"
            c.api_version = "v5"
            c.api_base = f"{c.base_url}/api/normal/v5"
            c.upload_url = f"{c.api_base}/normalmeta/upload/shp"
            c.search_url = f"{c.api_base}/normalmeta"
            import requests
            c.session = requests.Session()
            return c

    def test_creates_shp_file(self, client, tmp_path):
        shp_path = client._create_shapefile(BEIJING_GEOJSON, tmp_path)
        assert shp_path.exists()
        assert shp_path.suffix == ".shp"

    def test_output_is_clockwise(self, client, tmp_path):
        """Outer ring MUST be CW (ESRI convention) — CCW → server returns empty geometry."""
        shp_path = client._create_shapefile(BEIJING_GEOJSON, tmp_path)
        sf = shapefile.Reader(str(shp_path.with_suffix("")))
        shape = sf.shapes()[0]
        coords = shape.points
        # Compute signed area (shoelace) — negative = CW
        n = len(coords)
        signed_area = sum(
            (coords[i][0] * coords[(i + 1) % n][1] - coords[(i + 1) % n][0] * coords[i][1])
            for i in range(n)
        ) / 2.0
        assert signed_area < 0, (
            f"Shapefile outer ring is CCW (signed_area={signed_area:.4f}). "
            "Must be CW for the SASClouds server."
        )

    def test_accepts_feature_collection(self, client, tmp_path):
        shp_path = client._create_shapefile(BEIJING_FC, tmp_path)
        assert shp_path.exists()

    def test_accepts_feature_wrapper(self, client, tmp_path):
        feat = {"type": "Feature", "geometry": BEIJING_GEOJSON, "properties": {}}
        shp_path = client._create_shapefile(feat, tmp_path)
        assert shp_path.exists()

    def test_selects_largest_from_multipolygon(self, client, tmp_path):
        small = [[[0.0, 0.0], [0.1, 0.0], [0.1, 0.1], [0.0, 0.1], [0.0, 0.0]]]
        large = [[[116.2, 39.8], [116.6, 39.8], [116.6, 40.1],
                  [116.2, 40.1], [116.2, 39.8]]]
        mp = {
            "type": "MultiPolygon",
            "coordinates": [small, large],
        }
        shp_path = client._create_shapefile(mp, tmp_path)
        sf = shapefile.Reader(str(shp_path.with_suffix("")))
        pts = sf.shapes()[0].points
        # The large polygon spans roughly 0.4°×0.3° — all points > 100°
        assert all(abs(p[0]) > 100 for p in pts), "Large polygon was not selected"

    def test_simplifies_dense_polygon(self, client, tmp_path):
        # 400 points around a circle — should be simplified to ≤ 200 vertices
        import math as _math
        coords = [
            [116.4 + 0.2 * _math.cos(2 * _math.pi * i / 400),
             40.0  + 0.2 * _math.sin(2 * _math.pi * i / 400)]
            for i in range(400)
        ]
        coords.append(coords[0])
        geojson = {"type": "Polygon", "coordinates": [coords]}
        shp_path = client._create_shapefile(geojson, tmp_path)
        sf = shapefile.Reader(str(shp_path.with_suffix("")))
        n_pts = len(sf.shapes()[0].points)
        assert n_pts <= 201, f"Dense polygon not simplified: {n_pts} points"

    def test_repairs_invalid_polygon(self, client, tmp_path):
        # Self-intersecting bowtie — buffer(0) should fix it
        bowtie = {
            "type": "Polygon",
            "coordinates": [[
                [116.2, 39.8], [116.6, 40.1],
                [116.6, 39.8], [116.2, 40.1],
                [116.2, 39.8],
            ]],
        }
        # Should not raise
        shp_path = client._create_shapefile(bowtie, tmp_path)
        assert shp_path.exists()

    def test_rejects_unsupported_geometry(self, client, tmp_path):
        line = {
            "type": "LineString",
            "coordinates": [[116.2, 39.8], [116.6, 40.1]],
        }
        with pytest.raises(ValueError, match="Unsupported geometry"):
            client._create_shapefile(line, tmp_path)

    def test_raises_for_empty_feature_collection(self, client, tmp_path):
        empty_fc = {"type": "FeatureCollection", "features": []}
        with pytest.raises(ValueError):
            client._create_shapefile(empty_fc, tmp_path)


# =============================================================================
# 7. CORNER ORDERING (_order_corners_for_download)
# =============================================================================

class TestOrderCornersForDownload:
    def test_returns_ul_ur_ll_for_rectangle(self):
        from sasclouds_api_scraper import _order_corners_for_download
        # Rectangle: NW, NE, SE, SW = (8,49),(9,49),(9,48),(8,48)
        fp = {
            "coordinates": [[
                [8.0, 48.0], [9.0, 48.0],
                [9.0, 49.0], [8.0, 49.0],
                [8.0, 48.0],
            ]]
        }
        result = _order_corners_for_download(fp)
        assert result is not None
        ul, ur, ll = result
        # UL = NW → highest lat, lowest lon
        assert ul[1] > ll[1], "UL should have higher lat than LL"
        assert ul[0] < ur[0], "UL should have lower lon than UR"

    def test_returns_none_for_too_few_points(self):
        from sasclouds_api_scraper import _order_corners_for_download
        fp = {"coordinates": [[[116.2, 39.8], [116.6, 40.1]]]}
        assert _order_corners_for_download(fp) is None

    def test_returns_none_on_bad_geojson(self):
        from sasclouds_api_scraper import _order_corners_for_download
        assert _order_corners_for_download({}) is None
        assert _order_corners_for_download({"coordinates": []}) is None


# =============================================================================
# 8. VALIDATE SCENE
# =============================================================================

class TestValidateScene:
    @pytest.fixture
    def client(self):
        from sasclouds_api_scraper import SASCloudsAPIClient
        with patch.object(SASCloudsAPIClient, "_init_session", return_value="v5"):
            c = SASCloudsAPIClient.__new__(SASCloudsAPIClient)
            import requests
            c.session = requests.Session()
            c.api_version = "v5"
            return c

    def test_valid_scene_returns_true(self, client):
        assert client.validate_scene(SAMPLE_SCENE) is True

    def test_missing_field_returns_false(self, client):
        incomplete = {k: v for k, v in SAMPLE_SCENE.items() if k != "cloudPercent"}
        assert client.validate_scene(incomplete) is False

    def test_all_required_fields_checked(self, client):
        required = ["satelliteId", "sensorId", "acquisitionTime",
                    "cloudPercent", "quickViewUri", "boundary"]
        for field in required:
            scene = {k: v for k, v in SAMPLE_SCENE.items() if k != field}
            assert client.validate_scene(scene) is False, f"Should fail without {field}"


# =============================================================================
# 9. ENSURE_PLAYWRIGHT_BROWSER
# =============================================================================

class TestEnsurePlaywrightBrowser:
    def test_skips_gracefully_when_playwright_missing(self):
        from sasclouds_api_scraper import ensure_playwright_browser
        # Patch the import to fail so we test the skip path
        import builtins
        real_import = builtins.__import__
        def mock_import(name, *args, **kwargs):
            if name == "playwright":
                raise ImportError("mocked missing playwright")
            return real_import(name, *args, **kwargs)
        with patch("builtins.__import__", side_effect=mock_import):
            # Should not raise
            ensure_playwright_browser()

    def test_handles_subprocess_timeout(self):
        from sasclouds_api_scraper import ensure_playwright_browser
        import subprocess
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("cmd", 60)):
            # Should log warning and not raise
            ensure_playwright_browser()


# =============================================================================
# 10. ANTIMERIDIAN SPLITTING (sasclouds_map_utils)
# =============================================================================

class TestAntimeridian:
    def test_normal_polygon_not_split(self):
        from sasclouds_map_utils import split_polygon_at_antimeridian
        poly = shapely_shape(BEIJING_GEOJSON)
        parts = split_polygon_at_antimeridian(poly)
        assert len(parts) == 1

    def test_antimeridian_polygon_is_split(self):
        from sasclouds_map_utils import split_polygon_at_antimeridian
        poly = shapely_shape(ANTIMERIDIAN_GEOJSON)
        parts = split_polygon_at_antimeridian(poly)
        assert len(parts) >= 2, "Antimeridian polygon should produce at least 2 parts"

    def test_split_parts_within_bounds(self):
        from sasclouds_map_utils import split_polygon_at_antimeridian
        poly = shapely_shape(ANTIMERIDIAN_GEOJSON)
        for part in split_polygon_at_antimeridian(poly):
            bounds = part.bounds
            assert bounds[0] >= -180 and bounds[2] <= 180

    def test_empty_polygon_returns_empty_list(self):
        from sasclouds_map_utils import split_polygon_at_antimeridian
        empty = Polygon()
        assert split_polygon_at_antimeridian(empty) == []


# =============================================================================
# 11. NORMALIZE LONGITUDE (sasclouds_map_utils)
# =============================================================================

class TestNormalizeLongitude:
    def test_normal_longitudes_unchanged(self):
        from sasclouds_map_utils import normalize_longitude
        for lon in (0.0, 90.0, -90.0, 180.0, -180.0):
            result = normalize_longitude(lon)
            assert -180.0 <= result <= 180.0

    def test_wraps_positive_overflow(self):
        from sasclouds_map_utils import normalize_longitude
        assert normalize_longitude(270.0) == pytest.approx(-90.0)

    def test_wraps_negative_overflow(self):
        from sasclouds_map_utils import normalize_longitude
        assert normalize_longitude(-270.0) == pytest.approx(90.0)

    def test_wraps_360(self):
        from sasclouds_map_utils import normalize_longitude
        assert normalize_longitude(360.0) == pytest.approx(0.0)


# =============================================================================
# 12. CORNER ORDERING (sasclouds_map_utils)
# =============================================================================

class TestOrderCorners:
    def test_returns_nw_ne_se_sw(self):
        from sasclouds_map_utils import _order_corners
        # Square: lat 48–49, lon 8–9 → NW=(49,8) NE=(49,9) SE=(48,9) SW=(48,8)
        fp = {
            "coordinates": [[
                [8.0, 48.0], [9.0, 48.0],
                [9.0, 49.0], [8.0, 49.0],
                [8.0, 48.0],
            ]]
        }
        corners = _order_corners(fp)
        assert corners is not None
        assert len(corners) == 4
        nw, ne, se, sw = corners
        # NW: highest lat, lowest lon
        assert nw[0] > se[0], "NW lat should be higher than SE lat"
        assert nw[1] < ne[1], "NW lon should be lower than NE lon"
        # SE: lowest lat, highest lon
        assert se[0] < nw[0]
        assert se[1] > sw[1]

    def test_returns_none_for_too_few_points(self):
        from sasclouds_map_utils import _order_corners
        fp = {"coordinates": [[[0, 0], [1, 1]]]}
        assert _order_corners(fp) is None

    def test_handles_closed_ring(self):
        from sasclouds_map_utils import _order_corners
        # Closed ring: last == first
        fp = {
            "coordinates": [[
                [8.0, 48.0], [9.0, 48.0], [9.0, 49.0], [8.0, 49.0], [8.0, 48.0],
            ]]
        }
        assert _order_corners(fp) is not None

    def test_no_nan_in_valid_corners(self):
        from sasclouds_map_utils import _order_corners
        fp = {"coordinates": [[[8.0, 48.0], [9.0, 48.0], [9.0, 49.0], [8.0, 49.0], [8.0, 48.0]]]}
        corners = _order_corners(fp)
        for c in corners:
            for v in c:
                assert math.isfinite(v), f"NaN/Inf in corner: {corners}"


# =============================================================================
# 13. SATELLITE COLOUR (_sat_color)
# =============================================================================

class TestSatColor:
    def test_known_satellite_returns_hex(self):
        from sasclouds_map_utils import _sat_color
        color = _sat_color("GF1")
        assert color.startswith("#")
        assert len(color) == 7

    def test_unknown_satellite_returns_deterministic_hex(self):
        from sasclouds_map_utils import _sat_color
        c1 = _sat_color("UNKNOWN-XYZ-007")
        c2 = _sat_color("UNKNOWN-XYZ-007")
        assert c1 == c2, "Unknown satellite color must be deterministic"
        assert c1.startswith("#") and len(c1) == 7

    def test_different_unknowns_may_differ(self):
        from sasclouds_map_utils import _sat_color
        # Not guaranteed, but highly likely with MD5
        colors = {_sat_color(f"SAT-{i}") for i in range(10)}
        assert len(colors) > 1, "All 10 satellites got the same colour"


# =============================================================================
# 14. HANDLE DRAWING (sasclouds_map_utils)
# =============================================================================

class TestHandleDrawing:
    def test_returns_none_for_empty_map_data(self):
        from sasclouds_map_utils import handle_drawing
        assert handle_drawing(None) is None
        assert handle_drawing({}) is None

    def test_extracts_polygon_from_map_data(self):
        from sasclouds_map_utils import handle_drawing
        map_data = {
            "last_active_drawing": {
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[[116.2, 39.8], [116.6, 39.8],
                                     [116.6, 40.1], [116.2, 40.1],
                                     [116.2, 39.8]]],
                }
            }
        }
        result = handle_drawing(map_data)
        assert result is not None
        assert result["type"] == "Polygon"
        assert len(result["coordinates"][0]) == 5

    def test_returns_none_for_non_polygon(self):
        from sasclouds_map_utils import handle_drawing
        map_data = {
            "last_active_drawing": {
                "geometry": {"type": "Point", "coordinates": [116.4, 40.0]}
            }
        }
        assert handle_drawing(map_data) is None

    def test_returns_none_when_no_drawing(self):
        from sasclouds_map_utils import handle_drawing
        assert handle_drawing({"last_active_drawing": None}) is None


# =============================================================================
# 15. DATE TO MS (_date_to_ms in sasclouds_search_logic)
# =============================================================================

class TestDateToMs:
    def test_date_converts_correctly(self):
        from sasclouds_search_logic import _date_to_ms
        d = date(2025, 1, 1)
        ms = _date_to_ms(d)
        assert isinstance(ms, int)
        # 2025-01-01 00:00:00 local — result depends on system timezone;
        # sanity check: should be within ±13h of 1735689600000 (UTC)
        expected_utc_ms = 1735689600000
        assert abs(ms - expected_utc_ms) < 13 * 3600 * 1000

    def test_datetime_converts_correctly(self):
        from sasclouds_search_logic import _date_to_ms
        dt = datetime(2025, 1, 1, 0, 0, 0)
        ms = _date_to_ms(dt)
        assert isinstance(ms, int)

    def test_start_before_end(self):
        from sasclouds_search_logic import _date_to_ms
        start = _date_to_ms(date(2024, 1, 1))
        end = _date_to_ms(date(2025, 1, 1))
        assert start < end


# =============================================================================
# 16. ORBITSHOW — CONFIG.SATELLITES
# =============================================================================

class TestOrbitShowSatellites:
    def test_satellites_dict_has_categories(self):
        from config.satellites import SATELLITES
        assert len(SATELLITES) > 0
        for cat_name, cat in SATELLITES.items():
            assert isinstance(cat, dict), f"Category {cat_name} is not a dict"

    def test_satellite_count_positive(self):
        from config.satellites import get_satellite_count
        count = get_satellite_count()
        assert count > 50, f"Expected >50 satellites, got {count}"

    def test_get_satellite_by_norad(self):
        from config.satellites import get_satellite_by_norad
        sat = get_satellite_by_norad(41727)  # Gaofen-3 01
        assert sat is not None
        assert "cameras" in sat
        assert "norad" in sat

    def test_get_satellites_by_type(self):
        from config.satellites import get_satellites_by_type
        sar = get_satellites_by_type("SAR")
        optical = get_satellites_by_type("Optical")
        assert len(sar) > 0
        assert len(optical) > 0

    def test_all_cameras_have_swath_and_resolution(self):
        from config.satellites import get_all_cameras
        for cat, sat, cam, info in get_all_cameras():
            assert "swath_km" in info, f"Missing swath_km in {sat}/{cam}"
            assert "resolution_m" in info, f"Missing resolution_m in {sat}/{cam}"
            assert info["swath_km"] > 0
            assert info["resolution_m"] > 0

    def test_satellite_has_required_fields(self):
        from config.satellites import SATELLITES
        required = {"norad", "type", "provider", "cameras"}
        for cat_name, cat in SATELLITES.items():
            for sat_name, sat in cat.items():
                missing = required - set(sat.keys())
                assert not missing, f"{cat_name}/{sat_name} missing: {missing}"


# =============================================================================
# 17. ORBITSHOW — CONSTANTS
# =============================================================================

class TestOrbitShowConstants:
    def test_earth_radius(self):
        from config.constants import EARTH_RADIUS_KM
        assert 6370 < EARTH_RADIUS_KM < 6380

    def test_default_center_is_lat_lon(self):
        from config.constants import DEFAULT_CENTER
        assert len(DEFAULT_CENTER) == 2
        lat, lon = DEFAULT_CENTER
        assert -90 <= lat <= 90
        assert -180 <= lon <= 180


# =============================================================================
# 18. ORBITSHOW — MODELS (SatellitePass)
# =============================================================================

class TestSatellitePass:
    def _make_pass(self):
        from models.satellite_pass import SatellitePass
        from shapely.geometry import LineString, Polygon, Point
        return SatellitePass(
            id="test-pass-001",
            satellite_name="GF2",
            camera_name="PMS",
            norad_id=40118,
            provider="Siwei",
            pass_time=datetime(2025, 6, 15, 10, 30, 0, tzinfo=__import__("pytz").UTC),
            ground_track=LineString([[116.4, 39.9], [116.5, 40.0]]),
            footprint=Polygon([[116.2, 39.8], [116.6, 39.8],
                               [116.6, 40.1], [116.2, 40.1], [116.2, 39.8]]),
            swath_km=11.0,
            resolution_m=0.8,
            sensor_type="Optical",
            color="#00CED1",
            inclination=97.4,
            orbit_direction="Descending",
            track_azimuth=180.0,
            min_ona=2.5,
            max_ona=15.0,
            aoi_center=Point(116.4, 40.0),
        )

    def test_instantiation(self):
        p = self._make_pass()
        assert p.satellite_name == "GF2"
        assert p.swath_km == 11.0

    def test_time_properties_return_strings(self):
        p = self._make_pass()
        assert ":" in p.time_cet
        assert ":" in p.time_utc
        assert "-" in p.date_utc

    def test_local_time_approx(self):
        p = self._make_pass()
        lt = p.local_time_approx
        assert isinstance(lt, str) and len(lt) > 5

    def test_display_footprint_defaults_to_none(self):
        p = self._make_pass()
        assert p.display_footprint is None

    def test_tasked_attributes_default_false(self):
        p = self._make_pass()
        assert not p.selected
        assert not p.is_central
        assert not p.max_ona_reached


# =============================================================================
# 19. AOI HANDLER (data.aoi_handler)
# =============================================================================

class TestAOIHandler:
    def test_loads_geojson_file(self, tmp_path):
        from data.aoi_handler import AOIHandler
        geojson = {
            "type": "FeatureCollection",
            "features": [{
                "type": "Feature",
                "geometry": BEIJING_GEOJSON,
                "properties": {},
            }],
        }
        p = tmp_path / "aoi.geojson"
        p.write_text(json.dumps(geojson))
        result = AOIHandler.load_from_filepath(str(p))
        assert result is not None
        assert result.geom_type == "Polygon"

    def test_calculates_area_km2(self):
        from data.aoi_handler import AOIHandler
        from shapely.geometry import shape
        poly = shape(BEIJING_GEOJSON)
        area, unit = AOIHandler.calculate_area(poly)
        assert area > 0
        assert unit in ("km²", "ha", "m²")

    def test_calculate_area_none_returns_zero(self):
        from data.aoi_handler import AOIHandler
        area, unit = AOIHandler.calculate_area(None)
        assert area == 0

    def test_returns_none_for_unsupported_extension(self, tmp_path):
        from data.aoi_handler import AOIHandler
        p = tmp_path / "aoi.csv"
        p.write_text("lat,lon\n40,116\n")
        result = AOIHandler.load_from_filepath(str(p))
        assert result is None

    def test_loads_zipfile_with_shapefile(self, tmp_path):
        """Create a minimal shapefile ZIP and verify AOIHandler can read it."""
        import zipfile as zf
        # Build a minimal shapefile in a temp dir
        shp_dir = tmp_path / "shp"
        shp_dir.mkdir()
        import geopandas as gpd
        from shapely.geometry import shape
        gdf = gpd.GeoDataFrame(
            [{"geometry": shape(BEIJING_GEOJSON)}],
            crs="EPSG:4326",
        )
        gdf.to_file(str(shp_dir / "aoi.shp"))

        # Zip it
        zip_path = tmp_path / "aoi.zip"
        with zf.ZipFile(zip_path, "w") as z:
            for f in shp_dir.iterdir():
                z.write(f, f.name)

        from data.aoi_handler import AOIHandler
        result = AOIHandler.load_from_filepath(str(zip_path))
        assert result is not None
        assert result.geom_type == "Polygon"


# =============================================================================
# 20. SASCLOUDS_SIDEBAR — render_sasclouds_sidebar imports cleanly
# =============================================================================

class TestSASCloudsSidebar:
    def test_module_has_render_function(self):
        import sasclouds_sidebar
        assert callable(sasclouds_sidebar.render_sasclouds_sidebar)

    def test_sat_label_formats_correctly(self):
        import sasclouds_sidebar
        sat = {"satelliteId": "GF2", "sensorIds": ["PMS", "MUX"]}
        label = sasclouds_sidebar._sat_label(sat)
        assert "GF2" in label
        assert "PMS" in label

    def test_sat_label_no_sensors_shows_all(self):
        import sasclouds_sidebar
        sat = {"satelliteId": "GF3", "sensorIds": []}
        label = sasclouds_sidebar._sat_label(sat)
        assert "GF3" in label
        assert "All sensors" in label


# =============================================================================
# 21. SEARCH LOGIC — module-level helpers
# =============================================================================

class TestSearchLogic:
    def test_module_has_run_search(self):
        import sasclouds_search_logic
        assert callable(sasclouds_search_logic.run_search)

    def test_module_has_render_results_table(self):
        import sasclouds_search_logic
        assert callable(sasclouds_search_logic.render_results_table)

    def test_module_has_download_zip(self):
        import sasclouds_search_logic
        assert callable(sasclouds_search_logic._do_download_zip)


# =============================================================================
# 22. MAP UTILS — module-level interface
# =============================================================================

class TestMapUtils:
    def test_module_has_render_function(self):
        import sasclouds_map_utils
        assert callable(sasclouds_map_utils.render_sasclouds_map)

    def test_fetch_image_b64_returns_empty_for_bad_url(self):
        from sasclouds_map_utils import _fetch_image_b64
        # Cache key must be unique per test run to avoid cross-test pollution
        import time as _t
        fake_url = f"https://nonexistent.sasclouds-test-{_t.time()}.invalid/img.jpg"
        result = _fetch_image_b64(fake_url)
        assert result == "", "Expected empty string for a URL that fails to fetch"

    def test_fetch_image_b64_result_is_cached(self):
        from sasclouds_map_utils import _fetch_image_b64
        import time as _t
        url = f"https://nonexistent.cache-test-{int(_t.time())}.invalid/a.jpg"
        r1 = _fetch_image_b64(url)
        r2 = _fetch_image_b64(url)
        assert r1 == r2


# =============================================================================
# 23. INTEGRATION (LIVE) — real network calls
# =============================================================================

@pytest.mark.live
class TestLiveAPI:
    """
    Tests that make real HTTP requests to sasclouds.com.
    Run with:  pytest tests/test_full_suite.py -v -m live
    """

    @pytest.fixture(scope="class")
    def client(self):
        from sasclouds_api_scraper import SASCloudsAPIClient
        return SASCloudsAPIClient()

    def test_api_version_detected(self, client):
        assert client.api_version.startswith("v"), (
            f"Expected version like 'v5', got {client.api_version!r}"
        )

    def test_upload_aoi_returns_upload_id(self, client):
        upload_id = client.upload_aoi(BEIJING_GEOJSON)
        assert isinstance(upload_id, str) and upload_id, (
            f"Expected non-empty uploadId, got {upload_id!r}"
        )

    def test_search_returns_data_structure(self, client):
        upload_id = client.upload_aoi(BEIJING_GEOJSON)
        # Search GF2 for a 3-month window — should return results in Beijing area
        start_ms = int(datetime(2024, 1, 1).timestamp() * 1000)
        end_ms   = int(datetime(2024, 4, 1).timestamp() * 1000)
        result = client.search_scenes(
            upload_id, start_ms, end_ms,
            cloud_max=30,
            satellites=[{"satelliteId": "GF2", "sensorIds": ["PMS"]}],
            page=1, page_size=10,
        )
        assert result.get("code") == 0, f"API returned error: {result}"
        assert "data" in result
        assert "pageInfo" in result

    def test_scene_fields_match_schema(self, client):
        upload_id = client.upload_aoi(BEIJING_GEOJSON)
        start_ms = int(datetime(2024, 1, 1).timestamp() * 1000)
        end_ms   = int(datetime(2024, 4, 1).timestamp() * 1000)
        result = client.search_scenes(
            upload_id, start_ms, end_ms,
            cloud_max=30,
            satellites=[{"satelliteId": "GF2", "sensorIds": ["PMS"]}],
            page=1, page_size=5,
        )
        scenes = result.get("data", [])
        if not scenes:
            pytest.skip("No scenes returned — cannot validate schema")
        for scene in scenes:
            assert client.validate_scene(scene), (
                f"Scene failed schema validation: {list(scene.keys())}"
            )

    def test_quickview_url_rewrite(self, client):
        """Quickview URLs must use the HTTPS CDN, not the HTTP origin."""
        upload_id = client.upload_aoi(BEIJING_GEOJSON)
        start_ms = int(datetime(2024, 1, 1).timestamp() * 1000)
        end_ms   = int(datetime(2024, 4, 1).timestamp() * 1000)
        result = client.search_scenes(
            upload_id, start_ms, end_ms,
            cloud_max=50,
            satellites=[{"satelliteId": "GF2", "sensorIds": ["PMS"]}],
            page=1, page_size=5,
        )
        for scene in result.get("data", []):
            qv = scene.get("quickViewUri", "")
            if qv:
                assert "quickview.obs.cn-north-10.myhuaweicloud.com" not in qv or qv.startswith("https"), (
                    "Raw quickview URI should be rewritten in search_logic — "
                    "check sasclouds_search_logic.run_search"
                )

    def test_boundary_parses_as_geojson(self, client):
        upload_id = client.upload_aoi(BEIJING_GEOJSON)
        start_ms = int(datetime(2024, 1, 1).timestamp() * 1000)
        end_ms   = int(datetime(2024, 4, 1).timestamp() * 1000)
        result = client.search_scenes(
            upload_id, start_ms, end_ms,
            cloud_max=50,
            satellites=[{"satelliteId": "GF2", "sensorIds": ["PMS"]}],
            page=1, page_size=5,
        )
        for scene in result.get("data", []):
            boundary_str = scene.get("boundary", "")
            if boundary_str:
                geom = json.loads(boundary_str)
                assert "coordinates" in geom, "Boundary missing coordinates"
                # Should be parseable by shapely
                shapely_shape(geom)


# =============================================================================
# ENTRY POINT
# =============================================================================

if __name__ == "__main__":
    import subprocess, sys
    sys.exit(subprocess.call(
        [sys.executable, "-m", "pytest", __file__, "-v", "--tb=short"],
        cwd=str(ROOT),
    ))
