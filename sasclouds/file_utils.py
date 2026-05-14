# ============================================================================
# FILE: sasclouds/file_utils.py – File conversion (GeoJSON, KML, KMZ, Shapefile ZIP)
# ============================================================================
"""
File conversion utilities for SASClouds API integration.

Supports GeoJSON, Shapefile (ZIP), KML, KMZ uploads.

Extracted from the monolithic sasclouds_api_scraper.py (1438 lines).
"""

import json
import logging
import shutil
import tempfile
import zipfile
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import shapefile
from pykml import parser
from shapely.geometry import shape as shapely_shape
from shapely.validation import explain_validity

logger = logging.getLogger(__name__)


def convert_uploaded_file_to_geojson(
    uploaded_file,
    file_type: str,
) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """
    Convert an uploaded file to a GeoJSON-like dictionary.

    Parameters
    ----------
    uploaded_file : Streamlit UploadedFile or file-like
        The uploaded file object.
    file_type : str
        One of "geojson", "kml", "kmz", "shapefile".

    Returns
    -------
    tuple
        (geojson_dict, error_message) — error_message is None on success.
    """
    try:
        if file_type == "geojson":
            return _convert_geojson(uploaded_file)
        elif file_type == "kml":
            return _convert_kml(uploaded_file)
        elif file_type == "kmz":
            return _convert_kmz(uploaded_file)
        elif file_type == "shapefile":
            return _convert_shapefile_zip(uploaded_file)
        else:
            return None, f"Unsupported file type: {file_type}"
    except Exception as e:
        logger.exception("File conversion failed for %s", file_type)
        return None, str(e)


def _convert_geojson(uploaded_file) -> Tuple[Optional[Dict], Optional[str]]:
    """Parse a GeoJSON file."""
    content = uploaded_file.read()
    if isinstance(content, bytes):
        content = content.decode("utf-8")
    geojson = json.loads(content)
    return geojson, None


def _convert_kml(uploaded_file) -> Tuple[Optional[Dict], Optional[str]]:
    """Parse a KML file and convert to GeoJSON."""
    content = uploaded_file.read()
    if isinstance(content, bytes):
        content = content.decode("utf-8")
    root = parser.fromstring(content.encode("utf-8"))
    geojson = _kml_to_geojson(root)
    return geojson, None


def _convert_kmz(uploaded_file) -> Tuple[Optional[Dict], Optional[str]]:
    """Extract KML from KMZ and convert to GeoJSON."""
    with zipfile.ZipFile(BytesIO(uploaded_file.read())) as zf:
        kml_files = [n for n in zf.namelist() if n.endswith(".kml")]
        if not kml_files:
            return None, "No KML file found inside KMZ archive."
        with zf.open(kml_files[0]) as kml_file:
            content = kml_file.read().decode("utf-8")
    root = parser.fromstring(content.encode("utf-8"))
    geojson = _kml_to_geojson(root)
    return geojson, None


def _convert_shapefile_zip(uploaded_file) -> Tuple[Optional[Dict], Optional[str]]:
    """Extract Shapefile from ZIP and convert to GeoJSON."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        with zipfile.ZipFile(BytesIO(uploaded_file.read())) as zf:
            zf.extractall(tmp_path)
        shp_files = list(tmp_path.glob("*.shp"))
        if not shp_files:
            return None, "No .shp file found inside ZIP archive."
        reader = shapefile.Reader(str(shp_files[0]))
        geojson = _shapefile_to_geojson(reader)
    return geojson, None


def _kml_to_geojson(kml_root) -> Dict[str, Any]:
    """
    Convert a pyKML parsed KML document to a simple GeoJSON FeatureCollection.
    Only handles Polygon and MultiPolygon geometries.
    """
    features = []
    placemarks = kmml_root.Document.Folder.Placemark if hasattr(kml_root, 'Document') else []
    if not placemarks:
        placemarks = kmml_root.Document.Placemark if hasattr(kml_root, 'Document') else []

    for pm in placemarks if placemarks else []:
        try:
            geom = _extract_kml_geometry(pm)
            if geom:
                features.append({
                    "type": "Feature",
                    "geometry": geom,
                    "properties": {"name": str(pm.name) if hasattr(pm, 'name') else ""},
                })
        except Exception:
            continue

    return {"type": "FeatureCollection", "features": features}


def _extract_kml_geometry(placemark) -> Optional[Dict]:
    """Extract geometry from a KML Placemark."""
    try:
        polygon = placemark.Polygon
        coords = polygon.outerBoundaryIs.LinearRing.coordinates.text.strip()
        points = [
            [float(p.split(",")[0]), float(p.split(",")[1])]
            for p in coords.split()
        ]
        return {"type": "Polygon", "coordinates": [points]}
    except AttributeError:
        pass

    try:
        multipoly = placemark.MultiGeometry
        polygons = []
        for poly in multipoly.Polygon:
            coords = poly.outerBoundaryIs.LinearRing.coordinates.text.strip()
            points = [
                [float(p.split(",")[0]), float(p.split(",")[1])]
                for p in coords.split()
            ]
            polygons.append(points)
        return {"type": "MultiPolygon", "coordinates": [polygons]}
    except AttributeError:
        pass

    return None


def _shapefile_to_geojson(reader) -> Dict[str, Any]:
    """Convert a pyshp Reader to a GeoJSON FeatureCollection."""
    features = []
    for srec in reader.shapeRecords():
        shape = srec.shape
        props = dict(zip(
            [f[0] for f in reader.fields[1:]],
            srec.record
        ))
        geojson_geom = _pyshp_shape_to_geojson(shape)
        if geojson_geom:
            features.append({
                "type": "Feature",
                "geometry": geojson_geom,
                "properties": props,
            })
    return {"type": "FeatureCollection", "features": features}


def _pyshp_shape_to_geojson(shape) -> Optional[Dict]:
    """Convert a pyshp Shape to a GeoJSON geometry dict."""
    shape_type = shape.shapeType
    if shape_type in (5, 15):  # Polygon, PolygonZ
        coords = []
        for part in shape.parts:
            end = list(shape.parts[shape.parts.index(part) + 1:]) + [len(shape.points)]
            ring = [[p[0], p[1]] for p in shape.points[part:end[0]]]
            coords.append(ring)
        return {"type": "Polygon", "coordinates": coords}
    elif shape_type in (3, 13):  # PolyLine, PolyLineZ
        coords = []
        for part in shape.parts:
            end = list(shape.parts[shape.parts.index(part) + 1:]) + [len(shape.points)]
            line = [[p[0], p[1]] for p in shape.points[part:end[0]]]
            coords.append(line)
        return {"type": "MultiLineString", "coordinates": coords}
    elif shape_type in (1, 11):  # Point, PointZ
        return {"type": "Point", "coordinates": [shape.points[0][0], shape.points[0][1]]}
    return None
