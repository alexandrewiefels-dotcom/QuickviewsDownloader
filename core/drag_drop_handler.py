# core/drag_drop_handler.py
import math
import streamlit as st
from geometry.calculations import great_circle_distance, calculate_bearing
from navigation_tracker import track_user_action


def handle_drag_drop(detector, aoi):
    """
    Handles drag & drop of tasked footprints using per-pass perpendicular direction.
    
    Args:
        detector: PassDetector instance
        aoi: Area of Interest polygon
    
    Returns:
        True if drag drop was processed, False otherwise
    """
    if not st.session_state.get('pending_drag_pass_id') or not st.session_state.get('drag_click_position'):
        return False

    pass_id = st.session_state.pending_drag_pass_id
    click_lat, click_lon = st.session_state.drag_click_position
    aoi_centroid = aoi.centroid

    for p in st.session_state.passes:
        if p.id == pass_id and hasattr(p, 'tasked_footprint') and p.tasked_footprint:
            track_user_action("drag_drop_start", {"pass_id": pass_id, "satellite": p.satellite_name})
            
            perp_bearing = (p.track_azimuth + 90) % 360
            dist_km = great_circle_distance(aoi_centroid.y, aoi_centroid.x, click_lat, click_lon)
            bearing_click = calculate_bearing(aoi_centroid.y, aoi_centroid.x, click_lat, click_lon)
            diff = (bearing_click - perp_bearing + 360) % 360
            if diff > 180:
                diff -= 360
            new_offset = dist_km * math.cos(math.radians(diff))
            max_shift_km = detector.ground_range_from_ona(550.0, st.session_state.max_ona)
            new_offset = max(-max_shift_km, min(max_shift_km, new_offset))
            shift = p.original_offset_km - new_offset
            required_ona = detector.ona_from_distance(550.0, abs(shift))
            
            if required_ona > st.session_state.max_ona + 0.1:
                st.warning(f"Cannot move {p.satellite_name}: required ONA {required_ona:.1f}° exceeds max {st.session_state.max_ona}°")
                track_user_action("drag_drop_failed", {"reason": "ONA exceeded"})
                break

            track_coords = list(p.ground_track.coords)
            new_footprint = detector.create_shifted_footprint_from_coords(track_coords, p.swath_km, shift)
            if new_footprint and not new_footprint.is_empty:
                p.tasked_footprint = new_footprint
                p.tasked_ona = required_ona
                p.current_offset_km = new_offset
                p.display_footprint = new_footprint
                if st.session_state.tasking_results:
                    for r in st.session_state.tasking_results:
                        if r['id'] == p.id:
                            r['footprint'] = new_footprint
                            r['required_ona'] = required_ona
                            r['offset_km'] = shift
                            r['y_center'] = new_offset
                            break
                st.success(f"Moved {p.satellite_name} to offset {new_offset:.1f} km (ONA: {required_ona:.1f}°)")
                st.session_state.map_key += 1
                track_user_action("drag_drop_success", {"satellite": p.satellite_name})
            else:
                st.error("Failed to create shifted footprint")
            break

    st.session_state.pending_drag_pass_id = None
    st.session_state.drag_click_position = None
    return True


def reset_drag_drop_state():
    """Reset the drag and drop session state variables"""
    st.session_state.pending_drag_pass_id = None
    st.session_state.drag_click_position = None