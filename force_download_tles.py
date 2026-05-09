#!/usr/bin/env python3
# ============================================================================
# FILE: force_download_tles.py – Space‑Track primary bulk download for all satellites
# Now: fetches all NORADs in config (no time filter, no cooldown for full refresh)
# ============================================================================
import sys
import time
import json
import requests
import threading
import shutil
import argparse
from pathlib import Path
from datetime import datetime, timedelta
import streamlit as st

sys.path.insert(0, str(Path(__file__).parent))

from data.tle_fetcher import (
    TLEFetcher, CACHE_FILE, save_last_refresh, _update_supplier_stats,
    should_skip_norad, record_failed_attempt, reset_failed_attempts,
    N2YO_BULK_DELAY, CELESTRAK_INDIVIDUAL_DELAY, log_update_session,
)
from config.satellites import SATELLITES

# Guard against concurrent force-download runs
_force_download_lock = threading.Lock()
_force_download_running = False

# Space‑Track API endpoints
SPACE_TRACK_AUTH_URL = "https://www.space-track.org/ajaxauth/login"
SPACE_TRACK_BULK_URL = "https://www.space-track.org/basicspacedata/query/class/gp/decay_date/null-val/format/tle"

# Load credentials from Streamlit secrets
try:
    SPACE_TRACK_USER = st.secrets.get("SPACE_TRACK_USER")
    SPACE_TRACK_PASSWORD = st.secrets.get("SPACE_TRACK_PASSWORD")
    N2YO_API_KEY = st.secrets.get("N2YO_API_KEY")
except Exception:
    SPACE_TRACK_USER = None
    SPACE_TRACK_PASSWORD = None
    N2YO_API_KEY = None

# Cooldown file – optional, can be bypassed with force=True
LAST_DOWNLOAD_FILE = Path("data/last_space_track_download.json")

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
# Space‑Track login and bulk download (no time filter)
# --------------------------------------------------------------------------
def login_space_track():
    if not SPACE_TRACK_USER or not SPACE_TRACK_PASSWORD:
        return None
    try:
        session = requests.Session()
        auth_data = {"identity": SPACE_TRACK_USER, "password": SPACE_TRACK_PASSWORD}
        print(f"[Space-Track] Logging in as {SPACE_TRACK_USER}...")
        response = session.post(SPACE_TRACK_AUTH_URL, data=auth_data, timeout=30)
        if response.status_code == 200:
            print("[Space-Track] Login successful")
            return session
        else:
            print(f"[Space-Track] Login failed: HTTP {response.status_code}")
            return None
    except Exception as e:
        print(f"[Space-Track] Login error: {e}")
        return None

def bulk_download_for_norads(session, norad_list):
    """
    Download TLEs for a specific list of NORADs using Space‑Track.
    Uses the gp query with NORAD_CAT_ID filter.
    """
    if not norad_list:
        return {}
    norad_str = ",".join(str(n) for n in norad_list)
    url = f"{SPACE_TRACK_BULK_URL}/NORAD_CAT_ID/{norad_str}"
    try:
        print(f"[Space-Track] Requesting TLEs for {len(norad_list)} NORADs...")
        response = session.get(url, timeout=120)
        if response.status_code == 200:
            content = response.text
            lines = content.strip().split('\n')
            tles = {}
            for i in range(0, len(lines), 3):
                if i + 2 < len(lines):
                    line1 = lines[i+1].strip()
                    line2 = lines[i+2].strip()
                    if len(line2) >= 7:
                        norad_str = line2[2:7].strip()
                        if norad_str.isdigit():
                            norad = int(norad_str)
                            tles[norad] = (line1, line2)
            print(f"[Space-Track] Successfully parsed {len(tles)} TLEs")
            _update_supplier_stats("space_track_bulk", success=True)
            return tles
        else:
            print(f"[Space-Track] Bulk download failed: HTTP {response.status_code}")
            _update_supplier_stats("space_track_bulk", success=False)
            return {}
    except Exception as e:
        print(f"[Space-Track] Bulk download error: {e}")
        _update_supplier_stats("space_track_bulk", success=False)
        return {}

# --------------------------------------------------------------------------
# Main force download routine
# --------------------------------------------------------------------------
def force_download_all_tls():
    """
    1. Attempt Space‑Track bulk download for ALL satellites in config.
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
    print("  TLE FORCE DOWNLOAD – Space‑Track primary (all satellites)")
    print("=" * 70)

    all_norads = get_all_norads()
    total = len(all_norads)
    print(f"\n📡 Total satellites in config: {total}")

    fetcher = TLEFetcher()
    initial_valid = sum(1 for n in fetcher.tles if fetcher._is_valid_tle(fetcher.tles.get(n)))

    # ------------------------------------------------------------------
    # Step 1: Space‑Track bulk download (no cooldown, all NORADs)
    # ------------------------------------------------------------------
    print("\n[Step 1] Attempting Space‑Track bulk download for all NORADs...")
    session = login_space_track()
    space_track_tles = {}
    if session:
        # Split into chunks of 200 NORADs (Space‑Track may have URL length limits)
        chunk_size = 200
        for i in range(0, len(all_norads), chunk_size):
            chunk = all_norads[i:i+chunk_size]
            tles_chunk = bulk_download_for_norads(session, chunk)
            space_track_tles.update(tles_chunk)
            time.sleep(1)  # small delay between chunks
        session.close()
    else:
        print("   Space‑Track login failed – skipping bulk download.")

    # Apply Space‑Track results to cache
    if space_track_tles:
        matched = 0
        for norad in all_norads:
            if norad in space_track_tles:
                fetcher.tles[norad] = space_track_tles[norad]
                matched += 1
        fetcher._save_to_csv()
        print(f"   Space‑Track added {matched}/{total} TLEs")
        # Record successful download (optional, we may still use cooldown later)
        try:
            with open(LAST_DOWNLOAD_FILE, 'w') as f:
                json.dump({"last_download": datetime.now().isoformat()}, f)
        except:
            pass
    else:
        print("   Space‑Track returned no TLEs (check credentials).")

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
                print("✅")
                reset_failed_attempts(norad)
            else:
                print("❌ (will try N2YO or generate)")
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
    if still_missing and fetcher.n2yo_api_key:
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
                print("✅")
                reset_failed_attempts(norad)
            else:
                print("❌ (will generate placeholder)")
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
    parser = argparse.ArgumentParser(description='TLE Force Download – Space‑Track primary')
    parser.add_argument('--status', action='store_true', help='Show cache status only')
    args = parser.parse_args()
    if args.status:
        # Implement status display if needed
        pass
    else:
        force_download_all_tls()