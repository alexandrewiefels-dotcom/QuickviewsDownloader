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


# ── Config ─────────────────────────────────────────────────────────────────────
def load_config(config_path: Path = Path("config.json")) -> Dict:
    if config_path.exists():
        with open(config_path) as f:
            return json.load(f)
    return {}


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
        logger.info(f"API client ready | version={version} | base={self.api_base}")

    # ── Internal HTTP helper ───────────────────────────────────────────────────

    def _http(self, method: str, url: str, **kwargs) -> requests.Response:
        """
        Perform a request and log its timing at DEBUG level.
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
            if isinstance(results.get(v), int) and results[v] != 404:
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
                shx_size = shp_path.with_suffix(".shx").stat().st_size
                dbf_size = shp_path.with_suffix(".dbf").stat().st_size
            except OSError:
                shp_size = shx_size = dbf_size = 0
            total_upload_bytes = shp_size + shx_size + dbf_size

            files = {
                "file":     ("aoi.shp", open(shp_path,                       "rb"), "application/octet-stream"),
                "file_shx": ("aoi.shx", open(shp_path.with_suffix(".shx"),   "rb"), "application/octet-stream"),
                "file_dbf": ("aoi.dbf", open(shp_path.with_suffix(".dbf"),   "rb"), "application/octet-stream"),
            }
            logger.debug(
                f"POST multipart upload | shp={shp_size}B shx={shx_size}B dbf={dbf_size}B | "
                f"total={total_upload_bytes}B | cookies={[c.name for c in self.session.cookies]}"
            )

            resp = self._http("POST", self.upload_url, files=files, timeout=30)
            duration_ms = round((time.monotonic() - t0) * 1000)

            logger.debug(
                f"Upload response | HTTP {resp.status_code} | {duration_ms}ms | "
                f"body={resp.text[:400]}"
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
                shx_bytes=shx_size,
                dbf_bytes=dbf_size,
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
