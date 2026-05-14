# ============================================================================
# FILE: core/pass_runner.py – COMPLETE WITH PRE-FILTERING FOR VALID TLES
# FIX: Show warning if many satellites are skipped
# FIX: Replaced all print() with logging
# ============================================================================
import time
from datetime import datetime, timedelta, timezone
import streamlit as st
from detection.daylight_filter import filter_daylight_passes
from concurrent.futures import ThreadPoolExecutor, as_completed
import logging
import traceback

from core.exceptions import (
    TLEError,
    TLENotFoundError,
    TLEFetchError,
    PassDetectionError,
    GeometryError,
)

logger = logging.getLogger(__name__)


def process_single_satellite(detector, sat_config, aoi, ts, start_dt, end_dt, max_ona, fetch_weather=False):
    category_name, sat_name, cam_name, cam_info, sat_info = sat_config
    norad_id = sat_info["norad"]
    
    logger.info("=== Processing %s (NORAD %d) ===", sat_name, norad_id)
    tle_result = detector.tle_fetcher.fetch(norad_id, force_refresh=False)
    
    if tle_result is None:
        logger.warning("No valid TLE for %s (NORAD %d) – skipping", sat_name, norad_id)
        return []
    
    if not isinstance(tle_result, tuple):
        logger.error("TLE is not a tuple for %s, type=%s", sat_name, type(tle_result))
        return []
    
    try:
        if len(tle_result) == 2:
            line1, line2 = tle_result
        else:
            logger.error("TLE tuple has %d elements, expected 2", len(tle_result))
            return []
    except Exception as e:
        logger.error("Failed to unpack TLE: %s", e)
        return []
    
    if not line1 or not line2:
        logger.error("Empty TLE lines for %s", sat_name)
        return []
    
    if len(line1) < 69 or len(line2) < 69:
        logger.error("TLE lines too short for %s", sat_name)
        return []
    
    if '097.5000' in line2 and '000.0000' in line2:
        logger.warning("TLE for %s is a generated placeholder, skipping", sat_name)
        return []
    
    logger.info("Valid TLE for %s", sat_name)
    logger.info("   Mean motion: %s rev/day", line2[52:63].strip())
    logger.info("   AOI centroid: (%.2f, %.2f)", aoi.centroid.y, aoi.centroid.x)
    
    try:
        passes, opportunities = detector.detect_passes(
            sat_name, norad_id, sat_info, cam_name, cam_info,
            line1, line2, aoi, start_dt, end_dt, max_ona,
            fetch_weather=fetch_weather
        )
        logger.info("Found %d passes for %s", len(passes), sat_name)
        for i, p in enumerate(passes[:3]):
            pass_time = getattr(p, 'pass_time', None)
            if pass_time:
                logger.info("  Pass %d: %s UTC, Actual ONA=%.1f°, Filter ONA=%.1f°, dir=%s",
                           i+1, pass_time, p.min_ona, max_ona, p.orbit_direction)
        return passes
    except Exception as e:
        logger.error("Error in detect_passes for %s: %s", sat_name, e)
        traceback.print_exc()
        return []


def run_pass_detection(detector, selected_configs, aoi, ts, start_date, end_date, 
                       max_ona, progress_bar=None, start_time=None, max_workers=4,
                       fetch_weather=False, progress_callback=None):
    start_dt = datetime(start_date.year, start_date.month, start_date.day, 0, 0, 0, tzinfo=timezone.utc)
    end_dt = datetime(end_date.year, end_date.month, end_date.day, 23, 59, 59, tzinfo=timezone.utc)
    
    logger.info("Starting pass detection")
    logger.info("Date range: %s to %s", start_dt, end_dt)
    logger.info("Total satellites selected: %d", len(selected_configs))
    logger.info("Max ONA (filter): %.1f°", max_ona)
    logger.info("Using %d parallel workers", max_workers)
    logger.info("Fetch weather: %s", fetch_weather)
    
    t_prefilter = time.time()
    valid_configs = []
    skipped_count = 0
    for config in selected_configs:
        category_name, sat_name, cam_name, cam_info, sat_info = config
        norad = sat_info["norad"]
        tle = detector.tle_fetcher.fetch(norad, force_refresh=False)
        if tle is None:
            logger.warning("Skipping %s (NORAD %d) – TLE missing or generated", sat_name, norad)
            skipped_count += 1
            continue
        if len(tle) == 2 and '097.5000' in tle[1] and '000.0000' in tle[1]:
            logger.warning("Skipping %s (NORAD %d) – generated placeholder TLE", sat_name, norad)
            skipped_count += 1
            continue
        valid_configs.append(config)
    
    logger.info("Valid TLEs: %d / %d (skipped %d) — pre-filter took %.1fs",
                len(valid_configs), len(selected_configs), skipped_count, time.time() - t_prefilter)
    
    # Warn user if many satellites are skipped
    if skipped_count > len(selected_configs) / 2:
        st.warning(f"⚠️ {skipped_count} out of {len(selected_configs)} selected satellites have no valid TLE data. "
                   "Passes will only be calculated for the remaining satellites. "
                   "Check your internet connection and API keys (Space-Track / N2YO).")
    
    if not valid_configs:
        st.error("No satellites have valid TLE data. Cannot run detection.")
        return []
    
    if progress_callback:
        progress_callback(5, f"Valid TLEs: {len(valid_configs)} satellites. Starting detection...")
    
    detector._verbose_logging = False
    daylight_filter_setting = st.session_state.get('daylight_filter', "Daylight only (9am - 3pm local time)")
    orbit_filter = st.session_state.get('orbit_filter', 'Both')
    
    logger.info("Daylight filter setting: %s", daylight_filter_setting)
    logger.info("Orbit filter setting: %s", orbit_filter)
    
    all_passes = []
    total_configs = len(valid_configs)
    
    t_detection = time.time()
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_config = {
            executor.submit(process_single_satellite, detector, config, aoi, ts, start_dt, end_dt, max_ona, fetch_weather): config
            for config in valid_configs
        }
        completed = 0
        for future in as_completed(future_to_config):
            config = future_to_config[future]
            sat_name = config[1]
            try:
                passes = future.result(timeout=60)
                if passes:
                    all_passes.extend(passes)
                    logger.info("✅ %s: %d passes", sat_name, len(passes))
                else:
                    logger.warning("⚠️ %s: No passes found", sat_name)
            except Exception as e:
                logger.error("Error processing %s: %s", sat_name, e)
                traceback.print_exc()
            completed += 1
            if progress_bar:
                progress = completed / total_configs if total_configs > 0 else 0
                progress_bar.progress(progress, text=f"Processed {completed}/{total_configs} satellites...")
            if progress_callback:
                overall_progress = 5 + int((completed / total_configs) * 85) if total_configs > 0 else 5
                progress_callback(overall_progress, f"Processed {completed}/{total_configs} satellites...")
    
    detection_elapsed = time.time() - t_detection
    logger.info("Parallel detection took %.1fs for %d satellites", detection_elapsed, total_configs)
    
    all_passes.sort(key=lambda p: getattr(p, 'pass_time', datetime.min))
    logger.info("Total passes before any filter: %d", len(all_passes))
    
    if progress_callback:
        progress_callback(92, f"Applying filters to {len(all_passes)} passes...")
    
    if all_passes:
        logger.info("Sample passes BEFORE filters (with actual ONA):")
        for i, p in enumerate(all_passes[:5]):
            pass_time = getattr(p, 'pass_time', None)
            orbit_dir = getattr(p, 'orbit_direction', 'Unknown')
            if pass_time:
                logger.info("  Pass %d: %s UTC | Actual ONA=%.1f° | Filter ONA=%.1f° | Direction=%s",
                           i+1, pass_time, p.min_ona, max_ona, orbit_dir)
    else:
        logger.warning("No passes found before any filters!")
        logger.warning("Possible reasons:")
        logger.warning("  1. Satellites don't pass over the AOI in the selected date range")
        logger.warning("  2. TLE data is outdated or incorrect")
        logger.warning("  3. Max ONA filter is too restrictive")
        logger.warning("  4. AOI is too small or in a location with no satellite coverage")
    
    if orbit_filter != 'Both':
        original_count = len(all_passes)
        filtered_passes = [p for p in all_passes if getattr(p, 'orbit_direction', '') == orbit_filter]
        all_passes = filtered_passes
        logger.info("Orbit filter (%s): %d -> %d passes", orbit_filter, original_count, len(all_passes))
    
    if daylight_filter_setting == "Daylight only (9am - 3pm local time)":
        original_count = len(all_passes)
        if aoi and not aoi.is_empty:
            centroid = aoi.centroid
            logger.info("========== DAYLIGHT FILTER DEBUG ==========")
            logger.info("AOI centroid: (%.4f, %.4f)", centroid.y, centroid.x)
            lon = centroid.x
            utc_offset_hours = round(lon / 15)
            sign = '+' if utc_offset_hours >= 0 else '-'
            logger.info("Approximate UTC offset: UTC%s%d (from longitude)", sign, abs(utc_offset_hours))
            logger.info("Daylight hours: 9:00 to 15:00 solar time")
        if original_count > 0:
            logger.info("Sample passes BEFORE daylight filter (solar time):")
            for i, p in enumerate(all_passes[:5]):
                pass_time = getattr(p, 'start_time', getattr(p, 'pass_time', None))
                if pass_time and aoi:
                    from detection.daylight_filter import get_local_solar_hour
                    solar_hour = get_local_solar_hour(pass_time, aoi.centroid.x)
                    logger.info("  Pass %d: UTC=%s | Solar hour=%.1f | ONA=%.1f°",
                               i+1, pass_time.strftime('%H:%M'), solar_hour, p.min_ona)
            all_passes = filter_daylight_passes(all_passes, aoi, start_hour=9, end_hour=15)
            logger.info("Daylight filter result: %d -> %d passes (filtered out %d)",
                       original_count, len(all_passes), original_count - len(all_passes))
            if all_passes:
                logger.info("Sample passes AFTER daylight filter:")
                for i, p in enumerate(all_passes[:5]):
                    pass_time = getattr(p, 'start_time', getattr(p, 'pass_time', None))
                    if pass_time and aoi:
                        from detection.daylight_filter import get_local_solar_hour
                        solar_hour = get_local_solar_hour(pass_time, aoi.centroid.x)
                        logger.info("  Pass %d: UTC=%s | Solar hour=%.1f | ONA=%.1f°",
                                   i+1, pass_time.strftime('%H:%M'), solar_hour, p.min_ona)
            else:
                logger.warning("ALL %d passes were filtered out by daylight filter!", original_count)
                logger.warning("SUGGESTION: Change 'Pass time filter' to 'All times' in the sidebar.")
            logger.info("==============================================")
        else:
            logger.info("Daylight filter: skipped (no passes to filter)")
    
    all_passes.sort(key=lambda p: getattr(p, 'pass_time', datetime.min))
    logger.info("FINAL: %d passes detected", len(all_passes))
    
    if all_passes:
        logger.info("FINAL PASSES SUMMARY (Actual ONA values):")
        for i, p in enumerate(all_passes[:10]):
            pass_time = getattr(p, 'pass_time', None)
            if pass_time:
                logger.info("  %d: %s UTC | Satellite=%s | Actual ONA=%.1f° | Direction=%s",
                           i+1, pass_time, p.satellite_name, p.min_ona, p.orbit_direction)
        if len(all_passes) > 10:
            logger.info("  ... and %d more passes", len(all_passes) - 10)
    
    if start_time:
        elapsed = time.time() - start_time
        logger.info("Detection completed in %.1f seconds", elapsed)
        # Log timing breakdown
        logger.info("  ⏱ Timing breakdown:")
        logger.info("    TLE pre-filter:  %.1fs", t_prefilter - start_time)
        logger.info("    Parallel detection: %.1fs", detection_elapsed)
        logger.info("    Post-processing: %.1fs", time.time() - t_detection - detection_elapsed)
        logger.info("    Total: %.1fs", elapsed)
    
    if progress_callback:
        progress_callback(100, f"✅ Detection complete: {len(all_passes)} passes found")
    
    return all_passes
