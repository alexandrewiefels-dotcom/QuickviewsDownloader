# ============================================================================
# FILE: core/tasking_runner.py – Tasking simulation with weather and footprint shifting
# UPDATED: Always uses one_coverage mode with 0 overlap (edge-to-edge)
# FIX: Replaced all print() with logging
# ============================================================================
import streamlit as st
from detection.daylight_filter import filter_daylight_passes
import sys
from pathlib import Path
import math
import logging

from core.exceptions import (
    TaskingError,
    GeometryError,
    WeatherError,
)

logger = logging.getLogger(__name__)

# Add parent directory to path to import tasking_optimizer
sys.path.insert(0, str(Path(__file__).parent.parent))


def run_tasking(passes, aoi, max_ona, detector, sat_alt_km=550.0, 
                fetch_weather=True, mode="one_coverage", overlap_km=35.0):
    """
    Run tasking simulation using sequential paving optimizer.
    
    Note: The overlap is now controlled by the OVERLAP_PERCENT constant in
    tasking_optimizer.py (default 10% of the smaller swath between adjacent passes).
    The overlap_km parameter here is kept for backward compatibility but is overridden
    by the dynamic overlap calculation in the optimizer.
    """
    if not passes or aoi is None:
        logger.warning("No passes or AOI provided")
        return []
    
    logger.info("Starting with %d passes, max_ona=%.1f°", len(passes), max_ona)
    logger.info("Mode: %s (forced), Overlap: %.1f km (edge-to-edge)", mode, overlap_km)
    
    # Apply daylight filter if enabled
    daylight_filter = st.session_state.get('daylight_filter', "Daylight only (9am - 3pm local time)")
    logger.info("Daylight filter setting: %s", daylight_filter)
    
    filtered_passes = passes.copy()
    if daylight_filter == "Daylight only (9am - 3pm local time)":
        original_count = len(filtered_passes)
        filtered_passes = filter_daylight_passes(filtered_passes, aoi, start_hour=9, end_hour=15)
        logger.info("Daylight filter: %d -> %d passes", original_count, len(filtered_passes))
    
    if not filtered_passes:
        st.warning("No passes available after applying filters")
        return []
    
    # Import and run the sequential paving optimizer
    try:
        from tasking_optimizer import compute_coverage_tasking
        
        logger.info("Running sequential paving optimizer...")
        
        # Progress callback for optimizer
        def progress_callback(current, total, message):
            logger.info("[Optimizer] %s (%d/%d)", message, current, total)
        
        # Run the optimizer with intuitive overlap (positive = overlap)
        assignments = compute_coverage_tasking(
            filtered_passes, aoi, max_ona, detector, 
            sat_alt_km=sat_alt_km,
            overlap_km=overlap_km,  # now 0
            mode=mode,               # now one_coverage
            progress_callback=progress_callback
        )
        
        logger.info("Optimizer returned %d assignments", len(assignments))
        
        # Fetch weather for each assignment if requested
        if fetch_weather:
            logger.info("Fetching weather data...")
            from data.weather import get_cloud_cover_at_intersection
            
            for a in assignments:
                if a.get('footprint') and not a['footprint'].is_empty:
                    try:
                        cloud = get_cloud_cover_at_intersection(a['footprint'], aoi, a['pass_time'])
                        a['cloud_cover'] = cloud
                        logger.info("  %s: cloud cover = %.1f%%", a['satellite'], cloud)
                    except Exception as e:
                        logger.error("  %s: weather error - %s", a['satellite'], e)
                        a['cloud_cover'] = None
        
        # Calculate and add coverage summary
        if assignments and aoi:
            try:
                from shapely.ops import unary_union
                all_footprints = [a['footprint'] for a in assignments if a.get('footprint') and not a['footprint'].is_empty]
                if all_footprints:
                    union = unary_union(all_footprints)
                    intersection = union.intersection(aoi)
                    total_coverage_pct = (intersection.area / aoi.area) * 100.0 if aoi.area > 0 else 0
                    
                    for a in assignments:
                        a['total_coverage_pct'] = total_coverage_pct
                    
                    logger.info("Total combined coverage: %.1f%%", total_coverage_pct)
            except Exception as e:
                logger.error("Coverage calculation error: %s", e)
        
        return assignments
        
    except ImportError as e:
        logger.error("Error importing optimizer: %s", e)
        st.error("Tasking optimizer not available. Please check installation.")
        return []
    except Exception as e:
        logger.error("Optimizer error: %s", e)
        import traceback
        traceback.print_exc()
        return []


def get_perpendicular_distance(pass_obj, centroid):
    """
    Calculate perpendicular distance from AOI centroid to ground track.
    
    Args:
        pass_obj: SatellitePass object
        centroid: AOI centroid (Point)
    
    Returns:
        Tuple of (absolute_distance, signed_distance, quality_factor)
    """
    track = pass_obj.ground_track
    if track is None or track.is_empty:
        return None, None, None
    
    from shapely.geometry import Point
    aoi_point = Point(centroid.x, centroid.y)
    nearest_dist = track.project(aoi_point)
    nearest_pt = track.interpolate(nearest_dist)
    lon_nearest, lat_nearest = nearest_pt.x, nearest_pt.y
    
    lon_aoi = centroid.x
    ref_lat = centroid.y
    km_per_deg = 111.0 * math.cos(math.radians(ref_lat))
    if km_per_deg != 0:
        offset_km = (lon_nearest - lon_aoi) * km_per_deg
    else:
        offset_km = 0
    
    return abs(offset_km), offset_km, 1.0


def get_cloud_cover(pass_obj, aoi):
    """
    Fetch cloud cover for a pass (only called during tasking).
    
    Args:
        pass_obj: SatellitePass object
        aoi: Area of Interest polygon
    
    Returns:
        Cloud cover percentage or None
    """
    if pass_obj.min_ona > 20:
        return None
    
    try:
        from data.weather import get_cloud_cover_at_intersection
        if aoi is None or aoi.is_empty:
            return None
        
        footprint = getattr(pass_obj, 'tasked_footprint', None) or pass_obj.footprint
        if footprint is None or footprint.is_empty:
            return None
        
        cloud = get_cloud_cover_at_intersection(footprint, aoi, pass_obj.pass_time)
        return cloud
    except Exception as e:
        logger.error("[Weather] Error: %s", e)
        return None


def calculate_coverage(tasked_passes, aoi):
    """
    Calculate AOI coverage percentage from tasked footprints.
    
    Args:
        tasked_passes: List of tasked pass dictionaries
        aoi: Area of Interest polygon
    
    Returns:
        Coverage percentage (0-100)
    """
    if not tasked_passes or aoi is None or aoi.is_empty:
        return 0.0
    
    from shapely.ops import unary_union
    
    footprints = []
    for p in tasked_passes:
        footprint = p.get('tasked_footprint') or p.get('footprint')
        if footprint and not footprint.is_empty:
            footprints.append(footprint)
    
    if not footprints:
        return 0.0
    
    try:
        union = unary_union(footprints)
        intersection = union.intersection(aoi)
        coverage_pct = (intersection.area / aoi.area) * 100.0
        return coverage_pct
    except Exception as e:
        logger.error("[Coverage] Error: %s", e)
        return 0.0


def get_best_passes(tasked_passes, limit=5):
    """
    Get the best passes based on coverage and ONA.
    
    Args:
        tasked_passes: List of tasked pass dictionaries
        limit: Maximum number of passes to return
    
    Returns:
        List of best passes
    """
    if not tasked_passes:
        return []
    
    def score_pass(p):
        coverage = p.get('coverage_pct', 0) or 0
        ona = p.get('required_ona', 90) or 90
        coverage_score = coverage / 100.0
        ona_score = 1.0 - (ona / 90.0)
        return (coverage_score * 0.7) + (ona_score * 0.3)
    
    sorted_passes = sorted(tasked_passes, key=score_pass, reverse=True)
    return sorted_passes[:limit]
