# File: tests/test_sasclouds_scraper.py
"""
Unit tests for SASClouds API scraper using mocks.
Run with: python tests/test_sasclouds_scraper.py -v -s
"""

import json
import logging
import sys
import tempfile
from pathlib import Path
from datetime import datetime
from unittest.mock import patch, MagicMock, mock_open

import pytest
import requests
from PIL import Image

# Add parent directory to path to import the scraper module
sys.path.insert(0, str(Path(__file__).parent.parent))
from sasclouds_api_scraper import (
    SASCloudsAPIClient,
    log_search,
    log_aoi_upload,
    detect_api_version,
)

# ----------------------------------------------------------------------
# Configure logging for tests (verbose output)
# ----------------------------------------------------------------------
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(name)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
test_logger = logging.getLogger(__name__)


# ----------------------------------------------------------------------
# Fixtures
# ----------------------------------------------------------------------
@pytest.fixture
def mock_requests_post():
    """Mock requests.post to simulate API responses."""
    with patch("requests.post") as mock_post:
        yield mock_post


@pytest.fixture
def mock_shapefile_writer():
    """Mock shapefile.Writer to avoid creating real files."""
    with patch("shapefile.Writer") as mock_writer:
        mock_writer_instance = MagicMock()
        mock_writer.return_value = mock_writer_instance
        yield mock_writer


@pytest.fixture
def mock_tempfile():
    """Mock tempfile.TemporaryDirectory to return a predictable path."""
    with patch("tempfile.TemporaryDirectory") as mock_td:
        # Use a real temporary directory for the test so files can be created
        # Instead of returning a fake path, let it create a real temp dir
        def side_effect():
            real_tmp = tempfile.mkdtemp()
            return real_tmp
        mock_td.return_value.__enter__.side_effect = side_effect
        mock_td.return_value.__exit__.return_value = None
        yield mock_td


@pytest.fixture
def mock_image_open():
    """Mock PIL.Image.open to avoid reading real images."""
    with patch("PIL.Image.open") as mock_img_open:
        mock_img = MagicMock()
        mock_img.size = (100, 200)
        mock_img_open.return_value = mock_img
        yield mock_img_open


# ----------------------------------------------------------------------
# Tests for detect_api_version
# ----------------------------------------------------------------------
@patch("requests.get")
def test_detect_api_version_success(mock_get):
    """Test successful API version detection."""
    test_logger.info("=== Test: detect_api_version success ===")
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = '<script src="/api/normal/v5/normalmeta"></script>'
    mock_resp.raise_for_status = MagicMock()
    mock_get.return_value = mock_resp

    version = detect_api_version()
    assert version == "v5"
    test_logger.info(f"Detected version: {version}")


@patch("requests.get")
def test_detect_api_version_fallback(mock_get):
    """Test fallback when version not found in HTML."""
    test_logger.info("=== Test: detect_api_version fallback ===")
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = "<html>No API pattern here</html>"
    mock_resp.raise_for_status = MagicMock()
    mock_get.return_value = mock_resp

    version = detect_api_version()
    assert version == "v5"
    test_logger.info(f"Fallback version: {version}")


@patch("requests.get", side_effect=requests.RequestException("Network error"))
def test_detect_api_version_exception(mock_get):
    """Test exception handling in detection."""
    test_logger.info("=== Test: detect_api_version exception ===")
    version = detect_api_version()
    assert version == "v5"
    test_logger.info("Exception caught, returning fallback v5")


# ----------------------------------------------------------------------
# Tests for logging functions
# ----------------------------------------------------------------------
def test_log_search(tmp_path):
    """Test log_search writes correctly to search_history.jsonl."""
    test_logger.info("=== Test: log_search ===")
    # Override LOG_DIR to a temporary directory
    import sasclouds_api_scraper as module
    original_log_dir = module.LOG_DIR
    module.LOG_DIR = tmp_path
    log_search("test_session", {"type": "Polygon"}, {"cloud": 20}, 5)
    log_file = tmp_path / "search_history.jsonl"
    assert log_file.exists()
    content = log_file.read_text()
    assert "test_session" in content
    assert "Polygon" in content
    assert "cloud" in content
    test_logger.info(f"Log written: {content[:200]}...")
    module.LOG_DIR = original_log_dir


def test_log_aoi_upload(tmp_path):
    """Test log_aoi_upload writes correctly to aoi_history.jsonl."""
    test_logger.info("=== Test: log_aoi_upload ===")
    import sasclouds_api_scraper as module
    original_log_dir = module.LOG_DIR
    module.LOG_DIR = tmp_path
    log_aoi_upload("test_session", "polygon.geojson", {"type": "Polygon"})
    log_file = tmp_path / "aoi_history.jsonl"
    assert log_file.exists()
    content = log_file.read_text()
    assert "test_session" in content
    assert "polygon.geojson" in content
    test_logger.info(f"Log written: {content[:200]}...")
    module.LOG_DIR = original_log_dir


# ----------------------------------------------------------------------
# Tests for SASCloudsAPIClient
# ----------------------------------------------------------------------
class TestSASCloudsAPIClient:
    """Test the API client class with mocks."""

    def test_init(self):
        """Test client initialization."""
        test_logger.info("=== Test: SASCloudsAPIClient init ===")
        with patch("sasclouds_api_scraper.detect_api_version", return_value="v99"):
            client = SASCloudsAPIClient()
            assert client.api_base == "https://www.sasclouds.com/api/normal/v99"
            test_logger.info(f"API base set to: {client.api_base}")

    def test_upload_aoi_success(self, mock_requests_post, mock_shapefile_writer, mock_tempfile):
        """Test AOI upload success."""
        test_logger.info("=== Test: upload_aoi success ===")
        # Mock the response from the upload endpoint
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"code": 0, "data": {"uploadId": "test_upload_123"}}
        mock_requests_post.return_value = mock_resp

        # Mock file opening so that no real file is accessed
        with patch("builtins.open", mock_open(read_data=b"fake data")):
            client = SASCloudsAPIClient()
            polygon = {"type": "Polygon", "coordinates": [[[0,0],[1,0],[1,1],[0,1],[0,0]]]}
            upload_id = client.upload_aoi(polygon)
            assert upload_id == "test_upload_123"
            test_logger.info(f"Upload ID returned: {upload_id}")

    def test_upload_aoi_api_error(self, mock_requests_post, mock_shapefile_writer, mock_tempfile):
        """Test AOI upload where API returns error code."""
        test_logger.info("=== Test: upload_aoi API error ===")
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"code": 1, "message": "Invalid polygon"}
        mock_requests_post.return_value = mock_resp

        with patch("builtins.open", mock_open(read_data=b"fake data")):
            client = SASCloudsAPIClient()
            polygon = {"type": "Polygon", "coordinates": [[[0,0],[1,0],[1,1],[0,1],[0,0]]]}
            with pytest.raises(Exception, match="Upload failed with code 1"):
                client.upload_aoi(polygon)
            test_logger.info("API error raised as expected")

    @patch("sasclouds_api_scraper.requests.post")
    def test_upload_aoi_http_error(self, mock_post, mock_shapefile_writer, mock_tempfile):
        """Test AOI upload HTTP error."""
        test_logger.info("=== Test: upload_aoi HTTP error ===")
        mock_post.side_effect = requests.RequestException("Connection refused")

        with patch("builtins.open", mock_open(read_data=b"fake data")):
            client = SASCloudsAPIClient()
            polygon = {"type": "Polygon", "coordinates": [[[0,0],[1,0],[1,1],[0,1],[0,0]]]}
            with pytest.raises(requests.RequestException):
                client.upload_aoi(polygon)
            test_logger.info("HTTP error caught")

    def test_search_scenes_success(self, mock_requests_post):
        """Test search_scenes returns data."""
        test_logger.info("=== Test: search_scenes success ===")
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "code": 0,
            "data": [{"satelliteId": "GF5", "sensorId": "AHSI"}],
            "pageInfo": {"total": 1}
        }
        mock_requests_post.return_value = mock_resp

        client = SASCloudsAPIClient()
        result = client.search_scenes("upload_id", 1000, 2000, 20, [], 1, 10)
        assert result["data"][0]["satelliteId"] == "GF5"
        test_logger.info("Search returned expected data")

    def test_search_scenes_api_error(self, mock_requests_post):
        """Test search_scenes API error."""
        test_logger.info("=== Test: search_scenes API error ===")
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"code": 2, "message": "Invalid parameters"}
        mock_requests_post.return_value = mock_resp

        client = SASCloudsAPIClient()
        with pytest.raises(Exception, match="Search API error: Invalid parameters"):
            client.search_scenes("upload_id", 1000, 2000, 20, [], 1, 10)
        test_logger.info("API error handled")

    def test_validate_scene_valid(self):
        """Test validate_scene with valid scene."""
        test_logger.info("=== Test: validate_scene valid ===")
        client = SASCloudsAPIClient()
        scene = {
            "satelliteId": "GF5",
            "sensorId": "AHSI",
            "acquisitionTime": 123456,
            "cloudPercent": 10,
            "quickViewUri": "http://test.com",
            "boundary": "{}"
        }
        assert client.validate_scene(scene) is True
        test_logger.info("Valid scene passed")

    def test_validate_scene_invalid(self):
        """Test validate_scene with missing field."""
        test_logger.info("=== Test: validate_scene invalid (missing field) ===")
        client = SASCloudsAPIClient()
        scene = {"satelliteId": "GF5"}  # missing many fields
        assert client.validate_scene(scene) is False
        test_logger.info("Invalid scene rejected")

    def test_download_and_georeference_success(self, mock_image_open, tmp_path):
        """Test download_and_georeference with mock image and requests."""
        test_logger.info("=== Test: download_and_georeference success ===")
        with patch("requests.get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.content = b"fake image data"
            mock_get.return_value = mock_resp

            client = SASCloudsAPIClient()
            footprint = {
                "type": "Polygon",
                "coordinates": [[[0,0], [10,0], [10,10], [0,10], [0,0]]]
            }
            output_path = tmp_path / "test.jpg"
            result = client.download_and_georeference("http://example.com/image.jpg", footprint, output_path)
            assert result is True
            assert output_path.exists()
            assert output_path.with_suffix(".jgw").exists()
            assert output_path.with_suffix(".prj").exists()
            test_logger.info("Download and georeferencing succeeded")

    def test_download_and_georeference_http_error(self, tmp_path):
        """Test download failure (HTTP error)."""
        test_logger.info("=== Test: download_and_georeference HTTP error ===")
        with patch("requests.get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.status_code = 404
            mock_get.return_value = mock_resp

            client = SASCloudsAPIClient()
            footprint = {"type": "Polygon", "coordinates": [[[0,0],[1,0],[1,1],[0,1],[0,0]]]}
            output_path = tmp_path / "test2.jpg"
            result = client.download_and_georeference("http://example.com/missing.jpg", footprint, output_path)
            assert result is False
            test_logger.info("HTTP error handled, returned False")


# ----------------------------------------------------------------------
# Run tests
# ----------------------------------------------------------------------
if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])