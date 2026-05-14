# ============================================================================
# FILE: update_tles.py – TLE updater using Celestrak (primary) + Space‑Track bulk
# No API key required for Celestrak, minimal rate limiting.
# Space‑Track uses the new SpaceTrackBulkFetcher (once-per-hour, off-peak).
# ============================================================================
#!/usr/bin/env python3
import sys
import time
import argparse
import os
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent))

from data.tle_fetcher import TLEFetcher, save_last_refresh, CACHE_FILE
from data.space_track_fetcher import SpaceTrackBulkFetcher
from config.satellites import SATELLITES
from data.tle_fetcher import log_update_session


def get_all_satellite_norads() -> list:
    """Extract all NORAD IDs from the satellites configuration"""
    norads = set()
    
    for category_name, category in SATELLITES.items():
        for sat_name, sat_info in category.items():
            norad = sat_info.get("norad")
            if norad:
                norads.add(norad)
    
    return sorted(list(norads))


def update_all_satellites(force: bool = False) -> tuple:
    """Update all satellites using Celestrak bulk download + Space‑Track fallback"""
    fetcher = TLEFetcher()
    norads = get_all_satellite_norads()
    
    print(f"Updating TLEs for {len(norads)} satellites...")
    print("=" * 60)
    
    # ------------------------------------------------------------------
    # Step 1: Try Space‑Track bulk (once-per-hour, off-peak)
    # ------------------------------------------------------------------
    space_track_user = None
    space_track_pass = None
    try:
        import streamlit as st
        space_track_user = st.secrets.get("SPACE_TRACK_USER")
        space_track_pass = st.secrets.get("SPACE_TRACK_PASSWORD")
    except (ImportError, FileNotFoundError, KeyError):
        space_track_user = os.environ.get("SPACE_TRACK_USER")
        space_track_pass = os.environ.get("SPACE_TRACK_PASSWORD")
    
    space_track_tles = {}
    if space_track_user and space_track_pass:
        print("Attempting Space‑Track bulk download (once-per-hour, off-peak)...")
        st_fetcher = SpaceTrackBulkFetcher(
            username=space_track_user,
            password=space_track_pass,
        )
        if force:
            space_track_tles = st_fetcher.force_refresh(target_norads=norads)
        else:
            space_track_tles = st_fetcher.fetch(target_norads=norads)
        
        if space_track_tles:
            print(f"Space‑Track returned {len(space_track_tles)} TLEs")
            for norad in norads:
                if norad in space_track_tles:
                    fetcher.tles[norad] = space_track_tles[norad]
        else:
            print("Space‑Track returned no TLEs (cooldown may be active).")
    else:
        print("Space‑Track credentials not configured – skipping.")
    
    # ------------------------------------------------------------------
    # Step 2: Celestrak bulk download for remaining satellites
    # ------------------------------------------------------------------
    remaining = [n for n in norads if n not in fetcher.tles]
    if remaining:
        print(f"\nPerforming Celestrak bulk download for {len(remaining)} remaining satellites...")
        bulk_tles = fetcher.fetch_bulk_from_celestrak(group="active")
        
        success_count = 0
        failed_norads = []
        
        if bulk_tles:
            for norad in remaining:
                if norad in bulk_tles:
                    fetcher.tles[norad] = bulk_tles[norad]
                    success_count += 1
                    print(f"  NORAD {norad}: from bulk")
                else:
                    # Try individual fetch
                    print(f"  NORAD {norad}: bulk miss, trying individual...", end=" ")
                    tle = fetcher.fetch_from_celestrak_individual(norad)
                    if tle:
                        fetcher.tles[norad] = tle
                        success_count += 1
                        print("OK")
                    else:
                        failed_norads.append(norad)
                        print("FAIL")
                    time.sleep(0.1)
        else:
            # Bulk failed, try individual for all
            print("Bulk download failed, trying individual fetches...")
            for norad in remaining:
                print(f"  Fetching NORAD {norad}...", end=" ")
                tle = fetcher.fetch_from_celestrak_individual(norad)
                if tle:
                    fetcher.tles[norad] = tle
                    success_count += 1
                    print("OK")
                else:
                    failed_norads.append(norad)
                    print("FAIL")
                time.sleep(0.1)
    else:
        success_count = len(norads)
        failed_norads = []
    
    # Save to CSV
    fetcher._save_to_csv()
    
    # Save last refresh timestamp
    save_last_refresh()

    # Log the update session
    log_update_session(success_count, len(failed_norads), "celestrak+spacetrack", "Combined update")
    print("=" * 60)
    print(f"Update complete: {success_count}/{len(norads)} satellites updated")
    
    if failed_norads:
        print(f"Failed NORADs: {failed_norads[:20]}{'...' if len(failed_norads) > 20 else ''}")
    
    return success_count, failed_norads


def get_cache_status():
    """Get cache status"""
    fetcher = TLEFetcher()
    return fetcher.get_cache_status()


def main():
    parser = argparse.ArgumentParser(description='Update TLE data for satellites using Celestrak + Space‑Track')
    parser.add_argument('--force', action='store_true', help='Force update (ignore cache)')
    parser.add_argument('--status', action='store_true', help='Show cache status only')
    
    args = parser.parse_args()
    
    if args.status:
        status = get_cache_status()
        print(f"\n=== TLE Cache Status ===")
        print(f"Cache file: {CACHE_FILE}")
        print(f"Total satellites: {status['total_satellites']}")
        print(f"Generated TLEs: {status['generated_tles']}")
        print(f"Cache age: {status['cache_age_hours']} hours")
        print(f"Accuracy: {status['accuracy']}")
        return
    
    # Update TLEs
    update_all_satellites(force=args.force)
    
    print("\nDone!")


if __name__ == "__main__":
    main()
