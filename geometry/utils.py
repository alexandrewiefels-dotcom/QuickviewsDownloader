# ============================================================================
# FILE: geometry/utils.py – Fixed antimeridian handling, no circular import
# ADDED: clip_geometry_to_latitude_band() – used once at source
# ============================================================================
from shapely.geometry import Polygon, MultiPolygon, LineString, box
from shapely.validation import make_valid

def normalize_longitude(lon: float) -> float:
    """Normalize longitude to [-180, 180]."""
    return ((lon + 180) % 360) - 180

def clip_line_to_latitude_band(line: LineString, min_lat: float, max_lat: float) -> LineString:
    band = box(-180, min_lat, 180, max_lat)
    clipped = line.intersection(band)
    if clipped.is_empty:
        return LineString()
    if clipped.geom_type == 'LineString':
        return clipped
    elif clipped.geom_type == 'MultiLineString':
        return max(clipped.geoms, key=lambda ls: ls.length)
    else:
        return LineString()

def split_line_at_antimeridian(line: LineString) -> list:
    coords = list(line.coords)
    if len(coords) < 2:
        return [line]
    segments = []
    current_segment = [coords[0]]
    for i in range(1, len(coords)):
        lon1, lat1 = coords[i-1]
        lon2, lat2 = coords[i]
        if abs(lon2 - lon1) > 180:
            if len(current_segment) >= 2:
                segments.append(LineString(current_segment))
            current_segment = [coords[i]]
        else:
            current_segment.append(coords[i])
    if len(current_segment) >= 2:
        segments.append(LineString(current_segment))
    normalized_segments = []
    for seg in segments:
        norm_coords = [(normalize_longitude(lon), lat) for lon, lat in seg.coords]
        normalized_segments.append(LineString(norm_coords))
    return normalized_segments if normalized_segments else [line]

def split_polygon_at_antimeridian(poly):
    if poly.is_empty:
        return []
    if poly.geom_type == 'MultiPolygon':
        all_parts = []
        for part in poly.geoms:
            all_parts.extend(split_polygon_at_antimeridian(part))
        return all_parts
    normalized_coords = [(normalize_longitude(x), y) for x, y in poly.exterior.coords]
    try:
        poly_norm = Polygon(normalized_coords)
    except Exception:
        return [poly]
    if not poly_norm.is_valid:
        poly_norm = make_valid(poly_norm)
        if poly_norm.geom_type != 'Polygon':
            return [poly] if poly.geom_type == 'Polygon' else list(poly.geoms)
    min_lon, _, max_lon, _ = poly_norm.bounds
    if max_lon - min_lon < 180:
        return [poly_norm]
    world = box(-180, -90, 180, 90)
    parts = []
    shifted_east = Polygon([(x + 360, y) for x, y in normalized_coords])
    clipped_east = shifted_east.intersection(world)
    if not clipped_east.is_empty:
        if clipped_east.geom_type == 'Polygon':
            back = Polygon([(x - 360, y) for x, y in clipped_east.exterior.coords])
            if back.is_valid and not back.is_empty:
                parts.append(back)
        elif clipped_east.geom_type == 'MultiPolygon':
            for part in clipped_east.geoms:
                back = Polygon([(x - 360, y) for x, y in part.exterior.coords])
                if back.is_valid and not back.is_empty:
                    parts.append(back)
    shifted_west = Polygon([(x - 360, y) for x, y in normalized_coords])
    clipped_west = shifted_west.intersection(world)
    if not clipped_west.is_empty:
        if clipped_west.geom_type == 'Polygon':
            back = Polygon([(x + 360, y) for x, y in clipped_west.exterior.coords])
            if back.is_valid and not back.is_empty:
                parts.append(back)
        elif clipped_west.geom_type == 'MultiPolygon':
            for part in clipped_west.geoms:
                back = Polygon([(x + 360, y) for x, y in part.exterior.coords])
                if back.is_valid and not back.is_empty:
                    parts.append(back)
    if not parts:
        return [poly_norm]
    return parts

def clip_geometry_to_bbox(geom, lon_min, lon_max, lat_min, lat_max, margin_deg=0.5):
    """Clip geometry to a bounding box (longitude/latitude) with optional margin."""
    from shapely.geometry import box
    bbox = box(lon_min - margin_deg, lat_min - margin_deg,
               lon_max + margin_deg, lat_max + margin_deg)
    clipped = geom.intersection(bbox)
    if clipped.is_empty:
        return None
    # If result is MultiPolygon, take the largest part
    if clipped.geom_type == 'MultiPolygon':
        clipped = max(clipped.geoms, key=lambda g: g.area)
    elif clipped.geom_type == 'MultiLineString':
        clipped = max(clipped.geoms, key=lambda ls: ls.length)
    return clipped

def expand_longitude_range(lon_min, lon_max, expand_deg=3.0):
    """
    Expand the longitude range by expand_deg to the west and east.
    Returns a list of (lon_min, lon_max) tuples.
    If the expanded range does not cross the antimeridian, returns one tuple.
    If it crosses, returns two tuples (e.g., [-180, max] and [min, 180]).
    """
    # Expand west (subtract) and east (add)
    new_min = lon_min - expand_deg
    new_max = lon_max + expand_deg

    # Case 1: no wrap (within -180..180)
    if new_min >= -180 and new_max <= 180:
        return [(new_min, new_max)]

    # Case 2: wrap across the antimeridian
    # We'll split into two boxes: (new_min, 180) and (-180, new_max)
    # But new_min may be less than -180, so adjust.
    left_min = new_min
    left_max = 180.0
    right_min = -180.0
    right_max = new_max

    result = []
    if left_max > left_min:  # valid left segment
        result.append((left_min, left_max))
    if right_max > right_min:  # valid right segment
        result.append((right_min, right_max))
    return result


def clip_geometry_to_latitude_band(geom, min_lat, max_lat, margin_deg=1e-6):
    band = box(-180, min_lat - margin_deg, 180, max_lat + margin_deg)
    clipped = geom.intersection(band)
    if clipped.is_empty:
        return None
    if clipped.geom_type == 'MultiPolygon':
        clipped = max(clipped.geoms, key=lambda g: g.area)
    elif clipped.geom_type == 'MultiLineString':
        clipped = max(clipped.geoms, key=lambda ls: ls.length)
    return clipped