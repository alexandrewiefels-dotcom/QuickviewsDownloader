# ============================================================================
# FILE: visualization/kml_exporter.py – Uses pre‑clipped display geometries
# ============================================================================
import simplekml
from shapely.geometry import mapping, LineString, Polygon
from geometry.utils import normalize_longitude, split_polygon_at_antimeridian, split_line_at_antimeridian
from detection.daylight_filter import get_local_time_political

def normalize_coordinates(coords):
    normalized = []
    for coord in coords:
        if len(coord) >= 2:
            lon = coord[0]
            lat = coord[1]
            if lon > 180:
                lon = lon - 360
            normalized.append((lon, lat))
    return normalized

class KMLExporter:
    @staticmethod
    def export_passes(passes_to_export, aoi=None):
        kml = simplekml.Kml()

        # AOI
        if aoi:
            aoi_folder = kml.newfolder(name="AOI")
            geom = mapping(aoi)
            if geom['type'] == 'Polygon':
                pol = aoi_folder.newpolygon(name="Area of Interest")
                coords = normalize_coordinates(geom['coordinates'][0])
                pol.outerboundaryis = coords
                pol.style.polystyle.color = simplekml.Color.changealpha("33", "0000FF")
            elif geom['type'] == 'MultiPolygon':
                for poly_coords in geom['coordinates']:
                    pol = aoi_folder.newpolygon(name="Area of Interest")
                    coords = normalize_coordinates(poly_coords[0])
                    pol.outerboundaryis = coords
                    pol.style.polystyle.color = simplekml.Color.changealpha("33", "0000FF")

        # Swaths – use display_footprint
        swaths_folder = kml.newfolder(name="Swaths (all passes)")
        for p in passes_to_export:
            footprint = getattr(p, 'display_footprint', None) or p.footprint
            if footprint and not footprint.is_empty:
                parts = split_polygon_at_antimeridian(footprint)
                local_time_str = get_local_time_political(p.pass_time, aoi)
                for i, part in enumerate(parts):
                    name = f"{p.satellite_name} - {p.camera_name} - {local_time_str}"
                    if len(parts) > 1:
                        name += f" (part {i+1})"
                    pol = swaths_folder.newpolygon(name=name)
                    coords = normalize_coordinates(part.exterior.coords)
                    pol.outerboundaryis = coords
                    h = p.color.lstrip('#')
                    kml_color = f"44{h[4:6]}{h[2:4]}{h[0:2]}"
                    pol.style.polystyle.color = kml_color
                    pol.style.linestyle.width = 1
                    pol.extendeddata.newdata('Satellite', p.satellite_name)
                    pol.extendeddata.newdata('Camera', p.camera_name)
                    pol.extendeddata.newdata('Date (UTC)', p.date_utc)
                    pol.extendeddata.newdata('Time (UTC)', p.time_utc)
                    pol.extendeddata.newdata('Local Date', local_time_str.split()[0] if " " in local_time_str else local_time_str)
                    pol.extendeddata.newdata('Local Time', local_time_str.split()[1] if " " in local_time_str else "")
                    pol.extendeddata.newdata('ONA (°)', f"{p.min_ona:.1f}")
                    pol.extendeddata.newdata('Direction', p.orbit_direction)
                    if hasattr(p, 'mean_cloud_cover') and p.mean_cloud_cover is not None:
                        pol.extendeddata.newdata('Clouds', f"{p.mean_cloud_cover:.0f}%")
                    pol.extendeddata.newdata('NORAD ID', str(p.norad_id))

        # Ground tracks – use display_ground_track
        tracks_folder = kml.newfolder(name="Ground Tracks (all passes)")
        for p in passes_to_export:
            track = getattr(p, 'display_ground_track', None) or p.ground_track
            if track and not track.is_empty:
                track_segments = split_line_at_antimeridian(track)
                local_time_str = get_local_time_political(p.pass_time, aoi)
                for seg_idx, seg in enumerate(track_segments):
                    coords_norm = [(normalize_longitude(lon), lat) for lon, lat in seg.coords]
                    name = f"{p.satellite_name} - {p.camera_name} - {local_time_str}"
                    if len(track_segments) > 1:
                        name += f" (part {seg_idx+1})"
                    line = tracks_folder.newlinestring(name=name)
                    line.coords = coords_norm
                    h = p.color.lstrip('#')
                    line.style.linestyle.color = f"ff{h[4:6]}{h[2:4]}{h[0:2]}"
                    line.style.linestyle.width = 2
                    line.extendeddata.newdata('Satellite', p.satellite_name)
                    line.extendeddata.newdata('NORAD ID', str(p.norad_id))

        return kml.kml()

    @staticmethod
    def export_tasked_passes(passes_to_export, aoi=None):
        kml = simplekml.Kml()

        # AOI
        if aoi:
            aoi_folder = kml.newfolder(name="AOI")
            geom = mapping(aoi)
            if geom['type'] == 'Polygon':
                pol = aoi_folder.newpolygon(name="Area of Interest")
                coords = normalize_coordinates(geom['coordinates'][0])
                pol.outerboundaryis = coords
                pol.style.polystyle.color = simplekml.Color.changealpha("33", "0000FF")
            elif geom['type'] == 'MultiPolygon':
                for poly_coords in geom['coordinates']:
                    pol = aoi_folder.newpolygon(name="Area of Interest")
                    coords = normalize_coordinates(poly_coords[0])
                    pol.outerboundaryis = coords
                    pol.style.polystyle.color = simplekml.Color.changealpha("33", "0000FF")

        # Tasked swaths – use display_footprint
        swaths_folder = kml.newfolder(name="Tasked Swaths")
        for p in passes_to_export:
            footprint = getattr(p, 'display_footprint', None) or getattr(p, 'tasked_footprint', p.footprint)
            if footprint and not footprint.is_empty:
                parts = split_polygon_at_antimeridian(footprint)
                local_time_str = get_local_time_political(p.pass_time, aoi)
                for i, part in enumerate(parts):
                    name = f"{p.satellite_name} - {p.camera_name} - {local_time_str}"
                    if p.tasked_ona:
                        name += f" (ONA {p.tasked_ona:.1f}°)"
                    if len(parts) > 1:
                        name += f" (part {i+1})"
                    pol = swaths_folder.newpolygon(name=name)
                    coords = normalize_coordinates(part.exterior.coords)
                    pol.outerboundaryis = coords
                    h = p.color.lstrip('#')
                    kml_color = f"44{h[4:6]}{h[2:4]}{h[0:2]}"
                    pol.style.polystyle.color = kml_color
                    pol.style.linestyle.width = 1
                    pol.extendeddata.newdata('Satellite', p.satellite_name)
                    pol.extendeddata.newdata('Camera', p.camera_name)
                    pol.extendeddata.newdata('Date/Time UTC', p.datetime_utc)
                    pol.extendeddata.newdata('Date/Time local', local_time_str)
                    pol.extendeddata.newdata('ONA used (°)', f"{p.tasked_ona:.1f}" if p.tasked_ona else f"{p.min_ona:.1f}")
                    shift = getattr(p, 'tasked_shift_km', 0) or 0
                    if shift > 0:
                        offset_str = f"→ {abs(shift):.1f} km"
                    elif shift < 0:
                        offset_str = f"← {abs(shift):.1f} km"
                    else:
                        offset_str = f"{abs(shift):.1f} km"
                    pol.extendeddata.newdata('Offset', offset_str)
                    pol.extendeddata.newdata('Swath (km)', str(p.swath_km))
                    pol.extendeddata.newdata('GSD (m)', str(p.resolution_m))
                    if hasattr(p, 'mean_cloud_cover') and p.mean_cloud_cover is not None:
                        pol.extendeddata.newdata('Weather', f"{p.mean_cloud_cover:.0f}%")
                    if hasattr(p, 'coverage_pct') and p.coverage_pct:
                        pol.extendeddata.newdata('Coverage (%)', f"{p.coverage_pct:.1f}")
                    pol.extendeddata.newdata('NORAD ID', str(p.norad_id))

        # Ground tracks – use display_ground_track
        tracks_folder = kml.newfolder(name="Ground Tracks (tasked)")
        for p in passes_to_export:
            track = getattr(p, 'display_ground_track', None) or p.ground_track
            if track and not track.is_empty:
                track_segments = split_line_at_antimeridian(track)
                local_time_str = get_local_time_political(p.pass_time, aoi)
                for seg_idx, seg in enumerate(track_segments):
                    coords_norm = [(normalize_longitude(lon), lat) for lon, lat in seg.coords]
                    name = f"{p.satellite_name} - {p.camera_name} - {local_time_str}"
                    if len(track_segments) > 1:
                        name += f" (part {seg_idx+1})"
                    line = tracks_folder.newlinestring(name=name)
                    line.coords = coords_norm
                    h = p.color.lstrip('#')
                    line.style.linestyle.color = f"ff{h[4:6]}{h[2:4]}{h[0:2]}"
                    line.style.linestyle.width = 2
                    line.extendeddata.newdata('Satellite', p.satellite_name)
                    line.extendeddata.newdata('NORAD ID', str(p.norad_id))

        return kml.kml()