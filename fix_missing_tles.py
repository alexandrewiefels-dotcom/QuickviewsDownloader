# ============================================================================
# FILE: fix_missing_tles.py – Special script to fix missing TLEs
# ============================================================================
#!/usr/bin/env python3
import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from data.tle_fetcher import TLEFetcher, get_tle_fetcher, get_supplier_stats
from config.satellites import SATELLITES

# List of NORADs that failed in the last run
FAILED_NORADS = [44713, 49255, 46455]  # Add more as they fail

def download_single_satellite(norad: int) -> bool:
    """Download TLE for a single satellite using the TLEFetcher."""
    fetcher = get_tle_fetcher()
    tle = fetcher.fetch(norad, force_refresh=True)
    if tle:
        print(f"✅ NORAD {norad} downloaded successfully")
        return True
    else:
        print(f"❌ NORAD {norad} still missing after all attempts")
        return False

def show_cache_status():
    """Display current TLE cache status."""
    fetcher = get_tle_fetcher()
    status = fetcher.get_cache_status()
    print("=" * 70)
    print("  TLE CACHE STATUS")
    print("=" * 70)
    print(f"  Total satellites in cache: {status['total_satellites']}")
    print(f"  Cache age: {status['cache_age_hours']} hours")
    print(f"  Accuracy: {status['accuracy']}")
    print(f"  Generated TLEs: {status['generated_tles']}")
    print(f"  Pending missing downloads: {status['pending_missing_downloads']}")
    print(f"  Space-Track available: {status['space_track_available']}")
    print()
    stats = get_supplier_stats()
    if stats:
        print("  Supplier Stats:")
        for supplier, data in stats.items():
            print(f"    {supplier}: {data.get('success', 0)}/{data.get('total', 0)} successful")

def fix_failed_satellites():
    """Attempt to re-download failed satellites"""
    print("=" * 70)
    print("  FIX MISSING TLES")
    print("=" * 70)
    
    for norad in FAILED_NORADS:
        print(f"\n--- Processing NORAD {norad} ---")
        download_single_satellite(norad)
        print()

def check_alternative_ids():
    """Check if satellites have alternative NORAD IDs"""
    # Common Jilin satellites and their known NORADs
    known_mapping = {
        "JL1GF02A": [44713, 44714],  # Try alternative
        "JL1GF02D": [49255, 49256],
        "JL1GF 03B 02": [46455, 46454],
    }
    
    print("\n📡 Checking alternative NORAD IDs...")
    # This would need to be customized based on actual satellite data

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Fix missing TLEs')
    parser.add_argument('--all', action='store_true', help='Try all failed satellites')
    
    args = parser.parse_args()
    
    if args.all:
        fix_failed_satellites()
    else:
        show_cache_status()
