# File: sasclouds_api_scraper.py
"""
SASClouds API Client – handles AOI upload, scene search, download, georeferencing.
Supports GeoJSON, Shapefile (ZIP), KML, KMZ uploads.
"""

import json
import logging
import re
import tempfile
import shutil
import zipfile
from io import BytesIO
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Any

import requests
from PIL import Image
import shapefile
from shapely.geometry import shape as shapely_shape
from shapely.validation import explain_validity
from pykml import parser

# ======================================================================
# Satellite and sensor definitions (full list)
# ======================================================================
SATELLITE_GROUPS = {
    "Optical": {
        "2-meter": [
            {"satelliteId": "ZY3-1", "sensorIds": ["MUX"]},
            {"satelliteId": "ZY3-2", "sensorIds": ["MUX"]},
            {"satelliteId": "ZY3-3", "sensorIds": ["MUX"]},
            {"satelliteId": "ZY02C", "sensorIds": ["HRC"]},
            {"satelliteId": "ZY1-02D", "sensorIds": ["VNIC"]},
            {"satelliteId": "ZY1-02E", "sensorIds": ["VNIC"]},
            {"satelliteId": "2m8m", "sensorIds": ["PMS"]},
            {"satelliteId": "GF1", "sensorIds": ["PMS"]},
            {"satelliteId": "GF6", "sensorIds": ["PMS"]},
            {"satelliteId": "CBERS-04A", "sensorIds": ["WPM"]},
            {"satelliteId": "CM1", "sensorIds": ["DMC"]},
            {"satelliteId": "TH01", "sensorIds": ["GFB", "DGP"]},
            {"satelliteId": "SPOT6/7", "sensorIds": ["PMS"]},
        ],
        "Sub-meter": [
            {"satelliteId": "GF2", "sensorIds": ["PMS"]},
            {"satelliteId": "GF7", "sensorIds": ["MUX", "BWD", "FWD"]},
            {"satelliteId": "GFDM01", "sensorIds": ["PMS"]},
            {"satelliteId": "JL1", "sensorIds": ["PMS"]},
            {"satelliteId": "BJ2", "sensorIds": ["PMS"]},
            {"satelliteId": "BJ3", "sensorIds": ["PMS"]},
            {"satelliteId": "SV1", "sensorIds": ["PMS"]},
            {"satelliteId": "SV2", "sensorIds": ["PMS"]},
            {"satelliteId": "LJ3-2", "sensorIds": ["PMS"]},
            {"satelliteId": "GeoEye-1", "sensorIds": ["PMS"]},
            {"satelliteId": "WorldView-2", "sensorIds": ["PMS"]},
            {"satelliteId": "WorldView-3", "sensorIds": ["PMS"]},
            {"satelliteId": "WorldView-4", "sensorIds": ["PMS"]},
            {"satelliteId": "Pleiades", "sensorIds": ["PMS"]},
            {"satelliteId": "DEIMOS", "sensorIds": ["PMS"]},
            {"satelliteId": "KOMPSAT-2", "sensorIds": ["PMS"]},
            {"satelliteId": "KOMPSAT-3", "sensorIds": ["PMS"]},
            {"satelliteId": "KOMPSAT-3A", "sensorIds": ["PMS"]},
        ],
        "Other (wide‑angle)": [
            {"satelliteId": "GF1", "sensorIds": ["WFV"]},
            {"satelliteId": "GF6", "sensorIds": ["WFV"]},
            {"satelliteId": "GF4", "sensorIds": ["PMI", "IRS"]},
        ]
    },
    "Hyperspectral": {
        "Hyperspectral": [
            {"satelliteId": "ZY1-02D", "sensorIds": ["AHSI"]},
            {"satelliteId": "ZY1-02E", "sensorIds": ["AHSI"]},
            {"satelliteId": "GF5", "sensorIds": ["AHSI"]},
            {"satelliteId": "GF5A", "sensorIds": ["AHSI"]},
            {"satelliteId": "GF5B", "sensorIds": ["AHSI"]},
            {"satelliteId": "GF5", "sensorIds": ["VIMS"]},
            {"satelliteId": "LJ3-2", "sensorIds": ["HSI"]},
            {"satelliteId": "OHS-2/3", "sensorIds": ["MSS"]},
        ]
    },
    "SAR": {
        "SAR": [
            {"satelliteId": "GF3", "sensorIds": []},
            {"satelliteId": "CSAR", "sensorIds": []},
            {"satelliteId": "LSAR", "sensorIds": []},
        ]
    },
    "Other": {
        "Other sensors": [
            {"satelliteId": "JL-1GP", "sensorIds": ["PMS"]},
        ]
    }
}

# ----------------------------------------------------------------------
# Logging setup
# ----------------------------------------------------------------------
LOG_DIR = Path("./logs")
LOG_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(name)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_DIR / "api_errors.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ----------------------------------------------------------------------
# File conversion utilities (without geopandas/fiona)
# ----------------------------------------------------------------------
def convert_uploaded_file_to_geojson(uploaded_file) -> dict:
    """Convert uploaded file (GeoJSON, Shapefile ZIP, KML, KMZ) to GeoJSON dict."""
    filename = uploaded_file.name
    content = uploaded_file.read()
    
    if filename.endswith('.geojson'):
        return json.loads(content)
    
    if filename.endswith('.zip'):
        with tempfile.TemporaryDirectory() as tmpdir:
            zip_path = Path(tmpdir) / "upload.zip"
            zip_path.write_bytes(content)
            with zipfile.ZipFile(zip_path, 'r') as zf:
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
            for i in range(len(parts)-1):
                ring_points = shapes[0].points[parts[i]:parts[i+1]]
                rings.append([[p[0], p[1]] for p in ring_points])
            if not rings:
                raise ValueError("No polygon coordinates")
            return {"type": "Polygon", "coordinates": rings}
    
    if filename.endswith('.kml'):
        root = parser.parse(BytesIO(content)).getroot()
        ns = {"kml": "http://www.opengis.net/kml/2.2"}
        coords_elem = root.find(".//kml:Polygon/kml:outerBoundaryIs/kml:LinearRing/kml:coordinates", ns)
        if coords_elem is None:
            raise ValueError("No polygon found in KML")
        coords_text = coords_elem.text.strip()
        points = []
        for coord in coords_text.split():
            lon, lat, alt = coord.split(',')[:2]
            points.append([float(lon), float(lat)])
        if not points:
            raise ValueError("No coordinates")
        return {"type": "Polygon", "coordinates": [points]}
    
    if filename.endswith('.kmz'):
        with tempfile.TemporaryDirectory() as tmpdir:
            kmz_path = Path(tmpdir) / "upload.kmz"
            kmz_path.write_bytes(content)
            with zipfile.ZipFile(kmz_path, 'r') as zf:
                zf.extractall(tmpdir)
            kml_files = list(Path(tmpdir).glob("*.kml"))
            if not kml_files:
                raise ValueError("No KML file found in KMZ")
            root = parser.parse(kml_files[0]).getroot()
            ns = {"kml": "http://www.opengis.net/kml/2.2"}
            coords_elem = root.find(".//kml:Polygon/kml:outerBoundaryIs/kml:LinearRing/kml:coordinates", ns)
            if coords_elem is None:
                raise ValueError("No polygon found in KMZ")
            coords_text = coords_elem.text.strip()
            points = []
            for coord in coords_text.split():
                lon, lat, alt = coord.split(',')[:2]
                points.append([float(lon), float(lat)])
            if not points:
                raise ValueError("No coordinates")
            return {"type": "Polygon", "coordinates": [points]}
    
    raise ValueError(f"Unsupported file type: {filename}")

# ----------------------------------------------------------------------
# API version detection and config
# ----------------------------------------------------------------------
def detect_api_version(base_url: str = "https://www.sasclouds.com") -> str:
    try:
        logger.info(f"Detecting API version from {base_url}/english/normal/")
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
        logger.error(f"Version detection failed: {e}", exc_info=True)
        return "v5"

def load_config(config_path: Path = Path("config.json")) -> Dict:
    if config_path.exists():
        with open(config_path) as f:
            return json.load(f)
    return {}

# ----------------------------------------------------------------------
# Logging functions for admin dashboard
# ----------------------------------------------------------------------
def log_search(user_session_id: str, aoi_geojson: dict, filters: dict, num_scenes: int):
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
        """Convert any supported GeoJSON to shapefile after validating polygon."""
        logger.debug(f"Creating shapefile from GeoJSON: {geojson}")
        
        # Extract geometry
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
            logger.warning("MultiPolygon converted to largest Polygon")
        elif geom.geom_type != "Polygon":
            raise ValueError(f"Unsupported geometry type: {geom.geom_type}. Only Polygon is supported.")
        
        # Validate polygon
        if not geom.is_valid:
            logger.warning(f"Invalid polygon: {explain_validity(geom)}. Attempting to fix with buffer(0).")
            geom = geom.buffer(0)
            if not geom.is_valid:
                raise ValueError("Polygon is invalid and could not be fixed. Please simplify the AOI.")
        
        logger.info(f"Polygon bounds: minx={geom.bounds[0]}, miny={geom.bounds[1]}, maxx={geom.bounds[2]}, maxy={geom.bounds[3]}")
        
        w = shapefile.Writer(tmp_dir / "aoi", shapefile.POLYGON)
        w.field("ID", "N", 10)
        w.poly([list(geom.exterior.coords)])
        w.record(1)
        w.close()
        shp_path = tmp_dir / "aoi.shp"
        logger.debug(f"Shapefile created at {shp_path}")
        return shp_path

    def upload_aoi(self, polygon_geojson: Dict) -> str:
        logger.info("Uploading AOI...")
        try:
            with tempfile.TemporaryDirectory() as tmp:
                tmp_path = Path(tmp)
                shp_path = self._create_shapefile(polygon_geojson, tmp_path)
                files = {
                    "file": ("aoi.shp", open(shp_path, "rb"), "application/octet-stream"),
                    "file_shx": ("aoi.shx", open(shp_path.with_suffix(".shx"), "rb"), "application/octet-stream"),
                    "file_dbf": ("aoi.dbf", open(shp_path.with_suffix(".dbf"), "rb"), "application/octet-stream"),
                }
                logger.debug(f"Uploading files: {list(files.keys())}")
                resp = requests.post(self.upload_url, files=files, timeout=30)
                logger.debug(f"Upload response status: {resp.status_code}")
                resp.raise_for_status()
                data = resp.json()
                logger.debug(f"Upload response JSON: {data}")
                if data["code"] != 0:
                    error_msg = data.get("message", "Unknown error")
                    if "out-of-range" in error_msg.lower():
                        raise Exception(f"AOI out of range: The polygon may be outside the satellite coverage area. Try a smaller AOI or a region known to have data (e.g., within ±80° latitude). Details: {error_msg}")
                    raise Exception(f"Upload failed: {error_msg} (code {data['code']})")
                upload_id = data["data"]["uploadId"]
                logger.info(f"AOI uploaded successfully, ID: {upload_id}")
                return upload_id
        except Exception as e:
            logger.error(f"AOI upload failed: {e}", exc_info=True)
            raise

    def search_scenes(self, upload_id: str, start_ms: int, end_ms: int,
                      cloud_max: int, satellites: List[Dict],
                      page: int = 1, page_size: int = 50) -> Dict:
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
        logger.info(f"Searching scenes: page {page}, size {page_size}")
        logger.debug(f"Search payload: {json.dumps(payload, indent=2)}")
        try:
            resp = requests.post(self.search_url, json=payload, headers=headers, timeout=30)
            logger.debug(f"Search response status: {resp.status_code}")
            resp.raise_for_status()
            data = resp.json()
            logger.debug(f"Search response (truncated): {json.dumps(data, indent=2)[:500]}...")
            if data.get("code") != 0:
                logger.error(f"Search API returned error: {data}")
                raise Exception(f"Search API error: {data.get('message')}")
            return data
        except Exception as e:
            logger.error(f"Search failed: {e}", exc_info=True)
            raise

    def validate_scene(self, scene: Dict) -> bool:
        required = ["satelliteId", "sensorId", "acquisitionTime",
                    "cloudPercent", "quickViewUri", "boundary"]
        missing = [k for k in required if k not in scene]
        if missing:
            logger.error(f"API schema changed! Missing fields: {missing}")
            logger.error(f"Scene sample: {json.dumps(scene, indent=2)[:500]}")
            return False
        return True

    def download_and_georeference(self, image_url: str, footprint_geojson: Dict, output_path: Path) -> bool:
        try:
            logger.debug(f"Downloading image from {image_url}")
            resp = requests.get(image_url, timeout=20)
            if resp.status_code != 200:
                logger.warning(f"Failed to download {image_url}, HTTP {resp.status_code}")
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
            prj_content = 'GEOGCS["WGS 84",DATUM["WGS_1984",SPHEROID["WGS 84",6378137,298.257223563,AUTHORITY["EPSG","7030"]],AUTHORITY["EPSG","6326"]],PRIMEM["Greenwich",0,AUTHORITY["EPSG","8901"]],UNIT["degree",0.0174532925199433,AUTHORITY["EPSG","9122"]],AUTHORITY["EPSG","4326"]]'
            output_path.with_suffix(".prj").write_text(prj_content)
            logger.debug(f"Georeferenced {output_path.name}")
            return True
        except Exception as e:
            logger.error(f"Georeferencing failed for {image_url}: {e}", exc_info=True)
            return False