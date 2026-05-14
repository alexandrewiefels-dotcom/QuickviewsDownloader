# ============================================================================
# FILE: data/space_track_fetcher.py – Space‑Track bulk TLE fetcher
#
# Implements the "Once-per-Hour" rule with off-peak timing as required by
# Space‑Track's usage policy. Uses a single bulk query URL to download all
# TLEs updated in the last hour, then filters locally.
#
# Key constraints (per Space‑Track emails):
#   - The gp class may only be queried once per hour.
#   - Prohibited: Querying the same object multiple times.
#   - Required: Using the CREATION_DATE/>now-0.042 filter.
#   - Stay 10–25 minutes away from :00 and :30 marks.
# ============================================================================
import json
import logging
import random
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import requests

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# The ONLY URL we use for Space‑Track queries (bulk, time-filtered)
SPACE_TRACK_BULK_URL = (
    "https://www.space-track.org/basicspacedata/query"
    "/class/gp/decay_date/null-val"
    "/CREATION_DATE/%3Enow-0.042"
    "/format/tle"
)

SPACE_TRACK_AUTH_URL = "https://www.space-track.org/ajaxauth/login"
SPACE_TRACK_LOGOUT_URL = "https://www.space-track.org/ajaxauth/logout"

# Cooldown: 60 minutes between successful downloads
COOLDOWN_SECONDS = 3600  # 60 minutes

# Off-peak windows (minutes past the hour when it's safe to query)
# We avoid :00 and :30 by at least 10 minutes.
# Safe windows: :10–:20 and :40–:50
OFF_PEAK_WINDOWS = [
    (10, 20),   # 10-20 minutes past the hour
    (40, 50),   # 40-50 minutes past the hour
]

# Jitter: random delay of 1-5 minutes before any automated request
JITTER_MIN = 60    # 1 minute
JITTER_MAX = 300   # 5 minutes

# Local cache file for the last bulk download result
BULK_CACHE_FILE = Path("data/space_track_bulk_cache.json")
COOLDOWN_FILE = Path("data/space_track_cooldown.json")

# Connection settings
CONNECTION_TIMEOUT = 15
READ_TIMEOUT = 60

# ---------------------------------------------------------------------------
# Cooldown & timing helpers
# ---------------------------------------------------------------------------

def _load_cooldown() -> Optional[datetime]:
    """Load the timestamp of the last successful download from disk."""
    if not COOLDOWN_FILE.exists():
        return None
    try:
        with open(COOLDOWN_FILE, "r") as f:
            data = json.load(f)
        ts = data.get("last_download")
        if ts:
            return datetime.fromisoformat(ts)
    except (json.JSONDecodeError, IOError, ValueError):
        logger.warning("Could not read cooldown file, ignoring.")
    return None


def _save_cooldown():
    """Persist the current timestamp as the last successful download time."""
    try:
        COOLDOWN_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(COOLDOWN_FILE, "w") as f:
            json.dump({"last_download": datetime.now().isoformat()}, f)
    except (IOError, OSError) as e:
        logger.warning(f"Could not save cooldown: {e}")


def _is_cooldown_active() -> bool:
    """Return True if we are still within the 60-minute cooldown window."""
    last = _load_cooldown()
    if last is None:
        return False
    elapsed = (datetime.now() - last).total_seconds()
    return elapsed < COOLDOWN_SECONDS


def _seconds_until_cooldown_ends() -> float:
    """Return the number of seconds until the cooldown expires (0 if already expired)."""
    last = _load_cooldown()
    if last is None:
        return 0
    elapsed = (datetime.now() - last).total_seconds()
    remaining = COOLDOWN_SECONDS - elapsed
    return max(0, remaining)


def _is_off_peak() -> bool:
    """Return True if the current time is within an off-peak window."""
    now = datetime.now()
    minutes_past = now.minute + now.second / 60.0
    for start, end in OFF_PEAK_WINDOWS:
        if start <= minutes_past <= end:
            return True
    return False


def _wait_until_off_peak():
    """Sleep until the next off-peak window if we are currently in a peak period."""
    if _is_off_peak():
        return  # Already in a safe window

    now = datetime.now()
    minutes_past = now.minute + now.second / 60.0

    # Find the next off-peak window
    next_start = None
    for start, end in OFF_PEAK_WINDOWS:
        if minutes_past < start:
            next_start = start
            break

    if next_start is None:
        # Past the last window today; next window is tomorrow at :10
        next_start = OFF_PEAK_WINDOWS[0][0] + 60  # +60 minutes = next hour

    # Calculate sleep duration
    target_minutes = next_start
    target_time = now.replace(minute=0, second=0, microsecond=0) + timedelta(minutes=target_minutes)
    if target_time <= now:
        target_time += timedelta(hours=1)

    sleep_seconds = (target_time - now).total_seconds()
    logger.info(
        "Waiting %.0f seconds until next off-peak window (%d min past the hour)...",
        sleep_seconds, target_minutes,
    )
    time.sleep(sleep_seconds)


def _apply_jitter():
    """Sleep for a random duration between JITTER_MIN and JITTER_MAX seconds."""
    delay = random.uniform(JITTER_MIN, JITTER_MAX)
    logger.info("Applying jitter: sleeping %.0f seconds...", delay)
    time.sleep(delay)


# ---------------------------------------------------------------------------
# Bulk cache (local storage of the last bulk download)
# ---------------------------------------------------------------------------

def _load_bulk_cache() -> Dict[int, Tuple[str, str]]:
    """Load the last bulk download result from disk."""
    if not BULK_CACHE_FILE.exists():
        return {}
    try:
        with open(BULK_CACHE_FILE, "r") as f:
            raw = json.load(f)
        result = {}
        for norad_str, tle_data in raw.items():
            norad = int(norad_str)
            line1 = tle_data.get("line1", "")
            line2 = tle_data.get("line2", "")
            if line1 and line2 and len(line1) >= 69 and len(line2) >= 69:
                result[norad] = (line1, line2)
        logger.debug("Loaded %d TLEs from bulk cache", len(result))
        return result
    except (json.JSONDecodeError, IOError, ValueError) as e:
        logger.warning("Could not load bulk cache: %s", e)
        return {}


def _save_bulk_cache(tles: Dict[int, Tuple[str, str]]):
    """Persist the bulk download result to disk."""
    try:
        BULK_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        serializable = {}
        for norad, (line1, line2) in tles.items():
            serializable[str(norad)] = {"line1": line1, "line2": line2}
        with open(BULK_CACHE_FILE, "w") as f:
            json.dump(serializable, f, indent=2)
        logger.info("Saved %d TLEs to bulk cache (%s)", len(tles), BULK_CACHE_FILE)
    except (IOError, OSError) as e:
        logger.warning("Could not save bulk cache: %s", e)


# ---------------------------------------------------------------------------
# Space‑Track session management
# ---------------------------------------------------------------------------

class SpaceTrackSession:
    """Manages a Space‑Track authenticated session."""

    def __init__(self, username: Optional[str], password: Optional[str]):
        self.username = username
        self.password = password
        self._session: Optional[requests.Session] = None
        self._authenticated = False

    @property
    def is_authenticated(self) -> bool:
        return self._authenticated and self._session is not None

    def login(self) -> bool:
        """Authenticate with Space‑Track. Returns True on success."""
        if not self.username or not self.password:
            logger.warning("Space‑Track credentials not configured.")
            return False

        if self.is_authenticated:
            return True

        try:
            self._session = requests.Session()
            auth_data = {"identity": self.username, "password": self.password}
            logger.info("Logging in to Space‑Track as %s...", self.username)
            response = self._session.post(
                SPACE_TRACK_AUTH_URL, data=auth_data, timeout=CONNECTION_TIMEOUT
            )
            if response.status_code == 200:
                self._authenticated = True
                logger.info("Space‑Track login successful.")
                return True
            else:
                logger.error("Space‑Track login failed: HTTP %d", response.status_code)
                self._session = None
                return False
        except requests.RequestException as e:
            logger.error("Space‑Track login error: %s", e)
            self._session = None
            return False

    def logout(self):
        """Log out from Space‑Track."""
        if self._session:
            try:
                self._session.get(SPACE_TRACK_LOGOUT_URL, timeout=CONNECTION_TIMEOUT)
                logger.info("Space‑Track logged out.")
            except requests.RequestException as e:
                logger.warning("Space‑Track logout error (non‑fatal): %s", e)
            finally:
                self._session.close()
                self._session = None
                self._authenticated = False

    def get_session(self) -> Optional[requests.Session]:
        """Return the authenticated session, or None."""
        if self.is_authenticated:
            return self._session
        if self.login():
            return self._session
        return None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.logout()


# ---------------------------------------------------------------------------
# Main fetcher class
# ---------------------------------------------------------------------------

class SpaceTrackBulkFetcher:
    """
    Space‑Track bulk TLE fetcher that respects the "once-per-hour" rule.

    Usage:
        fetcher = SpaceTrackBulkFetcher(username, password)
        tles = fetcher.fetch()  # Returns Dict[int, Tuple[str, str]]

    The fetcher will:
    1. Check local cache first.
    2. If cache is older than 60 minutes AND we are in an off-peak window,
       perform a single bulk download.
    3. Filter the bulk result locally to find the satellites we need.
    4. Fall back to the last known TLE for satellites not in the bulk update.
    """

    def __init__(
        self,
        username: Optional[str] = None,
        password: Optional[str] = None,
    ):
        self._session_mgr = SpaceTrackSession(username, password)
        self._bulk_cache: Dict[int, Tuple[str, str]] = _load_bulk_cache()
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def fetch(self, target_norads: Optional[List[int]] = None) -> Dict[int, Tuple[str, str]]:
        """
        Fetch TLEs for the given NORADs (or all cached if None).

        Returns a dict of {norad: (line1, line2)} with the best available data.
        """
        with self._lock:
            return self._fetch_internal(target_norads)

    def force_refresh(self, target_norads: Optional[List[int]] = None) -> Dict[int, Tuple[str, str]]:
        """
        Force a bulk download from Space‑Track, ignoring cooldown.
        Use sparingly — only for manual admin operations.
        """
        with self._lock:
            logger.info("Force refresh requested — bypassing cooldown.")
            return self._do_bulk_download(target_norads)

    def get_cache_status(self) -> dict:
        """Return a status dict for display purposes."""
        with self._lock:
            cooldown_active = _is_cooldown_active()
            remaining = _seconds_until_cooldown_ends()
            off_peak = _is_off_peak()
            return {
                "cached_tles": len(self._bulk_cache),
                "cooldown_active": cooldown_active,
                "cooldown_remaining_seconds": round(remaining),
                "cooldown_remaining_minutes": round(remaining / 60, 1),
                "off_peak": off_peak,
                "next_off_peak_window": self._next_off_peak_description(),
            }

    def clear_cache(self):
        """Clear the local bulk cache (does NOT affect the CSV TLE cache)."""
        with self._lock:
            self._bulk_cache.clear()
            if BULK_CACHE_FILE.exists():
                BULK_CACHE_FILE.unlink()
            logger.info("Bulk cache cleared.")

    # ------------------------------------------------------------------
    # Internal logic
    # ------------------------------------------------------------------

    def _fetch_internal(self, target_norads: Optional[List[int]]) -> Dict[int, Tuple[str, str]]:
        """
        Core fetch logic:
        1. If cooldown is active, return cached data.
        2. If not off-peak, wait until next off-peak window.
        3. Perform bulk download.
        4. Filter locally for target NORADs.
        5. Fall back to cached TLEs for missing satellites.
        """
        # --- Step 1: Check cooldown ---
        if _is_cooldown_active():
            remaining = _seconds_until_cooldown_ends()
            logger.info(
                "Cooldown active (%.0f seconds remaining). Returning cached data.",
                remaining,
            )
            return self._filter_for_targets(target_norads)

        # --- Step 2: Wait for off-peak window ---
        _wait_until_off_peak()

        # --- Step 3: Apply jitter ---
        _apply_jitter()

        # --- Step 4: Perform bulk download ---
        return self._do_bulk_download(target_norads)

    def _do_bulk_download(
        self, target_norads: Optional[List[int]]
    ) -> Dict[int, Tuple[str, str]]:
        """
        Execute the actual bulk download from Space‑Track.
        Updates the local cache and cooldown on success.
        """
        session = self._session_mgr.get_session()
        if not session:
            logger.warning("No Space‑Track session available. Returning cached data.")
            return self._filter_for_targets(target_norads)

        try:
            logger.info("Performing bulk download from Space‑Track...")
            logger.debug("URL: %s", SPACE_TRACK_BULK_URL)

            response = session.get(
                SPACE_TRACK_BULK_URL, timeout=(CONNECTION_TIMEOUT, READ_TIMEOUT)
            )

            if response.status_code != 200:
                logger.error(
                    "Space‑Track bulk download failed: HTTP %d. Returning cached data.",
                    response.status_code,
                )
                return self._filter_for_targets(target_norads)

            # Parse the TLE data
            lines = response.text.strip().split("\n")
            logger.info("Downloaded %d lines from Space‑Track.", len(lines))

            new_tles: Dict[int, Tuple[str, str]] = {}
            for i in range(0, len(lines), 3):
                if i + 2 >= len(lines):
                    break
                line1 = lines[i + 1].strip()
                line2 = lines[i + 2].strip()
                if len(line2) >= 7 and line2.startswith("2 "):
                    norad_str = line2[2:7].strip()
                    if norad_str.isdigit():
                        norad = int(norad_str)
                        if len(line1) >= 69 and len(line2) >= 69:
                            new_tles[norad] = (line1, line2)

            logger.info(
                "Parsed %d TLEs from bulk download (%.1f KB).",
                len(new_tles),
                len(response.content) / 1024,
            )

            if new_tles:
                # Update the local cache with the new data
                self._bulk_cache.update(new_tles)
                _save_bulk_cache(self._bulk_cache)
                _save_cooldown()
                logger.info("Bulk cache updated and cooldown saved.")
            else:
                logger.warning("Bulk download returned 0 TLEs. Keeping existing cache.")

            return self._filter_for_targets(target_norads)

        except requests.RequestException as e:
            logger.error("Space‑Track bulk download error: %s", e)
            return self._filter_for_targets(target_norads)

    def _filter_for_targets(
        self, target_norads: Optional[List[int]]
    ) -> Dict[int, Tuple[str, str]]:
        """
        Filter the bulk cache for the requested NORADs.
        If a NORAD is not in the bulk cache, it is simply omitted
        (the caller should fall back to its own cache).
        """
        if target_norads is None:
            # Return everything we have
            return dict(self._bulk_cache)

        result = {}
        for norad in target_norads:
            if norad in self._bulk_cache:
                result[norad] = self._bulk_cache[norad]
        return result

    @staticmethod
    def _next_off_peak_description() -> str:
        """Return a human-readable description of the next off-peak window."""
        now = datetime.now()
        minutes_past = now.minute + now.second / 60.0

        for start, end in OFF_PEAK_WINDOWS:
            if minutes_past < start:
                return f"{start}-{end} min past the hour (in {start - minutes_past:.0f} min)"
            elif start <= minutes_past <= end:
                return f"Now ({start}-{end} min past the hour)"

        # Past the last window; next is at :10 of the next hour
        return f"10-20 min past the next hour (in {60 - minutes_past + 10:.0f} min)"


# ---------------------------------------------------------------------------
# Singleton accessor
# ---------------------------------------------------------------------------

_default_fetcher: Optional[SpaceTrackBulkFetcher] = None
_fetcher_lock = threading.Lock()


def get_space_track_fetcher(
    username: Optional[str] = None,
    password: Optional[str] = None,
) -> SpaceTrackBulkFetcher:
    """Get or create the singleton SpaceTrackBulkFetcher."""
    global _default_fetcher
    with _fetcher_lock:
        if _default_fetcher is None:
            _default_fetcher = SpaceTrackBulkFetcher(
                username=username, password=password
            )
        return _default_fetcher


def reset_space_track_fetcher():
    """Reset the singleton (useful for testing or credential changes)."""
    global _default_fetcher
    with _fetcher_lock:
        if _default_fetcher is not None:
            _default_fetcher._session_mgr.logout()
        _default_fetcher = None
