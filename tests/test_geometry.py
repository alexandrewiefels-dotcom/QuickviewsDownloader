"""
Unit tests for geometry/calculations.py and geometry/footprint.py.

Run with:
    pytest tests/test_geometry.py -v
"""

import math
import sys
from pathlib import Path

import pytest
from shapely.geometry import Polygon, LineString, MultiPolygon, Point

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


# =============================================================================
# 3.7 — geometry/calculations.py
# =============================================================================

class TestGreatCircleDistance:
    """great_circle_distance(lat1, lon1, lat2, lon2) -> km"""

    def test_zero_distance(self):
        from geometry.calculations import great_circle_distance
        d = great_circle_distance(48.0, 8.0, 48.0, 8.0)
        assert d == pytest.approx(0.0, abs=1e-6)

    def test_known_distance_paris_berlin(self):
        from geometry.calculations import great_circle_distance
        # Paris (48.8566, 2.3522) → Berlin (52.5200, 13.4050) ≈ 878 km
        d = great_circle_distance(48.8566, 2.3522, 52.5200, 13.4050)
        assert d == pytest.approx(878, rel=0.02)

    def test_equator_distance(self):
        from geometry.calculations import great_circle_distance
        # 1° along equator ≈ 111.2 km
        d = great_circle_distance(0.0, 0.0, 0.0, 1.0)
        assert d == pytest.approx(111.2, rel=0.01)

    def test_antipodal(self):
        from geometry.calculations import great_circle_distance
        # North Pole → South Pole ≈ half Earth circumference
        d = great_circle_distance(90.0, 0.0, -90.0, 0.0)
        assert d == pytest.approx(20015, rel=0.01)

    def test_wraps_antimeridian(self):
        from geometry.calculations import great_circle_distance
        # Points on either side of 180° meridian
        d = great_circle_distance(0.0, 179.0, 0.0, -179.0)
        assert d == pytest.approx(222.4, rel=0.02)


class TestCalculateBearing:
    """calculate_bearing(lat1, lon1, lat2, lon2) -> degrees"""

    def test_north(self):
        from geometry.calculations import calculate_bearing
        b = calculate_bearing(0.0, 0.0, 10.0, 0.0)
        assert b == pytest.approx(0.0, abs=1.0)  # due north

    def test_east(self):
        from geometry.calculations import calculate_bearing
        b = calculate_bearing(0.0, 0.0, 0.0, 10.0)
        assert b == pytest.approx(90.0, abs=1.0)  # due east

    def test_south(self):
        from geometry.calculations import calculate_bearing
        b = calculate_bearing(10.0, 0.0, 0.0, 0.0)
        assert b == pytest.approx(180.0, abs=1.0)  # due south

    def test_west(self):
        from geometry.calculations import calculate_bearing
        b = calculate_bearing(0.0, 10.0, 0.0, 0.0)
        assert b == pytest.approx(270.0, abs=1.0)  # due west

    def test_bearing_range(self):
        from geometry.calculations import calculate_bearing
        for lat1, lon1, lat2, lon2 in [
            (48.0, 8.0, 49.0, 9.0),
            (-33.0, -70.0, -34.0, -71.0),
            (35.0, 140.0, 36.0, 139.0),
        ]:
            b = calculate_bearing(lat1, lon1, lat2, lon2)
            assert 0 <= b <= 360, f"Bearing {b} out of range [0, 360]"


class TestCalculateONA:
    """calculate_ona(sat_lat, sat_lon, sat_alt, target_lat, target_lon) -> degrees"""

    def test_nadir_is_zero(self):
        from geometry.calculations import calculate_ona
        ona = calculate_ona(48.0, 8.0, 550.0, 48.0, 8.0)
        assert ona == pytest.approx(0.0, abs=0.1)

    def test_off_nadir_positive(self):
        from geometry.calculations import calculate_ona
        # Satellite at (48, 8, 550km), target 100km away
        ona = calculate_ona(48.0, 8.0, 550.0, 48.5, 8.5)
        assert ona > 0.0
        assert ona < 90.0

    def test_high_altitude_lower_ona(self):
        from geometry.calculations import calculate_ona
        # Same ground distance, higher altitude → lower ONA
        ona_low = calculate_ona(48.0, 8.0, 400.0, 48.5, 8.5)
        ona_high = calculate_ona(48.0, 8.0, 800.0, 48.5, 8.5)
        assert ona_high < ona_low


class TestComputeEffectiveSwath:
    """compute_effective_swath(swath_nadir_km, ona_deg, altitude_km) -> km"""

    def test_nadir_equals_swath(self):
        from geometry.calculations import compute_effective_swath
        eff = compute_effective_swath(30.0, 0.0, 550.0)
        assert eff == pytest.approx(30.0, rel=0.01)

    def test_off_nadir_reduces_swath(self):
        from geometry.calculations import compute_effective_swath
        eff = compute_effective_swath(30.0, 30.0, 550.0)
        assert eff < 30.0
        assert eff > 0.0

    def test_extreme_ona(self):
        from geometry.calculations import compute_effective_swath
        eff = compute_effective_swath(30.0, 60.0, 550.0)
        assert eff == pytest.approx(15.0, abs=0.01)  # Significantly reduced


class TestComputeONAFromGroundDistance:
    """compute_ona_from_ground_distance(altitude_km, ground_dist_km) -> degrees"""

    def test_zero_distance(self):
        from geometry.calculations import compute_ona_from_ground_distance
        ona = compute_ona_from_ground_distance(550.0, 0.0)
        assert ona == pytest.approx(0.0)

    def test_positive_distance(self):
        from geometry.calculations import compute_ona_from_ground_distance
        ona = compute_ona_from_ground_distance(550.0, 100.0)
        assert ona > 0.0
        assert ona < 90.0

    def test_monotonic(self):
        from geometry.calculations import compute_ona_from_ground_distance
        ona1 = compute_ona_from_ground_distance(550.0, 50.0)
        ona2 = compute_ona_from_ground_distance(550.0, 100.0)
        ona3 = compute_ona_from_ground_distance(550.0, 200.0)
        assert ona1 < ona2 < ona3


# =============================================================================
# 3.7 — geometry/footprint.py
# =============================================================================

class TestCreateSwathRibbon:
    """create_swath_ribbon_spherical(coords, swath_km) -> Polygon"""

    def test_returns_polygon(self):
        from geometry.footprint import create_swath_ribbon_spherical
        coords = [(8.0, 48.0), (9.0, 49.0)]
        fp = create_swath_ribbon_spherical(coords, 30.0)
        assert fp.geom_type == "Polygon"
        assert not fp.is_empty

    def test_single_point_returns_empty(self):
        from geometry.footprint import create_swath_ribbon_spherical
        fp = create_swath_ribbon_spherical([(8.0, 48.0)], 30.0)
        assert fp.is_empty

    def test_empty_coords(self):
        from geometry.footprint import create_swath_ribbon_spherical
        fp = create_swath_ribbon_spherical([], 30.0)
        assert fp.is_empty

    def test_larger_swath_larger_area(self):
        from geometry.footprint import create_swath_ribbon_spherical
        coords = [(8.0, 48.0), (9.0, 49.0)]
        fp_small = create_swath_ribbon_spherical(coords, 10.0)
        fp_large = create_swath_ribbon_spherical(coords, 50.0)
        assert fp_large.area > fp_small.area

    def test_with_lat_bounds(self):
        from geometry.footprint import create_swath_ribbon_spherical
        coords = [(8.0, 48.0), (9.0, 49.0)]
        fp = create_swath_ribbon_spherical(coords, 30.0, lat_bounds=(47.0, 50.0))
        assert fp.geom_type == "Polygon"
        assert not fp.is_empty

    def test_antimeridian_crossing(self):
        from geometry.footprint import create_swath_ribbon_spherical
        # Track crossing 180° meridian
        coords = [(175.0, 10.0), (-175.0, 11.0)]
        fp = create_swath_ribbon_spherical(coords, 30.0)
        assert fp.geom_type == "Polygon"
        assert not fp.is_empty


class TestOffsetLineEastWest:
    """offset_line_east_west(coords, offset_km, ref_lat) -> list"""

    def test_zero_offset(self):
        from geometry.footprint import offset_line_east_west
        coords = [(8.0, 48.0), (9.0, 49.0)]
        result = offset_line_east_west(coords, 0.0, 48.5)
        assert result == coords

    def test_positive_offset_shifts_east(self):
        from geometry.footprint import offset_line_east_west
        coords = [(8.0, 48.0), (9.0, 49.0)]
        result = offset_line_east_west(coords, 10.0, 48.5)
        for (orig_lon, orig_lat), (new_lon, new_lat) in zip(coords, result):
            assert new_lon > orig_lon  # shifted east
            assert new_lat == orig_lat  # latitude unchanged

    def test_negative_offset_shifts_west(self):
        from geometry.footprint import offset_line_east_west
        coords = [(8.0, 48.0), (9.0, 49.0)]
        result = offset_line_east_west(coords, -10.0, 48.5)
        for (orig_lon, orig_lat), (new_lon, new_lat) in zip(coords, result):
            assert new_lon < orig_lon  # shifted west

    def test_near_pole_large_shift(self):
        from geometry.footprint import offset_line_east_west
        coords = [(0.0, 89.0), (1.0, 89.5)]
        result = offset_line_east_west(coords, 10.0, 89.0)
        # cos(89°) ≈ 0.017 → km_per_deg ≈ 1.9 → offset is ~5.2° longitude
        # The function shifts near poles (only returns original when abs(cos_lat) < 0.01)
        assert result != coords  # Shift occurs
        for (orig_lon, orig_lat), (new_lon, new_lat) in zip(coords, result):
            assert new_lon > orig_lon  # shifted east
            assert new_lat == orig_lat  # latitude unchanged


class TestCreateOffsetSwathRibbon:
    """create_offset_swath_ribbon(coords, swath_km, offset_km) -> Polygon"""

    def test_zero_offset(self):
        from geometry.footprint import create_offset_swath_ribbon, create_swath_ribbon_spherical
        coords = [(8.0, 48.0), (9.0, 49.0)]
        fp_center = create_swath_ribbon_spherical(coords, 30.0)
        fp_offset = create_offset_swath_ribbon(coords, 30.0, 0.0)
        assert fp_center.area == pytest.approx(fp_offset.area, rel=0.01)

    def test_offset_changes_position(self):
        from geometry.footprint import create_offset_swath_ribbon
        coords = [(8.0, 48.0), (9.0, 49.0)]
        fp_center = create_offset_swath_ribbon(coords, 30.0, 0.0)
        fp_shifted = create_offset_swath_ribbon(coords, 30.0, 20.0)
        # Centroids should differ
        assert fp_center.centroid.distance(fp_shifted.centroid) > 0.1


class TestShiftLineString:
    """shift_linestring(line, offset_km, ref_lat) -> LineString"""

    def test_zero_offset(self):
        from geometry.footprint import shift_linestring
        line = LineString([(8.0, 48.0), (9.0, 49.0)])
        result = shift_linestring(line, 0.0, 48.5)
        assert result.equals(line)

    def test_positive_offset(self):
        from geometry.footprint import shift_linestring
        line = LineString([(8.0, 48.0), (9.0, 49.0)])
        result = shift_linestring(line, 10.0, 48.5)
        for (orig_lon, orig_lat), (new_lon, new_lat) in zip(line.coords, result.coords):
            assert new_lon > orig_lon

    def test_returns_linestring(self):
        from geometry.footprint import shift_linestring
        line = LineString([(8.0, 48.0), (9.0, 49.0)])
        result = shift_linestring(line, 10.0, 48.5)
        assert result.geom_type == "LineString"


class TestClipGeometryToLatitudeBand:
    """clip_geometry_to_latitude_band(geom, min_lat, max_lat) -> geometry"""

    def test_polygon_within_band(self):
        from geometry.footprint import clip_geometry_to_latitude_band
        poly = Polygon([(8.0, 48.0), (9.0, 48.0), (9.0, 49.0), (8.0, 49.0), (8.0, 48.0)])
        result = clip_geometry_to_latitude_band(poly, 47.0, 50.0)
        assert result is not None
        assert result.geom_type == "Polygon"

    def test_polygon_outside_band(self):
        from geometry.footprint import clip_geometry_to_latitude_band
        poly = Polygon([(8.0, 48.0), (9.0, 48.0), (9.0, 49.0), (8.0, 49.0), (8.0, 48.0)])
        result = clip_geometry_to_latitude_band(poly, 50.0, 51.0)
        assert result is None

    def test_partial_clip(self):
        from geometry.footprint import clip_geometry_to_latitude_band
        poly = Polygon([(8.0, 48.0), (9.0, 48.0), (9.0, 50.0), (8.0, 50.0), (8.0, 48.0)])
        result = clip_geometry_to_latitude_band(poly, 49.0, 51.0)
        assert result is not None
        assert result.area < poly.area
