# ============================================================================
# FILE: data/tle_fetcher.py – Robust CSV cache, atomic writes, singleton download lock
# ============================================================================
import streamlit as st
import requests
import pandas as pd
import time
import json
import math
import threading
import tempfile
import shutil
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Tuple, Dict, List
import warnings
import logging

logger = logging.getLogger(__name__)

# Constants
EARTH_RADIUS_KM = 6371.0
MU = 398600.44

# SINGLE CACHE FILE
CACHE_FILE = Path("data/tle_cache.csv")
LAST_REFRESH_FILE = Path("data/last_refresh.json")
SPACE_TRACK_LAST_QUERY_FILE = Path("data/space_track_last_query.json")
MISSING_NORADS_FILE = Path("data/missing_norads.json")
SUPPLIER_STATS_FILE = Path("data/supplier_stats.json")

# Space-Track is now handled by data/space_track_fetcher.py (bulk, once-per-hour, off-peak)
from data.space_track_fetcher import (
    SpaceTrackBulkFetcher,
    get_space_track_fetcher as get_st_fetcher,
    reset_space_track_fetcher as reset_st_fetcher,
)

# N2YO.com API (automatic fallback)
N2YO_TLE_URL = "https://api.n2yo.com/rest/v1/satellite/tle/{norad}&apiKey={api_key}"

# Celestrak URLs
CELESTRAK_BULK_URL = "https://celestrak.org/NORAD/elements/gp.php?GROUP=active&FORMAT=TLE"
CELESTRAK_SINGLE_URL = "https://celestrak.org/NORAD/elements/gp.php?CATNR={norad}&FORMAT=TLE"

# Cache settings
CACHE_VALIDITY_HOURS = 72
CONNECTION_TIMEOUT = 15      # Reduced from 30
READ_TIMEOUT = 30
TLE_UPDATE_LOG_FILE = Path("data/tle_update_log.json")

# Rate-limiting constants (all sources, all callers)
N2YO_REQUEST_DELAY = 1.0           # enforced by TLEFetcher.fetch_from_n2yo (lock-protected)
CELESTRAK_INDIVIDUAL_DELAY = 0.2   # between Celestrak individual requests in bulk ops
N2YO_BULK_DELAY = 6.0              # conservative N2YO delay during bulk force-downloads
PREFETCH_REQUEST_DELAY = 1.0       # between requests in the background prefetch loop

# Global download lock – prevents concurrent writes to cache
_download_lock = threading.Lock()
_download_in_progress = False

# Celestrak unreachable flag (reset after 5 minutes)
_celestrak_unreachable_until = 0
_celestrak_lock = threading.Lock()  # protects _celestrak_unreachable_until

# ============================================================================
# FAILURE TRACKING
# ============================================================================
FAILED_NORADS_FILE = Path("data/failed_norads.json")
MAX_FAILURES_BEFORE_SKIP = 3
SKIP_DURATION_HOURS = 24

def _load_failed_norads() -> dict:
    if not FAILED_NORADS_FILE.exists():
        return {}
    try:
        with open(FAILED_NORADS_FILE, 'r') as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        logger.warning(f"Could not read {FAILED_NORADS_FILE}, returning empty")
        return {}

def clear_all_failed_norads():
    try:
        if FAILED_NORADS_FILE.exists():
            FAILED_NORADS_FILE.unlink()
            print("[TLE] All failure records cleared.")
    except Exception as e:
        print(f"[TLE] Could not clear failure records: {e}")

def _save_failed_norads(data: dict):
    try:
        FAILED_NORADS_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(FAILED_NORADS_FILE, 'w') as f:
            json.dump(data, f, indent=2)
    except Exception:
        pass

def log_update_session(success_count, failed_count, supplier, details=""):
    try:
        log = []
        if TLE_UPDATE_LOG_FILE.exists():
            try:
                with open(TLE_UPDATE_LOG_FILE, 'r') as f:
                    log = json.load(f)
            except json.JSONDecodeError:
                print(f"[TLE] Corrupt {TLE_UPDATE_LOG_FILE}, resetting.")
                log = []
        log.append({
            "timestamp": datetime.now().isoformat(),
            "success": success_count,
            "failed": failed_count,
            "supplier": supplier,
            "details": details
        })
        if len(log) > 100:
            log = log[-100:]
        with open(TLE_UPDATE_LOG_FILE, 'w') as f:
            json.dump(log, f, indent=2)
    except Exception as e:
        print(f"[TLE] Failed to log update session: {e}")

def get_update_history():
    if not TLE_UPDATE_LOG_FILE.exists():
        return []
    try:
        with open(TLE_UPDATE_LOG_FILE, 'r') as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return []

def should_skip_norad(norad: int) -> bool:
    failed = _load_failed_norads()
    norad_str = str(norad)
    if norad_str not in failed:
        return False
    entry = failed[norad_str]
    skip_until = entry.get("skip_until")
    if skip_until:
        try:
            skip_time = datetime.fromisoformat(skip_until)
            if datetime.now() < skip_time:
                return True
        except (ValueError, TypeError):
            pass
    return False

def record_failed_attempt(norad: int):
    failed = _load_failed_norads()
    norad_str = str(norad)
    if norad_str not in failed:
        failed[norad_str] = {"fail_count": 0, "last_attempt": None, "skip_until": None}
    entry = failed[norad_str]
    entry["fail_count"] = entry.get("fail_count", 0) + 1
    entry["last_attempt"] = datetime.now().isoformat()
    if entry["fail_count"] >= MAX_FAILURES_BEFORE_SKIP:
        skip_until = datetime.now() + timedelta(hours=SKIP_DURATION_HOURS)
        entry["skip_until"] = skip_until.isoformat()
        print(f"[TLE] NORAD {norad} failed {entry['fail_count']} times. Skipping until {skip_until}")
    _save_failed_norads(failed)

def reset_failed_attempts(norad: int):
    failed = _load_failed_norads()
    norad_str = str(norad)
    if norad_str in failed:
        del failed[norad_str]
        _save_failed_norads(failed)
        print(f"[TLE] Reset failure tracking for NORAD {norad} (successful download)")

# Missing NORADs tracking
_missing_norads_to_download = set()
_missing_lock = threading.Lock()
_last_n2yo_request_time = 0
_n2yo_request_lock = threading.Lock()

def schedule_missing_norad_download(norad):
    with _missing_lock:
        _missing_norads_to_download.add(norad)
    try:
        existing = []
        if MISSING_NORADS_FILE.exists():
            with open(MISSING_NORADS_FILE, 'r') as f:
                existing = json.load(f)
        if norad not in existing:
            existing.append(norad)
            with open(MISSING_NORADS_FILE, 'w') as f:
                json.dump(existing, f, indent=2)
    except Exception:
        pass

def get_pending_missing_norads():
    with _missing_lock:
        return list(_missing_norads_to_download)

def clear_missing_norads():
    with _missing_lock:
        _missing_norads_to_download.clear()
    try:
        if MISSING_NORADS_FILE.exists():
            MISSING_NORADS_FILE.unlink()
    except Exception:
        pass

def background_download_missing():
    missing = get_pending_missing_norads()
    if not missing:
        return
    print(f"[Background] Starting download of {len(missing)} missing NORADs")
    fetcher = get_tle_fetcher()
    success_count = 0
    for norad in missing:
        if should_skip_norad(norad):
            print(f"[Background] Skipping NORAD {norad} (cooldown active)")
            continue
        tle = fetcher.fetch_from_celestrak_individual(norad)
        if not tle:
            print(f"[Background] Celestrak failed for {norad}, trying N2YO...")
            tle = fetcher.fetch_from_n2yo(norad)
        if tle:
            fetcher.tles[norad] = tle
            success_count += 1
            print(f"[Background] ✅ NORAD {norad} downloaded")
            fetcher._save_to_csv()
            reset_failed_attempts(norad)
        else:
            print(f"[Background] ❌ NORAD {norad} still missing after all attempts")
            record_failed_attempt(norad)
        time.sleep(0.5)
    clear_missing_norads()
    print(f"[Background] Missing NORAD download complete: {success_count}/{len(missing)} successful")

def save_last_refresh():
    try:
        LAST_REFRESH_FILE.parent.mkdir(parents=True, exist_ok=True)
        refresh_data = {
            "last_refresh": datetime.now().isoformat(),
            "status": "success"
        }
        with open(LAST_REFRESH_FILE, 'w') as f:
            json.dump(refresh_data, f, indent=2)
    except Exception:
        pass

def _update_supplier_stats(supplier: str, success: bool, norad: int = None):
    stats = {}
    if SUPPLIER_STATS_FILE.exists():
        try:
            with open(SUPPLIER_STATS_FILE, 'r') as f:
                stats = json.load(f)
        except (json.JSONDecodeError, IOError):
            logger.warning(f"Could not read {SUPPLIER_STATS_FILE}, resetting")
            stats = {}
    if supplier not in stats:
        stats[supplier] = {"total": 0, "success": 0, "failed": 0, "last_used": None, "last_norad": None}
    stats[supplier]["total"] += 1
    if success:
        stats[supplier]["success"] += 1
    else:
        stats[supplier]["failed"] += 1
    stats[supplier]["last_used"] = datetime.now().isoformat()
    if norad:
        stats[supplier]["last_norad"] = norad
    with open(SUPPLIER_STATS_FILE, 'w') as f:
        json.dump(stats, f, indent=2)

def get_supplier_stats():
    if not SUPPLIER_STATS_FILE.exists():
        return {}
    with open(SUPPLIER_STATS_FILE, 'r') as f:
        return json.load(f)

def is_celestrak_reachable():
    """Return True if Celestrak is likely reachable, else False."""
    global _celestrak_unreachable_until
    with _celestrak_lock:
        if time.time() < _celestrak_unreachable_until:
            return False
    try:
        r = requests.head("https://celestrak.org", timeout=5)
        if r.status_code < 500:
            return True
    except requests.RequestException:
        logger.debug("Celestrak HEAD request failed")
    with _celestrak_lock:
        _celestrak_unreachable_until = time.time() + 300
    return False

class TLEFetcher:
    """Fetch TLE data with CSV cache as PRIMARY source."""
    
    def __init__(self, space_track_user=None, space_track_pass=None, n2yo_api_key=None):
        if n2yo_api_key is None:
            try:
                n2yo_api_key = st.secrets.get("N2YO_API_KEY")
                space_track_user = st.secrets.get("SPACE_TRACK_USER")
                space_track_pass = st.secrets.get("SPACE_TRACK_PASSWORD")
                print(f"[TLE Fetcher] Loaded credentials: N2YO={'✅' if n2yo_api_key else '❌'}, Space-Track={'✅' if space_track_user else '❌'}")
            except Exception as e:
                print(f"[TLE Fetcher] Could not load secrets: {e}")
                import os
                n2yo_api_key = os.environ.get("N2YO_API_KEY")
                space_track_user = os.environ.get("SPACE_TRACK_USER")
                space_track_pass = os.environ.get("SPACE_TRACK_PASSWORD")
        
        self.space_track_user = space_track_user
        self.space_track_pass = space_track_pass
        self.n2yo_api_key = n2yo_api_key
        # Space‑Track is now handled by SpaceTrackBulkFetcher (data/space_track_fetcher.py)
        self.space_track_fetcher = None
        self.space_track_available = False
        self.celestrak_session = requests.Session()
        self.celestrak_session.headers.update({"User-Agent": "OrbitShow/1.0"})
        self._ts = None
        self.generated_tle_count = 0
        self._missing_download_triggered = False
        self._celestrak_timeout_count = 0
        self._n2yo_fallback_count = 0
        
        self.tles = {}
        self._load_from_csv()
        self._ensure_cache_file()
        self._load_pending_missing()
        
        # Initialize the Space‑Track bulk fetcher (respects 60-min cooldown, off-peak timing)
        if self.space_track_user and self.space_track_pass:
            self.space_track_fetcher = SpaceTrackBulkFetcher(
                username=self.space_track_user,
                password=self.space_track_pass,
            )
            self.space_track_available = True
            print(f"[TLE Fetcher] Space‑Track bulk fetcher initialized (once-per-hour, off-peak timing)")
        
        if self.n2yo_api_key:
            print(f"[TLE Fetcher] N2YO.com API configured (automatic fallback when Celestrak fails)")
        
        print(f"[TLE Fetcher] Cache contains {len(self.tles)} valid TLEs")
    
    def _load_pending_missing(self):
        if MISSING_NORADS_FILE.exists():
            try:
                with open(MISSING_NORADS_FILE, 'r') as f:
                    missing = json.load(f)
                for norad in missing:
                    schedule_missing_norad_download(norad)
            except Exception:
                pass
    
    def _ensure_cache_file(self):
        if not CACHE_FILE.exists():
            empty_df = pd.DataFrame(columns=['norad', 'line1', 'line2', 'source', 'epoch', 'last_updated'])
            empty_df.to_csv(CACHE_FILE, index=False)
            print(f"[TLE Cache] Created empty cache file at {CACHE_FILE}")
    
    def _get_timescale(self):
        if self._ts is None:
            from skyfield.api import load
            self._ts = load.timescale()
        return self._ts
    
    def _login_space_track(self):
        """Legacy method — now handled by SpaceTrackBulkFetcher."""
        if self.space_track_fetcher is not None:
            self.space_track_available = True
            return True
        self.space_track_available = False
        return False

    def _logout_space_track(self):
        """Legacy method — now handled by SpaceTrackBulkFetcher."""
        pass  # SpaceTrackBulkFetcher manages its own session

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.celestrak_session.close()

    def fetch_from_celestrak_individual(self, norad: int, max_retries=2) -> Optional[Tuple[str, str]]:
        """Fetch TLE for a single satellite from Celestrak with fast fail."""
        if not is_celestrak_reachable():
            return None
        url = CELESTRAK_SINGLE_URL.format(norad=norad)
        for attempt in range(max_retries):
            try:
                response = self.celestrak_session.get(url, timeout=10)
                if response.status_code == 200:
                    lines = response.text.strip().split('\n')
                    if len(lines) >= 3:
                        line1 = lines[1].strip()
                        line2 = lines[2].strip()
                        if len(line1) >= 69 and len(line2) >= 69:
                            _update_supplier_stats("celestrak", success=True, norad=norad)
                            return (line1, line2)
                elif response.status_code == 404:
                    break
                else:
                    print(f"[Celestrak] Attempt {attempt+1} for NORAD {norad} returned HTTP {response.status_code}")
            except requests.exceptions.Timeout:
                print(f"[Celestrak] Timeout on attempt {attempt+1} for NORAD {norad}")
            except Exception as e:
                print(f"[Celestrak] Error on attempt {attempt+1} for NORAD {norad}: {e}")
            if attempt < max_retries - 1:
                time.sleep(1)
        _update_supplier_stats("celestrak", success=False, norad=norad)
        return None

    def fetch_bulk_from_celestrak(self, group: str = "active") -> Dict[int, Tuple[str, str]]:
        """Download all TLEs for a Celestrak group in a single request."""
        url = f"https://celestrak.org/NORAD/elements/gp.php?GROUP={group}&FORMAT=TLE"
        try:
            print(f"[Celestrak] Bulk downloading group '{group}'...")
            response = self.celestrak_session.get(url, timeout=60)
            if response.status_code != 200:
                print(f"[Celestrak] Bulk download failed: HTTP {response.status_code}")
                return {}
            lines = response.text.strip().split('\n')
            tles: Dict[int, Tuple[str, str]] = {}
            for i in range(0, len(lines) - 2, 3):
                line1 = lines[i + 1].strip()
                line2 = lines[i + 2].strip()
                if (len(line1) >= 69 and len(line2) >= 69
                        and line1.startswith('1 ') and line2.startswith('2 ')):
                    norad_str = line2[2:7].strip()
                    if norad_str.isdigit():
                        tles[int(norad_str)] = (line1, line2)
            print(f"[Celestrak] Bulk download: {len(tles)} TLEs parsed")
            _update_supplier_stats("celestrak_bulk", success=True)
            return tles
        except Exception as e:
            print(f"[Celestrak] Bulk download error: {e}")
            _update_supplier_stats("celestrak_bulk", success=False)
            return {}

    def fetch_bulk_from_space_track(self, norads: List[int]) -> Dict[int, Tuple[str, str]]:
        """
        Fetch TLEs from Space‑Track using the new bulk fetcher.
        Delegates to SpaceTrackBulkFetcher which respects:
        - 60-minute cooldown
        - Off-peak timing (avoids :00 and :30)
        - Single bulk URL with CREATION_DATE filter
        - Local filtering
        """
        if not norads:
            return {}
        if self.space_track_fetcher is None:
            print("[Space-Track] Bulk fetcher not initialized (no credentials).")
            return {}
        
        print(f"[Space-Track] Fetching TLEs for {len(norads)} NORADs via bulk fetcher...")
        try:
            result = self.space_track_fetcher.fetch(target_norads=norads)
            if result:
                print(f"[Space-Track] Bulk fetcher returned {len(result)} TLEs")
                _update_supplier_stats("space_track_bulk", success=True)
                return result
            else:
                print("[Space-Track] Bulk fetcher returned no TLEs (cooldown may be active).")
                _update_supplier_stats("space_track_bulk", success=False)
                return {}
        except Exception as e:
            print(f"[Space-Track] Bulk fetcher error: {e}")
            _update_supplier_stats("space_track_bulk", success=False)
            return {}

    def fetch(self, norad: int, force_refresh: bool = False) -> Optional[Tuple[str, str]]:
        """
        Fetch TLE with the following rules:
    
        - If force_refresh=False: return cached TLE if it is valid (not a generated placeholder).
        - If force_refresh=True: try real sources (Celestrak, N2YO) first.
            - If a real source returns a valid TLE, overwrite cache and return it.
            - If all real sources fail:
                - If the NORAD has no entry in the cache at all, generate a placeholder and store it.
                - Otherwise (cache already has an entry, even if invalid/generated), do nothing and return None.
        """
        # ---------- STEP 1: Check cache (force_refresh=False) ----------
        if not force_refresh:
            if norad in self.tles:
                cached = self.tles[norad]
                if self._is_valid_tle(cached):
                    print(f"[TLE] Returning cached TLE for NORAD {norad}")
                    return cached
                else:
                    print(f"[TLE] Cached TLE for NORAD {norad} is invalid, will refresh if force_refresh=True")
            return None
    
        # ---------- force_refresh = True ----------
        # First, try to get a real TLE from available sources
        real_tle = None
    
        # Space‑Track is not used in individual fetch (handled in bulk).
        # Try Celestrak individual (primary fallback)
        real_tle = self.fetch_from_celestrak_individual(norad)
        if not real_tle and self.n2yo_api_key:
            real_tle = self.fetch_from_n2yo(norad)
    
        # If we obtained a real TLE, overwrite cache and return it
        if real_tle and self._is_valid_tle(real_tle):
            print(f"[TLE] ✅ NORAD {norad} fetched from real source, updating cache")
            self.tles[norad] = real_tle
            self._save_to_csv()
            reset_failed_attempts(norad)
            return real_tle
    
        # ---------- All real sources failed ----------
        # Only generate a placeholder if no entry exists at all in the cache
        if norad not in self.tles:
            print(f"[TLE] ⚠️ No TLE for NORAD {norad} and all real sources failed – generating placeholder")
            gen_tle = self._generate_approximate_tle(norad)
            self.tles[norad] = gen_tle
            self._save_to_csv()
            schedule_missing_norad_download(norad)
            if not self._missing_download_triggered:
                self._missing_download_triggered = True
                thread = threading.Thread(target=background_download_missing, daemon=True)
                thread.start()
            return gen_tle
        else:
            # Already has an entry (could be a placeholder or an old valid TLE)
            # Do not overwrite it with a new placeholder.
            print(f"[TLE] ⚠️ NORAD {norad} already has a cache entry (valid or generated). "
                  f"All real sources failed – keeping existing entry.")
            # Return the existing entry (even if it's a placeholder) so that the caller
            # can still use it? But the caller expects a valid TLE for pass detection.
            # Since it's invalid, we return None to indicate failure.
            return None

    def fetch_from_n2yo(self, norad: int) -> Optional[Tuple[str, str]]:
        global _last_n2yo_request_time
        if not self.n2yo_api_key:
            return None
        with _n2yo_request_lock:
            current_time = time.time()
            time_since_last = current_time - _last_n2yo_request_time
            if time_since_last < N2YO_REQUEST_DELAY:
                time.sleep(N2YO_REQUEST_DELAY - time_since_last)
            _last_n2yo_request_time = time.time()
        try:
            url = N2YO_TLE_URL.format(norad=norad, api_key=self.n2yo_api_key)
            response = requests.get(url, timeout=(CONNECTION_TIMEOUT, READ_TIMEOUT))
            if response.status_code == 200:
                data = response.json()
                if data.get('info', {}).get('satid') == norad:
                    tle_parts = data.get('tle', '').split('\n')
                    if len(tle_parts) >= 2:
                        line1 = tle_parts[0].strip()
                        line2 = tle_parts[1].strip()
                        if len(line1) >= 69 and len(line2) >= 69:
                            self._n2yo_fallback_count += 1
                            _update_supplier_stats("n2yo", success=True, norad=norad)
                            return (line1, line2)
            _update_supplier_stats("n2yo", success=False, norad=norad)
            return None
        except Exception as e:
            print(f"[N2YO] Fetch failed for {norad}: {e}")
            _update_supplier_stats("n2yo", success=False, norad=norad)
            return None

    def _load_from_csv(self):
        """Load TLEs from CSV cache with error recovery."""
        if not CACHE_FILE.exists():
            print("[TLE Cache] No cache file found")
            return
        try:
            # Attempt to read the CSV
            df = pd.read_csv(CACHE_FILE)
            if df.empty or 'norad' not in df.columns:
                raise ValueError("Empty or malformed CSV")
            print(f"[TLE Cache] Loaded {len(df)} rows from CSV")
            valid_count = 0
            for _, row in df.iterrows():
                try:
                    norad = int(row['norad'])
                    line1 = row['line1']
                    line2 = row['line2']
                    if line1 and line2 and len(line1) >= 69 and len(line2) >= 69:
                        if not ('097.5000' in line2 and '000.0000' in line2):
                            self.tles[norad] = (line1, line2)
                            valid_count += 1
                except (ValueError, KeyError):
                    continue
            print(f"[TLE Cache] Loaded {valid_count} valid TLEs")
            if valid_count > 0:
                print(f"[TLE Cache] Ready with {valid_count} satellites in cache")
        except Exception as e:
            print(f"[TLE Cache] Could not load CSV: {e}")
            # Try to restore from backup
            self._restore_from_backup()

    def _restore_from_backup(self):
        """Restore cache from the most recent backup."""
        backup_dir = Path("data/tle_cache_backup")
        if not backup_dir.exists():
            print("[TLE Cache] No backup directory found")
            return
        backups = sorted(backup_dir.glob("tle_cache_backup_*.csv"), reverse=True)
        if not backups:
            print("[TLE Cache] No backup files found")
            return
        latest = backups[0]
        try:
            shutil.copy2(latest, CACHE_FILE)
            print(f"[TLE Cache] Restored from backup: {latest.name}")
            # Reload
            df = pd.read_csv(CACHE_FILE)
            for _, row in df.iterrows():
                try:
                    norad = int(row['norad'])
                    line1 = row['line1']
                    line2 = row['line2']
                    if line1 and line2 and len(line1) >= 69 and len(line2) >= 69:
                        if not ('097.5000' in line2 and '000.0000' in line2):
                            self.tles[norad] = (line1, line2)
                except (ValueError, KeyError):
                    continue
            print(f"[TLE Cache] Reloaded {len(self.tles)} valid TLEs from backup")
        except Exception as e:
            print(f"[TLE Cache] Failed to restore from backup: {e}")

    def _save_to_csv(self):
        """Atomic write of cache to CSV using a temporary file."""
        global _download_in_progress
        if _download_in_progress:
            # Skip saving if another thread is already writing
            return
        _download_in_progress = True
        try:
            data = []
            for norad, (line1, line2) in self.tles.items():
                data.append({
                    'norad': norad,
                    'line1': line1,
                    'line2': line2,
                    'source': 'cache',
                    'epoch': '',
                    'last_updated': datetime.now().isoformat()
                })
            if data:
                df = pd.DataFrame(data)
                # Write to temporary file first
                with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, dir=CACHE_FILE.parent) as tmp:
                    df.to_csv(tmp.name, index=False)
                    tmp_path = Path(tmp.name)
                # Replace old cache with new one
                shutil.move(str(tmp_path), str(CACHE_FILE))
                print(f"[TLE Cache] Saved {len(data)} TLEs to CSV ({CACHE_FILE.stat().st_size / 1024:.1f} KB)")
        except Exception as e:
            print(f"[TLE Cache] Error saving CSV: {e}")
        finally:
            _download_in_progress = False

    def _is_valid_tle(self, tle: Tuple[str, str]) -> bool:
        if not tle or len(tle) != 2:
            return False
        line1, line2 = tle
        if len(line1) < 69 or len(line2) < 69:
            return False
        # Check for generated placeholder pattern
        if '097.5000' in line2 and '000.0000' in line2:
            return False
        return True

    def _generate_approximate_tle(self, norad: int) -> Tuple[str, str]:
        self.generated_tle_count += 1
        epoch_year = datetime.now().year % 100
        epoch_day = datetime.now().timetuple().tm_yday
        norad_str = f"{norad:05d}"
        line1 = f"1 {norad_str}U {epoch_year:02d}{epoch_day:08.4f}  .00000000  00000-0  00000-0 0 9999"
        line2 = f"2 {norad_str} 097.5000 000.0000 0000000 000.0000 000.0000 15.20000000 9999"
        warnings.warn(f"Using generated approximate TLE for NORAD {norad}")
        print(f"[TLE] Generated approximate TLE for NORAD {norad} (total generated: {self.generated_tle_count})")
        _update_supplier_stats("generated", success=True, norad=norad)
        return (line1, line2)

    def get_period_minutes(self, tle) -> float:
        try:
            mean_motion_str = tle[1][52:63].strip()
            mean_motion = float(mean_motion_str)
            return 1440.0 / mean_motion
        except (ValueError, IndexError, TypeError):
            logger.warning(f"Could not parse mean motion from TLE, returning default 95 min")
            return 95.0

    def compute_track(self, norad, tle, start_time, end_time, step_minutes=1.0):
        try:
            from skyfield.api import EarthSatellite
            ts = self._get_timescale()
            satellite = EarthSatellite(tle[0], tle[1], f"SAT{norad}", ts)
            track_points = []
            current = start_time
            total_seconds = (end_time - start_time).total_seconds()
            total_steps = int(total_seconds / (step_minutes * 60))
            if total_steps < 1 and total_seconds > 0:
                step_minutes = total_seconds / 120.0
                total_steps = 1
            for i in range(total_steps + 1):
                try:
                    t = ts.from_datetime(current)
                    geocentric = satellite.at(t)
                    subpoint = geocentric.subpoint()
                    lat = subpoint.latitude.degrees
                    lon = subpoint.longitude.degrees
                    if lon > 180:
                        lon = lon - 360
                    track_points.append((lat, lon, current))
                    current += timedelta(minutes=step_minutes)
                except Exception:
                    continue
            return track_points
        except Exception as e:
            print(f"[Track Error] Failed to compute track for NORAD {norad}: {e}")
            return []

    def compute_position(self, norad: int, tle: Tuple[str, str], dt: datetime) -> Tuple[float, float, float]:
        try:
            from skyfield.api import EarthSatellite
            ts = self._get_timescale()
            satellite = EarthSatellite(tle[0], tle[1], f"SAT{norad}", ts)
            t = ts.from_datetime(dt)
            geocentric = satellite.at(t)
            subpoint = geocentric.subpoint()
            lat = subpoint.latitude.degrees
            lon = subpoint.longitude.degrees
            alt = subpoint.elevation.km
            if lon > 180:
                lon = lon - 360
            return (lat, lon, alt)
        except Exception as e:
            print(f"Position error for NORAD {norad}: {e}")
            return (0.0, 0.0, 0.0)

    def get_cache_age_hours(self) -> float:
        if not LAST_REFRESH_FILE.exists():
            return 9999
        try:
            with open(LAST_REFRESH_FILE, 'r') as f:
                data = json.load(f)
            last_refresh = datetime.fromisoformat(data.get("last_refresh", "2000-01-01"))
            return (datetime.now() - last_refresh).total_seconds() / 3600
        except Exception:
            return 9999

    def get_cache_status(self) -> dict:
        cache_age_hours = self.get_cache_age_hours()
        if cache_age_hours <= 24:
            accuracy = "Excellent (error < 1 km)"
        elif cache_age_hours <= 48:
            accuracy = "Good (error 1-5 km)"
        elif cache_age_hours <= 72:
            accuracy = "Fair (error 5-15 km)"
        else:
            accuracy = "Poor (error > 50 km) - Refresh needed"
        pending_missing = get_pending_missing_norads()
        return {
            "total_satellites": len(self.tles),
            "cache_file": str(CACHE_FILE),
            "cache_exists": CACHE_FILE.exists(),
            "generated_tles": self.generated_tle_count,
            "celestrak_timeouts": self._celestrak_timeout_count,
            "n2yo_fallbacks": self._n2yo_fallback_count,
            "cache_age_hours": round(cache_age_hours, 1),
            "accuracy": accuracy,
            "pending_missing_downloads": len(pending_missing),
            "space_track_available": self.space_track_available
        }

_default_fetcher = None

def get_tle_fetcher():
    global _default_fetcher
    if _default_fetcher is None:
        try:
            n2yo_api_key = st.secrets.get("N2YO_API_KEY", None)
            space_track_user = st.secrets.get("SPACE_TRACK_USER", None)
            space_track_pass = st.secrets.get("SPACE_TRACK_PASSWORD", None)
        except Exception as e:
            print(f"[TLE Fetcher] Error reading secrets: {e}")
            n2yo_api_key = None
            space_track_user = None
            space_track_pass = None
        _default_fetcher = TLEFetcher(
            space_track_user=space_track_user,
            space_track_pass=space_track_pass,
            n2yo_api_key=n2yo_api_key
        )
    return _default_fetcher