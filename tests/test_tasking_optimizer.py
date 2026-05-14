"""
Unit tests for tasking_optimizer.py.

Run with:
    pytest tests/test_tasking_optimizer.py -v
"""

import math
import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from shapely.geometry import Polygon, Point, LineString

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


# =============================================================================
# 3.9 — tasking_optimizer.py
# =============================================================================

def _make_pass(name="GF2", norad=40118, swath_km=11.0, offset=0.0,
               direction="Descending", pass_time=None):
    """Helper to create a minimal SatellitePass for testing."""
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
        ground_track=LineString([(8.0, 48.0), (9.0, 49.0)]),
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


def _make_aoi():
    return Polygon([(8.0, 48.0), (9.0, 48.0), (9.0, 49.0), (8.0, 49.0), (8.0, 48.0)])


class TestTaskingOptimizerInit:
    """TaskingOptimizer.__init__"""

    def test_initializes_with_detector(self):
        from tasking_optimizer import TaskingOptimizer
        detector = MagicMock()
        opt = TaskingOptimizer(detector, sat_alt_km=550.0)
        assert opt.detector == detector
        assert opt.sat_alt_km == 550.0

    def test_default_altitude(self):
        from tasking_optimizer import TaskingOptimizer
        opt = TaskingOptimizer(MagicMock())
        assert opt.sat_alt_km == 550.0


class TestTaskingOptimizerVerifyGeographicOrder:
    """TaskingOptimizer._verify_geographic_order"""

    @pytest.fixture
    def optimizer(self):
        from tasking_optimizer import TaskingOptimizer
        return TaskingOptimizer(MagicMock())

    def test_sorted_returns_true(self, optimizer):
        passes = [_make_pass(offset=-10.0), _make_pass(offset=0.0), _make_pass(offset=10.0)]
        result = optimizer._verify_geographic_order(passes, Point(8.5, 48.5))
        assert result is True

    def test_unsorted_returns_false(self, optimizer):
        passes = [_make_pass(offset=10.0), _make_pass(offset=-10.0), _make_pass(offset=0.0)]
        result = optimizer._verify_geographic_order(passes, Point(8.5, 48.5))
        assert result is False


class TestTaskingOptimizerSelectBestPivot:
    """TaskingOptimizer._select_best_pivot"""

    @pytest.fixture
    def optimizer(self):
        from tasking_optimizer import TaskingOptimizer
        return TaskingOptimizer(MagicMock())

    def test_selects_closest_to_aoi(self, optimizer):
        passes = [_make_pass(offset=-50.0), _make_pass(offset=0.0), _make_pass(offset=50.0)]
        best_pass, best_idx = optimizer._select_best_pivot(passes, Point(8.5, 48.5), 30.0)
        assert best_idx == 1  # offset=0 is closest
        assert best_pass.original_offset_km == 0.0

    def test_returns_first_if_all_equal(self, optimizer):
        passes = [_make_pass(offset=10.0), _make_pass(offset=10.0)]
        best_pass, best_idx = optimizer._select_best_pivot(passes, Point(8.5, 48.5), 30.0)
        assert best_idx == 0


class TestTaskingOptimizerCalculatePassesNeeded:
    """TaskingOptimizer._calculate_passes_needed"""

    @pytest.fixture
    def optimizer(self):
        from tasking_optimizer import TaskingOptimizer
        return TaskingOptimizer(MagicMock())

    def test_returns_at_least_3(self, optimizer):
        passes = [_make_pass(swath_km=30.0)]
        aoi = _make_aoi()
        n = optimizer._calculate_passes_needed(passes, aoi, 30.0)
        assert n >= 3

    def test_wider_aoi_needs_more_passes(self, optimizer):
        passes = [_make_pass(swath_km=30.0)]
        small_aoi = Polygon([(8.0, 48.0), (8.5, 48.0), (8.5, 49.0), (8.0, 49.0), (8.0, 48.0)])
        wide_aoi = Polygon([(8.0, 48.0), (10.0, 48.0), (10.0, 49.0), (8.0, 49.0), (8.0, 48.0)])
        n_small = optimizer._calculate_passes_needed(passes, small_aoi, 30.0)
        n_wide = optimizer._calculate_passes_needed(passes, wide_aoi, 30.0)
        assert n_wide >= n_small

    def test_no_passes_returns_3(self, optimizer):
        n = optimizer._calculate_passes_needed([], _make_aoi(), 30.0)
        assert n == 3


class TestTaskingOptimizerCalculateTotalCoverage:
    """TaskingOptimizer._calculate_total_coverage"""

    @pytest.fixture
    def optimizer(self):
        from tasking_optimizer import TaskingOptimizer
        return TaskingOptimizer(MagicMock())

    def test_no_assignments_returns_zero(self, optimizer):
        coverage = optimizer._calculate_total_coverage([], _make_aoi())
        assert coverage == pytest.approx(0.0)

    def test_full_coverage_returns_100(self, optimizer):
        aoi = _make_aoi()
        assignments = [{'footprint': aoi}]
        coverage = optimizer._calculate_total_coverage(assignments, aoi)
        assert coverage == pytest.approx(100.0, rel=0.01)

    def test_partial_coverage(self, optimizer):
        aoi = _make_aoi()
        half_aoi = Polygon([(8.0, 48.0), (8.5, 48.0), (8.5, 49.0), (8.0, 49.0), (8.0, 48.0)])
        assignments = [{'footprint': half_aoi}]
        coverage = optimizer._calculate_total_coverage(assignments, aoi)
        assert 40.0 < coverage < 60.0  # Roughly half


class TestTaskingOptimizerComputeCoverageTasking:
    """TaskingOptimizer.compute_coverage_tasking"""

    @pytest.fixture
    def optimizer(self):
        from tasking_optimizer import TaskingOptimizer
        detector = MagicMock()
        detector.ground_range_from_ona.return_value = 200.0
        detector.ona_from_distance.return_value = 15.0
        detector.get_perpendicular_distance_to_aoi.return_value = (10.0, 5.0, 1.0)
        return TaskingOptimizer(detector, sat_alt_km=550.0)

    def test_empty_passes_returns_empty(self, optimizer):
        result = optimizer.compute_coverage_tasking([], _make_aoi(), 30.0)
        assert result == []

    def test_none_aoi_returns_empty(self, optimizer):
        passes = [_make_pass()]
        result = optimizer.compute_coverage_tasking(passes, None, 30.0)
        assert result == []

    def test_single_pass_returns_assignments(self, optimizer):
        passes = [_make_pass(offset=0.0)]
        aoi = _make_aoi()
        result = optimizer.compute_coverage_tasking(passes, aoi, 30.0)
        assert isinstance(result, list)
        # May be empty if no valid assignments, but should not crash

    def test_multiple_passes_returns_assignments(self, optimizer):
        passes = [
            _make_pass("GF2", 40118, swath_km=11.0, offset=-20.0),
            _make_pass("GF3", 41727, swath_km=30.0, offset=0.0),
            _make_pass("GF1", 40119, swath_km=15.0, offset=20.0),
        ]
        aoi = _make_aoi()
        result = optimizer.compute_coverage_tasking(passes, aoi, 30.0)
        assert isinstance(result, list)

    def test_multi_coverage_mode(self, optimizer):
        passes = [
            _make_pass("GF2", 40118, swath_km=11.0, offset=-20.0,
                       pass_time=datetime(2025, 6, 15, 10, 0, tzinfo=timezone.utc)),
            _make_pass("GF3", 41727, swath_km=30.0, offset=0.0,
                       pass_time=datetime(2025, 6, 15, 10, 30, tzinfo=timezone.utc)),
            _make_pass("GF1", 40119, swath_km=15.0, offset=20.0,
                       pass_time=datetime(2025, 6, 15, 11, 0, tzinfo=timezone.utc)),
        ]
        aoi = _make_aoi()
        result = optimizer.compute_coverage_tasking(passes, aoi, 30.0, mode="multi_coverage")
        assert isinstance(result, list)


class TestLegacyComputeCoverageTasking:
    """Legacy compute_coverage_tasking function"""

    def test_legacy_function_exists(self):
        from tasking_optimizer import compute_coverage_tasking
        assert callable(compute_coverage_tasking)

    def test_legacy_returns_list(self):
        from tasking_optimizer import compute_coverage_tasking
        detector = MagicMock()
        detector.ground_range_from_ona.return_value = 200.0
        detector.ona_from_distance.return_value = 15.0
        detector.get_perpendicular_distance_to_aoi.return_value = (10.0, 5.0, 1.0)
        result = compute_coverage_tasking([], _make_aoi(), 30.0, detector)
        assert isinstance(result, list)
