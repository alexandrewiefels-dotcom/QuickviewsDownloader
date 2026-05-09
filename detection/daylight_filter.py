# ============================================================================
# FILE: detection/daylight_filter.py
# Daylight filter using solar time (longitude-based approximation)
# No external timezone databases required
# ============================================================================
import logging
from datetime import datetime, timezone as dt_timezone
from datetime import timedelta

logger = logging.getLogger(__name__)


def get_local_solar_hour(pass_time_utc, aoi_centroid_lon):
    """
    Compute local solar hour (0-24) at given longitude.
    Local solar noon occurs when the sun is at its highest point.
    Formula: local_hour = UTC_hour + longitude/15   (mod 24)
    """
    # UTC time as decimal hours
    utc_hour = pass_time_utc.hour + pass_time_utc.minute / 60.0 + pass_time_utc.second / 3600.0
    # Longitude correction: each degree east adds 1/15 hour
    lon_correction = aoi_centroid_lon / 15.0
    local_hour = (utc_hour + lon_correction) % 24
    return local_hour

def get_local_time_political(pass_time, aoi):
    """
    Return local time string using political timezone approximation (round(lon/15)).
    This matches the CSV export method.
    """
    if aoi is None or aoi.is_empty:
        return pass_time.strftime("%Y-%m-%d %H:%M:%S")
    lon = aoi.centroid.x
    offset_hours = round(lon / 15)
    local_time = pass_time + timedelta(hours=offset_hours)
    return local_time.strftime("%Y-%m-%d %H:%M:%S")

def is_pass_in_daylight(pass_start_time, aoi_centroid_lat, aoi_centroid_lon,
                         start_hour=9, end_hour=15):
    """
    Check if a pass occurs during daylight hours (solar time).
    Latitude is ignored (only used for compatibility with existing calls).
    """
    if pass_start_time.tzinfo is None:
        pass_start_time = pass_start_time.replace(tzinfo=dt_timezone.utc)

    local_hour = get_local_solar_hour(pass_start_time, aoi_centroid_lon)
    is_daylight = start_hour <= local_hour <= end_hour

    if not is_daylight:
        logger.info(f"❌ FILTERED: UTC={pass_start_time.strftime('%H:%M')} "
                    f"→ Solar hour={local_hour:.2f} (range {start_hour}-{end_hour})")
        print(f"[DaylightFilter] ❌ FILTERED: UTC={pass_start_time.strftime('%H:%M')} -> Solar hour={local_hour:.1f}")
    else:
        logger.info(f"✅ KEPT: UTC={pass_start_time.strftime('%H:%M')} "
                    f"→ Solar hour={local_hour:.2f} (range {start_hour}-{end_hour})")
        print(f"[DaylightFilter] ✅ KEPT: UTC={pass_start_time.strftime('%H:%M')} -> Solar hour={local_hour:.1f}")

    return is_daylight


def filter_daylight_passes(passes, aoi, start_hour=9, end_hour=15):
    """
    Filter a list of passes to only those occurring during solar daylight hours.
    """
    if aoi is None or aoi.is_empty:
        logger.warning("No AOI provided for daylight filter, keeping all passes")
        return passes

    centroid = aoi.centroid
    centroid_lon = centroid.x

    print(f"\n{'='*60}")
    print(f"[DaylightFilter] AOI centroid longitude: {centroid_lon:.4f}°")
    print(f"[DaylightFilter] Using solar time (local hour = UTC + lon/15)")
    print(f"[DaylightFilter] Daylight hours: {start_hour}:00 to {end_hour}:00 solar time")
    print(f"[DaylightFilter] Total passes to filter: {len(passes)}")
    print(f"{'='*60}\n")

    filtered_passes = []
    kept_count = 0
    filtered_count = 0

    for p in passes:
        pass_time = getattr(p, 'start_time', None)
        if pass_time is None:
            pass_time = getattr(p, 'pass_time', None)

        if pass_time is None:
            logger.warning("Pass object has no time attribute, keeping pass")
            filtered_passes.append(p)
            kept_count += 1
            continue

        if is_pass_in_daylight(pass_time, centroid.y, centroid_lon, start_hour, end_hour):
            filtered_passes.append(p)
            kept_count += 1
        else:
            filtered_count += 1

    print(f"\n{'='*60}")
    print(f"[DaylightFilter] RESULT: kept {kept_count} of {len(passes)} passes (filtered {filtered_count})")

    if kept_count == 0 and len(passes) > 0:
        print(f"\n⚠️⚠️⚠️ [DaylightFilter] ALL {len(passes)} passes were filtered out! ⚠️⚠️⚠️")
        print(f"[DaylightFilter] Possible reasons:")
        print(f"   1. AOI longitude is such that all passes occur outside {start_hour}:00-{end_hour}:00 solar time")
        print(f"   2. The passes are at night (typical for sun-synchronous satellites in some seasons)")
        print(f"[DaylightFilter] AOI longitude: {centroid_lon:.4f}°")
        print(f"\n💡 SUGGESTION: Change 'Pass time filter' to 'All times' in the sidebar to see all passes.\n")

    print(f"{'='*60}\n")

    return filtered_passes


def get_local_time_str(pass_time, aoi):
    """
    Get local solar time string for display, showing only the hour (no minutes/seconds).
    Returns format: "YYYY-MM-DD HH:00 (solar)"
    """
    if aoi is None or aoi.is_empty:
        return pass_time.strftime("%Y-%m-%d %H:00")

    if pass_time.tzinfo is None:
        pass_time = pass_time.replace(tzinfo=dt_timezone.utc)

    centroid = aoi.centroid
    local_hour = get_local_solar_hour(pass_time, centroid.x)

    # Take only the integer hour (floor)
    h = int(local_hour)
    return f"{pass_time.year}-{pass_time.month:02d}-{pass_time.day:02d} {h:02d}:00 (solar)"


def get_local_hour(pass_time, aoi):
    """
    Get local solar hour as float.
    """
    if aoi is None or aoi.is_empty:
        return pass_time.hour + pass_time.minute / 60.0
    if pass_time.tzinfo is None:
        pass_time = pass_time.replace(tzinfo=dt_timezone.utc)
    return get_local_solar_hour(pass_time, aoi.centroid.x)


def get_utc_offset_str(aoi):
    """
    Return approximate UTC offset string based on longitude.
    Example: "UTC-4" for longitude -60°.
    """
    if aoi is None or aoi.is_empty:
        return "UTC"
    lon = aoi.centroid.x
    offset_hours = round(lon / 15)
    if offset_hours >= 0:
        return f"UTC+{offset_hours}"
    else:
        return f"UTC{offset_hours}"   # e.g., UTC-4
