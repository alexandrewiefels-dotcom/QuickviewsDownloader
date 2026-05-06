"""
SASClouds API Scraper – uses the official API, no browser needed.
Features: AOI upload (shapefile), scene search, georeferenced image download.
"""

import json
import tempfile
import shutil
from pathlib import Path
from datetime import datetime
import requests
from PIL import Image
import shapefile  # pyshp

# ----------------------------------------------------------------------
# API endpoints
# ----------------------------------------------------------------------
BASE_URL = "https://www.sasclouds.com"
UPLOAD_URL = f"{BASE_URL}/api/normal/v5/normalmeta/upload/shp"
SEARCH_URL = f"{BASE_URL}/api/normal/v5/normalmeta"

# ----------------------------------------------------------------------
# Helper functions
# ----------------------------------------------------------------------
def date_to_ms(year: int, month: int, day: int) -> int:
    """Convert date to milliseconds since epoch (UTC)."""
    dt = datetime(year, month, day)
    return int(dt.timestamp() * 1000)

def create_shapefile_from_geojson(geojson: dict, tmp_dir: Path) -> Path:
    """
    Convert a GeoJSON polygon to a shapefile (shp, shx, dbf) in a temporary folder.
    Returns the path to the .shp file.
    """
    from shapely.geometry import shape
    geom = shape(geojson)
    if geom.geom_type != "Polygon":
        raise ValueError("Only Polygon geometry is supported for AOI")
    # Create shapefile writer
    w = shapefile.Writer(tmp_dir / "aoi", shapefile.POLYGON)
    w.field("ID", "N", 10)
    w.poly([list(geom.exterior.coords)])
    w.record(1)
    w.close()
    return tmp_dir / "aoi.shp"

def upload_aoi(polygon_geojson: dict) -> str:
    """
    Upload a polygon (GeoJSON) to SASClouds and return the upload ID.
    """
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        shp_path = create_shapefile_from_geojson(polygon_geojson, tmp_path)
        # Also need .shx and .dbf files – they are created by shapefile.Writer
        files = {
            "file": ("aoi.shp", open(shp_path, "rb"), "application/octet-stream")
        }
        # Add .shx and .dbf if they exist
        for ext in [".shx", ".dbf"]:
            fpath = shp_path.with_suffix(ext)
            if fpath.exists():
                files[f"file"] = (f"aoi{ext}", open(fpath, "rb"), "application/octet-stream")
        resp = requests.post(UPLOAD_URL, files=files)
        resp.raise_for_status()
        data = resp.json()
        if data["code"] != 0:
            raise Exception(f"Upload failed: {data}")
        return data["data"]["uploadId"]

def search_scenes(upload_id: str, start_ms: int, end_ms: int, cloud_max: int,
                  satellites: list, page: int = 1, page_size: int = 50) -> dict:
    """Call the search API and return the JSON response."""
    payload = {
        "acquisitionTime": [{"Start": start_ms, "End": end_ms}],
        "tarInputTimeStart": None,
        "tarInputTimeEnd": None,
        "inputTimeStart": None,
        "inputTimeEnd": None,
        "cloudPercentMin": 0,
        "cloudPercentMax": cloud_max,
        "satellites": satellites,
        "shpUploadId": upload_id,
        "pageNum": page,
        "pageSize": page_size
    }
    headers = {"Content-Type": "application/json"}
    resp = requests.post(SEARCH_URL, json=payload, headers=headers)
    resp.raise_for_status()
    return resp.json()

def download_and_georeference(image_url: str, footprint_geojson: dict, output_path: Path) -> bool:
    """
    Download the full‑size quickview and create a world file (.jgw) using the footprint polygon.
    The world file is computed using the top‑left, top‑right and bottom‑left corner of the image.
    Assumes the image is oriented north‑up (no rotation). If rotation is present, you would need
    the three‑point affine method. The API provides only four corners, which is sufficient for a
    north‑up world file.
    """
    try:
        resp = requests.get(image_url, timeout=20)
        if resp.status_code != 200:
            return False
        output_path.write_bytes(resp.content)

        # Read image size
        img = Image.open(output_path)
        width, height = img.size
        img.close()

        # Extract polygon corners from GeoJSON
        coords = footprint_geojson["coordinates"][0]
        # corners: 0=top-left, 1=top-right, 2=bottom-right, 3=bottom-left (assuming clockwise)
        # But GeoJSON order may vary; we use min/max lat/lon to find corners.
        lons = [c[0] for c in coords]
        lats = [c[1] for c in coords]
        left = min(lons)
        right = max(lons)
        top = max(lats)
        bottom = min(lats)

        # Pixel size
        x_res = (right - left) / width
        y_res = (bottom - top) / height   # negative

        world_lines = [
            f"{x_res:.10f}",
            "0.0",
            "0.0",
            f"{y_res:.10f}",
            f"{left:.10f}",
            f"{top:.10f}"
        ]
        world_path = output_path.with_suffix(".jgw")
        world_path.write_text("\n".join(world_lines))

        # PRJ file (EPSG:4326)
        prj_path = output_path.with_suffix(".prj")
        prj_content = (
            'GEOGCS["WGS 84",'
            'DATUM["WGS_1984",'
            'SPHEROID["WGS 84",6378137,298.257223563,'
            'AUTHORITY["EPSG","7030"]],'
            'AUTHORITY["EPSG","6326"]],'
            'PRIMEM["Greenwich",0,'
            'AUTHORITY["EPSG","8901"]],'
            'UNIT["degree",0.0174532925199433,'
            'AUTHORITY["EPSG","9122"]],'
            'AUTHORITY["EPSG","4326"]]'
        )
        prj_path.write_text(prj_content)
        return True
    except Exception as e:
        print(f"Error downloading/georeferencing {image_url}: {e}")
        return False