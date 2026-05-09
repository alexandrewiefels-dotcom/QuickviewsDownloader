# ============================================================================
# FILE: fix_missing_tles.py – Special script to fix missing TLEs
# ============================================================================
#!/usr/bin/env python3
import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from force_download_tles import download_single_satellite, show_cache_status
from config.satellites import SATELLITES

# List of NORADs that failed in the last run
FAILED_NORADS = [44713, 49255, 46455]  # Add more as they fail

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
