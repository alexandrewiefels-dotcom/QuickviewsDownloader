# ============================================================================
# FILE: core/tasking_runner.py – Tasking simulation with weather and footprint shifting
# UPDATED: Always uses one_coverage mode with 0 overlap (edge-to-edge)
# ============================================================================
import streamlit as st
from detection.daylight_filter import filter_daylight_passes
import sys
from pathlib import Path
import math

# Add parent directory to path to import tasking_optimizer
sys.path.insert(0, str(Path(__file__).parent.parent))


def run_tasking(passes, aoi, max_ona, detector, sat_alt_km=550.0, 
                fetch_weather=True, mode="one_coverage", overlap_km=35.0):
    """
    Run tasking simulation using sequential paving optimizer.
    Note: mode and overlap_km parameters are ignored; always one_coverage with 0 overlap.
    """
    # Force one_coverage mode and 0 overlap
    #mode = "one_coverage"
    overlap_km = 40.0
    
    if not passes or aoi is None:
        print("[TaskingRunner] No passes or AOI provided")
        return []
    
    print(f"[TaskingRunner] Starting with {len(passes)} passes, max_ona={max_ona}°")
    print(f"[TaskingRunner] Mode: {mode} (forced), Overlap: {overlap_km} km (edge-to-edge)")
    
    # Apply daylight filter if enabled
    daylight_filter = st.session_state.get('daylight_filter', "Daylight only (9am - 3pm local time)")
    print(f"[TaskingRunner] Daylight filter setting: {daylight_filter}")
    
    filtered_passes = passes.copy()
    if daylight_filter == "Daylight only (9am - 3pm local time)":
        original_count = len(filtered_passes)
        filtered_passes = filter_daylight_passes(filtered_passes, aoi, start_hour=9, end_hour=15)
        print(f"[TaskingRunner] Daylight filter: {original_count} -> {len(filtered_passes)} passes")
    
    if not filtered_passes:
        st.warning("No passes available after applying filters")
        return []
    
    # Import and run the sequential paving optimizer
    try:
        from tasking_optimizer import compute_coverage_tasking
        
        print("[TaskingRunner] Running sequential paving optimizer...")
        
        # Progress callback for optimizer
        def progress_callback(current, total, message):
            print(f"[Optimizer] {message} ({current}/{total})")
        
        # Run the optimizer with intuitive overlap (positive = overlap)
        assignments = compute_coverage_tasking(
            filtered_passes, aoi, max_ona, detector, 
            sat_alt_km=sat_alt_km,
            overlap_km=overlap_km,  # now 0
            mode=mode,               # now one_coverage
            progress_callback=progress_callback
        )
        
        print(f"[TaskingRunner] Optimizer returned {len(assignments)} assignments")
        
        # Fetch weather for each assignment if requested
        if fetch_weather:
            print("[TaskingRunner] Fetching weather data...")
            from data.weather import get_cloud_cover_at_intersection
            
            for a in assignments:
                if a.get('footprint') and not a['footprint'].is_empty:
                    try:
                        cloud = get_cloud_cover_at_intersection(a['footprint'], aoi, a['pass_time'])
                        a['cloud_cover'] = cloud
                        print(f"  {a['satellite']}: cloud cover = {cloud}%")
                    except Exception as e:
                        print(f"  {a['satellite']}: weather error - {e}")
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
                    
                    print(f"[TaskingRunner] Total combined coverage: {total_coverage_pct:.1f}%")
            except Exception as e:
                print(f"[TaskingRunner] Coverage calculation error: {e}")
        
        return assignments
        
    except ImportError as e:
        print(f"[TaskingRunner] Error importing optimizer: {e}")
        st.error("Tasking optimizer not available. Please check installation.")
        return []
    except Exception as e:
        print(f"[TaskingRunner] Optimizer error: {e}")
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
        print(f"[Weather] Error: {e}")
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
        print(f"[Coverage] Error: {e}")
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
