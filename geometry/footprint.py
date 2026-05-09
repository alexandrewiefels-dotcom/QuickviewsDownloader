# ============================================================================
# FILE: geometry/footprint.py – Fixed swath ribbon with antimeridian splitting
# ADDED: shift_linestring, clip_geometry_to_latitude_band for tasking visualisation
# ============================================================================
import math
from typing import List, Tuple, Optional
from shapely.geometry import Polygon, LineString, MultiPolygon, box
from shapely.validation import make_valid
from shapely.ops import unary_union
from geometry.utils import normalize_longitude, split_line_at_antimeridian

# ------------------------------------------------------------------
# Core swath creation (unchanged)
# ------------------------------------------------------------------
def create_swath_ribbon_spherical(coords: List[Tuple[float, float]], swath_km: float,
                                   lat_bounds: Optional[Tuple[float, float]] = None) -> Polygon:
    if len(coords) < 2:
        return Polygon()
    line = LineString(coords)
    segments = split_line_at_antimeridian(line)
    if not segments:
        return Polygon()
    half_deg = swath_km / 2.0 / 111.0
    buffered_parts = []
    for seg in segments:
        buffered = seg.buffer(half_deg, cap_style=2, join_style=2)
        if not buffered.is_empty:
            if buffered.geom_type == 'Polygon':
                buffered_parts.append(buffered)
            elif buffered.geom_type == 'MultiPolygon':
                buffered_parts.extend(buffered.geoms)
    if not buffered_parts:
        return Polygon()
    if len(buffered_parts) == 1:
        footprint = buffered_parts[0]
    else:
        footprint = unary_union(buffered_parts)
    if not footprint.is_valid:
        footprint = make_valid(footprint)
    if footprint.geom_type == 'MultiPolygon':
        footprint = max(footprint.geoms, key=lambda g: g.area)
    elif footprint.geom_type != 'Polygon':
        return Polygon()
    if lat_bounds:
        lat_min, lat_max = lat_bounds
        lat_band = box(-180, lat_min - 1e-6, 180, lat_max + 1e-6)
        footprint = footprint.intersection(lat_band)
        if footprint.is_empty:
            return Polygon()
        if footprint.geom_type == 'MultiPolygon':
            footprint = max(footprint.geoms, key=lambda g: g.area)
    return footprint

def create_swath_ribbon(coords: List[Tuple[float, float]], swath_km: float) -> Polygon:
    return create_swath_ribbon_spherical(coords, swath_km)

def offset_line_east_west(coords: List[Tuple[float, float]], offset_km: float, ref_lat: float) -> List[Tuple[float, float]]:
    if abs(offset_km) < 1e-6:
        return coords
    cos_lat = math.cos(math.radians(ref_lat))
    if abs(cos_lat) < 0.01:
        return coords
    km_per_deg = 111.0 * cos_lat
    delta_lon = offset_km / km_per_deg
    return [(lon + delta_lon, lat) for lon, lat in coords]

def create_offset_swath_ribbon(coords: List[Tuple[float, float]], swath_km: float, offset_km: float,
                                lat_bounds: Optional[Tuple[float, float]] = None) -> Polygon:
    if lat_bounds:
        ref_lat = (lat_bounds[0] + lat_bounds[1]) / 2.0
    else:
        ref_lat = sum(lat for lon, lat in coords) / len(coords) if coords else 0.0
    shifted_coords = offset_line_east_west(coords, offset_km, ref_lat)
    return create_swath_ribbon_spherical(shifted_coords, swath_km, lat_bounds)

# ------------------------------------------------------------------
# NEW: Helper functions for tasking visualisation (clipping & shifting)
# ------------------------------------------------------------------
def shift_linestring(line, offset_km, ref_lat):
    """Shift a LineString laterally (east-west) by a given distance (km)."""
    import math
    from shapely.geometry import LineString
    if abs(offset_km) < 1e-6:
        return line
    km_per_deg = 111.0 * math.cos(math.radians(ref_lat))
    if abs(km_per_deg) < 1e-6:
        return line
    delta_lon = offset_km / km_per_deg
    new_coords = [(lon + delta_lon, lat) for lon, lat in line.coords]
    return LineString(new_coords)

def clip_geometry_to_latitude_band(geom, min_lat, max_lat, margin_deg=0.0):
    """Clip a geometry to a latitude band with an optional margin."""
    from shapely.geometry import box
    lat_band = box(-180, min_lat - margin_deg, 180, max_lat + margin_deg)
    clipped = geom.intersection(lat_band)
    if clipped.is_empty:
        return None
    if clipped.geom_type == 'MultiPolygon':
        return max(clipped.geoms, key=lambda g: g.area)
    if clipped.geom_type == 'MultiLineString':
        return max(clipped.geoms, key=lambda ls: ls.length)
    return clipped