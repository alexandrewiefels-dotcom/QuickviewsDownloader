"""
Unit tests for detection/pass_detector.py.

Run with:
    pytest tests/test_pass_detector.py -v
"""

import math
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from shapely.geometry import Polygon, Point, LineString

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


# =============================================================================
# 3.8 — detection/pass_detector.py
# =============================================================================

class TestPassDetectorGroundRange:
    """PassDetector.ground_range_from_ona(sat_alt_km, ona_deg) -> km"""

    @pytest.fixture
    def detector(self):
        from detection.pass_detector import PassDetector
        mock_tle = MagicMock()
        mock_ts = MagicMock()
        return PassDetector(mock_tle, mock_ts)

    def test_zero_ona(self, detector):
        gr = detector.ground_range_from_ona(550.0, 0.0)
        assert gr == pytest.approx(0.0)

    def test_positive_ona(self, detector):
        gr = detector.ground_range_from_ona(550.0, 30.0)
        assert gr > 0.0
        assert gr < 1000.0

    def test_higher_altitude_larger_range(self, detector):
        gr_low = detector.ground_range_from_ona(400.0, 30.0)
        gr_high = detector.ground_range_from_ona(800.0, 30.0)
        assert gr_high > gr_low

    def test_larger_ona_larger_range(self, detector):
        gr_small = detector.ground_range_from_ona(550.0, 10.0)
        gr_large = detector.ground_range_from_ona(550.0, 45.0)
        assert gr_large > gr_small


class TestPassDetectorONAFromDistance:
    """PassDetector.ona_from_distance(sat_alt_km, ground_dist_km) -> degrees"""

    @pytest.fixture
    def detector(self):
        from detection.pass_detector import PassDetector
        mock_tle = MagicMock()
        mock_ts = MagicMock()
        return PassDetector(mock_tle, mock_ts)

    def test_zero_distance(self, detector):
        ona = detector.ona_from_distance(550.0, 0.0)
        assert ona == pytest.approx(0.0)

    def test_positive_distance(self, detector):
        ona = detector.ona_from_distance(550.0, 100.0)
        assert ona > 0.0
        assert ona < 90.0

    def test_monotonic(self, detector):
        ona1 = detector.ona_from_distance(550.0, 50.0)
        ona2 = detector.ona_from_distance(550.0, 200.0)
        assert ona2 > ona1

    def test_extreme_distance_returns_90(self, detector):
        # Very large distance should return 90° (limb of Earth)
        ona = detector.ona_from_distance(550.0, 5000.0)
        assert ona == pytest.approx(90.0)


class TestPassDetectorHaversine:
    """PassDetector._haversine_distance(lat1, lon1, lat2, lon2) -> km"""

    @pytest.fixture
    def detector(self):
        from detection.pass_detector import PassDetector
        return PassDetector(MagicMock(), MagicMock())

    def test_zero_distance(self, detector):
        d = detector._haversine_distance(48.0, 8.0, 48.0, 8.0)
        assert d == pytest.approx(0.0, abs=1e-6)

    def test_known_distance(self, detector):
        # Paris → Berlin ≈ 878 km
        d = detector._haversine_distance(48.8566, 2.3522, 52.5200, 13.4050)
        assert d == pytest.approx(878, rel=0.02)

    def test_equator_degree(self, detector):
        d = detector._haversine_distance(0.0, 0.0, 0.0, 1.0)
        assert d == pytest.approx(111.2, rel=0.01)


class TestPassDetectorGeodesicMinDistance:
    """PassDetector._geodesic_min_distance(sat_lat, sat_lon, polygon) -> km"""

    @pytest.fixture
    def detector(self):
        from detection.pass_detector import PassDetector
        return PassDetector(MagicMock(), MagicMock())

    def test_point_inside_polygon(self, detector):
        poly = Polygon([(8.0, 48.0), (9.0, 48.0), (9.0, 49.0), (8.0, 49.0), (8.0, 48.0)])
        d = detector._geodesic_min_distance(48.5, 8.5, poly)
        assert d == pytest.approx(0.0)

    def test_point_outside_polygon(self, detector):
        poly = Polygon([(8.0, 48.0), (9.0, 48.0), (9.0, 49.0), (8.0, 49.0), (8.0, 48.0)])
        d = detector._geodesic_min_distance(50.0, 10.0, poly)
        assert d > 0.0

    def test_multipolygon(self, detector):
        poly1 = Polygon([(8.0, 48.0), (9.0, 48.0), (9.0, 49.0), (8.0, 49.0), (8.0, 48.0)])
        poly2 = Polygon([(10.0, 48.0), (11.0, 48.0), (11.0, 49.0), (10.0, 49.0), (10.0, 48.0)])
        from shapely.geometry import MultiPolygon
        mp = MultiPolygon([poly1, poly2])
        d = detector._geodesic_min_distance(48.5, 8.5, mp)
        assert d == pytest.approx(0.0)

    def test_far_point(self, detector):
        poly = Polygon([(8.0, 48.0), (9.0, 48.0), (9.0, 49.0), (8.0, 49.0), (8.0, 48.0)])
        d = detector._geodesic_min_distance(0.0, 0.0, poly)
        assert d > 500.0  # Far away


class TestPassDetectorPerpendicularDistance:
    """PassDetector.get_perpendicular_distance_to_aoi(pass_obj, aoi) -> tuple"""

    @pytest.fixture
    def detector(self):
        from detection.pass_detector import PassDetector
        return PassDetector(MagicMock(), MagicMock())

    def _make_pass(self, coords=None):
        from models.satellite_pass import SatellitePass
        if coords is None:
            coords = [(8.0, 48.0), (9.0, 49.0)]
        return SatellitePass(
            id="test",
            satellite_name="GF2",
            camera_name="PMS",
            norad_id=40118,
            provider="Siwei",
            pass_time=datetime(2025, 6, 15, 10, 30, tzinfo=timezone.utc),
            ground_track=LineString(coords),
            footprint=Polygon(),
            swath_km=11.0,
            resolution_m=0.8,
            sensor_type="Optical",
            color="#00CED1",
            inclination=97.4,
            orbit_direction="Descending",
            track_azimuth=180.0,
            min_ona=2.5,
            max_ona=15.0,
            aoi_center=Point(8.5, 48.5),
        )

    def test_returns_tuple(self, detector):
        p = self._make_pass()
        aoi = Polygon([(8.0, 48.0), (9.0, 48.0), (9.0, 49.0), (8.0, 49.0), (8.0, 48.0)])
        result = detector.get_perpendicular_distance_to_aoi(p, aoi)
        assert len(result) == 3
        abs_dist, signed_dist, _ = result
        assert abs_dist >= 0.0
        assert isinstance(signed_dist, float)

    def test_aoi_on_track(self, detector):
        p = self._make_pass()
        # AOI centered on the track
        aoi = Polygon([(8.4, 48.4), (8.6, 48.4), (8.6, 48.6), (8.4, 48.6), (8.4, 48.4)])
        abs_dist, signed_dist, _ = detector.get_perpendicular_distance_to_aoi(p, aoi)
        assert abs_dist < 10.0  # Close to track

    def test_empty_track_returns_none(self, detector):
        from models.satellite_pass import SatellitePass
        p = SatellitePass(
            id="test", satellite_name="GF2", camera_name="PMS",
            norad_id=40118, provider="Siwei",
            pass_time=datetime(2025, 6, 15, 10, 30, tzinfo=timezone.utc),
            ground_track=LineString(), footprint=Polygon(),
            swath_km=11.0, resolution_m=0.8, sensor_type="Optical",
            color="#00CED1", inclination=97.4, orbit_direction="Descending",
            track_azimuth=180.0, min_ona=2.5, max_ona=15.0,
        )
        aoi = Polygon([(8.0, 48.0), (9.0, 48.0), (9.0, 49.0), (8.0, 49.0), (8.0, 48.0)])
        result = detector.get_perpendicular_distance_to_aoi(p, aoi)
        assert result == (None, None, None)


class TestPassDetectorCreateShiftedFootprint:
    """PassDetector.create_shifted_footprint(pass_obj, offset_km) -> Polygon"""

    @pytest.fixture
    def detector(self):
        from detection.pass_detector import PassDetector
        return PassDetector(MagicMock(), MagicMock())

    def _make_pass(self):
        from models.satellite_pass import SatellitePass
        return SatellitePass(
            id="test", satellite_name="GF2", camera_name="PMS",
            norad_id=40118, provider="Siwei",
            pass_time=datetime(2025, 6, 15, 10, 30, tzinfo=timezone.utc),
            ground_track=LineString([(8.0, 48.0), (9.0, 49.0)]),
            footprint=Polygon(), swath_km=11.0, resolution_m=0.8,
            sensor_type="Optical", color="#00CED1", inclination=97.4,
            orbit_direction="Descending", track_azimuth=180.0,
            min_ona=2.5, max_ona=15.0,
        )

    def test_zero_offset(self, detector):
        p = self._make_pass()
        fp = detector.create_shifted_footprint(p, 0.0)
        assert fp.geom_type == "Polygon"

    def test_positive_offset(self, detector):
        p = self._make_pass()
        fp = detector.create_shifted_footprint(p, 10.0)
        assert fp.geom_type == "Polygon"
        assert not fp.is_empty


class TestPassDetectorDetectPasses:
    """PassDetector.detect_passes(...) -> (passes, [])"""

    @pytest.fixture
    def detector(self):
        from detection.pass_detector import PassDetector
        mock_tle = MagicMock()
        mock_ts = MagicMock()
        return PassDetector(mock_tle, mock_ts)

    def test_no_track_points_returns_empty(self, detector):
        """If _compute_track returns empty, detect_passes returns empty."""
        with patch.object(detector, '_compute_track', return_value=[]):
            result, _ = detector.detect_passes(
                "GF2", 40118, {"provider": "Siwei", "type": "Optical", "color": "#00CED1"},
                "PMS", {"swath_km": 11.0, "resolution_m": 0.8},
                "line1", "line2",
                Polygon([(8.0, 48.0), (9.0, 48.0), (9.0, 49.0), (8.0, 49.0), (8.0, 48.0)]),
                datetime(2025, 1, 1), datetime(2025, 1, 2), 30.0
            )
            assert result == []

    def test_returns_list(self, detector):
        """With valid track points, detect_passes returns a list."""
        track_points = [
            {'time': datetime(2025, 1, 1, 10, 0), 'lat': 48.0, 'lon': 8.0, 'alt': 550.0, 'dist_km': 0.0, 'can_see': True},
            {'time': datetime(2025, 1, 1, 10, 1), 'lat': 48.5, 'lon': 8.5, 'alt': 550.0, 'dist_km': 0.0, 'can_see': True},
            {'time': datetime(2025, 1, 1, 10, 2), 'lat': 49.0, 'lon': 9.0, 'alt': 550.0, 'dist_km': 0.0, 'can_see': True},
        ]
        with patch.object(detector, '_compute_track', return_value=track_points):
            result, _ = detector.detect_passes(
                "GF2", 40118, {"provider": "Siwei", "type": "Optical", "color": "#00CED1"},
                "PMS", {"swath_km": 11.0, "resolution_m": 0.8},
                "line1", "line2",
                Polygon([(8.0, 48.0), (9.0, 48.0), (9.0, 49.0), (8.0, 49.0), (8.0, 48.0)]),
                datetime(2025, 1, 1), datetime(2025, 1, 2), 30.0
            )
            assert isinstance(result, list)
