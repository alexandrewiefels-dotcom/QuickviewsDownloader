# File: map_utils.py
import logging

import folium
from folium.plugins import Draw
from shapely.affinity import translate
from shapely.geometry import box, mapping
from shapely.geometry import shape as shapely_shape
from shapely.validation import make_valid
from streamlit_folium import st_folium

logger = logging.getLogger(__name__)


# ── Antimeridian helpers ──────────────────────────────────────────────────────

def normalize_longitude(lon: float) -> float:
    return ((lon + 180) % 360) - 180


def split_polygon_at_antimeridian(poly):
    """Split a shapely Polygon at ±180° if it crosses the antimeridian."""
    if poly.is_empty:
        return []
    if poly.geom_type == "MultiPolygon":
        parts = []
        for part in poly.geoms:
            parts.extend(split_polygon_at_antimeridian(part))
        return parts

    from shapely.geometry import Polygon
    norm_coords = [(normalize_longitude(x), y) for x, y in poly.exterior.coords]
    poly_norm = Polygon(norm_coords)
    if not poly_norm.is_valid:
        poly_norm = make_valid(poly_norm)
    if poly_norm.geom_type != "Polygon":
        if poly_norm.geom_type == "MultiPolygon":
            parts = []
            for p in poly_norm.geoms:
                parts.extend(split_polygon_at_antimeridian(p))
            return parts
        return [poly] if poly.geom_type == "Polygon" else list(poly.geoms)

    min_lon, _, max_lon, _ = poly_norm.bounds
    if max_lon - min_lon <= 180:
        return [poly_norm]

    world = box(-180, -90, 180, 90)
    parts = []

    shifted_west = translate(poly_norm, xoff=-360)
    west_part = shifted_west.intersection(world)
    if not west_part.is_empty:
        west_part = translate(west_part, xoff=360)
        if west_part.geom_type == "Polygon":
            parts.append(west_part)
        elif west_part.geom_type == "MultiPolygon":
            parts.extend(west_part.geoms)

    shifted_east = translate(poly_norm, xoff=360)
    east_part = shifted_east.intersection(world)
    if not east_part.is_empty:
        east_part = translate(east_part, xoff=-360)
        if east_part.geom_type == "Polygon":
            parts.append(east_part)
        elif east_part.geom_type == "MultiPolygon":
            parts.extend(east_part.geoms)

    return parts if parts else [poly_norm]


# ── Drawing helper ────────────────────────────────────────────────────────────

def handle_drawing(map_data) -> dict | None:
    """Extract the last drawn polygon from st_folium map_data."""
    if map_data and map_data.get("last_active_drawing"):
        drawing = map_data["last_active_drawing"]
        if drawing and drawing.get("geometry") and drawing["geometry"]["type"] == "Polygon":
            coords = drawing["geometry"]["coordinates"][0]
            logger.debug(f"Drawing captured: Polygon with {len(coords)} vertices")
            return {"type": "Polygon", "coordinates": [coords]}
    return None


# ── Single map (drawing + AOI + footprints) ───────────────────────────────────

def render_main_map(polygon_geojson=None, features_for_map=None):
    """
    One interactive Folium map that:
    - provides drawing tools (polygon / rectangle)
    - overlays the current AOI in blue (when set)
    - overlays search-result footprints in red with quickview popups
    Returns st_folium map_data so callers can detect new drawings.
    """
    # ── Determine centre / zoom ───────────────────────────────────────
    if features_for_map:
        try:
            first_coords = features_for_map[0]["geometry"]["coordinates"][0]
            lats = [c[1] for c in first_coords]
            lons = [c[0] for c in first_coords]
            center = [sum(lats) / len(lats), sum(lons) / len(lons)]
            zoom = 7
            logger.debug(f"Map centre on first footprint: {center}")
        except Exception:
            center, zoom = [20.0, 0.0], 3
    elif polygon_geojson:
        try:
            geom = polygon_geojson
            if geom.get("type") == "FeatureCollection":
                coords = geom["features"][0]["geometry"]["coordinates"][0]
            elif geom.get("type") == "Feature":
                coords = geom["geometry"]["coordinates"][0]
            else:
                coords = geom["coordinates"][0]
            lats = [c[1] for c in coords]
            lons = [c[0] for c in coords]
            center = [(min(lats) + max(lats)) / 2, (min(lons) + max(lons)) / 2]
            zoom = 7
            logger.debug(f"Map centre on AOI: {center}")
        except Exception:
            center, zoom = [20.0, 0.0], 3
    else:
        center, zoom = [20.0, 0.0], 3

    m = folium.Map(location=center, zoom_start=zoom)

    # Drawing tools
    Draw(
        draw_options={
            "polygon": True, "rectangle": True,
            "circle": False, "marker": False,
            "polyline": False, "circlemarker": False,
        },
        edit_options={"edit": True, "remove": True},
    ).add_to(m)

    # ── AOI layer ─────────────────────────────────────────────────────
    if polygon_geojson:
        folium.GeoJson(
            polygon_geojson,
            name="AOI",
            style_function=lambda _: {"color": "#0055cc", "weight": 3, "fillOpacity": 0.15},
        ).add_to(m)
        logger.debug("AOI layer added to map")

    # ── Footprints layer ──────────────────────────────────────────────
    if features_for_map:
        fg = folium.FeatureGroup(name=f"Footprints ({len(features_for_map)} scenes)")
        split_errors = 0
        for feat in features_for_map:
            props = feat.get("properties", {})
            qv = props.get("quickview", "")
            popup_html = (
                f"<b>{props.get('satellite', '')} {props.get('sensor', '')}</b><br>"
                f"Date: {props.get('date', '')}<br>"
                f"Cloud: {props.get('cloud', '')}%<br>"
                f"<img src='{qv}' width='200' onerror='this.style.display=\"none\"'><br>"
                f"<a href='{qv}' target='_blank'>Open full image ↗</a>"
            )
            try:
                poly = shapely_shape(feat["geometry"])
                parts = split_polygon_at_antimeridian(poly)
            except Exception as exc:
                logger.warning(f"Antimeridian split failed: {exc}")
                split_errors += 1
                parts = []

            for part in parts:
                folium.GeoJson(
                    mapping(part),
                    popup=folium.Popup(popup_html, max_width=300),
                    style_function=lambda _: {"color": "#cc2200", "weight": 2, "fillOpacity": 0.1},
                ).add_to(fg)

        fg.add_to(m)
        if split_errors:
            logger.warning(f"{split_errors} footprints skipped (antimeridian split error)")
        logger.debug(f"Footprints layer: {len(features_for_map)} features added")

    if polygon_geojson or features_for_map:
        folium.LayerControl().add_to(m)

    logger.info(
        f"Map rendered | AOI={'yes' if polygon_geojson else 'no'} | "
        f"footprints={len(features_for_map) if features_for_map else 0} | "
        f"centre={center} zoom={zoom}"
    )
    return st_folium(m, use_container_width=True, height=600, key="main_map")
