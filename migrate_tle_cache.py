"""
TLE Cache Migration Script (3.15).

Migrates TLE data from legacy formats to the current cache format.
Supports migration from:
1. Old individual JSON files (data/tle_cache/*.json)
2. Old backup file (data/tle_backup.json)
3. Old export CSV (data/export_tles.csv)
4. Current CSV cache (data/tle_cache.csv) → SQLite (data/tle_cache.db)

Usage:
    python migrate_tle_cache.py              # Auto-detect and migrate
    python migrate_tle_cache.py --to-sqlite  # Force CSV → SQLite migration
    python migrate_tle_cache.py --dry-run    # Show what would be migrated
"""

import argparse
import json
import sys
import logging
from datetime import datetime
from pathlib import Path

import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)


def migrate_old_cache(dry_run: bool = False) -> int:
    """Migrate TLEs from old cache files to new single CSV. Returns count."""
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

            satellites = backup_data.get("satellites", backup_data)
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
                except Exception:
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
                except Exception:
                    pass
            print(f"  Loaded {count} TLEs from export CSV")
        except Exception as e:
            print(f"  Error reading export CSV: {e}")

    # 4. Save to new CSV
    if all_tles:
        if dry_run:
            print(f"\n📋 Dry run: {len(all_tles)} TLEs would be migrated to {new_cache_file}")
        else:
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

    return len(all_tles)


def migrate_csv_to_sqlite(dry_run: bool = False) -> int:
    """Migrate from CSV cache to SQLite. Returns count."""
    print("=" * 60)
    print("  CSV → SQLite MIGRATION")
    print("=" * 60)

    csv_path = Path("data/tle_cache.csv")
    if not csv_path.exists():
        print("\n⚠️ No CSV cache file found at data/tle_cache.csv")
        return 0

    try:
        from data.tle_cache_sqlite import SQLiteTLECache
        cache = SQLiteTLECache()

        # Check if SQLite already has data
        existing = cache.count()
        if existing > 0:
            print(f"\nℹ️ SQLite cache already has {existing} entries")
            choice = input("Overwrite? (y/N): ").strip().lower()
            if choice != 'y':
                print("Skipping SQLite migration.")
                return 0

        if dry_run:
            df = pd.read_csv(csv_path)
            print(f"\n📋 Dry run: {len(df)} TLEs would be migrated to SQLite")
            return len(df)

        count = cache.migrate_from_csv(csv_path)
        print(f"\n✅ SQLite migration complete: {count} TLEs migrated")
        print(f"   Database: {cache.db_path}")
        print(f"   Size: {cache.get_stats().get('db_size_mb', '?')} MB")
        return count

    except ImportError:
        print("\n❌ SQLite cache module not found. Run this from the project root.")
        return 0
    except Exception as e:
        print(f"\n❌ SQLite migration failed: {e}")
        return 0


def migrate_jsonl_to_sqlite(dry_run: bool = False) -> dict:
    """Migrate JSONL log files to SQLite. Returns dict of table -> count."""
    print("=" * 60)
    print("  JSONL → SQLite MIGRATION")
    print("=" * 60)

    try:
        from data.logs_sqlite import LogsSQLiteBackend
        backend = LogsSQLiteBackend()
    except ImportError:
        print("\n❌ Logs SQLite module not found.")
        return {}

    jsonl_mapping = {
        "logs/api_interactions.jsonl": "api_interactions",
        "logs/aoi_history.jsonl": "aoi_history",
        "logs/search_history.jsonl": "search_history",
        "logs/quickview_ops.jsonl": "quickview_ops",
    }

    results = {}
    for jsonl_path, table in jsonl_mapping.items():
        path = Path(jsonl_path)
        if not path.exists():
            print(f"\n⚠️ {jsonl_path} not found, skipping")
            continue

        if dry_run:
            with open(path) as f:
                count = sum(1 for _ in f)
            print(f"\n📋 Dry run: {count} entries from {jsonl_path} → {table}")
            results[table] = count
        else:
            count = backend.migrate_from_jsonl(jsonl_path, table)
            print(f"\n✅ Migrated {count} entries from {jsonl_path} → {table}")
            results[table] = count

    return results


def main():
    parser = argparse.ArgumentParser(description="Migrate TLE cache and log data")
    parser.add_argument("--to-sqlite", action="store_true",
                        help="Force CSV → SQLite migration")
    parser.add_argument("--logs", action="store_true",
                        help="Migrate JSONL log files to SQLite")
    parser.add_argument("--all", action="store_true",
                        help="Run all migrations")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would be migrated without doing it")

    args = parser.parse_args()

    # If no specific migration requested, run old cache migration
    if not any([args.to_sqlite, args.logs, args.all]):
        migrate_old_cache(dry_run=args.dry_run)
        return

    if args.all or args.to_sqlite:
        migrate_old_cache(dry_run=args.dry_run)
        migrate_csv_to_sqlite(dry_run=args.dry_run)

    if args.all or args.logs:
        migrate_jsonl_to_sqlite(dry_run=args.dry_run)

    print("\n" + "=" * 60)
    print("  Migration complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()
