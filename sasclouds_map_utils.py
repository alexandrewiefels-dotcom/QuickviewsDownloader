# SASClouds map utilities — Folium map with footprints, quickviews, AOI drawing.
# Renamed from map_utils.py to avoid collision with OrbitShow's visualization modules.
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

# ── Stable map ID seed (pure hex, no underscores) ────────────────────────────
_MAP_ID_SEED = b"sasclouds_archive_map"


def _log_quickview_fetch(url, status, http_code, size_bytes, elapsed_ms,
                          error="", headers_rx=None):
    try:
        _LOG_DIR.mkdir(exist_ok=True)
        record = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "url": url[:140], "status": status,
            "http_code": http_code, "size_bytes": size_bytes,
            "elapsed_ms": elapsed_ms, "error": error,
            "content_type": (headers_rx or {}).get("Content-Type", ""),
            "cors_header": (headers_rx or {}).get("Access-Control-Allow-Origin", ""),
        }
        with open(_LOG_DIR / f"{_SESSION_TS}_quickview_ops.jsonl", "a", encoding="utf-8") as f:
            f.write(_json.dumps(record) + "\n")
    except Exception:
        pass


# ── Satellite colour palette ──────────────────────────────────────────────────
_PALETTE = [
    "#e6194b", "#3cb44b", "#4363d8", "#f58231", "#911eb4",
    "#42d4f4", "#f032e6", "#bfef45", "#469990", "#9A6324",
    "#000075", "#808000", "#ffd8b1", "#aaffc3", "#dcbeff",
    "#800000", "#a9a9a9", "#fabed4", "#fffac8", "#e6beff",
]
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
    try:
        idx = _KNOWN_SATS.index(satellite_id)
    except ValueError:
        idx = int(hashlib.md5(satellite_id.encode()).hexdigest(), 16)
    return _PALETTE[idx % len(_PALETTE)]


# ── Image fetch ───────────────────────────────────────────────────────────────
_QV_HEADERS = {
    "Referer": "https://www.sasclouds.com/",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
}


@lru_cache(maxsize=120)
def _fetch_image_b64(url: str) -> str:
    """
    Fetch a quickview image and return it as a base64 data URI.
    Tries the given URL first; if it fails, attempts a fallback URL
    by replacing the Huawei OBS host with the original sasclouds.com host.
    """
    t0 = time.monotonic()
    urls_to_try = [url]

    # Build fallback URL: if the URL uses the Huawei OBS bucket, also try
    # the original sasclouds.com quickview host.
    if "obs.cn-north-10.myhuaweicloud.com" in url:
        fallback = url.replace(
            "https://quickview.obs.cn-north-10.myhuaweicloud.com",
            "https://quickview.sasclouds.com",
        )
        urls_to_try.append(fallback)
    elif "quickview.sasclouds.com" in url:
        fallback = url.replace(
            "https://quickview.sasclouds.com",
            "https://quickview.obs.cn-north-10.myhuaweicloud.com",
        )
        urls_to_try.append(fallback)

    for try_url in urls_to_try:
        try:
            resp = _requests.get(try_url, timeout=25, headers=_QV_HEADERS)
            elapsed_ms = int((time.monotonic() - t0) * 1000)
            if resp.status_code == 200:
                size_bytes = len(resp.content)
                _ct_hdr = resp.headers.get("Content-Type", "").split(";")[0].strip()
                _url_ext = try_url.lower().split("?")[0].rsplit(".", 1)[-1] if "." in try_url else ""
                if _ct_hdr in ("image/jpeg", "image/png", "image/webp", "image/gif"):
                    mime = _ct_hdr
                elif _url_ext in ("jpg", "jpeg"):
                    mime = "image/jpeg"
                else:
                    mime = "image/png"
                b64 = base64.b64encode(resp.content).decode()
                logger.info(f"Quickview OK | {size_bytes // 1024}KB | {elapsed_ms}ms | {try_url[:80]}")
                _log_quickview_fetch(try_url, "ok", 200, size_bytes, elapsed_ms, headers_rx=dict(resp.headers))
                return f"data:{mime};base64,{b64}"
            logger.warning(f"Quickview HTTP {resp.status_code} | {try_url[:80]}")
            _log_quickview_fetch(try_url, f"http_{resp.status_code}", resp.status_code, 0, elapsed_ms)
        except Exception as exc:
            elapsed_ms = int((time.monotonic() - t0) * 1000)
            logger.warning(f"Quickview EXCEPTION | {exc} | {try_url[:80]}")
            _log_quickview_fetch(try_url, "exception", 0, 0, elapsed_ms, error=str(exc))
    return ""


# ── Antimeridian helpers ──────────────────────────────────────────────────────
def normalize_longitude(lon: float) -> float:
    return ((lon + 180) % 360) - 180


def split_polygon_at_antimeridian(poly):
    if poly.is_empty:
        return []
    if poly.geom_type == "MultiPolygon":
        parts = []
        for part in poly.geoms:
            parts.extend(split_polygon_at_antimeridian(part))
        return parts
    from shapely.geometry import Polygon

    # Unwrap coordinates consecutively so edges crossing ±180° are unrolled
    # (e.g. 175→-175 becomes 175→185) rather than normalizing each coord in isolation.
    raw = list(poly.exterior.coords)
    unwrapped = [(raw[0][0], raw[0][1])]
    for pt in raw[1:]:
        prev_lon = unwrapped[-1][0]
        lon = pt[0]
        diff = lon - prev_lon
        if diff > 180:
            lon -= 360
        elif diff < -180:
            lon += 360
        unwrapped.append((lon, pt[1]))

    lons = [c[0] for c in unwrapped]
    min_lon, max_lon = min(lons), max(lons)

    # No antimeridian crossing — normalise and return as single polygon
    if min_lon >= -180 and max_lon <= 180:
        norm = [(normalize_longitude(x), y) for x, y in unwrapped]
        return [Polygon(norm)]

    poly_uw = Polygon(unwrapped)
    if not poly_uw.is_valid:
        poly_uw = make_valid(poly_uw)

    world = box(-180, -90, 180, 90)
    parts = []

    def _collect(geom):
        if geom.is_empty:
            return
        if geom.geom_type == "Polygon":
            parts.append(geom)
        elif geom.geom_type == "MultiPolygon":
            parts.extend(geom.geoms)

    # In-range slice
    _collect(poly_uw.intersection(world))
    # Eastern overflow (coords > 180): shift west and clip
    if max_lon > 180:
        _collect(translate(poly_uw, xoff=-360).intersection(world))
    # Western overflow (coords < -180): shift east and clip
    if min_lon < -180:
        _collect(translate(poly_uw, xoff=360).intersection(world))

    if not parts:
        norm = [(normalize_longitude(x), y) for x, y in unwrapped]
        return [Polygon(norm)]
    return parts


# ── Drawing helper ────────────────────────────────────────────────────────────
def handle_drawing(map_data) -> dict | None:
    if map_data and map_data.get("last_active_drawing"):
        drawing = map_data["last_active_drawing"]
        if drawing and drawing.get("geometry") and drawing["geometry"]["type"] == "Polygon":
            coords = drawing["geometry"]["coordinates"][0]
            return {"type": "Polygon", "coordinates": [coords]}
    return None


# ── Corner ordering ───────────────────────────────────────────────────────────
def _order_corners(footprint_geojson):
    try:
        coords = footprint_geojson["coordinates"][0]
        pts = list(coords[:-1]) if (len(coords) > 1 and coords[0] == coords[-1]) else list(coords)
        if len(pts) < 3:
            return None
        by_lat = sorted(pts, key=lambda c: c[1], reverse=True)
        half = len(pts) // 2 + len(pts) % 2
        top = sorted(by_lat[:half], key=lambda c: c[0])
        bot = sorted(by_lat[half:], key=lambda c: c[0])
        nw, ne = top[0], top[-1]
        sw, se = bot[0], bot[-1]
        return [[nw[1], nw[0]], [ne[1], ne[0]], [se[1], se[0]], [sw[1], sw[0]]]
    except Exception:
        return None


# ── Canvas warp layer JS ──────────────────────────────────────────────────────
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
      this._img.onload = function() {
        self._ready = true;
        if (self._map) self._draw();
      };
      this._img.onerror = function() {
        console.error('[QV] Image decode FAILED');
      };
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
        (pts[1][0]-pts[0][0])/iw, (pts[1][1]-pts[0][1])/iw,
        (pts[3][0]-pts[0][0])/ih, (pts[3][1]-pts[0][1])/ih,
        pts[0][0], pts[0][1]
      );
      ctx.drawImage(this._img, 0, 0);
      ctx.restore();
    }
  });
})();
</script>"""


# ── Main map ──────────────────────────────────────────────────────────────────
def render_sasclouds_map(
    polygon_geojson=None,
    features_for_map=None,
    preview_scenes=None,
    stored_center=None,
    stored_zoom=None,
    map_key: str = "sasclouds_map",
):
    """
    Interactive Folium map for SASClouds Archive page:
    - Drawing tools (polygon / rectangle)
    - AOI overlay (blue)
    - Scene footprints coloured per satellite with hover tooltip
    - Georeferenced quickview canvas overlays
    Returns st_folium map_data dict.
    """
    preview_scenes = preview_scenes or []
    center = stored_center or [20.0, 0.0]
    zoom = stored_zoom or 3

    if not stored_center:
        if preview_scenes:
            try:
                geom = shapely_shape(preview_scenes[0]["geometry"])
                w, s, e, n = geom.bounds
                center = [(s + n) / 2, (w + e) / 2]
                zoom = 9
            except Exception:
                pass
        elif features_for_map:
            try:
                first_coords = features_for_map[0]["geometry"]["coordinates"][0]
                lats = [c[1] for c in first_coords]
                lons = [c[0] for c in first_coords]
                center = [sum(lats) / len(lats), sum(lons) / len(lons)]
                zoom = 7
            except Exception:
                pass
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
            except Exception:
                pass

    m = folium.Map(
        location=center, zoom_start=zoom,
        zoom_snap=0.25, zoom_delta=0.5, wheel_px_per_zoom_level=80,
    )
    m._id = hashlib.md5(_MAP_ID_SEED).hexdigest()

    _draw = Draw(
        draw_options={"polygon": True, "rectangle": True,
                      "circle": False, "marker": False,
                      "polyline": False, "circlemarker": False},
        edit_options={"edit": True, "remove": True},
    )
    _draw._id = hashlib.md5(b"sasclouds_archive_draw").hexdigest()
    _draw.add_to(m)

    # AOI layer
    if polygon_geojson:
        _aoi = folium.GeoJson(
            polygon_geojson, name="AOI",
            style_function=lambda _: {"color": "#0055cc", "weight": 3, "fillOpacity": 0.15},
            popup=None,
        )
        _aoi._id = hashlib.md5(_json.dumps(polygon_geojson, sort_keys=True).encode()).hexdigest()
        _aoi.add_to(m)

    # Quickview canvas overlays
    if preview_scenes:
        m.get_root().html.add_child(Element(_WARP_LAYER_JS))
        map_var = m.get_name()
        for i, feat in enumerate(preview_scenes):
            props = feat.get("properties", {})
            sat = props.get("satellite", "?")
            date = props.get("date", "?")
            qv_url = props.get("quickview", "")
            scene_name = props.get("scene_name", "") or props.get("product_id", "") or ""
            label = f"[{i}] {sat} {date}"
            if scene_name:
                label = f"{scene_name}"
            if not qv_url:
                continue
            corners = _order_corners(feat["geometry"])
            if corners is None:
                continue
            _bad = [v for c in corners for v in c if not math.isfinite(v)]
            if _bad:
                continue
            img_data = _fetch_image_b64(qv_url)
            if not img_data:
                continue
            corners_js = _json.dumps(corners)
            _label_js = label.replace("'", "\\'")
            _qv_idx = i  # index in preview_scenes list
            js = f"""
<script>
(function(){{
  try {{
    if (typeof L === 'undefined' || typeof L.ImageWarpLayer === 'undefined' || typeof {map_var} === 'undefined')
      throw new Error('deps not ready');
    var qvLayer = new L.ImageWarpLayer("{img_data}", {corners_js}, {{opacity: 0.85}});
    // Click on the quickview image toggles visibility (show/hide)
    qvLayer.on('add', function() {{
      var canvas = this._canvas;
      if (canvas) {{
        canvas.style.cursor = 'pointer';
        canvas.addEventListener('click', function(e) {{
          // Toggle visibility: hide if visible, show if hidden
          if (qvLayer._canvas && qvLayer._canvas.style.display !== 'none') {{
            qvLayer._canvas.style.display = 'none';
          }} else {{
            if (qvLayer._canvas) qvLayer._canvas.style.display = '';
            qvLayer._draw();
          }}
        }});
      }}
    }});
    qvLayer.addTo({map_var});
  }} catch(e) {{ console.error('[QV] FAILED | {_label_js} |', e.message); }}
}})();
</script>"""
            m.get_root().html.add_child(Element(js))
            logger.info(f"Quickview injected | {label}")

    # Footprints layer
    if features_for_map:
        all_geojson_features = []
        for feat_idx, feat in enumerate(features_for_map):
            props = feat.get("properties", {})
            sat = props.get("satellite", "")
            try:
                poly = shapely_shape(feat["geometry"])
                parts = split_polygon_at_antimeridian(poly)
            except Exception:
                continue
            scene_name = props.get("scene_name", "") or props.get("product_id", "") or ""
            for part in parts:
                all_geojson_features.append({
                    "type": "Feature",
                    "geometry": mapping(part),
                    "properties": {
                        "satellite": sat,
                        "sensor": props.get("sensor", ""),
                        "date": props.get("date", ""),
                        "cloud": f"{props.get('cloud', 0):.1f} %",
                        "scene_name": scene_name,
                        "_color": _sat_color(sat),
                        "_idx": feat_idx,  # index for click-to-toggle quickview
                    },
                })

        if all_geojson_features:
            fc = {"type": "FeatureCollection", "features": all_geojson_features}
            _fp_hash = hashlib.md5(
                f"{len(all_geojson_features)}|{_json.dumps(all_geojson_features[0], sort_keys=True)}".encode()
            ).hexdigest()[:16]
            _fp_tt = folium.GeoJsonTooltip(
                fields=["scene_name", "satellite", "sensor", "date", "cloud"],
                aliases=["Scene", "Satellite", "Sensor", "Date", "Cloud"],
                sticky=True, labels=True,
                style="background-color:white;border:1px solid #ccc;border-radius:4px;font-size:12px;padding:6px 8px;",
            )
            _fp_tt._id = hashlib.md5(b"sasclouds_archive_fp_tooltip").hexdigest()

            _fp_layer = folium.GeoJson(
                fc,
                name=f"Footprints ({len(features_for_map)} scenes)",
                style_function=lambda f: {
                    "color": f["properties"]["_color"],
                    "fillColor": f["properties"]["_color"],
                    "weight": 1.5, "fillOpacity": 0.12,
                },
                highlight_function=lambda f: {
                    "color": f["properties"]["_color"],
                    "fillColor": f["properties"]["_color"],
                    "weight": 3, "fillOpacity": 0.35,
                },
                tooltip=_fp_tt,
                popup=folium.GeoJsonPopup(
                    fields=["scene_name", "satellite", "sensor", "date", "cloud", "_idx"],
                    aliases=["Scene", "Satellite", "Sensor", "Date", "Cloud", ""],
                    labels=True,
                    style="background-color:white;border:1px solid #ccc;border-radius:4px;font-size:12px;padding:6px 8px;min-width:200px;",
                ),
            )
            _fp_layer._id = _fp_hash
            _fp_layer.add_to(m)

            # Add click handler on footprints to toggle quickview via query param
            _map_var = m.get_name()
            _click_js = f"""
<script>
(function(){{
  var map = {_map_var};
  if (!map) return;
  map.on('click', function(e) {{
    // Check if a GeoJSON feature was clicked
    var layers = [];
    map.eachLayer(function(l) {{
      if (l.feature && l.feature.properties && l.feature.properties._idx !== undefined) {{
        layers.push(l);
      }}
    }});
    // Find the clicked feature by checking distance to click point
    var clickedIdx = null;
    var minDist = Infinity;
    layers.forEach(function(l) {{
      if (l.getLatLngs) {{
        try {{
          var latlngs = l.getLatLngs();
          var center = l.getCenter ? l.getCenter() : null;
          if (center) {{
            var dist = map.distance(center, e.latlng);
            if (dist < minDist) {{
              minDist = dist;
              clickedIdx = l.feature.properties._idx;
            }}
          }}
        }} catch(ex) {{}}
      }}
    }});
    if (clickedIdx !== null && minDist < 500) {{
      // Toggle quickview by navigating to a URL with qv_toggle param
      var url = new URL(window.location);
      url.searchParams.set('qv_toggle', clickedIdx);
      window.history.replaceState({{}}, '', url);
      // Trigger Streamlit rerun by dispatching a custom event
      window.dispatchEvent(new CustomEvent('qv-toggle', {{detail: {{idx: clickedIdx}}}}));
    }}
  }});
}})();
</script>"""
            m.get_root().html.add_child(Element(_click_js))

    if polygon_geojson or features_for_map or preview_scenes:
        _lc = folium.LayerControl(collapsed=False)
        _lc._id = hashlib.md5(b"sasclouds_archive_lc").hexdigest()
        _lc.add_to(m)

    return st_folium(
        m, use_container_width=True, height=600,
        key=map_key,
        returned_objects=["center", "zoom", "last_active_drawing"],
    )
