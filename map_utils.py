# File: map_utils.py
import base64
import hashlib
import json as _json
import logging
import math
import time
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

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

_LOG_DIR = Path(__file__).parent / "logs"
_SESSION_TS = datetime.now().strftime("%Y%m%d%H%M")


def _log_quickview_fetch(
    url: str,
    status: str,
    http_code: int,
    size_bytes: int,
    elapsed_ms: int,
    error: str = "",
    headers_rx: dict = None,
) -> None:
    """Append one JSONL record to logs/quickview_ops.jsonl for diagnostic analysis."""
    try:
        _LOG_DIR.mkdir(exist_ok=True)
        record = {
            "ts":          datetime.now(timezone.utc).isoformat(),
            "url":         url[:140],
            "status":      status,
            "http_code":   http_code,
            "size_bytes":  size_bytes,
            "elapsed_ms":  elapsed_ms,
            "error":       error,
            "content_type": (headers_rx or {}).get("Content-Type", ""),
            "cors_header":  (headers_rx or {}).get("Access-Control-Allow-Origin", ""),
        }
        with open(_LOG_DIR / f"{_SESSION_TS}_quickview_ops.jsonl", "a", encoding="utf-8") as f:
            f.write(_json.dumps(record) + "\n")
    except Exception:
        pass


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

_QV_HEADERS = {
    "Referer":    "https://www.sasclouds.com/",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
}


@lru_cache(maxsize=60)
def _fetch_image_b64(url: str) -> str:
    """
    Fetch quickview image and return a base64 data-URI for embedding in Folium.
    Results are cached in-process so repeated eye-button clicks are instant.
    Logs every attempt (success or failure) to logs/quickview_ops.jsonl.
    Returns empty string on failure.
    """
    t0 = time.monotonic()
    try:
        resp = _requests.get(url, timeout=25, headers=_QV_HEADERS)
        elapsed_ms = int((time.monotonic() - t0) * 1000)

        if resp.status_code == 200:
            size_bytes = len(resp.content)
            # Derive MIME from Content-Type header first; fall back to URL extension.
            # URL-based detection is unreliable — many CDN URLs end with "." or have no
            # extension, causing image/png to be declared for JPEG content, which breaks
            # rendering in Firefox and Safari.
            _ct_hdr  = resp.headers.get("Content-Type", "").split(";")[0].strip()
            _url_ext = url.lower().split("?")[0].rsplit(".", 1)[-1] if "." in url else ""
            if _ct_hdr in ("image/jpeg", "image/png", "image/webp", "image/gif"):
                mime = _ct_hdr
            elif _url_ext in ("jpg", "jpeg"):
                mime = "image/jpeg"
            else:
                mime = "image/png"
            if _ct_hdr and _ct_hdr != mime:
                logger.warning(
                    f"Quickview MIME mismatch | using={mime!r} | "
                    f"Content-Type={_ct_hdr!r} | url_ext='.{_url_ext}' | {url[:60]}"
                )
            else:
                logger.debug(
                    f"Quickview MIME={mime!r} | Content-Type={_ct_hdr!r} | "
                    f"url_ext='.{_url_ext}'"
                )
            b64 = base64.b64encode(resp.content).decode()
            logger.info(
                f"Quickview OK | {size_bytes // 1024}KB | {elapsed_ms}ms | {url[:80]}"
            )
            _log_quickview_fetch(
                url, "ok", 200, size_bytes, elapsed_ms,
                headers_rx=dict(resp.headers),
            )
            return f"data:{mime};base64,{b64}"

        # Non-200 — log status + response headers for diagnosis
        logger.warning(
            f"Quickview HTTP {resp.status_code} | {elapsed_ms}ms | {url[:80]}\n"
            f"  Content-Type : {resp.headers.get('Content-Type', 'n/a')}\n"
            f"  CORS         : {resp.headers.get('Access-Control-Allow-Origin', 'n/a')}\n"
            f"  Body snippet : {resp.text[:120]!r}"
        )
        _log_quickview_fetch(
            url, f"http_{resp.status_code}", resp.status_code, 0, elapsed_ms,
            headers_rx=dict(resp.headers),
        )

    except Exception as exc:
        elapsed_ms = int((time.monotonic() - t0) * 1000)
        logger.warning(
            f"Quickview EXCEPTION | {type(exc).__name__}: {exc} | {elapsed_ms}ms | {url[:80]}"
        )
        _log_quickview_fetch(url, f"exception", 0, 0, elapsed_ms, error=str(exc))

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
  console.log('[QV] Defining L.ImageWarpLayer class');
  L.ImageWarpLayer = L.Layer.extend({
    initialize: function(src, corners, options) {
      this._corners = corners;
      this._opacity = (options && options.opacity != null) ? options.opacity : 1.0;
      this._img = new Image();
      this._ready = false;
      this._drawLogged = false;
      var self = this;
      this._img.onload = function() {
        self._ready = true;
        console.log('[QV] Image decoded OK | ' + self._img.naturalWidth + 'x' + self._img.naturalHeight + 'px | corners=' + JSON.stringify(self._corners));
        if (self._map) self._draw();
      };
      this._img.onerror = function() {
        console.error('[QV] Image decode FAILED | src prefix=' + src.substring(0, 80));
      };
      this._img.src = src;
    },
    onAdd: function(map) {
      this._map = map;
      console.log('[QV] onAdd | map=' + map.getContainer().id + ' | corners=' + JSON.stringify(this._corners));
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
      if (!map || !this._ready) {
        if (!this._drawLogged) {
          console.log('[QV] _draw waiting | ready=' + this._ready + ' map=' + !!map);
          this._drawLogged = true;
        }
        return;
      }
      this._drawLogged = false;
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
      if (!iw || !ih) {
        console.warn('[QV] _draw skipped | naturalWidth/Height=0');
        return;
      }
      ctx.save();
      ctx.transform(
        (pts[1][0] - pts[0][0]) / iw, (pts[1][1] - pts[0][1]) / iw,
        (pts[3][0] - pts[0][0]) / ih, (pts[3][1] - pts[0][1]) / ih,
        pts[0][0], pts[0][1]
      );
      ctx.drawImage(this._img, 0, 0);
      ctx.restore();
      console.log('[QV] _draw OK | tl=(' + tl.x.toFixed(0) + ',' + tl.y.toFixed(0) + ') pts[0]=(' + pts[0][0].toFixed(0) + ',' + pts[0][1].toFixed(0) + ')');
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

    if stored_center:
        logger.debug(f"Zoom rule: stored | centre={stored_center} zoom={stored_zoom}")
    elif preview_scenes:
        try:
            geom = shapely_shape(preview_scenes[0]["geometry"])
            w, s, e, n = geom.bounds
            center = [(s + n) / 2, (w + e) / 2]
            zoom = 9
            logger.debug(f"Zoom rule: preview_scenes (n={len(preview_scenes)}) | centre={center} zoom={zoom}")
        except Exception as exc:
            logger.warning(f"Zoom rule: preview_scenes bounds failed: {exc}")
    elif features_for_map:
        try:
            first_coords = features_for_map[0]["geometry"]["coordinates"][0]
            lats = [c[1] for c in first_coords]
            lons = [c[0] for c in first_coords]
            center = [sum(lats) / len(lats), sum(lons) / len(lons)]
            zoom = 7
            logger.debug(f"Zoom rule: footprints (n={len(features_for_map)}) | centre={center} zoom={zoom}")
        except Exception as exc:
            logger.warning(f"Zoom rule: footprints centroid failed: {exc}")
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
            logger.debug(f"Zoom rule: AOI | centre={center} zoom={zoom}")
        except Exception as exc:
            logger.warning(f"Zoom rule: AOI centroid failed: {exc}")
    else:
        logger.debug(f"Zoom rule: default | centre={center} zoom={zoom}")

    m = folium.Map(
        location=center,
        zoom_start=zoom,
        zoom_snap=0.25,
        zoom_delta=0.5,
        wheel_px_per_zoom_level=80,
    )
    # Stable ID prevents st_folium from reloading the iframe on every rerun.
    # MUST be a pure lowercase hex string (no underscores) — st_folium's
    # _replace_folium_vars regex `_[a-z0-9]+(?!_)` strips the ID from variable
    # names by matching a single `_<hex>` suffix; any underscore inside the ID
    # would split the match and the map_div replacement would never fire.
    m._id = hashlib.md5(b"sasclouds_main_map").hexdigest()
    logger.debug(
        f"Folium map | centre={center} zoom_start={zoom} | "
        f"zoom_snap=0.25 zoom_delta=0.5 wheelPxPerZoomLevel=80"
    )

    # Drawing tools — fixed ID so the Draw plugin JS variable is always the same
    _draw = Draw(
        draw_options={
            "polygon": True, "rectangle": True,
            "circle": False, "marker": False,
            "polyline": False, "circlemarker": False,
        },
        edit_options={"edit": True, "remove": True},
    )
    _draw._id = hashlib.md5(b"sasclouds_draw").hexdigest()
    _draw.add_to(m)

    # ── AOI layer ─────────────────────────────────────────────────────────────
    if polygon_geojson:
        _aoi_layer = folium.GeoJson(
            polygon_geojson,
            name="AOI",
            style_function=lambda _: {"color": "#0055cc", "weight": 3, "fillOpacity": 0.15},
            popup=None,
        )
        _aoi_layer._id = hashlib.md5(
            _json.dumps(polygon_geojson, sort_keys=True).encode()
        ).hexdigest()
        _aoi_layer.add_to(m)

    # ── Georeferenced quickviews via Canvas warp ──────────────────────────────
    # Each preview scene is drawn onto a Canvas using an affine transform that
    # maps the image to its exact 4 footprint corners (TL, TR, BR, BL).
    # The layer class is defined inline — no external plugin required.
    if preview_scenes:
        logger.info(
            f"Quickview pipeline START | {len(preview_scenes)} scenes | "
            f"injecting L.ImageWarpLayer class into map body"
        )
        # Inject class definition into the HTML body (not <head>) so that
        # Leaflet is guaranteed to be loaded before L.Layer.extend() runs.
        # Scripts in <head> execute at position ~148 in the rendered HTML;
        # the Leaflet CDN link only appears at ~2260, so header injection
        # left 'L' undefined and the class was silently never created.
        m.get_root().html.add_child(Element(_WARP_LAYER_JS))

        map_var = m.get_name()
        logger.debug(f"Quickview map JS variable: {map_var!r}")
        ok_count = 0

        for i, feat in enumerate(preview_scenes):
            props  = feat.get("properties", {})
            sat    = props.get("satellite", "?")
            date   = props.get("date", "?")
            qv_url = props.get("quickview", "")
            label  = f"[{i}] {sat} {date}"

            if not qv_url:
                logger.warning(f"Quickview SKIP (no URL) | {label}")
                continue

            logger.debug(f"Quickview processing | {label} | url={qv_url[:80]}")

            corners = _order_corners(feat["geometry"])
            if corners is None:
                geom    = feat.get("geometry") or {}
                n_coords = len((geom.get("coordinates") or [[]])[0])
                logger.warning(
                    f"Quickview SKIP (corners=None) | {label} | "
                    f"geometry type={geom.get('type', 'n/a')} coords={n_coords}"
                )
                continue

            logger.debug(f"Quickview corners | {label} | {corners}")

            # Guard: NaN or Infinity in corners would produce an invalid affine
            # transform in the browser — canvas draws nothing with no JS error.
            _bad_coords = [
                (ci, vi, v)
                for ci, c in enumerate(corners)
                for vi, v in enumerate(c)
                if not math.isfinite(v)
            ]
            if _bad_coords:
                logger.error(
                    f"Quickview SKIP (NaN/Inf in corners) | {label} | "
                    f"bad at (corner,axis)={[(ci, vi) for ci, vi, _ in _bad_coords]} "
                    f"vals={[v for _, _, v in _bad_coords]}"
                )
                continue

            img_data = _fetch_image_b64(qv_url)
            if not img_data:
                logger.warning(f"Quickview SKIP (fetch failed) | {label} | url={qv_url[:80]}")
                continue

            logger.debug(
                f"Quickview fetch OK | {label} | data-URI len={len(img_data)} chars"
            )

            corners_js = _json.dumps(corners)
            _label_js  = label.replace("'", "\\'")
            js = f"""
<script>
(function(){{
  try {{
    if (typeof L === 'undefined')               {{ throw new Error('Leaflet (L) not defined'); }}
    if (typeof L.ImageWarpLayer === 'undefined') {{ throw new Error('L.ImageWarpLayer not defined — class script failed'); }}
    if (typeof {map_var} === 'undefined')        {{ throw new Error('map variable {map_var} not defined'); }}
    console.log('[QV] Instantiating | {_label_js}');
    new L.ImageWarpLayer("{img_data}", {corners_js}, {{opacity: 0.85}}).addTo({map_var});
    console.log('[QV] addTo OK | {_label_js}');
  }} catch(e) {{
    console.error('[QV] FAILED | {_label_js} |', e.message || String(e));
  }}
}})();
</script>"""
            m.get_root().html.add_child(Element(js))
            ok_count += 1
            logger.info(
                f"Quickview INJECTED | {label} | "
                f"img={len(img_data) // 1024}KB | corners={corners}"
            )

        logger.info(f"Quickview pipeline END | {ok_count}/{len(preview_scenes)} injected")

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

            # Stable ID based on scene count + first feature so the JS variable
            # name stays the same across reruns when data hasn't changed.
            _fp_hash = hashlib.md5(
                f"{len(all_geojson_features)}|{_json.dumps(all_geojson_features[0], sort_keys=True)}".encode()
            ).hexdigest()[:16]
            _fp_tooltip = folium.GeoJsonTooltip(
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
            )
            _fp_tooltip._id = hashlib.md5(b"sasclouds_fp_tooltip").hexdigest()
            _fp_layer = folium.GeoJson(
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
                tooltip=_fp_tooltip,
                popup=None,
            )
            _fp_layer._id = _fp_hash
            _fp_layer.add_to(m)

        if split_errors:
            logger.warning(f"{split_errors} footprints skipped (antimeridian split error)")
        logger.debug(f"Footprints layer: {len(features_for_map)} scenes")

    if polygon_geojson or features_for_map or preview_scenes:
        _lc = folium.LayerControl(collapsed=False)
        _lc._id = hashlib.md5(b"sasclouds_lc").hexdigest()
        _lc.add_to(m)

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
