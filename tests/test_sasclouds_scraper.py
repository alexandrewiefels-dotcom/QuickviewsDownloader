# tests/test_sasclouds_scraper.py
"""
Test suite covering all updated modules:

  aoi_handler          – GeoJSON / KML / Shapefile-ZIP loading, area calculation
  map_utils            – longitude normalisation, antimeridian splitting,
                         handle_drawing, render_main_map (new unified map)
  sasclouds_api_scraper – SASCloudsAPIClient (upload / search / download),
                          convert_uploaded_file_to_geojson (GeoJSON/KML/KMZ/ZIP),
                          logging helpers
  search_logic         – run_search (pagination, session_state keys,
                          quickview URL rewrite, bad-boundary skip),
                          create_download_zip (features_for_map preserved)
"""
import json
import logging
import os
import sys
import tempfile
import zipfile
from datetime import date
from io import BytesIO
from pathlib import Path
from unittest.mock import MagicMock, mock_open, patch

import pytest
import requests
from shapely.geometry import Polygon, mapping

sys.path.insert(0, str(Path(__file__).parent.parent))

from aoi_handler import AOIHandler
from map_utils import (
    handle_drawing,
    normalize_longitude,
    render_main_map,
    split_polygon_at_antimeridian,
)
from sasclouds_api_scraper import (
    SASCloudsAPIClient,
    convert_uploaded_file_to_geojson,
    log_aoi_upload,
    log_search,
)
from search_logic import create_download_zip, run_search

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s – %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

# ── Streamlit stub ────────────────────────────────────────────────────────────
import streamlit as st

st._is_running_with_streamlit = False
st.session_state = {}


# =============================================================================
# Shared fixtures
# =============================================================================

def _make_mock_response(status=200, json_body=None, content=b"", text=""):
    """Build a mock requests.Response for patching requests.Session.request."""
    r = MagicMock()
    r.status_code = status
    r.content = content
    r.text = text
    r.raise_for_status = MagicMock()
    r.json = MagicMock(return_value=json_body or {})
    return r


@pytest.fixture
def mock_requests_post():
    """Patch requests.Session.request for POST-based tests.
    Also skips _init_session by making load_config return a pinned api_version."""
    resp = _make_mock_response()
    with patch("requests.Session.request", return_value=resp) as mock, \
         patch("sasclouds_api_scraper.load_config", return_value={"api_version": "v5"}):
        mock._mock_response = resp          # tests can reconfigure via mock._mock_response
        yield mock


@pytest.fixture
def mock_requests_get():
    """Patch requests.Session.request for GET-based tests (downloads)."""
    resp = _make_mock_response(content=b"fake-image")
    with patch("requests.Session.request", return_value=resp) as mock, \
         patch("sasclouds_api_scraper.load_config", return_value={"api_version": "v5"}):
        mock._mock_response = resp
        yield mock


@pytest.fixture
def mock_shapefile_writer():
    with patch("shapefile.Writer") as mock:
        yield mock


@pytest.fixture
def mock_tempfile_dir():
    with patch("tempfile.TemporaryDirectory") as mock:
        real_dir = tempfile.mkdtemp()
        mock.return_value.__enter__ = MagicMock(return_value=real_dir)
        mock.return_value.__exit__ = MagicMock(return_value=False)
        mock.return_value.name = real_dir
        mock.return_value.cleanup = MagicMock()
        yield mock


@pytest.fixture
def mock_image_open():
    with patch("PIL.Image.open") as mock:
        yield mock


@pytest.fixture
def sample_polygon_geojson():
    return {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]]}


@pytest.fixture
def sample_geojson_file(tmp_path, sample_polygon_geojson):
    p = tmp_path / "test.geojson"
    p.write_text(json.dumps(sample_polygon_geojson))
    return str(p)


@pytest.fixture
def sample_kml_file(tmp_path):
    kml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<kml xmlns="http://www.opengis.net/kml/2.2">'
        "<Placemark><Polygon><outerBoundaryIs><LinearRing>"
        "<coordinates>0,0 1,0 1,1 0,1 0,0</coordinates>"
        "</LinearRing></outerBoundaryIs></Polygon></Placemark></kml>"
    )
    p = tmp_path / "test.kml"
    p.write_text(kml)
    return str(p)


@pytest.fixture
def sample_shapefile_zip(tmp_path):
    shp_dir = tmp_path / "shp"
    shp_dir.mkdir()
    _write_test_shapefile(shp_dir)
    zip_path = tmp_path / "test.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        for ext in (".shp", ".shx", ".dbf"):
            f = shp_dir / f"test{ext}"
            if f.exists():
                zf.write(f, arcname=f"test{ext}")
    return str(zip_path)


@pytest.fixture
def sample_features():
    """One footprint scene over Beijing."""
    return [
        {
            "geometry": {
                "type": "Polygon",
                "coordinates": [
                    [[116.0, 39.0], [117.0, 39.0], [117.0, 40.0], [116.0, 40.0], [116.0, 39.0]]
                ],
            },
            "properties": {
                "satellite": "GF5",
                "sensor": "AHSI",
                "date": "2025-01-01",
                "cloud": 10,
                "product_id": "prod123",
                "quickview": "https://example.com/thumb.jpg",
            },
        }
    ]


def _write_test_shapefile(directory: Path) -> Path:
    import shapefile as pyshp
    shp_path = directory / "test.shp"
    w = pyshp.Writer(shp_path, pyshp.POLYGON)
    w.field("ID", "N", 10)
    w.poly([[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]])
    w.record(1)
    w.close()
    return shp_path


def _make_scene(prod_id: str = "prod123") -> dict:
    return {
        "satelliteId": "GF5",
        "sensorId": "AHSI",
        "acquisitionTime": 1609459200000,
        "cloudPercent": 10,
        "productId": prod_id,
        "boundary": json.dumps({
            "type": "Polygon",
            "coordinates": [[[116, 39], [117, 39], [117, 40], [116, 40], [116, 39]]],
        }),
        "quickViewUri": "http://quickview.sasclouds.com/img.jpg",
    }


def _search_kwargs(polygon_geojson: dict) -> dict:
    return dict(
        polygon_geojson=polygon_geojson,
        aoi_filename="test.geojson",
        start_date=date(2025, 1, 1),
        end_date=date(2025, 6, 30),
        max_cloud=20,
        selected_satellites=[{"satelliteId": "GF5", "sensorIds": ["AHSI"]}],
        session_id="test-session-id",
        log_container=MagicMock(),
    )


# =============================================================================
# AOIHandler
# =============================================================================

class TestAOIHandler:
    def test_load_geojson(self, sample_geojson_file):
        poly = AOIHandler.load_from_filepath(sample_geojson_file)
        assert isinstance(poly, Polygon)
        assert poly.bounds == (0, 0, 1, 1)

    def test_load_kml(self, sample_kml_file):
        poly = AOIHandler.load_from_filepath(sample_kml_file)
        assert isinstance(poly, Polygon)
        assert poly.area > 0.9

    def test_load_shapefile_zip(self, sample_shapefile_zip):
        poly = AOIHandler.load_from_filepath(sample_shapefile_zip)
        assert isinstance(poly, Polygon)
        assert -0.1 <= poly.bounds[0] and poly.bounds[2] <= 1.1

    def test_load_unsupported_format_returns_none(self, tmp_path):
        f = tmp_path / "data.csv"
        f.write_text("lat,lon\n1,2")
        assert AOIHandler.load_from_filepath(str(f)) is None

    def test_calculate_area_polygon(self, sample_polygon_geojson):
        poly = Polygon(sample_polygon_geojson["coordinates"][0])
        area, unit = AOIHandler.calculate_area(poly)
        assert area > 0
        assert unit in ("km²", "m²", "ha")

    def test_calculate_area_none_returns_zero(self):
        area, unit = AOIHandler.calculate_area(None)
        assert area == 0
        assert unit == "km²"


# =============================================================================
# map_utils – normalize_longitude
# =============================================================================

def test_normalize_longitude_overflow_positive():
    assert normalize_longitude(190) == -170

def test_normalize_longitude_overflow_negative():
    assert normalize_longitude(-190) == 170

def test_normalize_longitude_at_180():
    assert normalize_longitude(180) == -180

def test_normalize_longitude_normal_values():
    assert normalize_longitude(0) == 0
    assert normalize_longitude(90) == 90
    assert normalize_longitude(-90) == -90


# =============================================================================
# map_utils – split_polygon_at_antimeridian
# NOTE: function expects shapely Polygon objects, NOT GeoJSON dicts.
# =============================================================================

def test_split_no_cross():
    poly = Polygon([(170, 10), (175, 10), (175, 20), (170, 20), (170, 10)])
    parts = split_polygon_at_antimeridian(poly)
    assert len(parts) == 1
    assert parts[0].equals(poly)

def test_split_polygon_spanning_over_180_degrees_returns_normalised():
    """
    A Shapely Polygon whose coordinates span more than 180° of longitude
    (e.g. a rectangle from -170 to 170) cannot be split by the shift-and-clip
    algorithm because shifting by ±360° moves the whole shape outside the world
    box and both intersections are empty.  The function therefore returns the
    normalised polygon unchanged (1 part).  The result must still lie within
    the valid [-180, 180] longitude range.
    """
    poly = Polygon([(170, 10), (-170, 10), (-170, 20), (170, 20), (170, 10)])
    parts = split_polygon_at_antimeridian(poly)
    assert len(parts) == 1
    mn, _, mx, _ = parts[0].bounds
    assert -180 <= mn and mx <= 180

def test_split_empty_polygon():
    empty = Polygon()
    assert split_polygon_at_antimeridian(empty) == []

def test_split_regular_polygon_not_near_antimeridian():
    poly = Polygon([(116, 39), (117, 39), (117, 40), (116, 40), (116, 39)])
    parts = split_polygon_at_antimeridian(poly)
    assert len(parts) == 1
    assert parts[0].is_valid

def test_split_receives_shapely_not_geojson_dict():
    """Regression: caller must pass shapely object; passing a dict raises AttributeError."""
    geojson_dict = {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]]}
    with pytest.raises(AttributeError):
        split_polygon_at_antimeridian(geojson_dict)


# =============================================================================
# map_utils – handle_drawing
# =============================================================================

def test_handle_drawing_valid():
    data = {
        "last_active_drawing": {
            "geometry": {
                "type": "Polygon",
                "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]],
            }
        }
    }
    result = handle_drawing(data)
    assert result is not None
    assert result["type"] == "Polygon"
    assert len(result["coordinates"][0]) == 5

def test_handle_drawing_empty_dict():
    assert handle_drawing({}) is None

def test_handle_drawing_none():
    assert handle_drawing(None) is None

def test_handle_drawing_wrong_geometry_type():
    data = {
        "last_active_drawing": {
            "geometry": {"type": "LineString", "coordinates": [[0, 0], [1, 1]]}
        }
    }
    assert handle_drawing(data) is None

def test_handle_drawing_missing_geometry():
    data = {"last_active_drawing": {"type": "Feature"}}
    assert handle_drawing(data) is None


# =============================================================================
# map_utils – render_main_map  (new unified map replacing show_aoi_map +
#             show_footprints_map)
# =============================================================================

class TestRenderMainMap:

    @patch("map_utils.st_folium")
    def test_renders_with_no_inputs(self, mock_st_folium):
        mock_st_folium.return_value = {}
        result = render_main_map()
        mock_st_folium.assert_called_once()
        assert result == {}

    @patch("map_utils.st_folium")
    def test_renders_with_aoi(self, mock_st_folium, sample_polygon_geojson):
        mock_st_folium.return_value = {}
        render_main_map(polygon_geojson=sample_polygon_geojson)
        mock_st_folium.assert_called_once()

    @patch("map_utils.st_folium")
    def test_renders_with_footprints(self, mock_st_folium, sample_features):
        mock_st_folium.return_value = {}
        render_main_map(features_for_map=sample_features)
        mock_st_folium.assert_called_once()

    @patch("map_utils.st_folium")
    def test_renders_with_aoi_and_footprints(self, mock_st_folium,
                                              sample_polygon_geojson, sample_features):
        mock_st_folium.return_value = {}
        result = render_main_map(polygon_geojson=sample_polygon_geojson,
                                 features_for_map=sample_features)
        mock_st_folium.assert_called_once()
        assert result == {}

    @patch("map_utils.st_folium")
    def test_uses_fixed_key_main_map(self, mock_st_folium):
        """key='main_map' must never change – Streamlit ties drawing state to it."""
        mock_st_folium.return_value = {}
        render_main_map()
        assert mock_st_folium.call_args.kwargs["key"] == "main_map"

    @patch("map_utils.st_folium")
    def test_default_centre_when_no_inputs(self, mock_st_folium):
        mock_st_folium.return_value = {}
        render_main_map()
        m = mock_st_folium.call_args.args[0]
        assert m.location == [20.0, 0.0]

    @patch("map_utils.st_folium")
    def test_centres_on_aoi_when_no_footprints(self, mock_st_folium, sample_polygon_geojson):
        mock_st_folium.return_value = {}
        render_main_map(polygon_geojson=sample_polygon_geojson)
        m = mock_st_folium.call_args.args[0]
        lat, lon = m.location
        # AOI spans [0,0]→[1,1], centre should be ~[0.5, 0.5]
        assert -0.1 < lat < 1.1
        assert -0.1 < lon < 1.1

    @patch("map_utils.st_folium")
    def test_centres_on_footprints_when_provided(self, mock_st_folium, sample_features):
        """Footprints over Beijing; centre should be near [39.5, 116.5]."""
        mock_st_folium.return_value = {}
        render_main_map(features_for_map=sample_features)
        m = mock_st_folium.call_args.args[0]
        lat, lon = m.location
        assert 35 < lat < 45
        assert 110 < lon < 125

    @patch("map_utils.st_folium")
    def test_handles_feature_collection_aoi(self, mock_st_folium):
        mock_st_folium.return_value = {}
        fc = {
            "type": "FeatureCollection",
            "features": [{
                "type": "Feature",
                "geometry": {"type": "Polygon",
                             "coordinates": [[[0, 0], [2, 0], [2, 2], [0, 2], [0, 0]]]},
                "properties": {},
            }],
        }
        render_main_map(polygon_geojson=fc)  # must not raise
        mock_st_folium.assert_called_once()

    @patch("map_utils.st_folium")
    def test_handles_antimeridian_footprint(self, mock_st_folium):
        """Footprint crossing ±180° must be split without raising."""
        mock_st_folium.return_value = {}
        features = [{
            "geometry": {
                "type": "Polygon",
                "coordinates": [[[170, 10], [-170, 10], [-170, 20], [170, 20], [170, 10]]],
            },
            "properties": {
                "satellite": "GF5", "sensor": "AHSI",
                "date": "2025-01-01", "cloud": 0,
                "product_id": "x", "quickview": "",
            },
        }]
        render_main_map(features_for_map=features)
        mock_st_folium.assert_called_once()

    @patch("map_utils.st_folium")
    def test_handles_bad_footprint_geometry_gracefully(self, mock_st_folium):
        """A footprint with no coordinates must not crash the whole map."""
        mock_st_folium.return_value = {}
        features = [{
            "geometry": {"type": "Polygon", "coordinates": []},
            "properties": {
                "satellite": "X", "sensor": "Y", "date": "2025-01-01",
                "cloud": 0, "product_id": "z", "quickview": "",
            },
        }]
        render_main_map(features_for_map=features)
        mock_st_folium.assert_called_once()

    @patch("map_utils.st_folium")
    def test_returns_st_folium_result(self, mock_st_folium):
        expected = {"last_active_drawing": None, "zoom": 5}
        mock_st_folium.return_value = expected
        result = render_main_map()
        assert result is expected


# =============================================================================
# sasclouds_api_scraper – SASCloudsAPIClient
# =============================================================================

class TestSASCloudsAPIClient:

    @pytest.fixture(autouse=True)
    def skip_init_session(self):
        """Skip real HTTP during __init__ by returning a pinned version from load_config."""
        with patch("sasclouds_api_scraper.load_config", return_value={"api_version": "v5"}):
            yield

    def test_init_uses_detected_version(self):
        with patch("sasclouds_api_scraper.load_config", return_value={"api_version": "v99"}):
            client = SASCloudsAPIClient()
        assert "v99" in client.api_base

    def test_upload_aoi_returns_upload_id(self, mock_requests_post,
                                           mock_tempfile_dir, sample_polygon_geojson):
        # mock_shapefile_writer intentionally absent — we need real .shp/.shx/.dbf
        # files on disk so that Path.read_bytes() succeeds.
        mock_requests_post._mock_response.json.return_value = {
            "code": 0, "data": {"uploadId": "uid_abc"},
        }
        mock_requests_post._mock_response.text = '{"code":0,"data":{"uploadId":"uid_abc"}}'
        uid = SASCloudsAPIClient().upload_aoi(sample_polygon_geojson)
        assert uid == "uid_abc"

    def test_upload_aoi_raises_on_api_error(self, mock_requests_post,
                                             mock_tempfile_dir, sample_polygon_geojson):
        # mock_shapefile_writer intentionally absent — real files required for read_bytes().
        mock_requests_post._mock_response.json.return_value = {
            "code": 1, "message": "Invalid polygon",
        }
        mock_requests_post._mock_response.text = '{"code":1,"message":"Invalid polygon"}'
        with pytest.raises(Exception, match="Upload failed: Invalid polygon"):
            SASCloudsAPIClient().upload_aoi(sample_polygon_geojson)

    def test_upload_aoi_raises_helpful_message_for_out_of_range(
            self, mock_requests_post,
            mock_tempfile_dir, sample_polygon_geojson):
        # mock_shapefile_writer intentionally absent — real files required for read_bytes().
        mock_requests_post._mock_response.json.return_value = {
            "code": 1, "message": "region out-of-range detected",
        }
        mock_requests_post._mock_response.text = '{"code":1,"message":"region out-of-range detected"}'
        with pytest.raises(Exception, match="AOI is outside the SASClouds archive coverage"):
            SASCloudsAPIClient().upload_aoi(sample_polygon_geojson)

    def test_search_scenes_returns_data(self, mock_requests_post):
        mock_requests_post._mock_response.json.return_value = {
            "code": 0,
            "data": [{"satelliteId": "GF5", "sensorId": "AHSI"}],
            "pageInfo": {"total": 1},
        }
        result = SASCloudsAPIClient().search_scenes(
            "uid", 0, 1, 20, [{"satelliteId": "GF5", "sensorIds": []}], 1, 50
        )
        assert result["data"][0]["satelliteId"] == "GF5"
        assert result["pageInfo"]["total"] == 1

    def test_search_scenes_raises_on_api_error(self, mock_requests_post):
        mock_requests_post._mock_response.json.return_value = {
            "code": 2, "message": "Invalid parameters",
        }
        with pytest.raises(Exception, match="Search API error: Invalid parameters"):
            SASCloudsAPIClient().search_scenes("uid", 0, 1, 20, [], 1, 50)

    def test_search_scenes_payload_contains_satellite_ids(self, mock_requests_post):
        mock_requests_post._mock_response.json.return_value = {
            "code": 0, "data": [], "pageInfo": {"total": 0},
        }
        sats = [{"satelliteId": "GF5", "sensorIds": ["AHSI"]},
                {"satelliteId": "ZY3-1", "sensorIds": ["MUX"]}]
        SASCloudsAPIClient().search_scenes("uid", 0, 1, 30, sats, 1, 50)
        # session.request("POST", url, json=payload, ...) — payload is in kwargs["json"]
        payload = mock_requests_post.call_args.kwargs["json"]
        ids = [s["satelliteId"] for s in payload["satellites"]]
        assert "GF5" in ids and "ZY3-1" in ids

    def test_search_scenes_payload_has_correct_cloud_max(self, mock_requests_post):
        mock_requests_post._mock_response.json.return_value = {
            "code": 0, "data": [], "pageInfo": {"total": 0},
        }
        SASCloudsAPIClient().search_scenes("uid", 0, 1, 35, [], 1, 50)
        payload = mock_requests_post.call_args.kwargs["json"]
        assert payload["cloudPercentMax"] == 35

    def test_search_scenes_payload_has_null_time_fields(self, mock_requests_post):
        """All four *Time fields must be present and None (confirmed from live HAR)."""
        mock_requests_post._mock_response.json.return_value = {
            "code": 0, "data": [], "pageInfo": {"total": 0},
        }
        SASCloudsAPIClient().search_scenes("uid", 0, 1, 20, [], 1, 50)
        payload = mock_requests_post.call_args.kwargs["json"]
        for field in ("tarInputTimeStart", "tarInputTimeEnd", "inputTimeStart", "inputTimeEnd"):
            assert field in payload, f"Missing field: {field}"
            assert payload[field] is None

    def test_download_and_georeference_success(self, mock_image_open, mock_requests_get, tmp_path):
        mock_requests_get._mock_response.status_code = 200
        mock_requests_get._mock_response.content = b"fake-image"
        mock_img = MagicMock()
        mock_img.size = (100, 200)
        mock_image_open.return_value = mock_img

        footprint = {"type": "Polygon",
                     "coordinates": [[[0, 0], [10, 0], [10, 10], [0, 10], [0, 0]]]}
        out = tmp_path / "scene.jpg"
        assert SASCloudsAPIClient().download_and_georeference(
            "http://x.com/img.jpg", footprint, out
        ) is True
        assert out.exists()
        assert out.with_suffix(".jgw").exists()
        assert out.with_suffix(".prj").exists()

    def test_download_and_georeference_jgw_has_six_lines(self, mock_image_open,
                                                           mock_requests_get, tmp_path):
        mock_requests_get._mock_response.content = b"img"
        mock_image_open.return_value.size = (100, 100)

        footprint = {"type": "Polygon",
                     "coordinates": [[[10, 20], [20, 20], [20, 30], [10, 30], [10, 20]]]}
        out = tmp_path / "scene.jpg"
        SASCloudsAPIClient().download_and_georeference("http://x.com/img.jpg", footprint, out)
        lines = out.with_suffix(".jgw").read_text().splitlines()
        assert len(lines) == 6
        for line in lines:
            float(line)  # each line must be a valid float

    def test_download_and_georeference_prj_contains_wgs84(self, mock_image_open,
                                                            mock_requests_get, tmp_path):
        mock_requests_get._mock_response.content = b"img"
        mock_image_open.return_value.size = (50, 50)

        footprint = {"type": "Polygon",
                     "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]]}
        out = tmp_path / "s.jpg"
        SASCloudsAPIClient().download_and_georeference("http://x.com/s.jpg", footprint, out)
        prj_text = out.with_suffix(".prj").read_text()
        assert "WGS 84" in prj_text
        assert "EPSG" in prj_text

    def test_download_and_georeference_fails_on_http_error(self, mock_requests_get, tmp_path):
        mock_requests_get._mock_response.status_code = 404
        footprint = {"type": "Polygon",
                     "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]]}
        result = SASCloudsAPIClient().download_and_georeference(
            "http://x.com/missing.jpg", footprint, tmp_path / "out.jpg"
        )
        assert result is False

    def test_validate_scene_valid(self):
        scene = {
            "satelliteId": "GF5", "sensorId": "AHSI",
            "acquisitionTime": 1000, "cloudPercent": 5,
            "quickViewUri": "http://x.com/q.jpg",
            "boundary": '{"type":"Polygon","coordinates":[]}',
        }
        assert SASCloudsAPIClient().validate_scene(scene) is True

    def test_validate_scene_missing_fields(self):
        assert SASCloudsAPIClient().validate_scene({"satelliteId": "GF5"}) is False


# =============================================================================
# sasclouds_api_scraper – logging helpers
# =============================================================================

def test_log_search_writes_correct_fields(tmp_path):
    import sasclouds_api_scraper as mod
    orig = mod.LOG_DIR
    mod.LOG_DIR = tmp_path
    log_search("sess1", {"type": "Polygon"}, {"cloud": 20}, 5)
    record = json.loads((tmp_path / "search_history.jsonl").read_text().strip())
    assert record["session_id"] == "sess1"
    assert record["num_scenes"] == 5
    assert record["type"] == "search"
    mod.LOG_DIR = orig


def test_log_search_appends_multiple_records(tmp_path):
    import sasclouds_api_scraper as mod
    orig = mod.LOG_DIR
    mod.LOG_DIR = tmp_path
    log_search("s1", {}, {}, 3)
    log_search("s2", {}, {}, 7)
    lines = (tmp_path / "search_history.jsonl").read_text().strip().splitlines()
    assert len(lines) == 2
    mod.LOG_DIR = orig


def test_log_aoi_upload_writes_correct_fields(tmp_path):
    import sasclouds_api_scraper as mod
    orig = mod.LOG_DIR
    mod.LOG_DIR = tmp_path
    log_aoi_upload("sess2", "my.geojson", {"type": "Polygon"})
    record = json.loads((tmp_path / "aoi_history.jsonl").read_text().strip())
    assert record["session_id"] == "sess2"
    assert record["filename"] == "my.geojson"
    assert record["type"] == "aoi_upload"
    mod.LOG_DIR = orig


# =============================================================================
# sasclouds_api_scraper – convert_uploaded_file_to_geojson
# =============================================================================

class _MockFile:
    """Minimal file-upload substitute."""
    def __init__(self, name: str, content: bytes):
        self.name = name
        self._content = content

    def read(self) -> bytes:
        return self._content


class TestConvertUploadedFile:

    def test_geojson(self):
        content = json.dumps({
            "type": "Polygon",
            "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]],
        }).encode()
        result = convert_uploaded_file_to_geojson(_MockFile("aoi.geojson", content))
        assert result["type"] == "Polygon"
        assert len(result["coordinates"][0]) == 5

    def test_kml_3d_coordinates(self):
        """KML with lon,lat,alt triples must parse without raising (bug fix: lon,lat = ...)."""
        kml = (
            b'<?xml version="1.0"?>'
            b'<kml xmlns="http://www.opengis.net/kml/2.2">'
            b"<Placemark><Polygon><outerBoundaryIs><LinearRing>"
            b"<coordinates>0,0,0 1,0,0 1,1,0 0,1,0 0,0,0</coordinates>"
            b"</LinearRing></outerBoundaryIs></Polygon></Placemark></kml>"
        )
        result = convert_uploaded_file_to_geojson(_MockFile("aoi.kml", kml))
        assert result["type"] == "Polygon"
        assert len(result["coordinates"][0]) == 5

    def test_kml_2d_coordinates(self):
        kml = (
            b'<?xml version="1.0"?>'
            b'<kml xmlns="http://www.opengis.net/kml/2.2">'
            b"<Placemark><Polygon><outerBoundaryIs><LinearRing>"
            b"<coordinates>0,0 1,0 1,1 0,1 0,0</coordinates>"
            b"</LinearRing></outerBoundaryIs></Polygon></Placemark></kml>"
        )
        result = convert_uploaded_file_to_geojson(_MockFile("aoi.kml", kml))
        assert result["type"] == "Polygon"

    def test_kml_no_polygon_raises(self):
        kml = b'<?xml version="1.0"?><kml xmlns="http://www.opengis.net/kml/2.2"><Document/></kml>'
        with pytest.raises(ValueError, match="No polygon found in KML"):
            convert_uploaded_file_to_geojson(_MockFile("aoi.kml", kml))

    def test_zip_shapefile(self, tmp_path):
        shp_dir = tmp_path / "shp"
        shp_dir.mkdir()
        _write_test_shapefile(shp_dir)
        buf = BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            for ext in (".shp", ".shx", ".dbf"):
                p = shp_dir / f"test{ext}"
                if p.exists():
                    zf.write(p, arcname=f"test{ext}")
        result = convert_uploaded_file_to_geojson(_MockFile("aoi.zip", buf.getvalue()))
        assert result["type"] == "Polygon"

    def test_zip_without_shp_raises(self):
        buf = BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("readme.txt", "no shapefile here")
        with pytest.raises(ValueError, match="No .shp file found"):
            convert_uploaded_file_to_geojson(_MockFile("aoi.zip", buf.getvalue()))

    def test_unsupported_extension_raises(self):
        with pytest.raises(ValueError, match="Unsupported file type"):
            convert_uploaded_file_to_geojson(_MockFile("aoi.csv", b"lat,lon\n1,2"))


# =============================================================================
# search_logic
# =============================================================================

class TestSearchLogic:
    """Patch Streamlit UI components for every test in the class."""

    @pytest.fixture(autouse=True)
    def mock_streamlit_ui(self):
        status_ctx = MagicMock()
        status_ctx.__enter__ = MagicMock(return_value=status_ctx)
        status_ctx.__exit__ = MagicMock(return_value=False)
        with patch("streamlit.status", return_value=status_ctx), \
             patch("streamlit.subheader"), \
             patch("streamlit.markdown"), \
             patch("streamlit.warning"), \
             patch("streamlit.error"), \
             patch("streamlit.button", return_value=False), \
             patch("streamlit.download_button"):
            yield

    # ── run_search ────────────────────────────────────────────────────────────

    @patch("search_logic.SASCloudsAPIClient")
    def test_run_search_sets_features_for_map(self, MockClient, sample_polygon_geojson):
        """features_for_map must be in session_state after a successful search."""
        MockClient.return_value.upload_aoi.return_value = "uid"
        MockClient.return_value.search_scenes.return_value = {
            "code": 0, "data": [_make_scene()], "pageInfo": {"total": 1},
        }
        st.session_state.clear()
        run_search(**_search_kwargs(sample_polygon_geojson))
        assert len(st.session_state.get("features_for_map", [])) == 1

    @patch("search_logic.SASCloudsAPIClient")
    def test_run_search_sets_scenes_for_download(self, MockClient, sample_polygon_geojson):
        MockClient.return_value.upload_aoi.return_value = "uid"
        MockClient.return_value.search_scenes.return_value = {
            "code": 0, "data": [_make_scene()], "pageInfo": {"total": 1},
        }
        st.session_state.clear()
        run_search(**_search_kwargs(sample_polygon_geojson))
        assert st.session_state.get("scenes_for_download") is not None
        assert st.session_state.get("features_for_download") is not None
        assert st.session_state.get("temp_dir_ready") is True

    @patch("search_logic.SASCloudsAPIClient")
    def test_run_search_no_scenes_leaves_session_clean(self, MockClient, sample_polygon_geojson):
        MockClient.return_value.upload_aoi.return_value = "uid"
        MockClient.return_value.search_scenes.return_value = {
            "code": 0, "data": [], "pageInfo": {"total": 0},
        }
        st.session_state.clear()
        run_search(**_search_kwargs(sample_polygon_geojson))
        assert "features_for_map" not in st.session_state
        assert st.session_state.get("temp_dir_ready") is not True

    @patch("search_logic.SASCloudsAPIClient")
    def test_run_search_paginates_until_total_reached(self, MockClient, sample_polygon_geojson):
        """All pages must be fetched until cumulative count equals total."""
        MockClient.return_value.upload_aoi.return_value = "uid"
        MockClient.return_value.search_scenes.side_effect = [
            {"code": 0, "data": [_make_scene("p1s1"), _make_scene("p1s2")],
             "pageInfo": {"total": 4}},
            {"code": 0, "data": [_make_scene("p2s1"), _make_scene("p2s2")],
             "pageInfo": {"total": 4}},
        ]
        st.session_state.clear()
        run_search(**_search_kwargs(sample_polygon_geojson))
        assert MockClient.return_value.search_scenes.call_count == 2
        assert len(st.session_state.get("scenes_for_download", [])) == 4
        assert len(st.session_state.get("features_for_map", [])) == 4

    @patch("search_logic.SASCloudsAPIClient")
    def test_run_search_stops_on_empty_page(self, MockClient, sample_polygon_geojson):
        """An empty page response must stop pagination even if total not reached."""
        MockClient.return_value.upload_aoi.return_value = "uid"
        MockClient.return_value.search_scenes.side_effect = [
            {"code": 0, "data": [_make_scene()], "pageInfo": {"total": 99}},
            {"code": 0, "data": [],               "pageInfo": {"total": 99}},
        ]
        st.session_state.clear()
        run_search(**_search_kwargs(sample_polygon_geojson))
        # Stops after the empty page; only 1 scene collected
        assert len(st.session_state.get("scenes_for_download", [])) == 1

    @patch("search_logic.SASCloudsAPIClient")
    def test_run_search_skips_scene_with_invalid_boundary(self, MockClient,
                                                            sample_polygon_geojson):
        bad = _make_scene("bad")
        bad["boundary"] = "NOT_VALID_JSON"
        good = _make_scene("good")
        MockClient.return_value.upload_aoi.return_value = "uid"
        MockClient.return_value.search_scenes.return_value = {
            "code": 0, "data": [bad, good], "pageInfo": {"total": 2},
        }
        st.session_state.clear()
        run_search(**_search_kwargs(sample_polygon_geojson))
        # Only the good scene appears in map features
        assert len(st.session_state.get("features_for_map", [])) == 1

    @patch("search_logic.SASCloudsAPIClient")
    def test_run_search_rewrites_quickview_domain(self, MockClient, sample_polygon_geojson):
        """Old sasclouds.com quickview domain must be rewritten to Huawei Cloud CDN."""
        scene = _make_scene()
        scene["quickViewUri"] = "http://quickview.sasclouds.com/path/thumb.jpg"
        MockClient.return_value.upload_aoi.return_value = "uid"
        MockClient.return_value.search_scenes.return_value = {
            "code": 0, "data": [scene], "pageInfo": {"total": 1},
        }
        st.session_state.clear()
        run_search(**_search_kwargs(sample_polygon_geojson))
        qv = st.session_state["features_for_map"][0]["properties"]["quickview"]
        assert "quickview.obs.cn-north-10.myhuaweicloud.com" in qv
        assert "quickview.sasclouds.com" not in qv

    @patch("search_logic.SASCloudsAPIClient")
    def test_run_search_features_for_map_equals_features_for_download(
            self, MockClient, sample_polygon_geojson):
        """Both keys must point to the same list (used by map and download)."""
        MockClient.return_value.upload_aoi.return_value = "uid"
        MockClient.return_value.search_scenes.return_value = {
            "code": 0, "data": [_make_scene(), _make_scene("s2")],
            "pageInfo": {"total": 2},
        }
        st.session_state.clear()
        run_search(**_search_kwargs(sample_polygon_geojson))
        assert st.session_state["features_for_map"] == st.session_state["features_for_download"]

    @patch("search_logic.SASCloudsAPIClient")
    def test_run_search_emits_info_logs(self, MockClient, sample_polygon_geojson, caplog):
        """Key stages must be logged at INFO level to appear in the terminal."""
        MockClient.return_value.upload_aoi.return_value = "uid_xyz"
        MockClient.return_value.search_scenes.return_value = {
            "code": 0, "data": [_make_scene()], "pageInfo": {"total": 1},
        }
        st.session_state.clear()
        with caplog.at_level(logging.INFO, logger="search_logic"):
            run_search(**_search_kwargs(sample_polygon_geojson))
        text = caplog.text
        assert "Uploaded in" in text        # upload confirmation (search_logic add_log)
        assert "Page 1" in text             # pagination progress
        assert "Search complete" in text    # final summary

    # ── create_download_zip ───────────────────────────────────────────────────

    @patch("search_logic.SASCloudsAPIClient")
    def test_create_download_zip_preserves_features_for_map(self, MockClient, tmp_path):
        """features_for_map must NOT be cleared so footprints stay on the map."""
        features = [
            {
                "geometry": {"type": "Polygon",
                             "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]]},
                "properties": {"quickview": "https://example.com/img.jpg"},
            }
        ]
        td = tmp_path / "td"
        td.mkdir()
        st.session_state.clear()
        st.session_state["temp_dir_ready"]        = True
        st.session_state["scenes_for_download"]   = [_make_scene()]
        st.session_state["features_for_download"] = features
        st.session_state["features_for_map"]      = features

        MockClient.return_value.download_and_georeference.return_value = True

        status_ctx = MagicMock()
        status_ctx.__enter__ = MagicMock(return_value=status_ctx)
        status_ctx.__exit__ = MagicMock(return_value=False)
        with patch("streamlit.button", return_value=True), \
             patch("streamlit.download_button"), \
             patch("streamlit.status", return_value=status_ctx), \
             patch("tempfile.mkdtemp", return_value=str(td)):
            create_download_zip()

        # Download state cleared …
        assert st.session_state.get("temp_dir_ready") is False
        assert st.session_state.get("scenes_for_download") is None
        assert st.session_state.get("features_for_download") is None
        # … but map footprints preserved
        assert st.session_state.get("features_for_map") == features

    @patch("search_logic.SASCloudsAPIClient")
    def test_create_download_zip_skips_when_button_not_clicked(self, MockClient):
        st.session_state.clear()
        st.session_state["temp_dir_ready"]        = True
        st.session_state["scenes_for_download"]   = [_make_scene()]
        st.session_state["features_for_download"] = []
        with patch("streamlit.button", return_value=False):
            create_download_zip()
        MockClient.return_value.download_and_georeference.assert_not_called()

    @patch("search_logic.SASCloudsAPIClient")
    def test_create_download_zip_skips_when_no_scenes(self, MockClient):
        st.session_state.clear()
        with patch("streamlit.button", return_value=True):
            create_download_zip()  # should return silently, no crash
        MockClient.assert_not_called()


# =============================================================================
if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
