# ============================================================================
# FILE: update_tles.py – TLE updater using Celestrak (primary)
# No API key required, minimal rate limiting
# UPDATED: Works with single CSV cache
# ============================================================================
#!/usr/bin/env python3
import sys
import time
import argparse
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent))

from data.tle_fetcher import TLEFetcher, save_last_refresh, CACHE_FILE
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
    """Update all satellites using Celestrak bulk download"""
    fetcher = TLEFetcher()
    norads = get_all_satellite_norads()
    
    print(f"Updating TLEs for {len(norads)} satellites...")
    print("Using Celestrak (no API key required, no rate limits)")
    print("=" * 60)
    
    # Try bulk download first
    print("Performing bulk download from Celestrak...")
    bulk_tles = fetcher.fetch_bulk_from_celestrak(group="active")
    
    success_count = 0
    failed_norads = []
    
    if bulk_tles:
        for norad in norads:
            if norad in bulk_tles:
                fetcher.tles[norad] = bulk_tles[norad]
                success_count += 1
                print(f"  ✅ NORAD {norad}: from bulk")
            else:
                # Try individual fetch
                print(f"  🔄 NORAD {norad}: bulk miss, trying individual...", end=" ")
                tle = fetcher.fetch_from_celestrak_individual(norad)
                if tle:
                    fetcher.tles[norad] = tle
                    success_count += 1
                    print("✅")
                else:
                    failed_norads.append(norad)
                    print("❌")
                time.sleep(0.1)
    else:
        # Bulk failed, try individual for all
        print("Bulk download failed, trying individual fetches...")
        for norad in norads:
            print(f"  Fetching NORAD {norad}...", end=" ")
            tle = fetcher.fetch_from_celestrak(norad)
            if tle:
                fetcher.tles[norad] = tle
                success_count += 1
                print("✅")
            else:
                failed_norads.append(norad)
                print("❌")
            time.sleep(0.1)
    
    # Save to CSV
    fetcher._save_to_csv()
    
    # Save last refresh timestamp
    save_last_refresh()

    # Log the update session
    log_update_session(success_count, len(failed_norads), "celestrak", "Bulk update")
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
    parser = argparse.ArgumentParser(description='Update TLE data for satellites using Celestrak')
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
