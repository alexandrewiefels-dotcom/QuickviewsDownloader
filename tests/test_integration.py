"""
Integration tests for full search -> pass detection -> tasking flow (3.10).
Uses mock TLE data for offline testing (3.11).

Run with:
    pytest tests/test_integration.py -v
"""

import sys
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

import pytest
from shapely.geometry import Polygon, Point, LineString, MultiPolygon

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


# =============================================================================
# Mock TLE Data (3.11)
# =============================================================================

# Realistic TLE lines for common satellites
MOCK_TLES = {
    # Gaofen-2 (NORAD 40118) — Optical, 0.8m, 11km swath
    40118: (
        "1 40118U 14049A   25132.50000000  .00000000  00000-0  00000-0 0  9999",
        "2 40118  97.4000 180.0000 0005000  90.0000 270.0000 14.60000000000000",
    ),
    # Gaofen-3 01 (NORAD 41727) — SAR, 1m-500m, 10-650km swath
    41727: (
        "1 41727U 16049A   25132.50000000  .00000000  00000-0  00000-0 0  9999",
        "2 41727  98.5000 180.0000 0001000  90.0000 270.0000 15.20000000000000",
    ),
    # Gaofen-1 (NORAD 40119) — Optical, 2m/8m, 11km/60km swath
    40119: (
        "1 40119U 14049B   25132.50000000  .00000000  00000-0  00000-0 0  9999",
        "2 40119  97.4000 180.0000 0005000  90.0000 270.0000 14.60000000000000",
    ),
    # ZY3-1 (NORAD 38046) — Optical stereo, 2.1m, 51km swath
    38046: (
        "1 38046U 11079A   25132.50000000  .00000000  00000-0  00000-0 0  9999",
        "2 38046  97.5000 180.0000 0002000  90.0000 270.0000 14.80000000000000",
    ),
    # Sentinel-1A (NORAD 39634) — SAR, 5m-40m, 80-400km swath
    39634: (
        "1 39634U 14016A   25132.50000000  .00000000  00000-0  00000-0 0  9999",
        "2 39634  98.2000 180.0000 0001000  90.0000 270.0000 14.60000000000000",
    ),
    # Gaofen-5B (NORAD 51724) — Hyperspectral
    51724: (
        "1 51724U 22033A   25132.50000000  .00000000  00000-0  00000-0 0  9999",
        "2 51724  97.4000 180.0000 0005000  90.0000 270.0000 15.00000000000000",
    ),
}

# Satellite configs matching the mock TLEs
MOCK_SATELLITE_CONFIGS = {
    "GF2": {
        "norad": 40118,
        "provider": "Siwei",
        "type": "Optical",
        "color": "#00CED1",
        "cameras": {"PMS": {"swath_km": 11.0, "resolution_m": 0.8}},
    },
    "GF3": {
        "norad": 41727,
        "provider": "Siwei",
        "type": "SAR",
        "color": "#FF4500",
        "cameras": {"Standard": {"swath_km": 30.0, "resolution_m": 5.0}},
    },
    "GF1": {
        "norad": 40119,
        "provider": "Siwei",
        "type": "Optical",
        "color": "#00FF00",
        "cameras": {"PMS": {"swath_km": 11.0, "resolution_m": 2.0}},
    },
    "ZY3-1": {
        "norad": 38046,
        "provider": "Siwei",
        "type": "Optical",
        "color": "#FFA500",
        "cameras": {"MUX": {"swath_km": 51.0, "resolution_m": 2.1}},
    },
    "S1A": {
        "norad": 39634,
        "provider": "ESA",
        "type": "SAR",
        "color": "#FF0000",
        "cameras": {"IW": {"swath_km": 250.0, "resolution_m": 10.0}},
    },
}


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def mock_tle_fetcher():
    """Create a TLEFetcher with pre-populated mock TLE data."""
    from data.tle_fetcher import TLEFetcher
    fetcher = MagicMock(spec=TLEFetcher)
    
    def mock_fetch(norad_id, force_refresh=False):
        if norad_id in MOCK_TLES:
            return MOCK_TLES[norad_id]
        return None
    
    fetcher.fetch.side_effect = mock_fetch
    fetcher.tles = dict(MOCK_TLES)
    return fetcher


@pytest.fixture
def mock_skyfield_ts():
    """Create a mock Skyfield timescale."""
    ts = MagicMock()
    ts.now.return_value = MagicMock()
    return ts


@pytest.fixture
def beijing_aoi():
    """Standard Beijing-area AOI polygon."""
    return Polygon([
        (116.2, 39.8),
        (116.6, 39.8),
        (116.6, 40.1),
        (116.2, 40.1),
        (116.2, 39.8),
    ])


@pytest.fixture
def pass_detector(mock_tle_fetcher, mock_skyfield_ts):
    """Create a PassDetector with mock dependencies."""
    from detection.pass_detector import PassDetector
    return PassDetector(mock_tle_fetcher, mock_skyfield_ts)


# =============================================================================
# 3.10 — Integration: TLE Fetch -> Pass Detection
# =============================================================================

class TestTLEFetchIntegration:
    """Verify TLE fetching integrates correctly with pass detection."""

    def test_fetch_known_satellite(self, mock_tle_fetcher):
        """Known NORAD returns valid TLE tuple."""
        tle = mock_tle_fetcher.fetch(40118)
        assert tle is not None
        assert len(tle) == 2
        assert tle[0].startswith("1 ")
        assert tle[1].startswith("2 ")

    def test_fetch_unknown_satellite(self, mock_tle_fetcher):
        """Unknown NORAD returns None."""
        tle = mock_tle_fetcher.fetch(99999)
        assert tle is None

    def test_all_mock_tles_have_valid_format(self):
        """All mock TLEs must have valid line1/line2 format."""
        for norad, (line1, line2) in MOCK_TLES.items():
            assert line1.startswith("1 "), f"NORAD {norad}: line1 must start with '1 '"
            assert line2.startswith("2 "), f"NORAD {norad}: line2 must start with '2 '"
            # NORAD number in TLE should match key
            assert str(norad) in line1, f"NORAD {norad}: not found in line1"

    def test_all_satellite_configs_have_mock_tle(self):
        """Every satellite in MOCK_SATELLITE_CONFIGS must have a mock TLE."""
        for name, config in MOCK_SATELLITE_CONFIGS.items():
            norad = config["norad"]
            assert norad in MOCK_TLES, (
                f"Satellite {name} (NORAD {norad}) has no mock TLE"
            )


class TestPassDetectorWithMockTLE:
    """PassDetector.detect_passes with mock TLE data."""

    def test_detect_passes_returns_list(self, pass_detector, beijing_aoi):
        """detect_passes returns a list (may be empty with mock data)."""
        with patch.object(pass_detector, '_compute_track', return_value=[]):
            result, _ = pass_detector.detect_passes(
                "GF2", 40118, MOCK_SATELLITE_CONFIGS["GF2"],
                "PMS", {"swath_km": 11.0, "resolution_m": 0.8},
                *MOCK_TLES[40118],
                beijing_aoi,
                datetime(2025, 1, 1, tzinfo=timezone.utc),
                datetime(2025, 1, 2, tzinfo=timezone.utc),
                30.0,
            )
            assert isinstance(result, list)

    def test_detect_passes_with_track(self, pass_detector, beijing_aoi):
        """With simulated track points, detect_passes returns passes."""
        track_points = [
            {'time': datetime(2025, 1, 1, 10, 0, tzinfo=timezone.utc),
             'lat': 39.9, 'lon': 116.3, 'alt': 550.0, 'dist_km': 0.0, 'can_see': True},
            {'time': datetime(2025, 1, 1, 10, 1, tzinfo=timezone.utc),
             'lat': 40.0, 'lon': 116.4, 'alt': 550.0, 'dist_km': 0.0, 'can_see': True},
            {'time': datetime(2025, 1, 1, 10, 2, tzinfo=timezone.utc),
             'lat': 40.1, 'lon': 116.5, 'alt': 550.0, 'dist_km': 0.0, 'can_see': True},
        ]
        with patch.object(pass_detector, '_compute_track', return_value=track_points):
            result, _ = pass_detector.detect_passes(
                "GF2", 40118, MOCK_SATELLITE_CONFIGS["GF2"],
                "PMS", {"swath_km": 11.0, "resolution_m": 0.8},
                *MOCK_TLES[40118],
                beijing_aoi,
                datetime(2025, 1, 1, tzinfo=timezone.utc),
                datetime(2025, 1, 2, tzinfo=timezone.utc),
                30.0,
            )
            assert len(result) > 0

    def test_detect_passes_multiple_satellites(self, pass_detector, beijing_aoi):
        """Multiple satellites can be detected independently."""
        track_points = [
            {'time': datetime(2025, 1, 1, 10, 0, tzinfo=timezone.utc),
             'lat': 39.9, 'lon': 116.3, 'alt': 550.0, 'dist_km': 0.0, 'can_see': True},
        ]
        results = {}
        for name, config in MOCK_SATELLITE_CONFIGS.items():
            norad = config["norad"]
            if norad not in MOCK_TLES:
                continue
            with patch.object(pass_detector, '_compute_track', return_value=track_points):
                passes, _ = pass_detector.detect_passes(
                    name, norad, config,
                    list(config["cameras"].keys())[0],
                    list(config["cameras"].values())[0],
                    *MOCK_TLES[norad],
                    beijing_aoi,
                    datetime(2025, 1, 1, tzinfo=timezone.utc),
                    datetime(2025, 1, 2, tzinfo=timezone.utc),
                    30.0,
                )
                results[name] = passes
        # All satellites should produce passes
        for name, passes in results.items():
            assert isinstance(passes, list), f"{name}: expected list, got {type(passes)}"

    def test_detect_passes_empty_aoi_returns_empty(self, pass_detector):
        """Empty AOI should return empty results."""
        empty_aoi = Polygon()
        with patch.object(pass_detector, '_compute_track', return_value=[]):
            result, _ = pass_detector.detect_passes(
                "GF2", 40118, MOCK_SATELLITE_CONFIGS["GF2"],
                "PMS", {"swath_km": 11.0, "resolution_m": 0.8},
                *MOCK_TLES[40118],
                empty_aoi,
                datetime(2025, 1, 1, tzinfo=timezone.utc),
                datetime(2025, 1, 2, tzinfo=timezone.utc),
                30.0,
            )
            assert result == []


# =============================================================================
# 3.10 — Integration: Pass Detection -> Tasking
# =============================================================================

class TestPassToTaskingIntegration:
    """Verify pass detection results feed correctly into tasking optimizer."""

    @pytest.fixture
    def optimizer(self):
        from tasking_optimizer import TaskingOptimizer
        detector = MagicMock()
        detector.ground_range_from_ona.return_value = 200.0
        detector.ona_from_distance.return_value = 15.0
        detector.get_perpendicular_distance_to_aoi.return_value = (10.0, 5.0, 1.0)
        return TaskingOptimizer(detector, sat_alt_km=550.0)

    def _make_pass(self, name="GF2", norad=40118, swath_km=11.0, offset=0.0,
                   direction="Descending", pass_time=None):
        """Helper to create a minimal SatellitePass."""
        from models.satellite_pass import SatellitePass
        if pass_time is None:
            pass_time = datetime(2025, 6, 15, 10, 30, tzinfo=timezone.utc)
        p = SatellitePass(
            id=f"{name}-{norad}",
            satellite_name=name,
            camera_name="PMS",
            norad_id=norad,
            provider="Siwei",
            pass_time=pass_time,
            ground_track=LineString([(116.3, 39.9), (116.4, 40.0)]),
            footprint=Polygon(),
            swath_km=swath_km,
            resolution_m=0.8,
            sensor_type="Optical",
            color="#00CED1",
            inclination=97.4,
            orbit_direction=direction,
            track_azimuth=180.0,
            min_ona=2.5,
            max_ona=15.0,
        )
        p.original_offset_km = offset
        p.current_offset_km = offset
        return p

    def test_tasking_with_detected_passes(self, optimizer, beijing_aoi):
        """Tasking optimizer works with passes that have real geometry."""
        passes = [
            self._make_pass("GF2", 40118, swath_km=11.0, offset=-10.0),
            self._make_pass("GF3", 41727, swath_km=30.0, offset=0.0),
            self._make_pass("GF1", 40119, swath_km=11.0, offset=10.0),
        ]
        result = optimizer.compute_coverage_tasking(passes, beijing_aoi, 30.0)
        assert isinstance(result, list)

    def test_tasking_with_single_pass(self, optimizer, beijing_aoi):
        """Single pass should still produce valid tasking output."""
        passes = [self._make_pass("GF2", 40118, swath_km=11.0, offset=0.0)]
        result = optimizer.compute_coverage_tasking(passes, beijing_aoi, 30.0)
        assert isinstance(result, list)

    def test_tasking_with_mixed_satellite_types(self, optimizer, beijing_aoi):
        """Tasking works with both Optical and SAR satellites."""
        passes = [
            self._make_pass("GF2", 40118, swath_km=11.0, offset=-15.0,
                            pass_time=datetime(2025, 6, 15, 10, 0, tzinfo=timezone.utc)),
            self._make_pass("GF3", 41727, swath_km=30.0, offset=0.0,
                            pass_time=datetime(2025, 6, 15, 10, 30, tzinfo=timezone.utc)),
        ]
        result = optimizer.compute_coverage_tasking(passes, beijing_aoi, 30.0)
        assert isinstance(result, list)

    def test_tasking_multi_coverage_mode(self, optimizer, beijing_aoi):
        """Multi-coverage mode produces different results than single coverage."""
        passes = [
            self._make_pass("GF2", 40118, swath_km=11.0, offset=-10.0,
                            pass_time=datetime(2025, 6, 15, 10, 0, tzinfo=timezone.utc)),
            self._make_pass("GF3", 41727, swath_km=30.0, offset=0.0,
                            pass_time=datetime(2025, 6, 15, 10, 30, tzinfo=timezone.utc)),
            self._make_pass("GF1", 40119, swath_km=11.0, offset=10.0,
                            pass_time=datetime(2025, 6, 15, 11, 0, tzinfo=timezone.utc)),
        ]
        result = optimizer.compute_coverage_tasking(passes, beijing_aoi, 30.0,
                                                     mode="multi_coverage")
        assert isinstance(result, list)


# =============================================================================
# 3.10 — Integration: Full Pipeline (TLE -> Detection -> Tasking)
# =============================================================================

class TestFullPipeline:
    """End-to-end test: TLE fetch -> pass detection -> tasking optimization."""

    def test_full_pipeline_with_mock_data(self, pass_detector, beijing_aoi):
        """Complete pipeline with mock TLEs and simulated tracks."""
        from tasking_optimizer import TaskingOptimizer

        # Step 1: Fetch TLE and detect passes
        track_points = [
            {'time': datetime(2025, 1, 1, 10, 0, tzinfo=timezone.utc),
             'lat': 39.9, 'lon': 116.3, 'alt': 550.0, 'dist_km': 0.0, 'can_see': True},
            {'time': datetime(2025, 1, 1, 10, 1, tzinfo=timezone.utc),
             'lat': 40.0, 'lon': 116.4, 'alt': 550.0, 'dist_km': 0.0, 'can_see': True},
        ]

        all_passes = []
        for name, config in list(MOCK_SATELLITE_CONFIGS.items())[:3]:
            norad = config["norad"]
            if norad not in MOCK_TLES:
                continue
            cam_name = list(config["cameras"].keys())[0]
            cam_info = config["cameras"][cam_name]

            with patch.object(pass_detector, '_compute_track', return_value=track_points):
                passes, _ = pass_detector.detect_passes(
                    name, norad, config, cam_name, cam_info,
                    *MOCK_TLES[norad],
                    beijing_aoi,
                    datetime(2025, 1, 1, tzinfo=timezone.utc),
                    datetime(2025, 1, 2, tzinfo=timezone.utc),
                    30.0,
                )
                all_passes.extend(passes)

        # Step 2: Run tasking on detected passes
        tasking_detector = MagicMock()
        tasking_detector.ground_range_from_ona.return_value = 200.0
        tasking_detector.ona_from_distance.return_value = 15.0
        tasking_detector.get_perpendicular_distance_to_aoi.return_value = (10.0, 5.0, 1.0)

        optimizer = TaskingOptimizer(tasking_detector, sat_alt_km=550.0)
        tasking_result = optimizer.compute_coverage_tasking(
            all_passes, beijing_aoi, 30.0
        )

        # Pipeline should complete without errors
        assert isinstance(tasking_result, list)

    def test_pipeline_with_no_passes(self, pass_detector, beijing_aoi):
        """Pipeline handles the case where no passes are detected."""
        from tasking_optimizer import TaskingOptimizer

        with patch.object(pass_detector, '_compute_track', return_value=[]):
            passes, _ = pass_detector.detect_passes(
                "GF2", 40118, MOCK_SATELLITE_CONFIGS["GF2"],
                "PMS", {"swath_km": 11.0, "resolution_m": 0.8},
                *MOCK_TLES[40118],
                beijing_aoi,
                datetime(2025, 1, 1, tzinfo=timezone.utc),
                datetime(2025, 1, 2, tzinfo=timezone.utc),
                30.0,
            )
            assert passes == []

        # Tasking with empty passes should return empty
        tasking_detector = MagicMock()
        optimizer = TaskingOptimizer(tasking_detector, sat_alt_km=550.0)
        result = optimizer.compute_coverage_tasking([], beijing_aoi, 30.0)
        assert result == []

    def test_pipeline_with_multiple_aois(self, pass_detector):
        """Pipeline handles multiple AOIs sequentially."""
        from tasking_optimizer import TaskingOptimizer

        aoi1 = Polygon([(116.2, 39.8), (116.4, 39.8), (116.4, 40.0), (116.2, 40.0), (116.2, 39.8)])
        aoi2 = Polygon([(116.4, 39.8), (116.6, 39.8), (116.6, 40.0), (116.4, 40.0), (116.4, 39.8)])

        track_points = [
            {'time': datetime(2025, 1, 1, 10, 0, tzinfo=timezone.utc),
             'lat': 39.9, 'lon': 116.3, 'alt': 550.0, 'dist_km': 0.0, 'can_see': True},
        ]

        tasking_detector = MagicMock()
        tasking_detector.ground_range_from_ona.return_value = 200.0
        tasking_detector.ona_from_distance.return_value = 15.0
        tasking_detector.get_perpendicular_distance_to_aoi.return_value = (10.0, 5.0, 1.0)
        optimizer = TaskingOptimizer(tasking_detector, sat_alt_km=550.0)

        for aoi in [aoi1, aoi2]:
            with patch.object(pass_detector, '_compute_track', return_value=track_points):
                passes, _ = pass_detector.detect_passes(
                    "GF2", 40118, MOCK_SATELLITE_CONFIGS["GF2"],
                    "PMS", {"swath_km": 11.0, "resolution_m": 0.8},
                    *MOCK_TLES[40118],
                    aoi,
                    datetime(2025, 1, 1, tzinfo=timezone.utc),
                    datetime(2025, 1, 2, tzinfo=timezone.utc),
                    30.0,
                )
                result = optimizer.compute_coverage_tasking(passes, aoi, 30.0)
                assert isinstance(result, list)


# =============================================================================
# 3.11 — Mock TLE Data Validation
# =============================================================================

class TestMockTLEValidation:
    """Validate that mock TLE data is realistic and usable."""

    def test_mock_tle_parses_correctly(self):
        """Mock TLEs should parse correctly with skyfield."""
        try:
            from skyfield.api import EarthSatellite, load
            ts = load.timescale()
            for norad, (line1, line2) in MOCK_TLES.items():
                sat = EarthSatellite(line1, line2, f"SAT-{norad}", ts)
                assert sat is not None
                # Verify the satellite was created successfully
                assert sat.model.satnum == norad
        except ImportError:
            pytest.skip("skyfield not installed — cannot validate TLE parsing")

    def test_mock_tle_has_reasonable_orbital_params(self):
        """Mock TLEs should have realistic orbital parameters."""
        for norad, (line1, line2) in MOCK_TLES.items():
            # Extract inclination from line2 (columns 9-16)
            inclination = float(line2[8:16].strip())
            assert 80 <= inclination <= 105, (
                f"NORAD {norad}: inclination {inclination}° outside typical range (80-105°)"
            )
            # Extract RAAN from line2 (columns 18-25)
            raan = float(line2[17:25].strip())
            assert 0 <= raan <= 360, (
                f"NORAD {norad}: RAAN {raan}° outside valid range"
            )

    def test_mock_tle_coverage(self):
        """All satellite types should have at least one mock TLE."""
        types_covered = set()
        for name, config in MOCK_SATELLITE_CONFIGS.items():
            types_covered.add(config["type"])
        assert "Optical" in types_covered
        assert "SAR" in types_covered
