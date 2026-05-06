"""
SASClouds API Client – handles AOI upload, scene search, download, georeferencing.
Includes logging functions for admin dashboard.
"""

import json
import logging
import re
import tempfile
import shutil
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Any

import requests
from PIL import Image
import shapefile
from shapely.geometry import shape

# ----------------------------------------------------------------------
# Logging setup
# ----------------------------------------------------------------------
LOG_DIR = Path("./logs")
LOG_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_DIR / "api_errors.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ----------------------------------------------------------------------
# API version detection
# ----------------------------------------------------------------------
def detect_api_version(base_url: str = "https://www.sasclouds.com") -> str:
    try:
        resp = requests.get(f"{base_url}/english/normal/", timeout=10)
        resp.raise_for_status()
        match = re.search(r'/api/normal/(v\d+)/', resp.text)
        if match:
            version = match.group(1)
            logger.info(f"Detected API version: {version}")
            return version
        else:
            logger.warning("Could not detect API version, using fallback 'v5'")
            return "v5"
    except Exception as e:
        logger.error(f"Version detection failed: {e}")
        return "v5"

# ----------------------------------------------------------------------
# Configuration loader
# ----------------------------------------------------------------------
def load_config(config_path: Path = Path("config.json")) -> Dict:
    if config_path.exists():
        with open(config_path) as f:
            return json.load(f)
    return {}

# ----------------------------------------------------------------------
# Logging functions for admin dashboard
# ----------------------------------------------------------------------
def log_search(user_session_id: str, aoi_geojson: dict, filters: dict, num_scenes: int):
    """Append a search record to logs/search_history.jsonl"""
    record = {
        "timestamp": datetime.now().isoformat(),
        "type": "search",
        "session_id": user_session_id,
        "aoi": aoi_geojson,
        "filters": filters,
        "num_scenes": num_scenes
    }
    with open(LOG_DIR / "search_history.jsonl", "a") as f:
        f.write(json.dumps(record) + "\n")

def log_aoi_upload(user_session_id: str, filename: str, aoi_geojson: dict):
    """Append an AOI upload record to logs/aoi_history.jsonl"""
    record = {
        "timestamp": datetime.now().isoformat(),
        "type": "aoi_upload",
        "session_id": user_session_id,
        "filename": filename,
        "geometry": aoi_geojson
    }
    with open(LOG_DIR / "aoi_history.jsonl", "a") as f:
        f.write(json.dumps(record) + "\n")

# ----------------------------------------------------------------------
# API client class
# ----------------------------------------------------------------------
class SASCloudsAPIClient:
    def __init__(self, base_url: str = "https://www.sasclouds.com"):
        self.base_url = base_url
        config = load_config()
        version = config.get("api_version")
        if not version:
            version = detect_api_version(base_url)
        self.api_base = f"{base_url}/api/normal/{version}"
        self.upload_url = f"{self.api_base}/normalmeta/upload/shp"
        self.search_url = f"{self.api_base}/normalmeta"
        logger.info(f"Using API base: {self.api_base}")

    def _create_shapefile(self, geojson: Dict, tmp_dir: Path) -> Path:
        """Convert GeoJSON polygon to a shapefile (shp, shx, dbf)."""
        geom = shape(geojson)
        if geom.geom_type != "Polygon":
            raise ValueError("Only Polygon geometry is supported")
        w = shapefile.Writer(tmp_dir / "aoi", shapefile.POLYGON)
        w.field("ID", "N", 10)
        w.poly([list(geom.exterior.coords)])
        w.record(1)
        w.close()
        return tmp_dir / "aoi.shp"

    def upload_aoi(self, polygon_geojson: Dict) -> str:
        """Upload a GeoJSON polygon and return upload ID."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            shp_path = self._create_shapefile(polygon_geojson, tmp_path)
            files = {"file": ("aoi.shp", open(shp_path, "rb"), "application/octet-stream")}
            for ext in [".shx", ".dbf"]:
                fpath = shp_path.with_suffix(ext)
                if fpath.exists():
                    files[f"file_{ext}"] = (f"aoi{ext}", open(fpath, "rb"), "application/octet-stream")
            resp = requests.post(self.upload_url, files=files)
            resp.raise_for_status()
            data = resp.json()
            if data["code"] != 0:
                raise Exception(f"Upload failed: {data}")
            return data["data"]["uploadId"]

    def search_scenes(self, upload_id: str, start_ms: int, end_ms: int,
                      cloud_max: int, satellites: List[Dict],
                      page: int = 1, page_size: int = 50) -> Dict:
        """Search scenes via API."""
        payload = {
            "acquisitionTime": [{"Start": start_ms, "End": end_ms}],
            "cloudPercentMin": 0,
            "cloudPercentMax": cloud_max,
            "satellites": satellites,
            "shpUploadId": upload_id,
            "pageNum": page,
            "pageSize": page_size
        }
        headers = {"Content-Type": "application/json"}
        resp = requests.post(self.search_url, json=payload, headers=headers)
        resp.raise_for_status()
        return resp.json()

    def validate_scene(self, scene: Dict) -> bool:
        """Check if scene contains all required fields."""
        required = ["satelliteId", "sensorId", "acquisitionTime",
                    "cloudPercent", "quickViewUri", "boundary"]
        missing = [k for k in required if k not in scene]
        if missing:
            logger.error(f"API schema changed! Missing fields: {missing}")
            logger.error(f"Scene sample: {json.dumps(scene, indent=2)[:500]}")
            return False
        return True

    def download_and_georeference(self, image_url: str, footprint_geojson: Dict, output_path: Path) -> bool:
        """Download image and create world file (north‑up)."""
        try:
            resp = requests.get(image_url, timeout=20)
            if resp.status_code != 200:
                return False
            output_path.write_bytes(resp.content)
            img = Image.open(output_path)
            width, height = img.size
            img.close()
            coords = footprint_geojson["coordinates"][0]
            lons = [c[0] for c in coords]
            lats = [c[1] for c in coords]
            left, right = min(lons), max(lons)
            top, bottom = max(lats), min(lats)
            x_res = (right - left) / width
            y_res = (bottom - top) / height
            world_lines = [f"{x_res:.10f}", "0.0", "0.0", f"{y_res:.10f}", f"{left:.10f}", f"{top:.10f}"]
            output_path.with_suffix(".jgw").write_text("\n".join(world_lines))
            # Write PRJ (EPSG:4326)
            prj_content = 'GEOGCS["WGS 84",DATUM["WGS_1984",SPHEROID["WGS 84",6378137,298.257223563,AUTHORITY["EPSG","7030"]],AUTHORITY["EPSG","6326"]],PRIMEM["Greenwich",0,AUTHORITY["EPSG","8901"]],UNIT["degree",0.0174532925199433,AUTHORITY["EPSG","9122"]],AUTHORITY["EPSG","4326"]]'
            output_path.with_suffix(".prj").write_text(prj_content)
            return True
        except Exception as e:
            logger.error(f"Georeferencing failed for {image_url}: {e}")
            return False