# File: sasclouds_api_scraper.py
"""
SASClouds API Client – AOI upload, scene search, download, georeferencing.
Supports GeoJSON, Shapefile (ZIP), KML, KMZ uploads.

Logging outputs
  logs/api_errors.log          human-readable, WARNING+ from this module
  logs/app.log                 human-readable, all levels, all modules (written by main.py)
  logs/api_interactions.jsonl  machine-readable JSONL; one record per API event
                               → load with pandas: pd.read_json("logs/api_interactions.jsonl", lines=True)
"""

import json
import logging
import re
import tempfile
import shutil
import time
import zipfile
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Dict, List, Optional

import requests
from PIL import Image
import shapefile
from shapely.geometry import shape as shapely_shape
from shapely.validation import explain_validity
from pykml import parser


# ── Satellite and sensor definitions ──────────────────────────────────────────
# ZY1F is the API identifier confirmed from a live HAR capture (2026-05-06).
# ZY1-02D / ZY1-02E are per-satellite names; both are kept because the API
# may accept either form — test and remove whichever returns no results.
SATELLITE_GROUPS = {
    "Optical": {
        "2-meter": [
            {"satelliteId": "ZY3-1",    "sensorIds": ["MUX"]},
            {"satelliteId": "ZY3-2",    "sensorIds": ["MUX"]},
            {"satelliteId": "ZY3-3",    "sensorIds": ["MUX"]},
            {"satelliteId": "ZY02C",    "sensorIds": ["HRC"]},
            {"satelliteId": "ZY1F",     "sensorIds": ["VNIC"]},
            {"satelliteId": "ZY1-02D",  "sensorIds": ["VNIC"]},
            {"satelliteId": "ZY1-02E",  "sensorIds": ["VNIC"]},
            {"satelliteId": "2m8m",     "sensorIds": ["PMS"]},
            {"satelliteId": "GF1",      "sensorIds": ["PMS"]},
            {"satelliteId": "GF6",      "sensorIds": ["PMS"]},
            {"satelliteId": "CBERS-04A","sensorIds": ["WPM"]},
            {"satelliteId": "CM1",      "sensorIds": ["DMC"]},
            {"satelliteId": "TH01",     "sensorIds": ["GFB", "DGP"]},
            {"satelliteId": "SPOT6/7",  "sensorIds": ["PMS"]},
        ],
        "Sub-meter": [
            {"satelliteId": "GF2",         "sensorIds": ["PMS"]},
            {"satelliteId": "GF7",         "sensorIds": ["MUX", "BWD", "FWD"]},
            {"satelliteId": "GFDM01",      "sensorIds": ["PMS"]},
            {"satelliteId": "JL1",         "sensorIds": ["PMS"]},
            {"satelliteId": "BJ2",         "sensorIds": ["PMS"]},
            {"satelliteId": "BJ3",         "sensorIds": ["PMS"]},
            {"satelliteId": "SV1",         "sensorIds": ["PMS"]},
            {"satelliteId": "SV2",         "sensorIds": ["PMS"]},
            {"satelliteId": "LJ3-2",       "sensorIds": ["PMS"]},
            {"satelliteId": "GeoEye-1",    "sensorIds": ["PMS"]},
            {"satelliteId": "WorldView-2", "sensorIds": ["PMS"]},
            {"satelliteId": "WorldView-3", "sensorIds": ["PMS"]},
            {"satelliteId": "WorldView-4", "sensorIds": ["PMS"]},
            {"satelliteId": "Pleiades",    "sensorIds": ["PMS"]},
            {"satelliteId": "DEIMOS",      "sensorIds": ["PMS"]},
            {"satelliteId": "KOMPSAT-2",   "sensorIds": ["PMS"]},
            {"satelliteId": "KOMPSAT-3",   "sensorIds": ["PMS"]},
            {"satelliteId": "KOMPSAT-3A",  "sensorIds": ["PMS"]},
        ],
        "Other (wide-angle)": [
            {"satelliteId": "GF1", "sensorIds": ["WFV"]},
            {"satelliteId": "GF6", "sensorIds": ["WFV"]},
            {"satelliteId": "GF4", "sensorIds": ["PMI", "IRS"]},
        ],
    },
    "Hyperspectral": {
        "Hyperspectral": [
            {"satelliteId": "ZY1-02D", "sensorIds": ["AHSI"]},
            {"satelliteId": "ZY1-02E", "sensorIds": ["AHSI"]},
            {"satelliteId": "GF5",     "sensorIds": ["AHSI"]},
            {"satelliteId": "GF5A",    "sensorIds": ["AHSI"]},
            {"satelliteId": "GF5B",    "sensorIds": ["AHSI"]},
            {"satelliteId": "GF5",     "sensorIds": ["VIMS"]},
            {"satelliteId": "LJ3-2",   "sensorIds": ["HSI"]},
            {"satelliteId": "OHS-2/3", "sensorIds": ["MSS"]},
        ],
    },
    "SAR": {
        "SAR": [
            {"satelliteId": "GF3",  "sensorIds": []},
            {"satelliteId": "CSAR", "sensorIds": []},
            {"satelliteId": "LSAR", "sensorIds": []},
        ],
    },
    "Other": {
        "Other sensors": [
            {"satelliteId": "JL-1GP", "sensorIds": ["PMS"]},
        ],
    },
}


# ── Paths ──────────────────────────────────────────────────────────────────────
LOG_DIR = Path("./logs")
LOG_DIR.mkdir(exist_ok=True)

_STRUCTURED_LOG = LOG_DIR / "api_interactions.jsonl"


# ── Loggers ───────────────────────────────────────────────────────────────────
# Root logger is configured in main.py.  We get this module's child logger and
# also attach a WARNING+ file handler so errors survive even without main.py.
logger = logging.getLogger(__name__)

if not any(
    isinstance(h, logging.FileHandler) and
    getattr(h, "baseFilename", None) == str((LOG_DIR / "api_errors.log").resolve())
    for h in logger.handlers
):
    _err_handler = logging.FileHandler(LOG_DIR / "api_errors.log", encoding="utf-8")
    _err_handler.setLevel(logging.WARNING)
    _err_handler.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)-8s] %(name)s – %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))
    logger.addHandler(_err_handler)


# ── Structured event logger ────────────────────────────────────────────────────
def _log_event(event: str, **fields) -> None:
    """
    Append one JSON line to logs/api_interactions.jsonl.

    Every record has:
      ts     – UTC timestamp (ISO-8601 with milliseconds)
      event  – event type string (e.g. 'aoi_upload_success', 'search_page')
      ...    – event-specific fields

    Load all records into a DataFrame for reporting:
      import pandas as pd
      df = pd.read_json("logs/api_interactions.jsonl", lines=True)
    """
    record = {
        "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
        "event": event,
        **fields,
    }
    try:
        with open(_STRUCTURED_LOG, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
    except OSError as exc:
        logger.warning(f"Structured log write failed: {exc}")


# ── Token scraper ──────────────────────────────────────────────────────────────
def fetch_token_from_page() -> Optional[str]:
    """
    Try to extract the auth token from the sasclouds.com homepage using a plain
    HTTP GET — no browser, instant.  Returns None when the token is not embedded
    in the HTML/JS (i.e. requires JavaScript execution or login to appear).
    """
    try:
        resp = requests.get(
            "https://www.sasclouds.com/english/normal/",
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/147.0.0.0 Safari/537.36"
                ),
                "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
            },
            timeout=15,
        )
        # Some sites set the token as a cookie which JS then forwards as a header
        for name in ("token", "Token", "TOKEN", "auth_token", "authToken"):
            val = resp.cookies.get(name)
            if val and len(val) > 10:
                logger.info(f"Token found in cookie '{name}' (length={len(val)})")
                return val
        # Token may be embedded as a JS variable in the page HTML
        for pattern in [
            r'"[Tt]oken"\s*:\s*"([A-Za-z0-9_\-\.]{20,})"',
            r"'[Tt]oken'\s*:\s*'([A-Za-z0-9_\-\.]{20,})'",
            r'[Tt]oken\s*[=:]\s*["\']([A-Za-z0-9_\-\.]{20,})["\']',
        ]:
            m = re.search(pattern, resp.text)
            if m:
                tok = m.group(1)
                logger.info(f"Token found in page HTML (length={len(tok)})")
                return tok
        logger.debug("fetch_token_from_page: token not found in HTML/cookies")
    except Exception as exc:
        logger.debug(f"fetch_token_from_page failed: {exc}")
    return None


def _save_token_to_config(token: str) -> None:
    cfg = load_config()
    cfg.setdefault("api_version", "v5")
    cfg["token"] = token
    try:
        with open("config.json", "w", encoding="utf-8") as fh:
            json.dump(cfg, fh, indent=2)
            fh.write("\n")
    except OSError as exc:
        logger.warning(f"Could not write config.json: {exc}")


def auto_login_and_capture_token(
    username: str,
    password: str,
    headless: bool = True,
    timeout_seconds: int = 90,
) -> Optional[str]:
    """
    Log in to sasclouds.com with the given credentials and capture the Token
    header from the first /api/normal/ API request.

    Login selectors are heuristic (common Chinese-site patterns). If login
    fails silently, run with headless=False to watch the browser and inspect
    the actual form selectors.

    Must be called from the MAIN process (not a background thread) on Windows
    due to asyncio constraints.  Use scrape_token.py as a subprocess wrapper.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise RuntimeError(
            "playwright not installed.\n"
            "Run:  pip install playwright && playwright install chromium"
        )

    captured: list = []

    def _on_request(request):
        if "/api/normal/" not in request.url:
            return
        tok = request.headers.get("token") or request.headers.get("Token")
        if tok and not captured:
            captured.append(tok)
            logger.info(f"Token captured after login (length={len(tok)})")

    def _try_fill(page, selectors, value, label):
        for sel in selectors:
            try:
                page.fill(sel, value, timeout=2_000)
                logger.debug(f"Filled {label!r} using selector {sel!r}")
                return True
            except Exception:
                pass
        logger.warning(f"Could not fill {label!r} — no selector matched: {selectors}")
        return False

    def _try_click(page, selectors, label):
        for sel in selectors:
            try:
                page.click(sel, timeout=2_000)
                logger.debug(f"Clicked {label!r} using selector {sel!r}")
                return True
            except Exception:
                pass
        logger.warning(f"Could not click {label!r} — no selector matched: {selectors}")
        return False

    logger.info(f"auto_login_and_capture_token: headless={headless}")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        ctx = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/147.0.0.0 Safari/537.36"
            )
        )
        page = ctx.new_page()
        page.on("request", _on_request)

        page.goto("https://www.sasclouds.com/english/normal/", timeout=30_000)
        try:
            page.wait_for_load_state("networkidle", timeout=10_000)
        except Exception:
            pass

        # Open login dialog / navigate to login page
        _try_click(page, [
            "text=Login", "text=登录", "text=Sign In",
            "a[href*='login']", ".login-btn", "#login-btn",
            "[class*='login']", "button:has-text('Login')",
        ], "open login")
        try:
            page.wait_for_load_state("networkidle", timeout=6_000)
        except Exception:
            pass

        # Username / email field
        _try_fill(page, [
            "input[name='loginName']", "input[name='username']",
            "input[name='userName']",  "input[name='email']",
            "input[type='email']",     "input[id='username']",
            "input[id='loginName']",   "input[id='email']",
            "input[placeholder*='账号']", "input[placeholder*='用户名']",
            "input[placeholder*='username' i]", "input[placeholder*='email' i]",
        ], username, "username")

        # Password field
        _try_fill(page, [
            "input[type='password']",
            "input[name='password']",
            "input[id='password']",
            "input[placeholder*='密码']",
            "input[placeholder*='password' i]",
        ], password, "password")

        # Submit
        _try_click(page, [
            "button[type='submit']", "input[type='submit']",
            "text=Login", "text=登录", "text=Sign In",
            ".login-submit", "#login-submit",
            "button:has-text('Login')", "button:has-text('登录')",
        ], "submit")
        try:
            page.wait_for_load_state("networkidle", timeout=15_000)
        except Exception:
            pass

        # Wait for a token-bearing API request
        deadline = time.monotonic() + timeout_seconds
        while not captured and time.monotonic() < deadline:
            try:
                page.wait_for_timeout(500)
            except Exception:
                break

        # If still no token, click the search button to trigger an API call
        if not captured:
            logger.info("No token yet — triggering a search click")
            _try_click(page, [
                "button:has-text('Search')", "text=Search", "text=搜索",
                ".search-btn", "#search-btn", "button[type='submit']",
            ], "search trigger")
            deadline2 = time.monotonic() + 15
            while not captured and time.monotonic() < deadline2:
                try:
                    page.wait_for_timeout(500)
                except Exception:
                    break

        browser.close()

    if not captured:
        logger.warning("auto_login_and_capture_token: no token captured")
        return None

    token = captured[0]
    _save_token_to_config(token)
    _log_event("token_auto_login", token_length=len(token), headless=headless)
    return token


def ensure_playwright_browser() -> None:
    """
    Install the Playwright Chromium browser binary if it is not already present.
    Safe to call repeatedly — Playwright is a no-op when the browser is current.
    """
    import subprocess
    import sys
    try:
        result = subprocess.run(
            [sys.executable, "-m", "playwright", "install", "chromium", "--with-deps"],
            capture_output=True, text=True, timeout=180,
        )
        if result.returncode == 0:
            logger.info("Playwright Chromium ready")
        else:
            logger.warning(f"playwright install returned {result.returncode}: {result.stderr[:300]}")
    except Exception as exc:
        logger.warning(f"Could not run playwright install: {exc}")


def scrape_token_via_browser(timeout_seconds: int = 90, headless: bool = True) -> Optional[str]:
    """
    Capture the sasclouds.com auth token without credentials.

    Strategy (escalating):
      1. Plain HTTP GET — checks HTML / server cookies instantly.
      2. Headless Chromium with anti-WAF-detection:
         a. Intercept EVERY request header for Token.
         b. Intercept EVERY response header + JSON body for Token.
         c. Read localStorage / sessionStorage after JS runs.
         d. Click Search to force an /api/normal/ call.
      All browser events print() to stdout so they appear in the parent log.
    """
    # ── Fast path ─────────────────────────────────────────────────────────────
    token = fetch_token_from_page()
    if token:
        _save_token_to_config(token)
        _log_event("token_scraped", token_length=len(token), source="http")
        return token

    print("[scrape] HTTP fast-path: no token in page HTML/cookies")

    # ── Playwright ────────────────────────────────────────────────────────────
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise RuntimeError(
            "playwright is not installed.\n"
            "Run:  pip install playwright && playwright install chromium"
        )

    captured: list = []
    seen_urls: list = []

    def _grab(value: str, source: str):
        if value and len(value) > 10 and not captured:
            captured.append(value)
            print(f"[scrape] TOKEN FOUND via {source} (length={len(value)})")

    def _on_request(request):
        url = request.url
        seen_urls.append(url)
        # Any header that looks like a token
        for h in ("token", "Token", "authorization", "Authorization", "x-token"):
            v = request.headers.get(h, "")
            if v and len(v) > 10:
                _grab(v.replace("Bearer ", ""), f"request header '{h}' → {url[:60]}")

    def _on_response(response):
        url = response.url
        # Response headers
        for h in ("token", "Token", "x-token", "X-Token",
                   "authorization", "Authorization", "x-auth-token"):
            v = response.headers.get(h, "")
            if v and len(v) > 10:
                _grab(v.replace("Bearer ", ""), f"response header '{h}' ← {url[:60]}")
        # JSON response body (for init/auth endpoints)
        ct = response.headers.get("content-type", "")
        if "application/json" in ct and not captured:
            try:
                body = response.json()
                def _search_json(obj, depth=0):
                    if depth > 4 or captured:
                        return
                    if isinstance(obj, dict):
                        for k, v in obj.items():
                            if k.lower() in ("token", "access_token", "usertoken",
                                             "auth_token", "authtoken"):
                                if isinstance(v, str) and len(v) > 10:
                                    _grab(v, f"response JSON key '{k}' ← {url[:60]}")
                                    return
                            _search_json(v, depth + 1)
                    elif isinstance(obj, list):
                        for item in obj[:5]:
                            _search_json(item, depth + 1)
                _search_json(body)
            except Exception:
                pass

    print(f"[scrape] Launching Chromium headless={headless}")
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=headless,
            args=["--disable-blink-features=AutomationControlled"],
        )
        ctx = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/147.0.0.0 Safari/537.36"
            ),
            locale="en-US",
            timezone_id="America/New_York",
        )
        # Remove navigator.webdriver flag (WAF fingerprint)
        ctx.add_init_script(
            "Object.defineProperty(navigator,'webdriver',{get:()=>undefined});"
            "window.chrome={runtime:{}};"
        )
        page = ctx.new_page()
        page.on("request",  _on_request)
        page.on("response", _on_response)

        print("[scrape] GET https://www.sasclouds.com/english/normal/")
        page.goto("https://www.sasclouds.com/english/normal/", timeout=30_000)
        try:
            page.wait_for_load_state("networkidle", timeout=12_000)
        except Exception:
            pass
        print(f"[scrape] Page loaded. Requests seen so far: {len(seen_urls)}")

        # localStorage / sessionStorage
        if not captured:
            try:
                stored = page.evaluate("""() => {
                    const keys = ['token','Token','TOKEN','auth_token','authToken',
                                  'access_token','userToken','Authorization'];
                    for (const k of keys) {
                        const v = localStorage.getItem(k) || sessionStorage.getItem(k);
                        if (v && v.length > 10) return v;
                    }
                    return null;
                }""")
                if stored:
                    _grab(stored, "localStorage/sessionStorage")
                else:
                    print("[scrape] Storage: no token key found")
            except Exception as exc:
                print(f"[scrape] Storage check failed: {exc}")

        # Click Search to force an API call
        if not captured:
            print("[scrape] Trying to click Search button…")
            clicked = False
            for sel in [
                "button:has-text('Search')", "button:has-text('搜索')",
                ".search-btn", "#search-btn",
                "input[type='submit']",  "button[type='submit']",
                "[class*='search']",
            ]:
                try:
                    page.click(sel, timeout=2_000)
                    print(f"[scrape] Clicked: {sel!r}")
                    clicked = True
                    break
                except Exception:
                    pass
            if not clicked:
                print("[scrape] No search button found — waiting for any API call")

        # Wait loop
        deadline = time.monotonic() + timeout_seconds
        while not captured and time.monotonic() < deadline:
            try:
                page.wait_for_timeout(1_000)
            except Exception:
                break

        # Diagnostic dump when token not found
        if not captured:
            print(f"[scrape] Timed out. Total URLs seen: {len(seen_urls)}")
            for u in seen_urls[:30]:
                print(f"  {u[:100]}")
            try:
                title = page.title()
                print(f"[scrape] Page title: {title!r}")
            except Exception:
                pass

        browser.close()

    if not captured:
        print("[scrape] FAILED — no token captured")
        return None

    token = captured[0]
    _save_token_to_config(token)
    _log_event("token_scraped", token_length=len(token), source="browser", headless=headless)
    print(f"[scrape] Token saved (length={len(token)})")
    return token


# ── Config ─────────────────────────────────────────────────────────────────────
def load_config(config_path: Path = Path("config.json")) -> Dict:
    if config_path.exists():
        with open(config_path) as f:
            return json.load(f)
    return {}


def _read_secret(key: str) -> Optional[str]:
    """Read a value from st.secrets if Streamlit is available, else return None."""
    try:
        import streamlit as st
        return st.secrets.get(key)
    except Exception:
        return None


# ── Activity log helpers (human-readable JSONL for admin dashboard) ─────────────
def log_search(user_session_id: str, aoi_geojson: dict, filters: dict, num_scenes: int):
    record = {
        "timestamp": datetime.now().isoformat(),
        "type": "search",
        "session_id": user_session_id,
        "aoi": aoi_geojson,
        "filters": filters,
        "num_scenes": num_scenes,
    }
    with open(LOG_DIR / "search_history.jsonl", "a") as f:
        f.write(json.dumps(record) + "\n")


def log_aoi_upload(user_session_id: str, filename: str, aoi_geojson: dict):
    record = {
        "timestamp": datetime.now().isoformat(),
        "type": "aoi_upload",
        "session_id": user_session_id,
        "filename": filename,
        "geometry": aoi_geojson,
    }
    with open(LOG_DIR / "aoi_history.jsonl", "a") as f:
        f.write(json.dumps(record) + "\n")


# ── File conversion utilities ──────────────────────────────────────────────────
def convert_uploaded_file_to_geojson(uploaded_file) -> dict:
    """Convert uploaded file (GeoJSON, Shapefile ZIP, KML, KMZ) to GeoJSON dict."""
    filename = uploaded_file.name
    content = uploaded_file.read()

    if filename.endswith(".geojson"):
        return json.loads(content)

    if filename.endswith(".zip"):
        with tempfile.TemporaryDirectory() as tmpdir:
            zip_path = Path(tmpdir) / "upload.zip"
            zip_path.write_bytes(content)
            with zipfile.ZipFile(zip_path, "r") as zf:
                zf.extractall(tmpdir)
            shp_files = list(Path(tmpdir).glob("*.shp"))
            if not shp_files:
                raise ValueError("No .shp file found in ZIP")
            sf = shapefile.Reader(shp_files[0])
            shapes = sf.shapes()
            if not shapes:
                raise ValueError("No shapes found in shapefile")
            parts = list(shapes[0].parts) + [len(shapes[0].points)]
            rings = []
            for i in range(len(parts) - 1):
                ring_pts = shapes[0].points[parts[i]:parts[i + 1]]
                rings.append([[p[0], p[1]] for p in ring_pts])
            if not rings:
                raise ValueError("No polygon coordinates found in shapefile")
            sf.close()
            return {"type": "Polygon", "coordinates": rings}

    if filename.endswith(".kml"):
        root = parser.parse(BytesIO(content)).getroot()
        ns = {"kml": "http://www.opengis.net/kml/2.2"}
        coords_elem = root.find(
            ".//kml:Polygon/kml:outerBoundaryIs/kml:LinearRing/kml:coordinates", ns
        )
        if coords_elem is None:
            raise ValueError("No polygon found in KML")
        points = [
            [float(v) for v in c.split(",")[:2]]
            for c in coords_elem.text.strip().split()
        ]
        if not points:
            raise ValueError("No coordinates in KML polygon")
        return {"type": "Polygon", "coordinates": [points]}

    if filename.endswith(".kmz"):
        with tempfile.TemporaryDirectory() as tmpdir:
            kmz_path = Path(tmpdir) / "upload.kmz"
            kmz_path.write_bytes(content)
            with zipfile.ZipFile(kmz_path, "r") as zf:
                zf.extractall(tmpdir)
            kml_files = list(Path(tmpdir).glob("*.kml"))
            if not kml_files:
                raise ValueError("No KML file found in KMZ")
            root = parser.parse(kml_files[0]).getroot()
            ns = {"kml": "http://www.opengis.net/kml/2.2"}
            coords_elem = root.find(
                ".//kml:Polygon/kml:outerBoundaryIs/kml:LinearRing/kml:coordinates", ns
            )
            if coords_elem is None:
                raise ValueError("No polygon found in KMZ")
            points = [
                [float(v) for v in c.split(",")[:2]]
                for c in coords_elem.text.strip().split()
            ]
            if not points:
                raise ValueError("No coordinates in KMZ polygon")
            return {"type": "Polygon", "coordinates": [points]}

    raise ValueError(f"Unsupported file type: {filename}")


# ── API client ─────────────────────────────────────────────────────────────────
class SASCloudsAPIClient:
    """
    HTTP client for the SASClouds REST API.

    Every outbound request is timed and its result written to two places:
      logs/app.log                 — human-readable line (DEBUG level)
      logs/api_interactions.jsonl  — structured JSONL record
    """

    # Browser headers matching the live site (Chrome 147, confirmed from HAR 2026-05-06)
    _BROWSER_HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/147.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://www.sasclouds.com/english/normal/",
        "Origin": "https://www.sasclouds.com",
        "sec-ch-ua": '"Google Chrome";v="147", "Not.A/Brand";v="8", "Chromium";v="147"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-origin",
    }

    def __init__(self, base_url: str = "https://www.sasclouds.com"):
        self.base_url = base_url
        self.session = requests.Session()
        self.session.headers.update(self._BROWSER_HEADERS)

        config = load_config()
        version = config.get("api_version") or self._init_session(base_url)
        self.api_version = version
        self.api_base = f"{base_url}/api/normal/{version}"
        self.upload_url = f"{self.api_base}/normalmeta/upload/shp"
        self.search_url = f"{self.api_base}/normalmeta"

        # Token is optional — the API works anonymously (confirmed from HAR 2026-05-06).
        # Set it if available; omit it otherwise (no Token header = anonymous browsing).
        token = config.get("token") or _read_secret("sasclouds_token")
        if token:
            self.session.headers["Token"] = token
            logger.info(f"Auth token loaded (length={len(token)})")
        else:
            logger.info("No auth token — proceeding anonymously (API is public)")

        logger.info(f"API client ready | version={version} | base={self.api_base}")

    def refresh_token(self) -> bool:
        """
        Re-fetch the auth token (HTTP fast-path first, then Playwright subprocess)
        and update the live session header.  Returns True on success.
        Called automatically when the server returns HTTP 401.
        """
        import subprocess, sys
        logger.info("Refreshing auth token…")

        # Fast path — no browser needed
        token = fetch_token_from_page()

        # Slow path — run scrape_token.py in a subprocess to avoid asyncio
        # conflicts on Windows when called from inside the Streamlit process
        if not token:
            try:
                script_path = Path(__file__).parent / "scrape_token.py"
                proc = subprocess.run(
                    [sys.executable, str(script_path), "--headless"],
                    capture_output=True, text=True, timeout=75,
                    cwd=str(Path(__file__).parent),
                )
                if proc.returncode == 0:
                    token = load_config().get("token")
            except Exception as exc:
                logger.error(f"Token refresh subprocess failed: {exc}")

        if token:
            self.session.headers["Token"] = token
            _log_event("token_refreshed", token_length=len(token))
            logger.info(f"Token refreshed (length={len(token)})")
            return True

        logger.error("Token refresh failed — all methods exhausted")
        return False

    # ── Internal HTTP helper ───────────────────────────────────────────────────

    def _http(self, method: str, url: str, **kwargs) -> requests.Response:
        """
        Perform a request, log its timing at DEBUG level, and write a structured
        event for every HTTP response (success or HTTP error alike).
        Raises on network failure; HTTP status checking is the caller's job.
        """
        t0 = time.monotonic()
        try:
            resp = self.session.request(method, url, **kwargs)
            duration_ms = round((time.monotonic() - t0) * 1000)
            logger.debug(
                f"{method} {url} → HTTP {resp.status_code} "
                f"({duration_ms}ms, {len(resp.content)}B)"
            )
            _log_event(
                "http_request",
                method=method,
                url=url,
                status=resp.status_code,
                duration_ms=duration_ms,
                response_bytes=len(resp.content),
            )
            return resp
        except Exception as exc:
            duration_ms = round((time.monotonic() - t0) * 1000)
            logger.error(f"Network error | {method} {url} | {duration_ms}ms | {exc}")
            _log_event("network_error", method=method, url=url,
                       duration_ms=duration_ms, error=str(exc))
            raise

    # ── Version detection ──────────────────────────────────────────────────────

    def _probe_api_version(self, base_url: str) -> Optional[str]:
        """Try v1–v12 with a lightweight OPTIONS request; return first non-404 version."""
        logger.info("Probing API versions v1–v12 via OPTIONS requests…")
        results: dict = {}
        for n in range(1, 13):
            v = f"v{n}"
            url = f"{base_url}/api/normal/{v}/normalmeta/upload/shp"
            try:
                r = self._http("OPTIONS", url, timeout=8)
                results[v] = r.status_code
            except Exception as exc:
                results[v] = f"ERR({exc})"
        logger.info(f"Version probe results: {results}")
        _log_event("version_probe_complete", results=results)
        for n in range(1, 13):
            v = f"v{n}"
            if isinstance(results.get(v), int) and results[v] not in (401, 403, 404):
                return v
        return None

    def _scan_js_bundles(self, base_url: str, html: str) -> Optional[str]:
        """Search up to 3 JS bundles for an embedded API version string."""
        script_srcs = re.findall(
            r'<script[^>]+src=["\']([^"\']+\.js[^"\']*)["\']', html
        )
        logger.debug(f"JS bundles found in HTML: {len(script_srcs)}")
        checked = 0
        for src in script_srcs:
            if checked >= 3:
                break
            url = (
                src if src.startswith("http")
                else base_url.rstrip("/") + "/" + src.lstrip("/")
            )
            try:
                r = self._http("GET", url, timeout=10)
                if r.status_code == 200:
                    checked += 1
                    for pattern in [r"/api/normal/(v\d+)/", r"api/normal/(v\d+)"]:
                        m = re.search(pattern, r.text)
                        if m:
                            version = m.group(1)
                            logger.info(f"API version {version!r} found in {url}")
                            return version
                    logger.debug(f"No version string in JS bundle: {url}")
            except Exception as exc:
                logger.debug(f"JS bundle fetch failed ({url}): {exc}")
        return None

    def _init_session(self, base_url: str) -> str:
        """
        GET the homepage to establish session cookies, then detect the API version.
        Detection order: HTML patterns → JS bundle scan → version probe → 'v5'.
        """
        page_url = f"{base_url}/english/normal/"
        logger.info(f"Initializing session: GET {page_url}")
        t0 = time.monotonic()
        version = "v5"
        detection_method = "fallback"
        homepage_status = None
        cookies_received: list = []

        try:
            resp = self.session.get(page_url, timeout=15)
            homepage_duration_ms = round((time.monotonic() - t0) * 1000)
            homepage_status = resp.status_code
            resp.raise_for_status()

            cookies_received = [c.name for c in self.session.cookies]
            waf_only = (
                all(k.startswith("HWWAF") for k in cookies_received)
                if cookies_received else True
            )
            logger.info(
                f"Homepage | HTTP {resp.status_code} | {len(resp.text)} chars | "
                f"{homepage_duration_ms}ms | cookies={cookies_received}"
            )
            if waf_only:
                logger.warning(
                    "Only Huawei WAF cookies received — no app session cookie. "
                    "API calls may be rejected. "
                    f"Cookies: {cookies_received}"
                )

            # 1. Direct HTML pattern match
            for pattern in [
                r"/api/normal/(v\d+)/",
                r'api/normal/(v\d+)',
                r'"apiVersion"\s*:\s*"(v\d+)"',
                r'version["\s:=]+(v\d+)',
            ]:
                m = re.search(pattern, resp.text, re.IGNORECASE)
                if m:
                    version = m.group(1)
                    detection_method = "html_pattern"
                    logger.info(
                        f"API version {version!r} detected from HTML "
                        f"(pattern={pattern!r})"
                    )
                    break

            # 2. Scan JS bundles
            if detection_method == "fallback":
                v = self._scan_js_bundles(base_url, resp.text)
                if v:
                    version = v
                    detection_method = "js_bundle"

            # 3. Active version probe
            if detection_method == "fallback":
                v = self._probe_api_version(base_url)
                if v:
                    version = v
                    detection_method = "version_probe"
                else:
                    logger.warning(
                        "All version detection methods failed — using hardcoded 'v5'. "
                        "To override permanently, create config.json: "
                        '{"api_version": "v5"}'
                    )

        except Exception as exc:
            logger.error(f"Session initialization failed: {exc}", exc_info=True)
            _log_event(
                "session_init_error",
                base_url=base_url,
                homepage_status=homepage_status,
                error=str(exc),
            )
            return "v5"

        _log_event(
            "session_init",
            base_url=base_url,
            homepage_status=homepage_status,
            homepage_duration_ms=round((time.monotonic() - t0) * 1000),
            cookies_received=cookies_received,
            waf_only_cookies=all(k.startswith("HWWAF") for k in cookies_received) if cookies_received else True,
            api_version=version,
            detection_method=detection_method,
        )
        logger.info(
            f"Session ready | version={version} | detection_method={detection_method}"
        )
        return version

    # ── Shapefile builder ──────────────────────────────────────────────────────

    def _create_shapefile(self, geojson: Dict, tmp_dir: Path) -> Path:
        logger.debug(f"Building shapefile | GeoJSON type={geojson.get('type')}")

        if geojson.get("type") == "FeatureCollection":
            if not geojson.get("features"):
                raise ValueError("FeatureCollection has no features")
            geom_data = geojson["features"][0].get("geometry")
            if not geom_data:
                raise ValueError("First feature has no geometry")
            geom = shapely_shape(geom_data)
        elif geojson.get("type") == "Feature":
            geom_data = geojson.get("geometry")
            if not geom_data:
                raise ValueError("Feature has no geometry")
            geom = shapely_shape(geom_data)
        else:
            geom = shapely_shape(geojson)

        if geom.geom_type == "MultiPolygon":
            geom = max(geom.geoms, key=lambda p: p.area)
            logger.warning("MultiPolygon input: selected the largest polygon for upload")
        elif geom.geom_type != "Polygon":
            raise ValueError(
                f"Unsupported geometry type: {geom.geom_type}. Only Polygon is supported."
            )

        if not geom.is_valid:
            reason = explain_validity(geom)
            logger.warning(f"Invalid polygon ({reason}) — attempting buffer(0) repair")
            geom = geom.buffer(0)
            if not geom.is_valid:
                raise ValueError(
                    "Polygon is invalid and could not be repaired. Please simplify the AOI."
                )

        # Simplify dense polygons — the API rejects shapes with too many vertices.
        MAX_VERTICES = 200
        n_before = len(list(geom.exterior.coords))
        if n_before > MAX_VERTICES:
            bounds_raw = geom.bounds
            tol = min(bounds_raw[2] - bounds_raw[0], bounds_raw[3] - bounds_raw[1]) / 1000
            simplified = geom.simplify(tol, preserve_topology=True)
            while len(list(simplified.exterior.coords)) > MAX_VERTICES and tol < 1.0:
                tol *= 2
                simplified = geom.simplify(tol, preserve_topology=True)
            geom = simplified
            n_after = len(list(geom.exterior.coords))
            logger.info(
                f"AOI simplified: {n_before} → {n_after} vertices (tolerance={tol:.6f}°)"
            )

        bounds = geom.bounds  # (minX, minY, maxX, maxY) = (W, S, E, N)
        n_vertices = len(list(geom.exterior.coords))
        logger.info(
            f"AOI | vertices={n_vertices} | "
            f"W={bounds[0]:.4f} S={bounds[1]:.4f} E={bounds[2]:.4f} N={bounds[3]:.4f}"
        )

        w = shapefile.Writer(tmp_dir / "aoi", shapefile.POLYGON)
        w.field("ID", "N", 10)
        w.poly([list(geom.exterior.coords)])
        w.record(1)
        w.close()

        shp_path = tmp_dir / "aoi.shp"
        return shp_path

    # ── Public API methods ─────────────────────────────────────────────────────

    def upload_aoi(self, polygon_geojson: Dict) -> str:
        """Upload AOI shapefile; returns the server uploadId."""
        logger.info(f"Uploading AOI → {self.upload_url}")
        tmp_dir = None
        files = None
        t0 = time.monotonic()
        try:
            tmp_dir = tempfile.TemporaryDirectory()
            tmp_path = Path(tmp_dir.name)
            shp_path = self._create_shapefile(polygon_geojson, tmp_path)
            try:
                shp_size = shp_path.stat().st_size
            except OSError:
                shp_size = 0
            total_upload_bytes = shp_size

            # HAR confirms the browser only sends the .shp file (not .shx/.dbf).
            files = {
                "file": ("aoi.shp", open(shp_path, "rb"), "application/octet-stream"),
            }
            logger.debug(
                f"POST multipart upload | shp={shp_size}B | "
                f"cookies={[c.name for c in self.session.cookies]}"
            )

            resp = self._http("POST", self.upload_url, files=files, timeout=30)
            duration_ms = round((time.monotonic() - t0) * 1000)

            logger.debug(
                f"Upload response | HTTP {resp.status_code} | {duration_ms}ms | "
                f"body={resp.text[:400]}"
            )
            if resp.status_code == 401:
                _log_event("auth_error", url=self.upload_url, http_status=401, body=resp.text[:300])
                logger.warning("Upload got HTTP 401 — attempting token refresh and retry")
                if self.refresh_token():
                    for _, (_, fp, _) in files.items():
                        fp.seek(0)
                    resp = self._http("POST", self.upload_url, files=files, timeout=30)
                    duration_ms = round((time.monotonic() - t0) * 1000)
                if resp.status_code == 401:
                    raise Exception(
                        'HTTP 401 – Token required and auto-refresh failed.\n'
                        '  Run  python scrape_token.py --visible  locally to capture it,\n'
                        '  then add to Streamlit secrets:  sasclouds_token = "<value>"'
                    )
            resp.raise_for_status()
            data = resp.json()

            if data.get("code") != 0:
                error_msg = data.get("message", "Unknown error")
                logger.error(
                    f"AOI upload rejected by server | code={data['code']} | "
                    f"message={error_msg!r} | full_body={resp.text[:600]}"
                )
                _log_event(
                    "aoi_upload_error",
                    url=self.upload_url,
                    http_status=resp.status_code,
                    duration_ms=duration_ms,
                    upload_bytes=total_upload_bytes,
                    api_code=data["code"],
                    api_message=error_msg,
                )
                if "out-of-range" in error_msg.lower():
                    try:
                        g = shapely_shape(polygon_geojson)
                        b = g.bounds
                        coord_hint = (
                            f"W={b[0]:.4f} S={b[1]:.4f} E={b[2]:.4f} N={b[3]:.4f}"
                        )
                        in_asia = -20 <= b[0] <= 160 and -15 <= b[1] <= 55
                        coverage_hint = (
                            "AOI is OUTSIDE typical Chinese satellite coverage "
                            "(approx lon -20–160, lat -15–55)"
                            if not in_asia else
                            "AOI is within typical coverage — likely an API version or session issue"
                        )
                    except Exception:
                        coord_hint = "(could not parse AOI bounds)"
                        coverage_hint = "unknown"
                    cookies = [c.name for c in self.session.cookies]
                    raise Exception(
                        f"AOI rejected: server returned 'out-of-range'.\n"
                        f"  API base  : {self.api_base}\n"
                        f"  AOI bounds: {coord_hint}\n"
                        f"  Coverage  : {coverage_hint}\n"
                        f"  Cookies   : {cookies}\n"
                        f"  Fix       : create config.json with {{\"api_version\": \"v5\"}}"
                    )
                raise Exception(f"Upload failed: {error_msg} (code {data['code']})")

            upload_id = data["data"]["uploadId"]
            logger.info(f"AOI uploaded | uploadId={upload_id} | {duration_ms}ms")
            _log_event(
                "aoi_upload_success",
                url=self.upload_url,
                http_status=resp.status_code,
                duration_ms=duration_ms,
                upload_id=upload_id,
                upload_bytes=total_upload_bytes,
                shp_bytes=shp_size,
                api_version=self.api_version,
            )
            return upload_id

        finally:
            if files:
                for _, (_, fp, _) in files.items():
                    try:
                        fp.close()
                    except Exception:
                        pass
            if tmp_dir:
                tmp_dir.cleanup()

    def search_scenes(
        self,
        upload_id: str,
        start_ms: int,
        end_ms: int,
        cloud_max: int,
        satellites: List[Dict],
        page: int = 1,
        page_size: int = 50,
    ) -> Dict:
        """
        POST to /normalmeta; returns the full JSON response dict.
        Payload matches the schema confirmed from the live HAR (2026-05-06):
        all four *Time fields must be present (null when unused).
        """
        payload = {
            "acquisitionTime":   [{"Start": start_ms, "End": end_ms}],
            "tarInputTimeStart": None,
            "tarInputTimeEnd":   None,
            "inputTimeStart":    None,
            "inputTimeEnd":      None,
            "cloudPercentMin":   0,
            "cloudPercentMax":   cloud_max,
            "satellites":        satellites,
            "shpUploadId":       upload_id,
            "pageNum":           page,
            "pageSize":          page_size,
        }
        sat_ids = [s["satelliteId"] for s in satellites]
        logger.info(
            f"POST normalmeta | page={page} size={page_size} | "
            f"uploadId={upload_id} | cloud≤{cloud_max}% | "
            f"satellites({len(satellites)})={sat_ids}"
        )
        logger.debug(f"Search payload: {json.dumps(payload)}")

        t0 = time.monotonic()
        try:
            resp = self._http(
                "POST", self.search_url,
                json=payload,
                headers={"Content-Type": "application/json;charset=UTF-8"},
                timeout=30,
            )
            duration_ms = round((time.monotonic() - t0) * 1000)
            if resp.status_code == 401:
                _log_event("auth_error", url=self.search_url, http_status=401, body=resp.text[:300])
                logger.warning("Search got HTTP 401 — attempting token refresh and retry")
                if self.refresh_token():
                    resp = self._http(
                        "POST", self.search_url,
                        json=payload,
                        headers={"Content-Type": "application/json;charset=UTF-8"},
                        timeout=30,
                    )
                    duration_ms = round((time.monotonic() - t0) * 1000)
                if resp.status_code == 401:
                    raise Exception(
                        'HTTP 401 – Token required and auto-refresh failed.\n'
                        '  Run  python scrape_token.py --visible  locally to capture it,\n'
                        '  then add to Streamlit secrets:  sasclouds_token = "<value>"'
                    )
            resp.raise_for_status()
            data = resp.json()

            scenes = data.get("data") or []
            page_info = data.get("pageInfo", {})
            total = page_info.get("total", 0)
            api_code = data.get("code")

            logger.info(
                f"Search page {page} | code={api_code} | "
                f"scenes={len(scenes)}/{total} | {duration_ms}ms"
            )
            _log_event(
                "search_page",
                url=self.search_url,
                http_status=resp.status_code,
                duration_ms=duration_ms,
                page=page,
                page_size=page_size,
                upload_id=upload_id,
                start_ms=start_ms,
                end_ms=end_ms,
                cloud_max=cloud_max,
                satellite_ids=sat_ids,
                satellite_count=len(satellites),
                api_code=api_code,
                scenes_returned=len(scenes),
                total_available=total,
                api_version=self.api_version,
            )

            if api_code != 0:
                msg = data.get("message", "Unknown API error")
                logger.error(
                    f"Search API error | code={api_code} | message={msg!r} | "
                    f"full_body={resp.text[:400]}"
                )
                raise Exception(f"Search API error: {msg} (code {api_code})")

            return data

        except Exception as exc:
            logger.error(f"search_scenes failed (page={page}): {exc}", exc_info=True)
            raise

    def validate_scene(self, scene: Dict) -> bool:
        """Check that all expected fields are present; logs a warning if the API schema changed."""
        required = [
            "satelliteId", "sensorId", "acquisitionTime",
            "cloudPercent", "quickViewUri", "boundary",
        ]
        missing = [k for k in required if k not in scene]
        if missing:
            logger.error(
                f"API schema change detected! "
                f"Missing fields: {missing} | "
                f"Fields present: {list(scene.keys())}"
            )
            _log_event(
                "schema_mismatch",
                missing_fields=missing,
                present_fields=list(scene.keys()),
            )
            return False
        return True

    def download_and_georeference(
        self, image_url: str, footprint_geojson: Dict, output_path: Path
    ) -> bool:
        """Download a quickview image and write JGW + PRJ sidecar files."""
        t0 = time.monotonic()
        try:
            logger.info(f"Downloading quickview: {image_url}")
            resp = self._http("GET", image_url, timeout=30)
            duration_ms = round((time.monotonic() - t0) * 1000)

            if resp.status_code != 200:
                logger.warning(
                    f"Download failed | HTTP {resp.status_code} | "
                    f"{duration_ms}ms | {image_url}"
                )
                _log_event(
                    "quickview_download_fail",
                    url=image_url,
                    http_status=resp.status_code,
                    duration_ms=duration_ms,
                )
                return False

            size_bytes = len(resp.content)
            output_path.write_bytes(resp.content)

            img = Image.open(output_path)
            width, height = img.size
            img.close()

            coords = footprint_geojson["coordinates"][0]
            lons = [c[0] for c in coords]
            lats = [c[1] for c in coords]
            left, right = min(lons), max(lons)
            top, bottom  = max(lats), min(lats)
            x_res = (right - left) / width
            y_res = (bottom - top) / height

            output_path.with_suffix(".jgw").write_text(
                "\n".join([
                    f"{x_res:.10f}", "0.0", "0.0",
                    f"{y_res:.10f}", f"{left:.10f}", f"{top:.10f}",
                ])
            )
            output_path.with_suffix(".prj").write_text(
                'GEOGCS["WGS 84",DATUM["WGS_1984",'
                'SPHEROID["WGS 84",6378137,298.257223563,AUTHORITY["EPSG","7030"]],'
                'AUTHORITY["EPSG","6326"]],PRIMEM["Greenwich",0,AUTHORITY["EPSG","8901"]],'
                'UNIT["degree",0.0174532925199433,AUTHORITY["EPSG","9122"]],'
                'AUTHORITY["EPSG","4326"]]'
            )

            logger.info(
                f"Georeferenced | {output_path.name} | {width}×{height}px | "
                f"{size_bytes/1024:.1f}KB | {duration_ms}ms"
            )
            _log_event(
                "quickview_download_success",
                url=image_url,
                output_file=output_path.name,
                http_status=resp.status_code,
                duration_ms=duration_ms,
                size_bytes=size_bytes,
                image_width=width,
                image_height=height,
                x_res_deg=round(x_res, 8),
                y_res_deg=round(y_res, 8),
            )
            return True

        except Exception as exc:
            duration_ms = round((time.monotonic() - t0) * 1000)
            logger.error(
                f"download_and_georeference failed | {image_url} | "
                f"{duration_ms}ms | {exc}",
                exc_info=True,
            )
            _log_event(
                "quickview_download_error",
                url=image_url,
                duration_ms=duration_ms,
                error=str(exc),
            )
            return False
