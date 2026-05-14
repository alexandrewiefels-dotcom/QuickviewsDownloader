#!/usr/bin/env python3
# ============================================================================
# FILE: force_download_tles.py – Space‑Track primary bulk download for all satellites
# Uses the new SpaceTrackBulkFetcher (once-per-hour, off-peak timing, bulk URL).
# ============================================================================
import sys
import time
import json
import requests
import threading
import shutil
import argparse
import os
from pathlib import Path
from datetime import datetime, timedelta
sys.path.insert(0, str(Path(__file__).parent))

from data.tle_fetcher import (
    TLEFetcher, CACHE_FILE, save_last_refresh, _update_supplier_stats,
    should_skip_norad, record_failed_attempt, reset_failed_attempts,
    N2YO_BULK_DELAY, CELESTRAK_INDIVIDUAL_DELAY, log_update_session,
)
from data.space_track_fetcher import SpaceTrackBulkFetcher
from config.satellites import SATELLITES

# Guard against concurrent force-download runs
_force_download_lock = threading.Lock()
_force_download_running = False

# Load credentials — try Streamlit secrets first, then env vars, then None
SPACE_TRACK_USER = None
SPACE_TRACK_PASSWORD = None
N2YO_API_KEY = None

try:
    import streamlit as st
    SPACE_TRACK_USER = st.secrets.get("SPACE_TRACK_USER")
    SPACE_TRACK_PASSWORD = st.secrets.get("SPACE_TRACK_PASSWORD")
    N2YO_API_KEY = st.secrets.get("N2YO_API_KEY")
except (ImportError, FileNotFoundError, KeyError):
    # Running outside Streamlit context — try environment variables
    SPACE_TRACK_USER = os.environ.get("SPACE_TRACK_USER")
    SPACE_TRACK_PASSWORD = os.environ.get("SPACE_TRACK_PASSWORD")
    N2YO_API_KEY = os.environ.get("N2YO_API_KEY")

# --------------------------------------------------------------------------
# Helper: get all NORADs from config
# --------------------------------------------------------------------------
def get_all_norads() -> list:
    norads = []
    for category in SATELLITES.values():
        for sat_info in category.values():
            norad = sat_info.get("norad")
            if norad:
                norads.append(norad)
    return list(dict.fromkeys(norads))  # unique

# --------------------------------------------------------------------------
# Main force download routine
# --------------------------------------------------------------------------
def force_download_all_tls():
    """
    1. Attempt Space‑Track bulk download via SpaceTrackBulkFetcher (once-per-hour).
    2. For missing NORADs, fallback to Celestrak individual.
    3. If still missing, try N2YO.
    4. Generate approximate TLEs as last resort.
    """
    global _force_download_running
    with _force_download_lock:
        if _force_download_running:
            print("[Force Download] Already in progress – skipping duplicate run.")
            return False
        _force_download_running = True
    try:
        return _force_download_all_tls_inner()
    finally:
        with _force_download_lock:
            _force_download_running = False


def _force_download_all_tls_inner():
    print("=" * 70)
    print("  TLE FORCE DOWNLOAD – Space‑Track bulk (once-per-hour, off-peak)")
    print("=" * 70)

    all_norads = get_all_norads()
    total = len(all_norads)
    print(f"\n📡 Total satellites in config: {total}")

    fetcher = TLEFetcher()
    initial_valid = sum(1 for n in fetcher.tles if fetcher._is_valid_tle(fetcher.tles.get(n)))

    # ------------------------------------------------------------------
    # Step 1: Space‑Track bulk download via SpaceTrackBulkFetcher
    # ------------------------------------------------------------------
    print("\n[Step 1] Attempting Space‑Track bulk download (once-per-hour, off-peak)...")
    space_track_tles = {}
    if SPACE_TRACK_USER and SPACE_TRACK_PASSWORD:
        st_fetcher = SpaceTrackBulkFetcher(
            username=SPACE_TRACK_USER,
            password=SPACE_TRACK_PASSWORD,
        )
        # Use force_refresh to bypass cooldown (this is a manual admin operation)
        print("   Using force_refresh (manual admin operation, bypasses cooldown)...")
        space_track_tles = st_fetcher.force_refresh(target_norads=all_norads)
    else:
        print("   Space‑Track credentials not configured – skipping bulk download.")

    # Apply Space‑Track results to cache
    if space_track_tles:
        matched = 0
        for norad in all_norads:
            if norad in space_track_tles:
                fetcher.tles[norad] = space_track_tles[norad]
                matched += 1
        fetcher._save_to_csv()
        print(f"   Space‑Track added {matched}/{total} TLEs")
    else:
        print("   Space‑Track returned no TLEs (check credentials or cooldown).")

    # ------------------------------------------------------------------
    # Step 2: Celestrak individual for still missing satellites
    # ------------------------------------------------------------------
    still_missing = [n for n in all_norads if n not in fetcher.tles]
    if still_missing:
        print(f"\n[Step 2] Celestrak individual download ({len(still_missing)} satellites)...")
        cel_success = 0
        for idx, norad in enumerate(still_missing, 1):
            print(f"   [{idx}/{len(still_missing)}] NORAD {norad} ... ", end="")
            tle = fetcher.fetch_from_celestrak_individual(norad)
            if tle:
                fetcher.tles[norad] = tle
                cel_success += 1
                print("OK")
                reset_failed_attempts(norad)
            else:
                print("FAIL (will try N2YO or generate)")
            if idx % 10 == 0:
                fetcher._save_to_csv()
            time.sleep(CELESTRAK_INDIVIDUAL_DELAY)
        if cel_success:
            fetcher._save_to_csv()
            print(f"   Celestrak added {cel_success} new TLEs")
        still_missing = [n for n in all_norads if n not in fetcher.tles]

    # ------------------------------------------------------------------
    # Step 3: N2YO individual fallback
    # ------------------------------------------------------------------
    if still_missing and N2YO_API_KEY:
        print(f"\n[Step 3] N2YO individual download ({len(still_missing)} satellites)...")
        n2yo_success = 0
        for idx, norad in enumerate(still_missing, 1):
            if should_skip_norad(norad):
                print(f"   [{idx}/{len(still_missing)}] NORAD {norad} – skipping (cooldown active)")
                continue
            print(f"   [{idx}/{len(still_missing)}] NORAD {norad} ... ", end="")
            tle = fetcher.fetch_from_n2yo(norad)
            if tle:
                fetcher.tles[norad] = tle
                n2yo_success += 1
                print("OK")
                reset_failed_attempts(norad)
            else:
                print("FAIL (will generate placeholder)")
                record_failed_attempt(norad)
            if idx % 10 == 0:
                fetcher._save_to_csv()
            time.sleep(N2YO_BULK_DELAY)
        if n2yo_success:
            fetcher._save_to_csv()
            print(f"   N2YO added {n2yo_success} new TLEs")
        still_missing = [n for n in all_norads if n not in fetcher.tles]

    # ------------------------------------------------------------------
    # Step 4: Generate approximate TLEs as last resort
    # ------------------------------------------------------------------
    if still_missing:
        print(f"\n[Step 4] Generating approximate TLEs for {len(still_missing)} satellites...")
        for norad in still_missing:
            line1, line2 = fetcher._generate_approximate_tle(norad)
            fetcher.tles[norad] = (line1, line2)
            record_failed_attempt(norad)
        fetcher._save_to_csv()
        print(f"   Generated {len(still_missing)} placeholder TLEs")

    # Final stats
    final_valid = sum(1 for n in all_norads if fetcher._is_valid_tle(fetcher.tles.get(n)))
    print("\n" + "=" * 70)
    print("  DOWNLOAD COMPLETE")
    print("=" * 70)
    print(f"   Valid TLEs: {final_valid}/{total}")
    print(f"   Still missing (placeholders): {total - final_valid}")
    if CACHE_FILE.exists():
        size_kb = CACHE_FILE.stat().st_size / 1024
        print(f"   Cache size: {size_kb:.1f} KB")

    save_last_refresh()
    return True

# --------------------------------------------------------------------------
# CLI entry
# --------------------------------------------------------------------------
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='TLE Force Download – Space‑Track bulk')
    parser.add_argument('--status', action='store_true', help='Show cache status only')
    args = parser.parse_args()
    if args.status:
        pass
    else:
        force_download_all_tls()
