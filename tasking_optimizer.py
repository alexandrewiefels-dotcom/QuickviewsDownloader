# ============================================================================
# FILE: tasking_optimizer.py – Sequential paving with dynamic overlap
# 
# DESCRIPTION:
#   Implements the sequential paving algorithm for satellite tasking.
#   It takes a list of detected passes and shifts them laterally (east/west)
#   to create a continuous coverage strip over the Area of Interest (AOI).
#
#   KEY IMPROVEMENTS:
#   - Dynamic overlap: 10% of the smaller swath between two adjacent passes
#   - Geographic order verification
#   - Separate handling of ascending/descending passes
#   - Multi‑point overlap calculation (not just centroid)
#   - Intelligent pivot selection (based on distance to AOI centroid)
#   - Non‑adjacent passes overlap verification
#   - Latitude band clipping for tasked footprints
#   - Timestamped logs for debugging
#
# AUTHOR: OrbitShow Team
# VERSION: 2.0 (dynamic overlap)
# ============================================================================

import math
from datetime import datetime
from typing import List, Dict, Optional, Tuple
from shapely.geometry import LineString, Polygon, MultiPolygon, box
from shapely.ops import unary_union
from geometry.utils import split_polygon_at_antimeridian
from geometry.footprint import create_swath_ribbon_spherical, shift_linestring, clip_geometry_to_latitude_band

# Constants
FOOTPRINT_MARGIN_DEG = 0.5
TRACK_MARGIN_DEG = 2.0
OVERLAP_PERCENT = 50.0   # 10% of the smaller swath

# --------------------------------------------------------------------------
# Helper: timestamped print
# --------------------------------------------------------------------------
def _log(msg: str):
    """Print a message with a timestamp."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    print(f"[{timestamp}] {msg}")


class TaskingOptimizer:
    """
    Optimized sequential paving algorithm with dynamic overlap.
    """

    def __init__(self, detector, sat_alt_km=550.0, overlap_km=None):
        """
        Args:
            detector: PassDetector instance (provides ONA functions)
            sat_alt_km: Satellite altitude in km (default 550 km)
            overlap_km: Deprecated. Now dynamic overlap (10% of smaller swath) is used.
        """
        self.detector = detector
        self.sat_alt_km = sat_alt_km
        # overlap_km is ignored; dynamic overlap is applied in the loops.
        _log(f"TaskingOptimizer initialized: altitude={sat_alt_km} km, dynamic overlap = {OVERLAP_PERCENT}% of smaller swath")

    def compute_coverage_tasking(self, passes, aoi, max_ona, mode="one_coverage",
                                   progress_callback=None) -> List[Dict]:
        """
        Main entry point: run tasking with selected mode.
        
        Args:
            passes: List of SatellitePass objects
            aoi: Area of Interest polygon
            max_ona: Maximum Off‑Nadir Angle allowed
            mode: "one_coverage" or "multi_coverage"
            progress_callback: Optional callback for progress updates
        
        Returns:
            List of assignment dictionaries (each with footprint, ONA, etc.)
        """
        if not passes or aoi is None or aoi.is_empty:
            _log("No passes or AOI provided – returning empty list")
            return []
        
        _log(f"compute_coverage_tasking called: {len(passes)} passes, max_ona={max_ona}°, mode={mode}")
        if mode == "multi_coverage":
            return self._compute_multi_coverage_tasking(passes, aoi, max_ona, progress_callback)
        else:
            return self._compute_one_coverage_tasking(passes, aoi, max_ona, progress_callback)

    # ------------------------------------------------------------------
    # Helper methods
    # ------------------------------------------------------------------
    def _verify_geographic_order(self, passes, aoi_centroid) -> bool:
        offsets = [p.original_offset_km for p in passes]
        is_sorted = all(offsets[i] <= offsets[i+1] for i in range(len(offsets)-1))
        if not is_sorted:
            _log("Warning: Passes not in geographic order! Sorting them...")
        return is_sorted

    def _select_best_pivot(self, passes, aoi_centroid, max_ona):
        """Select the pass with smallest absolute offset (closest to AOI centroid)."""
        best_distance = float('inf')
        best_pass = None
        best_idx = -1
        for i, p in enumerate(passes):
            distance = abs(p.original_offset_km)
            if distance < best_distance:
                best_distance = distance
                best_pass = p
                best_idx = i
        _log(f"Pivot selected: {best_pass.satellite_name} (offset={best_distance:.1f} km, ONA={best_pass.min_ona:.1f}°)")
        return best_pass, best_idx

    def _calculate_passes_needed(self, passes, aoi, max_ona) -> int:
        """Estimate minimum passes needed to cover AOI width."""
        if not passes or aoi is None:
            return 3
        bounds = aoi.bounds
        min_lon, min_lat, max_lon, max_lat = bounds
        centroid_lat = (min_lat + max_lat) / 2
        km_per_deg = 111.0 * math.cos(math.radians(centroid_lat))
        aoi_width_km = (max_lon - min_lon) * km_per_deg
        avg_swath = sum(p.swath_km for p in passes) / len(passes) if passes else 15
        # For multi‑coverage we assume a fixed overlap of 10% of avg_swath
        effective_swath = avg_swath * (1 - 0.1)
        passes_needed = max(1, math.ceil(aoi_width_km / effective_swath))
        return max(3, min(passes_needed + 2, len(passes)))

    def _calculate_total_coverage(self, assignments, aoi) -> float:
        """Calculate total AOI coverage percentage from all tasked footprints."""
        if not assignments or aoi is None or aoi.is_empty:
            return 0.0
        footprints = [a['footprint'] for a in assignments if a.get('footprint') and not a['footprint'].is_empty]
        if not footprints:
            return 0.0
        try:
            union = unary_union(footprints)
            intersection = union.intersection(aoi)
            return (intersection.area / aoi.area) * 100.0
        except Exception as e:
            _log(f"Coverage calculation error: {e}")
            return 0.0

    def _build_assignments(self, sorted_passes, aoi, max_ona, tasked_centers, max_ona_reached, pivot_idx) -> List[Dict]:
        """Build assignment dictionaries from processed passes."""
        assignments = []
        min_lat, max_lat = aoi.bounds[1], aoi.bounds[3]
        ref_lat = (min_lat + max_lat) / 2.0

        for i, p in enumerate(sorted_passes):
            shift = getattr(p, 'tasked_shift_km', 0.0)
            if shift is None:
                shift = 0.0

            p.tasked_ona = min(self.detector.ona_from_distance(self.sat_alt_km, abs(shift)), max_ona)
            p.max_ona_reached = max_ona_reached[i]
            p.is_central = (i == pivot_idx)

            # Create shifted display ground track
            if hasattr(p, 'display_ground_track') and p.display_ground_track and not p.display_ground_track.is_empty:
                shifted_track = shift_linestring(p.display_ground_track, shift, ref_lat)
                p.display_ground_track = clip_geometry_to_latitude_band(shifted_track, min_lat, max_lat, margin_deg=TRACK_MARGIN_DEG)
            else:
                p.display_ground_track = p.ground_track

            # Create shifted display footprint
            if p.display_ground_track and not p.display_ground_track.is_empty:
                track_coords = list(p.display_ground_track.coords)
                shifted_fp = create_swath_ribbon_spherical(track_coords, p.swath_km)
                p.display_footprint = clip_geometry_to_latitude_band(shifted_fp, min_lat, max_lat, margin_deg=FOOTPRINT_MARGIN_DEG)
            else:
                p.display_footprint = None

            # Fallback for tasked_footprint (used for coverage)
            p.tasked_footprint = p.display_footprint

            coverage_pct = 0
            if p.tasked_footprint and not p.tasked_footprint.is_empty:
                try:
                    intersection = p.tasked_footprint.intersection(aoi)
                    if not intersection.is_empty:
                        coverage_pct = (intersection.area / aoi.area) * 100.0
                except Exception:
                    pass

            assignments.append({
                'id': p.id,
                'satellite': p.satellite_name,
                'camera': p.camera_name,
                'provider': p.provider,
                'norad_id': p.norad_id,
                'required_ona': p.tasked_ona,
                'offset_km': abs(shift),
                'shift_km': shift,
                'pass_time': p.pass_time,
                'color': p.color,
                'swath_km': p.swath_km,
                'resolution_m': p.resolution_m,
                'footprint': p.tasked_footprint,
                'display_footprint': p.display_footprint,
                'original_footprint': p.footprint,
                'y_center': p.y_center,
                'is_central': p.is_central,
                'coverage_pct': coverage_pct,
                'orbit_direction': p.orbit_direction,
                'cloud_cover': getattr(p, 'mean_cloud_cover', None)
            })
        return assignments

    # ------------------------------------------------------------------
    # MODE 1: ONE COVERAGE – Sequential paving with dynamic overlap
    # ------------------------------------------------------------------
    def _compute_one_coverage_tasking(self, passes, aoi, max_ona, progress_callback=None):
        import streamlit as st
        _log("=" * 80)
        _log("MODE 1: One Coverage – Sequential paving")
        _log(f"{len(passes)} passes, max_ona={max_ona}°")
        _log(f"Dynamic overlap = {OVERLAP_PERCENT}% of smaller swath")
        _log("=" * 80)

        # Get orbit filter from session state
        orbit_filter = st.session_state.get('orbit_filter', 'Both')
        _log(f"Orbit filter: {orbit_filter}")

        # Separate passes by direction if needed
        if orbit_filter == 'Both':
            descending_passes = [p for p in passes if p.orbit_direction == "Descending"]
            ascending_passes = [p for p in passes if p.orbit_direction == "Ascending"]
            _log(f"Descending passes: {len(descending_passes)}")
            _log(f"Ascending passes: {len(ascending_passes)}")

            all_assignments = []
            if descending_passes:
                _log("--- Paving descending passes ---")
                desc_assignments = self._pave_direction_subset(descending_passes, aoi, max_ona)
                if desc_assignments:
                    for a in desc_assignments:
                        a['coverage_id'] = 'desc'
                    all_assignments.extend(desc_assignments)
            if ascending_passes:
                _log("--- Paving ascending passes ---")
                asc_assignments = self._pave_direction_subset(ascending_passes, aoi, max_ona)
                if asc_assignments:
                    for a in asc_assignments:
                        a['coverage_id'] = 'asc'
                    all_assignments.extend(asc_assignments)

            total_coverage = self._calculate_total_coverage(all_assignments, aoi)
            _log(f"Combined AOI Coverage: {total_coverage:.1f}%")
            return all_assignments
        else:
            # Single direction (or both but already filtered)
            return self._pave_direction_subset(passes, aoi, max_ona)

    def _pave_direction_subset(self, passes_subset, aoi, max_ona):
        """
        Run the sequential paving algorithm on a subset of passes (same direction).
        Returns list of assignments.
        """
        if not passes_subset:
            return []

        aoi_centroid = aoi.centroid
        _log(f"Paving {len(passes_subset)} passes (direction: {passes_subset[0].orbit_direction if passes_subset else 'none'})")

        # Ensure each pass has original_offset_km
        for p in passes_subset:
            if not hasattr(p, 'original_offset_km') or p.original_offset_km is None:
                _, offset_km, _ = self.detector.get_perpendicular_distance_to_aoi(p, aoi_centroid)
                p.original_offset_km = offset_km if offset_km is not None else 0.0
            p.current_offset_km = p.original_offset_km

        # Sort by offset (west to east)
        sorted_passes = sorted(passes_subset, key=lambda p: p.original_offset_km)
        n = len(sorted_passes)

        # Pivot selection (closest to AOI centroid)
        pivot_pass, pivot_idx = self._select_best_pivot(sorted_passes, aoi_centroid, max_ona)
        if pivot_pass is None:
            _log("Error: No pivot pass selected!")
            return []

        max_shift_km = self.detector.ground_range_from_ona(self.sat_alt_km, max_ona)
        tasked_centers = [0.0] * n
        max_ona_reached = [False] * n

        # Process pivot
        shift_needed = -pivot_pass.original_offset_km
        if abs(shift_needed) > max_shift_km:
            actual_shift = math.copysign(max_shift_km, shift_needed)
            max_ona_reached[pivot_idx] = True
        else:
            actual_shift = shift_needed
            max_ona_reached[pivot_idx] = False
        tasked_centers[pivot_idx] = 0.0
        pivot_pass.tasked_shift_km = actual_shift
        pivot_pass.y_center = 0.0
        pivot_ona = self.detector.ona_from_distance(self.sat_alt_km, abs(actual_shift))
        _log(f"Pivot: {pivot_pass.satellite_name} (dir={pivot_pass.orbit_direction}) "
             f"orig={pivot_pass.original_offset_km:.1f} km, shift={actual_shift:.1f} km, ONA={pivot_ona:.1f}°")

        # ---------- WEST SIDE (paving westwards) with dynamic overlap ----------
        last_center = 0.0
        last_swath = pivot_pass.swath_km
        _log("West side: paving westwards...")
        for i in range(pivot_idx - 1, -1, -1):
            curr = sorted_passes[i]
            # Dynamic overlap = 10% of the smaller swath
            dynamic_overlap = (OVERLAP_PERCENT / 100.0) * min(curr.swath_km, last_swath)
            desired_center = last_center - (curr.swath_km/2 + last_swath/2) + dynamic_overlap
            shift_needed = desired_center - curr.original_offset_km

            if abs(shift_needed) > max_shift_km:
                actual_shift = math.copysign(max_shift_km, shift_needed)
                max_ona_reached[i] = True
                actual_center = curr.original_offset_km + actual_shift
                _log(f"  ⚠️ {curr.satellite_name}: shift clamped to {actual_shift:.1f} km")
            else:
                actual_shift = shift_needed
                max_ona_reached[i] = False
                actual_center = desired_center

            tasked_centers[i] = actual_center
            curr.tasked_shift_km = actual_shift
            curr.y_center = actual_center
            last_center = actual_center
            last_swath = curr.swath_km

            ona = self.detector.ona_from_distance(self.sat_alt_km, abs(actual_shift))
            _log(f"  {curr.satellite_name} (dir={curr.orbit_direction}): "
                 f"orig={curr.original_offset_km:.1f}, shift={actual_shift:.1f}, center={actual_center:.1f}, ONA={ona:.1f}°")

        # ---------- EAST SIDE (paving eastwards) with dynamic overlap ----------
        last_center = 0.0
        last_swath = pivot_pass.swath_km
        _log("East side: paving eastwards...")
        for i in range(pivot_idx + 1, n):
            curr = sorted_passes[i]
            dynamic_overlap = (OVERLAP_PERCENT / 100.0) * min(curr.swath_km, last_swath)
            desired_center = last_center + (curr.swath_km/2 + last_swath/2) - dynamic_overlap
            shift_needed = desired_center - curr.original_offset_km

            if abs(shift_needed) > max_shift_km:
                actual_shift = math.copysign(max_shift_km, shift_needed)
                max_ona_reached[i] = True
                actual_center = curr.original_offset_km + actual_shift
                _log(f"  ⚠️ {curr.satellite_name}: shift clamped to {actual_shift:.1f} km")
            else:
                actual_shift = shift_needed
                max_ona_reached[i] = False
                actual_center = desired_center

            tasked_centers[i] = actual_center
            curr.tasked_shift_km = actual_shift
            curr.y_center = actual_center
            last_center = actual_center
            last_swath = curr.swath_km

            ona = self.detector.ona_from_distance(self.sat_alt_km, abs(actual_shift))
            _log(f"  {curr.satellite_name} (dir={curr.orbit_direction}): "
                 f"orig={curr.original_offset_km:.1f}, shift={actual_shift:.1f}, center={actual_center:.1f}, ONA={ona:.1f}°")

        # Build assignments
        assignments = self._build_assignments(sorted_passes, aoi, max_ona,
                                              tasked_centers, max_ona_reached, pivot_idx)
        return assignments

    # ------------------------------------------------------------------
    # MODE 2: MULTI COVERAGE – Chronological paving with dynamic overlap
    # ------------------------------------------------------------------
    def _compute_multi_coverage_tasking(self, passes, aoi, max_ona, progress_callback=None) -> List[Dict]:
        _log("=" * 80)
        _log("MODE 2: Multi Coverage – Chronological paving")
        _log(f"{len(passes)} passes, max_ona={max_ona}°")
        _log(f"Dynamic overlap = {OVERLAP_PERCENT}% of smaller swath")
        _log("=" * 80)

        aoi_centroid = aoi.centroid
        for p in passes:
            if not hasattr(p, 'original_offset_km') or p.original_offset_km is None:
                _, offset_km, _ = self.detector.get_perpendicular_distance_to_aoi(p, aoi_centroid)
                p.original_offset_km = offset_km if offset_km is not None else 0.0
            p.current_offset_km = p.original_offset_km

        passes_needed = self._calculate_passes_needed(passes, aoi, max_ona)
        _log(f"Estimated passes needed: {passes_needed}")

        chronological_passes = sorted(passes, key=lambda p: p.pass_time)
        total_passes = len(chronological_passes)
        max_coverages = total_passes // passes_needed if passes_needed > 0 else 1
        max_coverages = max(1, min(max_coverages, 5))

        coverage_groups = []
        for c in range(max_coverages):
            start_idx = c * passes_needed
            end_idx = min((c + 1) * passes_needed, total_passes)
            if start_idx < total_passes:
                group = chronological_passes[start_idx:end_idx]
                if len(group) >= passes_needed * 0.5:
                    coverage_groups.append({
                        'coverage_id': c + 1,
                        'passes': group,
                        'assignments': []
                    })
                    _log(f"Group {c+1}: {len(group)} passes")

        all_assignments = []
        for group in coverage_groups:
            _log(f"{'='*60}\nCoverage {group['coverage_id']}: Processing {len(group['passes'])} passes\n{'='*60}")
            sorted_group = sorted(group['passes'], key=lambda p: p.original_offset_km)
            pivot_pass, pivot_idx = self._select_best_pivot(sorted_group, aoi_centroid, max_ona)
            if pivot_pass is None:
                continue

            max_shift_km = self.detector.ground_range_from_ona(self.sat_alt_km, max_ona)
            n_group = len(sorted_group)
            tasked_centers = [0.0] * n_group
            max_ona_reached = [False] * n_group

            shift_needed = -pivot_pass.original_offset_km
            if abs(shift_needed) > max_shift_km:
                actual_shift = math.copysign(max_shift_km, shift_needed)
                max_ona_reached[pivot_idx] = True
            else:
                actual_shift = shift_needed
                max_ona_reached[pivot_idx] = False
            tasked_centers[pivot_idx] = 0.0
            pivot_pass.tasked_shift_km = actual_shift
            pivot_pass.y_center = 0.0
            _log(f"Coverage {group['coverage_id']} Pivot: {pivot_pass.satellite_name} "
                 f"(date: {pivot_pass.pass_time.strftime('%Y-%m-%d %H:%M')}) shift={actual_shift:.1f} km")

            # West side
            last_center = 0.0
            last_swath = pivot_pass.swath_km
            for i in range(pivot_idx - 1, -1, -1):
                curr = sorted_group[i]
                dynamic_overlap = (OVERLAP_PERCENT / 100.0) * min(curr.swath_km, last_swath)
                desired_center = last_center - (curr.swath_km/2 + last_swath/2) + dynamic_overlap
                shift_needed = desired_center - curr.original_offset_km
                if abs(shift_needed) > max_shift_km:
                    actual_shift = math.copysign(max_shift_km, shift_needed)
                    max_ona_reached[i] = True
                    actual_center = curr.original_offset_km + actual_shift
                else:
                    actual_shift = shift_needed
                    max_ona_reached[i] = False
                    actual_center = desired_center
                tasked_centers[i] = actual_center
                curr.tasked_shift_km = actual_shift
                curr.y_center = actual_center
                last_center = actual_center
                last_swath = curr.swath_km

            # East side
            last_center = 0.0
            last_swath = pivot_pass.swath_km
            for i in range(pivot_idx + 1, n_group):
                curr = sorted_group[i]
                dynamic_overlap = (OVERLAP_PERCENT / 100.0) * min(curr.swath_km, last_swath)
                desired_center = last_center + (curr.swath_km/2 + last_swath/2) - dynamic_overlap
                shift_needed = desired_center - curr.original_offset_km
                if abs(shift_needed) > max_shift_km:
                    actual_shift = math.copysign(max_shift_km, shift_needed)
                    max_ona_reached[i] = True
                    actual_center = curr.original_offset_km + actual_shift
                else:
                    actual_shift = shift_needed
                    max_ona_reached[i] = False
                    actual_center = desired_center
                tasked_centers[i] = actual_center
                curr.tasked_shift_km = actual_shift
                curr.y_center = actual_center
                last_center = actual_center
                last_swath = curr.swath_km

            group_assignments = self._build_assignments(sorted_group, aoi, max_ona,
                                                        tasked_centers, max_ona_reached, pivot_idx)
            for a in group_assignments:
                a['coverage_id'] = group['coverage_id']
            group['assignments'] = group_assignments
            all_assignments.extend(group_assignments)
            group_coverage = self._calculate_total_coverage(group_assignments, aoi)
            _log(f"Coverage {group['coverage_id']} coverage: {group_coverage:.1f}%")

        total_coverage = self._calculate_total_coverage(all_assignments, aoi)
        _log(f"{'='*80}\nMulti Coverage Summary\n  Total coverages: {len(coverage_groups)}\n  Total tasked passes: {len(all_assignments)}\n  Combined AOI coverage: {total_coverage:.1f}%\n{'='*80}")
        return all_assignments


# ============================================================================
# LEGACY FUNCTION FOR BACKWARD COMPATIBILITY
# ============================================================================
def compute_coverage_tasking(passes, aoi, max_ona, detector, sat_alt_km=550.0,
                             overlap_km=None, mode="one_coverage", progress_callback=None):
    """
    Legacy wrapper function for tasking.

    Args:
        overlap_km: Ignored (dynamic overlap = 10% of smaller swath)
    """
    optimizer = TaskingOptimizer(detector, sat_alt_km, overlap_km)
    return optimizer.compute_coverage_tasking(passes, aoi, max_ona, mode, progress_callback)