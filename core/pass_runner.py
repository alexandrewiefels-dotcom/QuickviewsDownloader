# ============================================================================
# FILE: core/pass_runner.py – COMPLETE WITH PRE-FILTERING FOR VALID TLES
# FIX: Show warning if many satellites are skipped
# ============================================================================
import time
from datetime import datetime, timedelta, timezone
import streamlit as st
from detection.daylight_filter import filter_daylight_passes
from concurrent.futures import ThreadPoolExecutor, as_completed
import logging
import traceback

logger = logging.getLogger(__name__)

def process_single_satellite(detector, sat_config, aoi, ts, start_dt, end_dt, max_ona, fetch_weather=False):
    category_name, sat_name, cam_name, cam_info, sat_info = sat_config
    norad_id = sat_info["norad"]
    
    print(f"\n[PassRunner] === Processing {sat_name} (NORAD {norad_id}) ===")
    tle_result = detector.tle_fetcher.fetch(norad_id, force_refresh=False)
    
    if tle_result is None:
        print(f"[PassRunner] ⚠️ No valid TLE for {sat_name} (NORAD {norad_id}) – skipping")
        return []
    
    if not isinstance(tle_result, tuple):
        print(f"[PassRunner] ❌ TLE is not a tuple for {sat_name}, type={type(tle_result)}")
        return []
    
    try:
        if len(tle_result) == 2:
            line1, line2 = tle_result
        else:
            print(f"[PassRunner] ❌ TLE tuple has {len(tle_result)} elements, expected 2")
            return []
    except Exception as e:
        print(f"[PassRunner] ❌ Failed to unpack TLE: {e}")
        return []
    
    if not line1 or not line2:
        print(f"[PassRunner] ❌ Empty TLE lines for {sat_name}")
        return []
    
    if len(line1) < 69 or len(line2) < 69:
        print(f"[PassRunner] ❌ TLE lines too short for {sat_name}")
        return []
    
    if '097.5000' in line2 and '000.0000' in line2:
        print(f"[PassRunner] ⚠️ TLE for {sat_name} is a generated placeholder, skipping")
        return []
    
    print(f"[PassRunner] ✅ Valid TLE for {sat_name}")
    print(f"[PassRunner]    Mean motion: {line2[52:63].strip()} rev/day")
    print(f"[PassRunner]    AOI centroid: ({aoi.centroid.y:.2f}, {aoi.centroid.x:.2f})")
    
    try:
        passes, opportunities = detector.detect_passes(
            sat_name, norad_id, sat_info, cam_name, cam_info,
            line1, line2, aoi, start_dt, end_dt, max_ona,
            fetch_weather=fetch_weather
        )
        print(f"[PassRunner] Found {len(passes)} passes for {sat_name}")
        for i, p in enumerate(passes[:3]):
            pass_time = getattr(p, 'pass_time', None)
            if pass_time:
                print(f"[PassRunner]   Pass {i+1}: {pass_time} UTC, Actual ONA={p.min_ona:.1f}°, Filter ONA={max_ona}°, dir={p.orbit_direction}")
        return passes
    except Exception as e:
        print(f"[PassRunner] ❌ Error in detect_passes for {sat_name}: {e}")
        traceback.print_exc()
        return []

def run_pass_detection(detector, selected_configs, aoi, ts, start_date, end_date, 
                       max_ona, progress_bar=None, start_time=None, max_workers=4,
                       fetch_weather=False, progress_callback=None):
    start_dt = datetime(start_date.year, start_date.month, start_date.day, 0, 0, 0, tzinfo=timezone.utc)
    end_dt = datetime(end_date.year, end_date.month, end_date.day, 23, 59, 59, tzinfo=timezone.utc)
    
    print(f"\n[PassRunner] Starting pass detection")
    print(f"[PassRunner] Date range: {start_dt} to {end_dt}")
    print(f"[PassRunner] Total satellites selected: {len(selected_configs)}")
    print(f"[PassRunner] Max ONA (filter): {max_ona}°")
    print(f"[PassRunner] Using {max_workers} parallel workers")
    print(f"[PassRunner] Fetch weather: {fetch_weather}")
    
    valid_configs = []
    skipped_count = 0
    for config in selected_configs:
        category_name, sat_name, cam_name, cam_info, sat_info = config
        norad = sat_info["norad"]
        tle = detector.tle_fetcher.fetch(norad, force_refresh=False)
        if tle is None:
            print(f"[PassRunner] ⚠️ Skipping {sat_name} (NORAD {norad}) – TLE missing or generated")
            skipped_count += 1
            continue
        if len(tle) == 2 and '097.5000' in tle[1] and '000.0000' in tle[1]:
            print(f"[PassRunner] ⚠️ Skipping {sat_name} (NORAD {norad}) – generated placeholder TLE")
            skipped_count += 1
            continue
        valid_configs.append(config)
    
    print(f"[PassRunner] Valid TLEs: {len(valid_configs)} / {len(selected_configs)} (skipped {skipped_count})")
    
    # FIX: Warn user if many satellites are skipped
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
    
    print(f"[PassRunner] Daylight filter setting: {daylight_filter_setting}")
    print(f"[PassRunner] Orbit filter setting: {orbit_filter}")
    
    all_passes = []
    total_configs = len(valid_configs)
    
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
                    print(f"[PassRunner] ✅ {sat_name}: {len(passes)} passes")
                else:
                    print(f"[PassRunner] ⚠️ {sat_name}: No passes found")
            except Exception as e:
                print(f"[PassRunner] ❌ Error processing {sat_name}: {e}")
                traceback.print_exc()
            completed += 1
            if progress_bar:
                progress = completed / total_configs if total_configs > 0 else 0
                progress_bar.progress(progress, text=f"Processed {completed}/{total_configs} satellites...")
            if progress_callback:
                overall_progress = 5 + int((completed / total_configs) * 85) if total_configs > 0 else 5
                progress_callback(overall_progress, f"Processed {completed}/{total_configs} satellites...")
    
    all_passes.sort(key=lambda p: getattr(p, 'pass_time', datetime.min))
    print(f"\n[PassRunner] Total passes before any filter: {len(all_passes)}")
    
    if progress_callback:
        progress_callback(92, f"Applying filters to {len(all_passes)} passes...")
    
    if all_passes:
        print("[PassRunner] Sample passes BEFORE filters (with actual ONA):")
        for i, p in enumerate(all_passes[:5]):
            pass_time = getattr(p, 'pass_time', None)
            orbit_dir = getattr(p, 'orbit_direction', 'Unknown')
            if pass_time:
                print(f"  Pass {i+1}: {pass_time} UTC | Actual ONA={p.min_ona:.1f}° | Filter ONA={max_ona}° | Direction={orbit_dir}")
    else:
        print("[PassRunner] WARNING: No passes found before any filters!")
        print("[PassRunner] Possible reasons:")
        print("  1. Satellites don't pass over the AOI in the selected date range")
        print("  2. TLE data is outdated or incorrect")
        print("  3. Max ONA filter is too restrictive")
        print("  4. AOI is too small or in a location with no satellite coverage")
    
    if orbit_filter != 'Both':
        original_count = len(all_passes)
        filtered_passes = [p for p in all_passes if getattr(p, 'orbit_direction', '') == orbit_filter]
        all_passes = filtered_passes
        print(f"[PassRunner] Orbit filter ({orbit_filter}): {original_count} -> {len(all_passes)} passes")
    
    if daylight_filter_setting == "Daylight only (9am - 3pm local time)":
        original_count = len(all_passes)
        if aoi and not aoi.is_empty:
            centroid = aoi.centroid
            print(f"\n[PassRunner] ========== DAYLIGHT FILTER DEBUG ==========")
            print(f"[PassRunner] AOI centroid: ({centroid.y:.4f}, {centroid.x:.4f})")
            lon = centroid.x
            utc_offset_hours = round(lon / 15)
            sign = '+' if utc_offset_hours >= 0 else '-'
            print(f"[PassRunner] Approximate UTC offset: UTC{sign}{abs(utc_offset_hours)} (from longitude)")
            print(f"[PassRunner] Daylight hours: 9:00 to 15:00 solar time")
        if original_count > 0:
            print(f"\n[PassRunner] Sample passes BEFORE daylight filter (solar time):")
            for i, p in enumerate(all_passes[:5]):
                pass_time = getattr(p, 'start_time', getattr(p, 'pass_time', None))
                if pass_time and aoi:
                    from detection.daylight_filter import get_local_solar_hour
                    solar_hour = get_local_solar_hour(pass_time, aoi.centroid.x)
                    print(f"  Pass {i+1}: UTC={pass_time.strftime('%H:%M')} | Solar hour={solar_hour:.1f} | ONA={p.min_ona:.1f}°")
            all_passes = filter_daylight_passes(all_passes, aoi, start_hour=9, end_hour=15)
            print(f"\n[PassRunner] Daylight filter result: {original_count} -> {len(all_passes)} passes (filtered out {original_count - len(all_passes)})")
            if all_passes:
                print(f"\n[PassRunner] Sample passes AFTER daylight filter:")
                for i, p in enumerate(all_passes[:5]):
                    pass_time = getattr(p, 'start_time', getattr(p, 'pass_time', None))
                    if pass_time and aoi:
                        from detection.daylight_filter import get_local_solar_hour
                        solar_hour = get_local_solar_hour(pass_time, aoi.centroid.x)
                        print(f"  Pass {i+1}: UTC={pass_time.strftime('%H:%M')} | Solar hour={solar_hour:.1f} | ONA={p.min_ona:.1f}°")
            else:
                print(f"\n[PassRunner] ⚠️ ALL {original_count} passes were filtered out by daylight filter!")
                print(f"[PassRunner] SUGGESTION: Change 'Pass time filter' to 'All times' in the sidebar.")
            print(f"\n[PassRunner] ==============================================\n")
        else:
            print(f"[PassRunner] Daylight filter: skipped (no passes to filter)")
    
    all_passes.sort(key=lambda p: getattr(p, 'pass_time', datetime.min))
    print(f"\n[PassRunner] FINAL: {len(all_passes)} passes detected")
    
    if all_passes:
        print(f"\n[PassRunner] FINAL PASSES SUMMARY (Actual ONA values):")
        for i, p in enumerate(all_passes[:10]):
            pass_time = getattr(p, 'pass_time', None)
            if pass_time:
                print(f"  {i+1}: {pass_time} UTC | Satellite={p.satellite_name} | Actual ONA={p.min_ona:.1f}° | Direction={p.orbit_direction}")
        if len(all_passes) > 10:
            print(f"  ... and {len(all_passes) - 10} more passes")
    
    if start_time:
        elapsed = time.time() - start_time
        print(f"\n[PassRunner] Detection completed in {elapsed:.1f} seconds")
    
    if progress_callback:
        progress_callback(100, f"✅ Detection complete: {len(all_passes)} passes found")
    
    return all_passes