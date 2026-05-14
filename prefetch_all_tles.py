# ============================================================================
# FILE: prefetch_all_tles.py – TLE pre-fetch with singleton download lock
# ============================================================================
#!/usr/bin/env python3
import sys
import time
import json
import threading
import shutil
import os
from pathlib import Path
from datetime import datetime, timedelta

sys.path.insert(0, str(Path(__file__).parent))

from data.tle_fetcher import TLEFetcher, get_tle_fetcher, save_last_refresh, CACHE_FILE, PREFETCH_REQUEST_DELAY
from config.satellites import SATELLITES

# Try to load Streamlit secrets for credentials, fall back to env vars
SPACE_TRACK_USER = os.environ.get("SPACE_TRACK_USER")
SPACE_TRACK_PASSWORD = os.environ.get("SPACE_TRACK_PASSWORD")
N2YO_API_KEY = os.environ.get("N2YO_API_KEY")

# Only try Streamlit secrets if running inside Streamlit runtime
try:
    import streamlit.runtime.scriptrunner as _sr
    if _sr.get_script_run_ctx() is not None:
        import streamlit as st
        SPACE_TRACK_USER = SPACE_TRACK_USER or st.secrets.get("SPACE_TRACK_USER")
        SPACE_TRACK_PASSWORD = SPACE_TRACK_PASSWORD or st.secrets.get("SPACE_TRACK_PASSWORD")
        N2YO_API_KEY = N2YO_API_KEY or st.secrets.get("N2YO_API_KEY")
except (ImportError, RuntimeError):
    pass

PROGRESS_FILE = Path("data/prefetch_progress.json")
LAST_REFRESH_FILE = Path("data/last_refresh.json")
CACHE_INITIALIZED_FILE = Path("data/cache_initialized.json")
CACHE_BACKUP_DIR = Path("data/tle_cache_backup")

CACHE_VALIDITY_HOURS = 72
BACKGROUND_REFRESH_HOURS = 48
MAX_CACHE_AGE_DAYS = 7

# Global lock to prevent multiple background refreshes
_refresh_running = False
_refresh_lock = threading.Lock()

def get_all_satellite_norads_from_config() -> tuple:
    norads = []
    norad_names = {}
    for category in SATELLITES.values():
        for sat_name, sat_info in category.items():
            norad = sat_info.get("norad")
            if norad:
                norads.append(norad)
                norad_names[norad] = sat_name
    return list(dict.fromkeys(norads)), norad_names

def backup_current_cache():
    if not CACHE_FILE.exists():
        return None
    CACHE_BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = CACHE_BACKUP_DIR / f"tle_cache_backup_{timestamp}.csv"
    shutil.copy2(CACHE_FILE, backup_path)
    for old in CACHE_BACKUP_DIR.glob("tle_cache_backup_*.csv"):
        try:
            backup_time_str = old.name.replace("tle_cache_backup_", "").replace(".csv", "")
            backup_time = datetime.strptime(backup_time_str, "%Y%m%d_%H%M%S")
            if datetime.now() - backup_time > timedelta(days=MAX_CACHE_AGE_DAYS):
                old.unlink()
        except:
            pass
    return backup_path

def restore_from_backup_if_needed():
    backups = sorted(CACHE_BACKUP_DIR.glob("tle_cache_backup_*.csv"), reverse=True)
    if not backups:
        return False
    latest_backup = backups[0]
    try:
        if not CACHE_FILE.exists() or CACHE_FILE.stat().st_size < 1000:
            shutil.copy2(latest_backup, CACHE_FILE)
            print(f"Restored cache from backup: {latest_backup.name}")
            return True
    except Exception as e:
        print(f"Warning: Could not restore from backup: {e}")
    return False

def save_progress(completed_norads: list, current_index: int, total: int):
    try:
        PROGRESS_FILE.parent.mkdir(parents=True, exist_ok=True)
        progress_data = {
            "completed_norads": completed_norads,
            "current_index": current_index,
            "total": total,
            "last_updated": datetime.now().isoformat()
        }
        with open(PROGRESS_FILE, 'w') as f:
            json.dump(progress_data, f, indent=2)
    except Exception:
        pass

def load_progress() -> tuple:
    if not PROGRESS_FILE.exists():
        return [], 0, 0
    try:
        with open(PROGRESS_FILE, 'r') as f:
            progress_data = json.load(f)
        completed = progress_data.get("completed_norads", [])
        current_index = progress_data.get("current_index", 0)
        total = progress_data.get("total", 0)
        return completed, current_index, total
    except Exception:
        return [], 0, 0

def clear_progress():
    try:
        if PROGRESS_FILE.exists():
            PROGRESS_FILE.unlink()
    except Exception:
        pass

def save_cache_initialized():
    try:
        CACHE_INITIALIZED_FILE.parent.mkdir(parents=True, exist_ok=True)
        data = {"initialized_at": datetime.now().isoformat(), "status": "success"}
        with open(CACHE_INITIALIZED_FILE, 'w') as f:
            json.dump(data, f, indent=2)
    except Exception:
        pass

def is_cache_initialized() -> bool:
    return CACHE_INITIALIZED_FILE.exists()

def needs_background_refresh() -> bool:
    if not is_cache_initialized():
        return True
    if not LAST_REFRESH_FILE.exists():
        return True
    try:
        with open(LAST_REFRESH_FILE, 'r') as f:
            data = json.load(f)
        last_refresh = datetime.fromisoformat(data.get("last_refresh", "2000-01-01"))
        hours_since = (datetime.now() - last_refresh).total_seconds() / 3600
        return hours_since >= BACKGROUND_REFRESH_HOURS
    except Exception:
        return True

def get_cache_age_hours() -> float:
    if not LAST_REFRESH_FILE.exists():
        return 9999
    try:
        with open(LAST_REFRESH_FILE, 'r') as f:
            data = json.load(f)
        last_refresh = datetime.fromisoformat(data.get("last_refresh", "2000-01-01"))
        return (datetime.now() - last_refresh).total_seconds() / 3600
    except Exception:
        return 9999

def prefetch_all_tles_silent(progress_callback=None, resume=True):
    """
    Pre-fetch all TLEs - COMPLETELY SILENT.
    Uses the global download lock to avoid concurrent runs.
    """
    global _refresh_running
    with _refresh_lock:
        if _refresh_running:
            print("[Prefetch] Download already in progress, skipping.")
            return {"success": 0, "total": 0, "already_done": False}
        _refresh_running = True

    try:
        all_norads, norad_names = get_all_satellite_norads_from_config()
        total = len(all_norads)

        backup_current_cache()
        completed_norads = []
        if resume:
            completed_norads, _, _ = load_progress()

        pending_norads = [n for n in all_norads if n not in completed_norads]
        already_done = len(completed_norads)
        pending = len(pending_norads)

        if pending == 0:
            if not is_cache_initialized():
                save_cache_initialized()
            save_last_refresh()
            return {"success": already_done, "total": total, "already_done": True}

        fetcher = get_tle_fetcher()
        success_count = already_done

        # Try Space-Track bulk download via SpaceTrackBulkFetcher (once-per-hour, off-peak)
        if fetcher.space_track_available and fetcher.space_track_fetcher is not None:
            print(f"[Prefetch] Trying Space-Track bulk for {len(pending_norads)} NORADs...")
            bulk_tles = fetcher.space_track_fetcher.fetch(target_norads=pending_norads)
            if bulk_tles:
                for norad in list(pending_norads):
                    if norad in bulk_tles:
                        fetcher.tles[norad] = bulk_tles[norad]
                        completed_norads.append(norad)
                        success_count += 1
                fetcher._save_to_csv()
                pending_norads = [n for n in pending_norads if n not in fetcher.tles]
                print(f"[Prefetch] Space-Track bulk: {success_count - already_done} fetched, "
                      f"{len(pending_norads)} still pending")
            else:
                print("[Prefetch] Space-Track bulk returned no TLEs (cooldown may be active).")

        saves_since_last_write = 0
        for idx, norad in enumerate(pending_norads, 1):
            current_global_idx = already_done + idx
            if progress_callback:
                progress_callback(current_global_idx, total, "")

            if norad in fetcher.tles:
                completed_norads.append(norad)
                success_count += 1
                save_progress(completed_norads, current_global_idx, total)
                continue

            tle = fetcher.fetch_from_celestrak_individual(norad)
            if tle:
                fetcher.tles[norad] = tle
                success_count += 1
            else:
                tle = fetcher.fetch_from_n2yo(norad)
                if tle:
                    fetcher.tles[norad] = tle
                    success_count += 1
                else:
                    tle = fetcher._generate_approximate_tle(norad)
                    fetcher.tles[norad] = tle

            saves_since_last_write += 1
            if saves_since_last_write >= 10:
                fetcher._save_to_csv()
                saves_since_last_write = 0

            completed_norads.append(norad)
            save_progress(completed_norads, current_global_idx, total)

            if idx < len(pending_norads):
                time.sleep(PREFETCH_REQUEST_DELAY)

        if saves_since_last_write > 0:
            fetcher._save_to_csv()

        if success_count >= total:
            clear_progress()
            save_cache_initialized()
            save_last_refresh()

        return {"success": success_count, "total": total, "completed": success_count >= total}
    finally:
        _refresh_running = False

def background_refresh_if_needed():
    """Run background refresh silently if needed, using the global lock."""
    if not needs_background_refresh():
        return False
    # Already running?
    if _refresh_running:
        return False

    def _refresh():
        prefetch_all_tles_silent()

    thread = threading.Thread(target=_refresh, daemon=True)
    thread.start()
    return True

def is_cache_populated() -> bool:
    restore_from_backup_if_needed()
    if not is_cache_initialized():
        return False
    fetcher = get_tle_fetcher()
    all_norads, _ = get_all_satellite_norads_from_config()
    if not all_norads:
        return False
    valid_count = 0
    for norad in all_norads[:20]:
        if norad in fetcher.tles:
            valid_count += 1
    if valid_count >= 5:
        if PROGRESS_FILE.exists():
            try:
                with open(PROGRESS_FILE, 'r') as f:
                    progress = json.load(f)
                if progress.get("current_index", 0) < progress.get("total", 0):
                    return False
            except:
                pass
        return True
    return False

def get_cache_summary() -> dict:
    fetcher = get_tle_fetcher()
    all_norads, norad_names = get_all_satellite_norads_from_config()
    valid_count = 0
    for norad in all_norads:
        if norad in fetcher.tles:
            valid_count += 1
    cache_age_hours = get_cache_age_hours()
    if cache_age_hours <= 24:
        accuracy = "Excellent (error < 1 km)"
    elif cache_age_hours <= 48:
        accuracy = "Good (error 1-5 km)"
    elif cache_age_hours <= 72:
        accuracy = "Fair (error 5-15 km)"
    else:
        accuracy = "Poor (error > 50 km) - Refresh needed"
    last_refresh = None
    if LAST_REFRESH_FILE.exists():
        try:
            with open(LAST_REFRESH_FILE, 'r') as f:
                data = json.load(f)
                last_refresh = data.get("last_refresh")
        except:
            pass
    return {
        "total_satellites": len(all_norads),
        "cached_valid": valid_count,
        "cached_missing": len(all_norads) - valid_count,
        "generated_tles": fetcher.generated_tle_count,
        "cache_validity_hours": CACHE_VALIDITY_HOURS,
        "cache_age_hours": round(cache_age_hours, 1),
        "accuracy": accuracy,
        "last_refresh": last_refresh,
        "needs_refresh": needs_background_refresh(),
        "cache_initialized": is_cache_initialized()
    }

def reset_prefetch():
    try:
        if PROGRESS_FILE.exists():
            PROGRESS_FILE.unlink()
        if LAST_REFRESH_FILE.exists():
            LAST_REFRESH_FILE.unlink()
        if CACHE_INITIALIZED_FILE.exists():
            CACHE_INITIALIZED_FILE.unlink()
        if CACHE_BACKUP_DIR.exists():
            shutil.rmtree(CACHE_BACKUP_DIR)
    except:
        pass

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description='TLE Pre-fetch Tool')
    parser.add_argument('--reset', action='store_true', help='Reset progress and start over')
    parser.add_argument('--status', action='store_true', help='Show cache status (admin only)')
    args = parser.parse_args()
    if args.reset:
        reset_prefetch()
        print("Reset complete. Cache will be rebuilt on next background refresh.")
    elif args.status:
        summary = get_cache_summary()
        print("\n📊 TLE Cache Status:")
        for k, v in summary.items():
            print(f"   {k}: {v}")
    else:
        prefetch_all_tles_silent()