# ============================================================================
# FILE: visualization/map_renderer.py – Complete version with live tracking fix
# - Fixed 90° rotation in live tracks (correct (lat,lon) ↔ (lon,lat) handling)
# - Proper antimeridian splitting for all lines
# - Unique satellite colours based on NORAD
# ============================================================================
import folium
from streamlit_folium import st_folium
from folium.plugins import Draw, MeasureControl
import streamlit as st
from shapely.geometry import mapping, Point, LineString, box, MultiLineString
from shapely.ops import unary_union
import geopandas as gpd
from config.constants import MAP_TILES
from datetime import datetime
import math
import logging
from geometry.calculations import calculate_bearing
from geometry.utils import clip_geometry_to_bbox, split_polygon_at_antimeridian, split_line_at_antimeridian, normalize_longitude, expand_longitude_range, shapely_coords_to_folium

from geometry.footprint import clip_geometry_to_latitude_band

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

FOOTPRINT_MARGIN_DEG = 0.5
TRACK_MARGIN_DEG = 2.0

LIVE_COLORS = [
    "#FF0000", "#00FF00", "#0000FF", "#FFA500", "#800080",
    "#00FFFF", "#FF00FF", "#FFFF00", "#FF4500", "#2E8B57",
    "#DC143C", "#00CED1", "#FF1493", "#FFD700", "#ADFF2F"
]

def clip_geometry_to_expanded_bbox(geom, lon_min, lon_max, lat_min, lat_max, expand_deg=3.0, lat_margin=0.5):
        """
        Clip geometry to the expanded longitude range (east/west) plus latitude margin.
        Handles antimeridian wrapping by splitting into multiple clips.
        """
        from shapely.geometry import box, MultiPolygon
        from shapely.ops import unary_union

        # Expand latitude range with margin
        lat_min_exp = lat_min - lat_margin
        lat_max_exp = lat_max + lat_margin

        # Get expanded longitude ranges (may be multiple)
        lon_ranges = expand_longitude_range(lon_min, lon_max, expand_deg)

        clipped_parts = []
        for (lmin, lmax) in lon_ranges:
            bbox = box(lmin, lat_min_exp, lmax, lat_max_exp)
            clipped = geom.intersection(bbox)
            if not clipped.is_empty:
                # If result is a MultiPolygon, add all components
                if clipped.geom_type == 'MultiPolygon':
                    clipped_parts.extend(clipped.geoms)
                else:
                    clipped_parts.append(clipped)

        if not clipped_parts:
            return None
        if len(clipped_parts) == 1:
            return clipped_parts[0]
        # Union multiple parts (they are separated by antimeridian)
        union = unary_union(clipped_parts)
        return union

class MapRenderer:
    def __init__(self):
        pass

    def _get_satellite_color(self, norad: int) -> str:
        return LIVE_COLORS[norad % len(LIVE_COLORS)]

    def _split_line_at_antimeridian(self, line: LineString):
        coords = list(line.coords)
        if len(coords) < 2:
            return [line]
        segments = []
        current_segment = [coords[0]]
        for i in range(1, len(coords)):
            lon1, lat1 = coords[i-1][:2]
            lon2, lat2 = coords[i][:2]
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

    

    def _get_aoi_name(self, aoi):
        if aoi is None or aoi.is_empty:
            return "No AOI defined"
        country = st.session_state.get('country_selected', None)
        if country:
            return f"Country: {country}"
        if st.session_state.get('last_drawing_hash'):
            return "Drawing (custom polygon)"
        return "Uploaded AOI"

    def _get_pass_tooltip(self, p, is_tasked=False, is_central=False):
        tooltip_lines = []
        tooltip_lines.append(f"<b>{p.satellite_name}</b>")
        tooltip_lines.append(f"Camera: {p.camera_name}")
        tooltip_lines.append(f"Provider: {p.provider}")
        tooltip_lines.append(f"Date: {p.date_utc8}")
        tooltip_lines.append(f"Time: {p.time_utc8} UTC+8")
        if is_central:
            tooltip_lines.append("<span style='color: #00FF00;'>⭐ CENTRAL PASS</span>")
        if is_tasked and hasattr(p, 'tasked_ona') and p.tasked_ona:
            tooltip_lines.append(f"ONA used: {p.tasked_ona:.1f}°")
        else:
            tooltip_lines.append(f"Min ONA: {p.min_ona:.1f}°")
            tooltip_lines.append(f"Max ONA: {p.max_ona:.1f}°")
        tooltip_lines.append(f"Direction: {p.orbit_direction}")
        tooltip_lines.append(f"Swath: {p.swath_km:.0f} km")
        tooltip_lines.append(f"Resolution: {p.resolution_m:.1f} m")
        if hasattr(p, 'mean_cloud_cover') and p.mean_cloud_cover is not None:
            cloud = p.mean_cloud_cover
            cloud_icon = "☀️" if cloud <= 30 else "⛅" if cloud <= 70 else "☁️"
            tooltip_lines.append(f"Clouds: {cloud_icon} {cloud:.0f}%")
        return "<br>".join(tooltip_lines)

    def _add_filter_info_window(self, m, filters_dict, selected_satellites=None):
        html = """<div style="position: fixed; top: 10px; right: 10px; z-index: 1000; background-color: rgba(0,0,0,0.8); color: white; padding: 12px 15px; border-radius: 8px; font-family: Arial; font-size: 11px; max-width: 320px; backdrop-filter: blur(5px); border-right: 3px solid #2ecc71;"><b style="font-size:13px;">🔍 Active Filters</b><br><hr style="margin:5px 0; border-color:#444;">"""
        for k, v in filters_dict.items():
            html += f"<b>{k}:</b> {v}<br>"
        if selected_satellites:
            html += "<hr style='margin:5px 0; border-color:#444;'><b>🛰️ Selected satellites:</b><br>"
            for sat in selected_satellites[:5]:
                html += f"<span style='font-size:10px;'>• {sat}</span><br>"
            if len(selected_satellites) > 5:
                html += f"<span style='font-size:10px; color:#888;'>... and {len(selected_satellites)-5} more</span><br>"
        html += "</div>"
        m.get_root().html.add_child(folium.Element(html))

    def _add_legend(self, m):
        legend_html = """
        <div style="position: fixed; bottom: 20px; right: 10px; z-index: 1000; background-color: rgba(0,0,0,0.75); color: white; padding: 10px 15px; border-radius: 8px; font-family: Arial; font-size: 12px; backdrop-filter: blur(5px); border-left: 4px solid #FFD700;">
            <b>📋 Tasking Legend</b><br>
            <span style="color: #00FF00;">●</span> Central Pass (pivot)<br>
            <span style="color: #FFD700; border-bottom: 2px dashed #FFD700;">⬚</span> Tasked Footprint (shifted)<br>
            <span style="color: #666666; border-bottom: 2px dashed #666666;">⬚</span> Shifted Ground Track<br>
            <span style="color: #FF4500;">●</span> SAR Satellite<br>
            <span style="color: #00FF00;">●</span> Optical Satellite<br>
            <span style="color: #FFA500;">●</span> Video Satellite<br>
            <hr style="margin:5px 0; border-color:#555;">
            <span style="color: #FFFF00;">🟡</span> Highlighted Pass<br>
            <span style="color: #00FFFF;">🔵</span> Area of Interest (AOI)<br>
            <span style="font-size: 10px; color: #aaa;">✨ Hover over footprints for details</span>
        </div>
        """
        m.get_root().html.add_child(folium.Element(legend_html))

    def _get_responsive_height(self, default_height=700):
        """Calculate responsive map height based on viewport."""
        # Use session state to store the height (can be overridden by JS)
        height = st.session_state.get('_map_height', default_height)
        # Clamp between min and max
        height = max(400, min(900, height))
        return height

    def _add_debounce_js(self, m):
        """Add JavaScript debounce for drawing tool to prevent excessive re-renders."""
        debounce_js = """
        <script>
        (function() {
            var debounceTimer = null;
            var originalOnDraw = null;
            
            // Wait for the map and draw control to be ready
            var checkInterval = setInterval(function() {
                var drawControl = document.querySelector('.leaflet-draw');
                if (drawControl) {
                    clearInterval(checkInterval);
                    
                    // Override the draw:created event with debounce
                    var map = document.querySelector('.folium-map');
                    if (map && map._leaflet_map) {
                        var leafletMap = map._leaflet_map;
                        leafletMap.on('draw:drawstart', function() {
                            // Disable Streamlit auto-rendering during drawing
                            window.streamlitAutoRender = false;
                        });
                        leafletMap.on('draw:drawstop', function() {
                            // Re-enable after a short delay
                            setTimeout(function() {
                                window.streamlitAutoRender = true;
                            }, 500);
                        });
                    }
                }
            }, 500);
        })();
        </script>
        """
        m.get_root().html.add_child(folium.Element(debounce_js))

    def _add_responsive_height_js(self, m):
        """Add JavaScript to report viewport height for responsive map sizing."""
        height_js = """
        <script>
        (function() {
            function reportHeight() {
                var vh = window.innerHeight;
                var header = document.querySelector('header') ? document.querySelector('header').offsetHeight : 0;
                var footer = document.querySelector('footer') ? document.querySelector('footer').offsetHeight : 0;
                var availableHeight = vh - header - footer - 100; // 100px padding
                availableHeight = Math.max(400, Math.min(900, availableHeight));
                
                // Store in a data attribute for Streamlit to read
                var container = document.querySelector('.folium-map');
                if (container) {
                    container.setAttribute('data-available-height', availableHeight);
                }
            }
            reportHeight();
            window.addEventListener('resize', reportHeight);
        })();
        </script>
        """
        m.get_root().html.add_child(folium.Element(height_js))

    def _filter_passes_by_zoom(self, passes: list, zoom: int, aoi) -> list:
        """
        Server-side filtering: at low zoom levels, only render a representative
        subset of passes to reduce map rendering overhead.
        
        - zoom < 4: show only 10 passes (closest to AOI center)
        - zoom 4-5: show only 25 passes
        - zoom 6-7: show only 50 passes
        - zoom >= 8: show all passes
        """
        total = len(passes)
        if total <= 50:
            return passes  # No filtering needed for small sets
        
        if zoom is None:
            zoom = 2
        
        if zoom >= 8:
            return passes
        
        # Determine limit based on zoom level
        if zoom < 4:
            limit = 10
        elif zoom < 6:
            limit = 25
        else:  # zoom 6-7
            limit = 50
        
        # If we have aoi, sort passes by proximity to AOI center
        if aoi is not None and not aoi.is_empty:
            try:
                center = aoi.centroid
                aoi_lon, aoi_lat = center.x, center.y
                
                def _pass_distance(p):
                    """Estimate distance from pass footprint center to AOI center."""
                    fp = getattr(p, 'display_footprint', None) or p.footprint
                    if fp is None or fp.is_empty:
                        return float('inf')
                    try:
                        fp_center = fp.centroid
                        return ((fp_center.x - aoi_lon) ** 2 + (fp_center.y - aoi_lat) ** 2) ** 0.5
                    except Exception:
                        return float('inf')
                
                sorted_passes = sorted(passes, key=_pass_distance)
                return sorted_passes[:limit]
            except Exception:
                pass
        
        # Fallback: return first N passes
        return passes[:limit]

    def render(self, center, zoom, aoi, passes, opportunities, map_key=0, height=700,
               live_satellites=None, show_tracks=True, highlighted_pass_id=None,
               filters=None, selected_satellites=None, apply_filter=None,
               sasclouds_features=None, sasclouds_preview_scenes=None):
        """
        Renders the map with AOI, clipped footprints, ground tracks, and live satellites.
        """
        # Use responsive height if available
        height = self._get_responsive_height(height)
        
        m = folium.Map(location=center, zoom_start=zoom, tiles=MAP_TILES)
        
        # Add debounce JS for drawing tool
        self._add_debounce_js(m)
        
        # Add responsive height JS
        self._add_responsive_height_js(m)
        
        # Server-side lazy-load filtering for large pass sets (2.9)
        passes = self._filter_passes_by_zoom(passes, zoom, aoi)
        MeasureControl(position='bottomleft', primary_length_unit='kilometers', secondary_length_unit='miles').add_to(m)
        
        # Custom CSS to fix measure control visibility
        measure_css = """
        <style>
        .leaflet-control-measure {
            background-color: rgba(255, 255, 255, 0.95) !important;
            color: #000000 !important;
            border-radius: 4px;
            border: 1px solid #ccc;
        }
        .leaflet-control-measure .leaflet-control-measure-toggle {
            background-color: white !important;
            color: black !important;
        }
        .leaflet-control-measure .leaflet-control-measure-interaction,
        .leaflet-control-measure .leaflet-control-measure-interaction label,
        .leaflet-control-measure .leaflet-control-measure-interaction input,
        .leaflet-control-measure .leaflet-control-measure-interaction button,
        .leaflet-control-measure .leaflet-control-measure-interaction span,
        .leaflet-control-measure .leaflet-control-measure-interaction div {
            color: #000000 !important;
            background-color: #ffffff !important;
        }
        .leaflet-control-measure .leaflet-control-measure-interaction input {
            border: 1px solid #999;
        }
        </style>
        """
        m.get_root().html.add_child(folium.Element(measure_css))
        
        draw = Draw(draw_options={'polygon': True, 'rectangle': True, 'circle': False,
                                  'marker': False, 'polyline': False, 'circlemarker': False},
                    edit_options={'edit': True, 'remove': True})
        draw.add_to(m)

        # AOI
        if aoi is not None and not aoi.is_empty:
            from data.aoi_handler import AOIHandler
            area_value, area_unit = AOIHandler.calculate_area(aoi)
            aoi_name = self._get_aoi_name(aoi)
            area_text = f"<b>📍 AOI:</b> {aoi_name}<br><b>Area:</b> {area_value:,.2f} {area_unit}"
            gdf = gpd.GeoDataFrame([{"geometry": aoi}], crs="EPSG:4326")
            folium.GeoJson(gdf.__geo_interface__, name="AOI",
                           style_function=lambda x: {"fillColor": "#00FFFF", "color": "#006666",
                                                     "weight": 3, "fillOpacity": 0.2},
                           tooltip=aoi_name, popup=folium.Popup(area_text, max_width=250)).add_to(m)

        if filters:
            self._add_filter_info_window(m, filters, selected_satellites)
        if st.session_state.get('tasking_results'):
            self._add_legend(m)

        # Latitude band from AOI
        if aoi and not aoi.is_empty:
            bounds = aoi.bounds
            lat_min, lat_max = bounds[1], bounds[3]
        else:
            lat_min, lat_max = -90, 90

        orbit_filter = st.session_state.get('orbit_filter', 'Both')
        filtered_passes = [p for p in passes if orbit_filter == 'Both' or p.orbit_direction == orbit_filter]

        # ---------- Render satellite passes (search & tasked) ----------
        for p in filtered_passes:
            # Get attributes safely
            is_tasked = hasattr(p, 'tasked_footprint') and p.tasked_footprint is not None
            is_central = getattr(p, 'is_central', False)          # FIX: from pass object
            footprint = getattr(p, 'display_footprint', None) or p.footprint
            ground_track = getattr(p, 'display_ground_track', None) or p.ground_track   # FIX

            if footprint is None or footprint.is_empty:
                continue
            
            # Clip to AOI bounding box (if AOI exists)
            if aoi and not aoi.is_empty:
                bounds = aoi.bounds
                lon_min, lat_min, lon_max, lat_max = bounds
                # Clip footprint
                clip_margin = st.session_state.get('clip_margin_deg', 10.0)
                clipped_fp = clip_geometry_to_expanded_bbox(footprint, lon_min, lon_max, lat_min, lat_max, expand_deg=clip_margin, lat_margin=0.5)
                if clipped_fp is None or clipped_fp.is_empty:
                    continue
                footprint = clipped_fp
                # Also clip ground track (if present)
                if ground_track and not ground_track.is_empty:
                    clipped_track = clip_geometry_to_expanded_bbox(ground_track, lon_min, lon_max, lat_min, lat_max, expand_deg=clip_margin, lat_margin=2.0)
                    if clipped_track is not None and not clipped_track.is_empty:
                        ground_track = clipped_track

            # Split at antimeridian
            parts = split_polygon_at_antimeridian(footprint)
            tooltip_text = self._get_pass_tooltip(p, is_tasked, is_central)

            # Render footprint parts
            for part in parts:
                if part.is_empty:
                    continue
                geojson = mapping(part)
                if highlighted_pass_id and p.id == highlighted_pass_id:
                    style = {"fillColor": "#FFFF00", "color": "#FF0000", "weight": 4, "fillOpacity": 0.6}
                elif is_central:
                    style = {"fillColor": "#00FF00", "color": "#00AA00", "weight": 4, "fillOpacity": 0.6}
                elif is_tasked:
                    style = {"fillColor": p.color, "color": "#FFD700", "weight": 3, "fillOpacity": 0.35, "dashArray": "5,5"}
                else:
                    style = {"fillColor": p.color, "color": "#333333", "weight": 1, "fillOpacity": 0.15}
                folium.GeoJson(geojson, name=f"footprint_{p.id}", id=f"pass_{p.id}",
                               style_function=lambda x, s=style: s,
                               tooltip=folium.Tooltip(tooltip_text, sticky=True,
                                          style="background-color:rgba(0,0,0,0.85); color:white; font-family:monospace; font-size:11px; border-radius:5px; padding:8px; border:1px solid #2ecc71; max-width:280px;"),
                               popup=folium.Popup(tooltip_text, max_width=300)).add_to(m)

            # Render ground track (if present and show_tracks is True)
            if show_tracks and ground_track and not ground_track.is_empty:
                # Split track at antimeridian
                track_segments = split_line_at_antimeridian(ground_track)
                for seg in track_segments:
                    if seg.is_empty or len(seg.coords) < 2:
                        continue
                    coords = list(seg.coords)
                    coords_norm = shapely_coords_to_folium(coords)
                    if is_central:
                        track_color = "#00FF00"
                        track_weight = 4
                        dash_array = None
                    elif is_tasked:
                        track_color = "#666666"
                        track_weight = 1.5
                        dash_array = "5,5"
                    else:
                        track_color = p.color
                        track_weight = 2
                        dash_array = None
                    folium.PolyLine(locations=coords_norm, color=track_color, weight=track_weight,
                                    opacity=0.7, dash_array=dash_array,
                                    tooltip=f"Ground track: {p.orbit_direction}<br>Satellite: {p.satellite_name}").add_to(m)

                    # Direction arrow
                    if ground_track and len(ground_track.coords) >= 2:
                        orig_coords = list(ground_track.coords)
                        if len(orig_coords) >= 2:
                            lon1, lat1 = orig_coords[-2]
                            lon2, lat2 = orig_coords[-1]
                            bearing = calculate_bearing(lat1, lon1, lat2, lon2)
                            end_lat, end_lon = coords_norm[-1]
                            arrow_html = f'<div style="transform: rotate({bearing}deg); font-size: 12px; text-align: center; line-height: 1; color: {track_color};">▶</div>'
                            folium.Marker(location=[end_lat, end_lon],
                                          icon=folium.DivIcon(html=arrow_html, icon_size=(12,12), icon_anchor=(6,6)),
                                          tooltip="Track direction").add_to(m)

        # ---------- Live satellites (track drawing fixed) ----------
        if live_satellites:
            for sat in live_satellites:
                norad = sat['norad']
                name = sat['name']
                lat = sat['lat']
                lon = sat['lon']
                alt = sat['alt']
                time = sat['time']
                track = sat.get('track', [])
                lon_norm = normalize_longitude(lon)
                tooltip_text = f"🛰️ {name}\nAltitude: {alt:.1f} km\nTime: {time.strftime('%H:%M:%S')} UTC"
                
                sat_color = self._get_satellite_color(norad)
                
                # Position indicator
                folium.CircleMarker(location=[lat, lon_norm], radius=12, color=sat_color, fill=True,
                                    fill_color=sat_color, fill_opacity=0.6, tooltip=tooltip_text).add_to(m)
                # Satellite icon
                folium.Marker(location=[lat, lon_norm],
                              icon=folium.DivIcon(html=f'<div style="font-size:28px; color:{sat_color}; text-shadow:1px 1px 2px black;">🛰️</div>',
                                                  icon_anchor=(14,14), icon_size=(28,28)),
                              tooltip=tooltip_text).add_to(m)
                
                # Draw orbit track (FIXED: correct lon/lat order for Shapely)
                if track and st.session_state.get('show_live_track', True):
                    try:
                        # track is list of (lat, lon) – convert to (lon, lat) for Shapely
                        track_points_lonlat = [(lon, lat) for lat, lon in track]
                        if len(track_points_lonlat) >= 2:
                            track_line = LineString(track_points_lonlat)
                            # Split at antimeridian
                            segments = split_line_at_antimeridian(track_line)
                            for seg in segments:
                                if seg.is_empty or len(seg.coords) < 2:
                                    continue
                                coords = list(seg.coords)   # (lon, lat)
                                # Convert back to (lat, lon) for Folium
                                coords_norm = [(lat, lon) for lon, lat in coords]
                                folium.PolyLine(locations=coords_norm, color=sat_color, weight=2,
                                                opacity=0.6, tooltip=f"Orbit track - {name}").add_to(m)
                    except Exception as e:
                        logger.error(f"Error rendering track for {name}: {e}")

        # ── SASClouds layers (footprints + quickview canvas) ──────────────────
        if sasclouds_features or sasclouds_preview_scenes:
            from branca.element import Element as _Elem
            from sasclouds_map_utils import (
                _WARP_LAYER_JS, _order_corners, _sat_color,
                _fetch_image_b64,
                split_polygon_at_antimeridian as _sc_split,
            )
            from shapely.geometry import shape as _sc_shape
            import json as _json
            import math as _math

            # Quickview georeferenced image overlays
            if sasclouds_preview_scenes:
                m.get_root().html.add_child(_Elem(_WARP_LAYER_JS))
                _mv = m.get_name()
                for _i, _feat in enumerate(sasclouds_preview_scenes):
                    _props = _feat.get("properties", {})
                    _sat   = _props.get("satellite", "?")
                    _dt    = _props.get("date", "?")
                    _qv    = _props.get("quickview", "")
                    _lbl   = f"[{_i}] {_sat} {_dt}"
                    if not _qv:
                        continue
                    _corners = _order_corners(_feat["geometry"])
                    if _corners is None:
                        continue
                    if any(not _math.isfinite(v) for c in _corners for v in c):
                        continue
                    _img = _fetch_image_b64(_qv)
                    if not _img:
                        continue
                    _cjs = _json.dumps(_corners)
                    _lbl_js = _lbl.replace("'", "\\'")
                    _js = f"""<script>
(function(){{
  try {{
    if(typeof L==='undefined'||typeof L.ImageWarpLayer==='undefined'||typeof {_mv}==='undefined')
      throw new Error('deps not ready');
    new L.ImageWarpLayer("{_img}",{_cjs},{{opacity:0.85}}).addTo({_mv});
  }}catch(e){{console.error('[QV] FAILED|{_lbl_js}|',e.message);}}
}})();
</script>"""
                    m.get_root().html.add_child(_Elem(_js))

            # SASClouds footprint polygons
            if sasclouds_features:
                _sc_feats = []
                for _feat in sasclouds_features:
                    _props = _feat.get("properties", {})
                    _sat   = _props.get("satellite", "")
                    try:
                        _parts = _sc_split(_sc_shape(_feat["geometry"]))
                    except Exception:
                        continue
                    for _part in _parts:
                        _sc_feats.append({
                            "type": "Feature",
                            "geometry": mapping(_part),
                            "properties": {
                                "satellite": _sat,
                                "sensor":    _props.get("sensor", ""),
                                "date":      _props.get("date", ""),
                                "cloud":     f"{_props.get('cloud', 0):.1f}%",
                                "_color":    _sat_color(_sat),
                            },
                        })
                if _sc_feats:
                    _sc_tt = folium.GeoJsonTooltip(
                        fields=["satellite", "sensor", "date", "cloud"],
                        aliases=["Satellite", "Sensor", "Date", "Cloud"],
                        sticky=True, labels=True,
                        style=("background-color:white;border:1px solid #ccc;"
                               "border-radius:4px;font-size:12px;padding:6px 8px;"),
                    )
                    folium.GeoJson(
                        {"type": "FeatureCollection", "features": _sc_feats},
                        name=f"SASClouds ({len(sasclouds_features)} scenes)",
                        style_function=lambda f: {
                            "color":       f["properties"]["_color"],
                            "fillColor":   f["properties"]["_color"],
                            "weight": 1.5, "fillOpacity": 0.22,
                        },
                        highlight_function=lambda f: {
                            "color":       f["properties"]["_color"],
                            "fillColor":   f["properties"]["_color"],
                            "weight": 3,   "fillOpacity": 0.45,
                        },
                        tooltip=_sc_tt,
                    ).add_to(m)

        # Return map data for drawing tool
        # Show zoom-based filtering note for large pass sets (2.9)
        if passes and len(passes) > 50:
            _zoom_level = zoom if zoom else 2
            if _zoom_level < 8:
                _note_html = """
                <div style="position:absolute;bottom:20px;left:50%;transform:translateX(-50%);
                            background:rgba(0,0,0,0.7);color:white;padding:8px 16px;
                            border-radius:8px;font-size:13px;z-index:1000;
                            border:1px solid #2ecc71;">
                    🔍 Showing %d of %d passes — zoom in for more
                </div>
                """ % (len(passes), len(passes))
                m.get_root().html.add_child(_Elem(_note_html))
        
        map_data = st_folium(m, key=f"map_{map_key}", width="100%", height=height,
                             returned_objects=["last_active_drawing"])
        return map_data
