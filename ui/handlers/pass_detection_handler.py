# ui/handlers/pass_detection_handler.py – Pass detection orchestration
# Centralizes the logic for running pass detection from the UI layer.

import streamlit as st
import logging
from datetime import datetime, timezone
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)


def run_pass_detection_from_sidebar(
    detector,
    selected_configs: List[Tuple],
    aoi,
    ts,
    start_date,
    end_date,
    max_ona: float,
    min_ona: float = 0.0,
    orbit_filter: str = "Both",
    daylight_filter: str = "All times",
    max_workers: int = 4,
    fetch_weather: bool = False,
) -> List:
    """
    Orchestrate pass detection from sidebar inputs.
    
    Args:
        detector: PassDetector instance
        selected_configs: List of (category, sat_name, cam_name, cam_info, sat_info) tuples
        aoi: Area of Interest polygon
        ts: Skyfield timescale
        start_date: Start date
        end_date: End date
        max_ona: Maximum off-nadir angle
        min_ona: Minimum off-nadir angle
        orbit_filter: "Both", "Ascending", or "Descending"
        daylight_filter: "All times" or "Daylight only (9am - 3pm local time)"
        max_workers: Max parallel workers for detection
        fetch_weather: Whether to fetch weather data
    
    Returns:
        List of SatellitePass objects
    """
    from core.pass_runner import run_pass_detection

    if not selected_configs:
        st.warning("No satellite configurations selected.")
        return []

    if aoi is None or aoi.is_empty:
        st.error("No Area of Interest (AOI) defined. Please upload or draw an AOI.")
        return []

    # Run detection
    progress_bar = st.progress(0, text="🔍 Searching for satellite passes...")
    start_time = datetime.now(timezone.utc)

    try:
        all_passes, _ = run_pass_detection(
            detector=detector,
            selected_configs=selected_configs,
            aoi=aoi,
            ts=ts,
            start_date=start_date,
            end_date=end_date,
            max_ona=max_ona,
            progress_bar=progress_bar,
            start_time=start_time,
            max_workers=max_workers,
            fetch_weather=fetch_weather,
        )
    except Exception as e:
        logger.exception(f"Pass detection failed: {e}")
        st.error(f"Pass detection failed: {str(e)}")
        return []
    finally:
        progress_bar.empty()

    # Apply orbit direction filter
    if orbit_filter != "Both":
        all_passes = [p for p in all_passes if p.orbit_direction == orbit_filter]

    # Apply minimum ONA filter
    if min_ona > 0:
        all_passes = [p for p in all_passes if p.min_ona >= min_ona]

    # Apply daylight filter
    if daylight_filter == "Daylight only (9am - 3pm local time)":
        from detection.daylight_filter import filter_daylight_passes
        original_count = len(all_passes)
        all_passes = filter_daylight_passes(all_passes, aoi, start_hour=9, end_hour=15)
        filtered_count = original_count - len(all_passes)
        if filtered_count > 0:
            st.info(f"🌙 Daylight filter removed {filtered_count} night-time passes.")

    # Summary — always show, even for 0 passes
    elapsed = (datetime.now(timezone.utc) - start_time).total_seconds()
    if all_passes:
        st.success(f"✅ Search complete: **{len(all_passes)} passes** found across "
                   f"{len(set(p.satellite_name for p in all_passes))} satellites "
                   f"in **{elapsed:.1f}s**.")
    else:
        st.info(f"🔍 Search complete: **0 passes** found in **{elapsed:.1f}s**. "
                "Try expanding the date range, increasing max ONA, or selecting more satellites.")

    return all_passes
