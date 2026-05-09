# ============================================================================
# FILE: cleanup_tle_cache.py – Remove old TLE cache files
# Run this after migration to clean up old files
# ============================================================================
#!/usr/bin/env python3
import shutil
from pathlib import Path

def cleanup_old_cache():
    """Remove old TLE cache files and directories"""
    
    print("=" * 60)
    print("  TLE CACHE CLEANUP")
    print("=" * 60)
    
    # Files/directories to remove
    to_remove = [
        Path("data/tle_cache"),           # Old individual JSON files directory
        Path("data/tle_backup.json"),      # Old backup file
        Path("data/prefetch_progress.json"), # Old progress file
        Path("data/cache_initialized.json"), # Old initialization flag
        Path("data/tle_cache_backup"),     # Old backup directory
        Path("data/export_tles.csv"),      # Old export CSV (replaced by tle_cache.csv)
    ]
    
    removed_count = 0
    for item in to_remove:
        if item.exists():
            try:
                if item.is_dir():
                    shutil.rmtree(item)
                    print(f"🗑️  Removed directory: {item}")
                else:
                    item.unlink()
                    print(f"🗑️  Removed file: {item}")
                removed_count += 1
            except Exception as e:
                print(f"⚠️  Could not remove {item}: {e}")
    
    print(f"\n✅ Cleanup complete. Removed {removed_count} items.")
    print("\n📁 New single cache file: data/tle_cache.csv")
    print("   To populate it, run: python force_download_tles.py")


if __name__ == "__main__":
    cleanup_old_cache()
