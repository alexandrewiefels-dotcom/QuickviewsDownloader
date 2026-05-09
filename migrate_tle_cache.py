# ============================================================================
# FILE: migrate_tle_cache.py – Migrate old TLEs to new single CSV cache
# Run this once to convert existing TLEs to the new format
# ============================================================================
#!/usr/bin/env python3
import json
import pandas as pd
from pathlib import Path

def migrate_old_cache():
    """Migrate TLEs from old cache files to new single CSV"""
    
    print("=" * 60)
    print("  TLE CACHE MIGRATION")
    print("=" * 60)
    
    new_cache_file = Path("data/tle_cache.csv")
    old_cache_dir = Path("data/tle_cache")
    old_backup_file = Path("data/tle_backup.json")
    old_export_file = Path("data/export_tles.csv")
    
    all_tles = {}
    
    # 1. Try to load from old individual JSON files
    if old_cache_dir.exists():
        print("\n📁 Reading old individual JSON files...")
        count = 0
        for json_file in old_cache_dir.glob("*.json"):
            if json_file.name in ["all_tles.json", "scheduler_status.json"]:
                continue
            try:
                with open(json_file, 'r') as f:
                    data = json.load(f)
                    norad = data.get('norad')
                    line1 = data.get('line1')
                    line2 = data.get('line2')
                    if norad and line1 and line2:
                        all_tles[norad] = (line1, line2)
                        count += 1
            except Exception as e:
                print(f"  Error reading {json_file.name}: {e}")
        print(f"  Loaded {count} TLEs from individual files")
    
    # 2. Try to load from old backup file
    if old_backup_file.exists():
        print("\n📁 Reading old backup file...")
        try:
            with open(old_backup_file, 'r') as f:
                backup_data = json.load(f)
            
            if "satellites" in backup_data:
                satellites = backup_data["satellites"]
            else:
                satellites = backup_data
            
            count = 0
            for norad_str, tle_data in satellites.items():
                try:
                    norad = int(norad_str)
                    if isinstance(tle_data, list) and len(tle_data) >= 2:
                        all_tles[norad] = (tle_data[0], tle_data[1])
                        count += 1
                    elif isinstance(tle_data, dict) and 'line1' in tle_data:
                        all_tles[norad] = (tle_data['line1'], tle_data['line2'])
                        count += 1
                except:
                    pass
            print(f"  Loaded {count} TLEs from backup")
        except Exception as e:
            print(f"  Error reading backup: {e}")
    
    # 3. Try to load from old export CSV
    if old_export_file.exists():
        print("\n📁 Reading old export CSV...")
        try:
            df = pd.read_csv(old_export_file)
            count = 0
            for _, row in df.iterrows():
                try:
                    norad = int(row['norad'])
                    line1 = row.get('line1') or row.get('tle1')
                    line2 = row.get('line2') or row.get('tle2')
                    if line1 and line2:
                        all_tles[norad] = (line1, line2)
                        count += 1
                except:
                    pass
            print(f"  Loaded {count} TLEs from export CSV")
        except Exception as e:
            print(f"  Error reading export CSV: {e}")
    
    # 4. Save to new CSV
    if all_tles:
        data = []
        for norad, (line1, line2) in all_tles.items():
            data.append({
                'norad': norad,
                'line1': line1,
                'line2': line2,
                'source': 'migrated',
                'last_updated': datetime.now().isoformat()
            })
        
        df = pd.DataFrame(data)
        df.to_csv(new_cache_file, index=False)
        print(f"\n✅ Migration complete: {len(data)} TLEs saved to {new_cache_file}")
    else:
        print("\n⚠️ No TLEs found to migrate")
    
    print("\n💡 Next steps:")
    print("   1. Run: python cleanup_tle_cache.py (to remove old files)")
    print("   2. Run: python force_download_tles.py (to get fresh TLEs)")


if __name__ == "__main__":
    from datetime import datetime
    migrate_old_cache()
