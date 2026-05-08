# File: map_utils.py
import base64
import json as _json
import logging
from functools import lru_cache

import folium
import requests as _requests
from branca.element import Element
from folium.plugins import Draw
from shapely.affinity import translate
from shapely.geometry import box, mapping
from shapely.geometry import shape as shapely_shape
from shapely.validation import make_valid
from streamlit_folium import st_folium

logger = logging.getLogger(__name__)


# ── Satellite colour palette ──────────────────────────────────────────────────
# 20 visually distinct colours; unknown satellites fall back to a deterministic
# hash into the same palette so every satellite always gets the same colour.
_PALETTE = [
    "#e6194b", "#3cb44b", "#4363d8", "#f58231", "#911eb4",
    "#42d4f4", "#f032e6", "#bfef45", "#469990", "#9A6324",
    "#000075", "#808000", "#ffd8b1", "#aaffc3", "#dcbeff",
    "#800000", "#a9a9a9", "#fabed4", "#fffac8", "#e6beff",
]

# Ordered list of known satellite IDs – index → palette slot.
_KNOWN_SATS = [
    "ZY3-1", "ZY3-2", "ZY3-3", "ZY02C", "ZY1F", "ZY1E", "ZY1-02D", "ZY1-02E",
    "2m8m", "GF1", "GF1B", "GF1C", "GF1D", "GF2", "GF5", "GF5A", "GF5B",
    "GF6", "GF7", "GFDM01", "JL1", "BJ2", "BJ3", "SV1", "SV2",
    "GF3", "CSAR", "LSAR", "GF4", "CBERS-04A", "CB04A", "CM1", "TH01",
    "SPOT6/7", "LJ3-2", "GeoEye-1", "WorldView-2", "WorldView-3", "WorldView-4",
    "Pleiades", "DEIMOS", "KOMPSAT-2", "KOMPSAT-3", "KOMPSAT-3A",
    "JL1KF01B", "JL1KF02B", "JL1KF01C", "JL1GF04A", "OHS-2/3", "JL-1GP",
]


def _sat_color(satellite_id: str) -> str:
    """Return a stable hex colour for a satellite ID."""
    try:
        idx = _KNOWN_SATS.index(satellite_id)
    except ValueError:
        import hashlib
        idx = int(hashlib.md5(satellite_id.encode()).hexdigest(), 16)
    return _PALETTE[idx % len(_PALETTE)]


# ── Image fetch (module-level cache, persists across Streamlit reruns) ────────

@lru_cache(maxsize=60)
def _fetch_image_b64(url: str) -> str:
    """
    Fetch quickview image and return a base64 data-URI for embedding in Folium.
    Results are cached so repeated eye-button clicks are instant.
    Returns empty string on failure.
    """
    try:
        resp = _requests.get(url, timeout=25)
        if resp.status_code == 200:
            mime = "image/jpeg" if url.lower().split("?")[0].endswith((".jpg", ".jpeg")) else "image/png"
            b64 = base64.b64encode(resp.content).decode()
            logger.debug(f"Quickview fetched and cached ({len(resp.content)//1024}KB): {url[:60]}")
            return f"data:{mime};base64,{b64}"
    except Exception as exc:
        logger.warning(f"Could not fetch quickview image: {exc}")
    return ""


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


# ── Corner ordering ───────────────────────────────────────────────────────────

def _order_corners(footprint_geojson):
    """
    Return footprint corners ordered [NW, NE, SE, SW] as [[lat, lon], ...]
    for use with Leaflet.ImageTransform (TL, TR, BR, BL convention).
    Assumes roughly north-up imagery.
    """
    try:
        coords = footprint_geojson["coordinates"][0]
        pts = list(coords[:-1]) if (len(coords) > 1 and coords[0] == coords[-1]) else list(coords)
        if len(pts) < 3:
            return None
        # Split into top/bottom halves by latitude, then sort each by longitude
        by_lat = sorted(pts, key=lambda c: c[1], reverse=True)
        half   = len(pts) // 2 + len(pts) % 2
        top    = sorted(by_lat[:half], key=lambda c: c[0])   # ascending lon → [NW, NE]
        bot    = sorted(by_lat[half:], key=lambda c: c[0])   # ascending lon → [SW, SE]
        nw, ne = top[0],  top[-1]
        sw, se = bot[0],  bot[-1]
        return [
            [nw[1], nw[0]],   # TL / NW  [lat, lon]
            [ne[1], ne[0]],   # TR / NE
            [se[1], se[0]],   # BR / SE
            [sw[1], sw[0]],   # BL / SW
        ]
    except Exception:
        return None


# ── Main map ──────────────────────────────────────────────────────────────────

# Self-contained Canvas 2D warp layer — no external plugin needed.
# Uses an affine transform that maps the image exactly to TL/TR/BL corners
# (affine = exact for parallelogram swaths; good approximation for all satellite strips).
_WARP_LAYER_JS = """<script>
(function(){
  if (window._ImageWarpLayerDefined) return;
  window._ImageWarpLayerDefined = true;
  L.ImageWarpLayer = L.Layer.extend({
    initialize: function(src, corners, options) {
      this._corners = corners;
      this._opacity = (options && options.opacity != null) ? options.opacity : 1.0;
      this._img = new Image();
      this._ready = false;
      var self = this;
      this._img.onload = function() { self._ready = true; if (self._map) self._draw(); };
      this._img.src = src;
    },
    onAdd: function(map) {
      this._map = map;
      if (!this._canvas) {
        this._canvas = document.createElement('canvas');
        this._canvas.style.cssText = 'position:absolute;pointer-events:none';
      }
      map.getPanes().overlayPane.appendChild(this._canvas);
      map.on('moveend zoomend viewreset', this._draw, this);
      this._draw();
    },
    onRemove: function(map) {
      if (this._canvas && this._canvas.parentNode)
        this._canvas.parentNode.removeChild(this._canvas);
      map.off('moveend zoomend viewreset', this._draw, this);
      this._map = null;
    },
    _draw: function() {
      var map = this._map;
      if (!map || !this._ready) return;
      var size = map.getSize();
      var c = this._canvas;
      c.width = size.x; c.height = size.y;
      var tl = map.containerPointToLayerPoint([0, 0]);
      L.DomUtil.setPosition(c, tl);
      var ctx = c.getContext('2d');
      ctx.clearRect(0, 0, size.x, size.y);
      ctx.globalAlpha = this._opacity;
      var pts = this._corners.map(function(ll) {
        var p = map.latLngToLayerPoint(L.latLng(ll[0], ll[1]));
        return [p.x - tl.x, p.y - tl.y];
      });
      var iw = this._img.naturalWidth, ih = this._img.naturalHeight;
      if (!iw || !ih) return;
      ctx.save();
      ctx.transform(
        (pts[1][0] - pts[0][0]) / iw, (pts[1][1] - pts[0][1]) / iw,
        (pts[3][0] - pts[0][0]) / ih, (pts[3][1] - pts[0][1]) / ih,
        pts[0][0], pts[0][1]
      );
      ctx.drawImage(this._img, 0, 0);
      ctx.restore();
    }
  });
})();
</script>"""


def render_main_map(
    polygon_geojson=None,
    features_for_map=None,
    preview_scenes=None,      # list of feature dicts to show as georef quickviews
    stored_center=None,
    stored_zoom=None,
):
    """
    Interactive Folium map:
    - Drawing tools (polygon / rectangle)
    - AOI overlay (blue)
    - Search footprints coloured per satellite, hover tooltip, no click action
    - Multiple georeferenced quickviews via Leaflet.ImageTransform (4-corner warp)
    Returns st_folium map_data dict.
    """
    preview_scenes = preview_scenes or []

    # ── Default centre / zoom ─────────────────────────────────────────────────
    center, zoom = stored_center or [20.0, 0.0], stored_zoom or 3

    if preview_scenes and not stored_center:
        try:
            geom = shapely_shape(preview_scenes[0]["geometry"])
            w, s, e, n = geom.bounds
            center = [(s + n) / 2, (w + e) / 2]
            zoom = 9
        except Exception:
            pass
    elif features_for_map and not stored_center:
        try:
            first_coords = features_for_map[0]["geometry"]["coordinates"][0]
            lats = [c[1] for c in first_coords]
            lons = [c[0] for c in first_coords]
            center = [sum(lats) / len(lats), sum(lons) / len(lons)]
            zoom = 7
        except Exception:
            pass
    elif polygon_geojson and not stored_center:
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
        except Exception:
            pass

    m = folium.Map(
        location=center,
        zoom_start=zoom,
        zoom_snap=0.25,
        zoom_delta=0.5,
        wheel_px_per_zoom_level=80,
    )

    # Drawing tools
    Draw(
        draw_options={
            "polygon": True, "rectangle": True,
            "circle": False, "marker": False,
            "polyline": False, "circlemarker": False,
        },
        edit_options={"edit": True, "remove": True},
    ).add_to(m)

    # ── AOI layer ─────────────────────────────────────────────────────────────
    if polygon_geojson:
        folium.GeoJson(
            polygon_geojson,
            name="AOI",
            style_function=lambda _: {"color": "#0055cc", "weight": 3, "fillOpacity": 0.15},
            popup=None,
        ).add_to(m)

    # ── Georeferenced quickviews via Canvas warp ──────────────────────────────
    # Each preview scene is drawn onto a Canvas using an affine transform that
    # maps the image to its exact 4 footprint corners (TL, TR, BR, BL).
    # The layer class is defined inline — no external plugin required.
    if preview_scenes:
        m.get_root().header.add_child(Element(_WARP_LAYER_JS))

        map_var = m.get_name()
        ok_count = 0

        for feat in preview_scenes:
            qv_url = feat["properties"].get("quickview", "")
            if not qv_url:
                continue
            corners = _order_corners(feat["geometry"])
            if corners is None:
                continue
            img_data = _fetch_image_b64(qv_url)
            if not img_data:
                logger.warning(f"Quickview fetch failed: {qv_url[:60]}")
                continue

            props = feat["properties"]
            corners_js = _json.dumps(corners)

            # L.ImageWarpLayer is defined inline in <head>, so it is guaranteed
            # to exist by the time this body script runs.
            js = f"""
<script>
(function(){{
  new L.ImageWarpLayer("{img_data}", {corners_js}, {{opacity: 0.85}}).addTo({map_var});
}})();
</script>"""
            m.get_root().html.add_child(Element(js))
            ok_count += 1
            logger.debug(
                f"Quickview warp queued | {props.get('satellite')} "
                f"{props.get('date')} | corners={corners}"
            )

        logger.info(f"Quickview layers: {ok_count}/{len(preview_scenes)} added")

    # ── Footprints layer ───────────────────────────────────────────────────────
    if features_for_map:
        all_geojson_features = []
        split_errors = 0

        for feat in features_for_map:
            props = feat.get("properties", {})
            sat   = props.get("satellite", "")
            try:
                poly  = shapely_shape(feat["geometry"])
                parts = split_polygon_at_antimeridian(poly)
            except Exception as exc:
                logger.warning(f"Antimeridian split failed: {exc}")
                split_errors += 1
                continue

            for part in parts:
                all_geojson_features.append({
                    "type": "Feature",
                    "geometry": mapping(part),
                    "properties": {
                        "satellite": sat,
                        "sensor":    props.get("sensor", ""),
                        "date":      props.get("date", ""),
                        "cloud":     f"{props.get('cloud', 0):.1f} %",
                        "_color":    _sat_color(sat),
                    },
                })

        if all_geojson_features:
            fc = {"type": "FeatureCollection", "features": all_geojson_features}

            folium.GeoJson(
                fc,
                name=f"Footprints ({len(features_for_map)} scenes)",
                style_function=lambda f: {
                    "color":       f["properties"]["_color"],
                    "fillColor":   f["properties"]["_color"],
                    "weight":      1.5,
                    "fillOpacity": 0.12,
                },
                highlight_function=lambda f: {
                    "color":       f["properties"]["_color"],
                    "fillColor":   f["properties"]["_color"],
                    "weight":      3,
                    "fillOpacity": 0.35,
                },
                tooltip=folium.GeoJsonTooltip(
                    fields=["satellite", "sensor", "date", "cloud"],
                    aliases=["Satellite", "Sensor", "Date", "Cloud"],
                    sticky=True,
                    labels=True,
                    style=(
                        "background-color:white;"
                        "border:1px solid #ccc;"
                        "border-radius:4px;"
                        "font-size:12px;"
                        "padding:6px 8px;"
                        "box-shadow:2px 2px 4px rgba(0,0,0,0.15);"
                    ),
                ),
                popup=None,
            ).add_to(m)

        if split_errors:
            logger.warning(f"{split_errors} footprints skipped (antimeridian split error)")
        logger.debug(f"Footprints layer: {len(features_for_map)} scenes")

    if polygon_geojson or features_for_map or preview_scenes:
        folium.LayerControl(collapsed=False).add_to(m)

    logger.info(
        f"Map rendered | AOI={'yes' if polygon_geojson else 'no'} | "
        f"footprints={len(features_for_map) if features_for_map else 0} | "
        f"previews={len(preview_scenes)} | "
        f"centre={center} zoom={zoom}"
    )

    return st_folium(
        m,
        use_container_width=True,
        height=700,
        key="main_map",
        returned_objects=["center", "zoom", "last_active_drawing"],
    )
