import math
import hashlib
from datetime import timedelta
from shapely.geometry import Point, LineString, box
from shapely.ops import unary_union
from geometry.footprint import create_swath_ribbon, create_offset_swath_ribbon
from geometry.utils import split_polygon_at_antimeridian, normalize_longitude
from models.satellite_pass import SatellitePass

class PassDetector:
    def __init__(self, tle_fetcher, ts, coarse_step=1.0, fine_step=0.5):
        self.tle_fetcher = tle_fetcher
        self.ts = ts
        self.step_minutes = fine_step

    # ------------------------------------------------------------------
    # Required for tasking
    # ------------------------------------------------------------------
    def ground_range_from_ona(self, sat_alt_km, ona_deg):
        if ona_deg <= 0:
            return 0.0
        R = 6371.0
        r = R + sat_alt_km
        ona_rad = math.radians(ona_deg)
        sin_central = (r / R) * math.sin(ona_rad)
        sin_central = max(-1.0, min(1.0, sin_central))
        central_angle = math.asin(sin_central) - ona_rad
        return R * central_angle

    def ona_from_distance(self, sat_alt_km, ground_dist_km):
        if ground_dist_km <= 0:
            return 0.0
        R = 6371.0
        r = R + sat_alt_km
        central_angle = ground_dist_km / R
        max_central = math.acos(R / r)
        if central_angle > max_central:
            return 90.0
        num = R * math.sin(central_angle)
        den = r - R * math.cos(central_angle)
        if den <= 0:
            return 90.0
        return math.degrees(math.atan2(num, den))

    def _geodesic_min_distance(self, sat_lat, sat_lon, polygon):
        """
        Compute the minimum geodesic distance (in km) from a satellite
        subpoint (sat_lat, sat_lon) to a polygon on the Earth's surface.
        
        Uses a two-pass approach:
        1. Fast bounding-box distance estimate
        2. Fine-grained distance to polygon exterior coordinates
        """
        R = 6371.0  # Earth radius in km
        
        # If the satellite subpoint is inside the polygon, distance is 0
        point = Point(sat_lon, sat_lat)
        if polygon.contains(point):
            return 0.0
        
        # Get polygon exterior coordinates for distance calculation
        if polygon.geom_type == 'Polygon':
            coords = list(polygon.exterior.coords)
        elif polygon.geom_type == 'MultiPolygon':
            # Use the nearest polygon's exterior
            min_dist = float('inf')
            for sub_poly in polygon.geoms:
                d = self._geodesic_min_distance(sat_lat, sat_lon, sub_poly)
                if d < min_dist:
                    min_dist = d
            return min_dist
        else:
            # Fallback: use shapely distance (in degrees) and convert
            min_dist_deg = polygon.distance(point)
            mean_lat = polygon.centroid.y
            km_per_deg = 111.0 * math.cos(math.radians(mean_lat))
            return min_dist_deg * km_per_deg
        
        # Compute minimum great-circle distance to any exterior point
        min_dist = float('inf')
        for coord in coords:
            lon, lat = coord  # shapely uses (lon, lat) order
            d = self._haversine_distance(sat_lat, sat_lon, lat, lon)
            if d < min_dist:
                min_dist = d
        
        # If result is 0 or extremely small while point is clearly outside,
        # fallback to Euclidean approximation.
        if min_dist < 1e-6:
            # Quick bounding box check
            min_lon, min_lat, max_lon, max_lat = polygon.bounds
            if sat_lon < min_lon - 0.1 or sat_lon > max_lon + 0.1 or sat_lat < min_lat - 0.1 or sat_lat > max_lat + 0.1:
                # Distance in km using simple spherical law of cosines
                d_lat = math.radians(sat_lat - (min_lat + max_lat)/2)
                d_lon = math.radians(sat_lon - (min_lon + max_lon)/2)
                a = math.sin(d_lat/2)**2 + math.cos(math.radians((min_lat+max_lat)/2)) * math.cos(math.radians(sat_lat)) * math.sin(d_lon/2)**2
                c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
                min_dist = R * c
        return min_dist
    
    def _haversine_distance(self, lat1, lon1, lat2, lon2):
        """Compute great-circle distance in km between two lat/lon points."""
        R = 6371.0
        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)
        a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
        return R * c

    def create_shifted_footprint(self, pass_obj, offset_km):
        coords = list(pass_obj.ground_track.coords)
        return self.create_shifted_footprint_from_coords(coords, pass_obj.swath_km, offset_km)

    def create_shifted_footprint_from_coords(self, coords, swath_km, offset_km, lat_bounds=None):
        return create_offset_swath_ribbon(coords, swath_km, offset_km, lat_bounds)

    def get_perpendicular_distance_to_aoi(self, pass_obj: SatellitePass, aoi, ref_lon=None):
        track = pass_obj.ground_track
        if track is None or track.is_empty:
            return None, None, None
    
        from shapely.geometry import Point, LineString
        min_dist_deg = track.distance(aoi)
        centroid = aoi.centroid
        mean_lat = centroid.y
        km_per_deg = 111.0 * math.cos(math.radians(mean_lat))
        abs_dist_km = min_dist_deg * km_per_deg
    
        from shapely.ops import nearest_points
        track_point, aoi_point = nearest_points(track, aoi)
        track_lon = track_point.x
        track_lat = track_point.y
    
        if ref_lon is None:
            ref_lon = centroid.x
    
        signed_dist_km = abs_dist_km * (1 if track_lon > ref_lon else -1)
        return abs_dist_km, signed_dist_km, 1.0

    # ------------------------------------------------------------------
    # Track computation (for detection and extended display)
    # ------------------------------------------------------------------
    def _compute_track(self, norad_id, line1, line2, start_dt, end_dt):
        from skyfield.api import EarthSatellite
        sat = EarthSatellite(line1, line2, f"SAT{norad_id}", self.ts)
        points = []
        current = start_dt
        while current <= end_dt:
            t = self.ts.from_datetime(current)
            geo = sat.at(t)
            sub = geo.subpoint()
            points.append({
                'time': current,
                'lat': sub.latitude.degrees,
                'lon': sub.longitude.degrees,
                'alt': sub.elevation.km
            })
            current += timedelta(minutes=self.step_minutes)
        return points

    def _compute_track_fast(self, norad_id, line1, line2, start_dt, end_dt, step_minutes=None):
        """
        Faster track computation using vectorised approach.
        Same as _compute_track but with optional larger step for pre-filtering.
        """
        from skyfield.api import EarthSatellite
        sat = EarthSatellite(line1, line2, f"SAT{norad_id}", self.ts)
        step = step_minutes or self.step_minutes
        points = []
        current = start_dt
        while current <= end_dt:
            t = self.ts.from_datetime(current)
            geo = sat.at(t)
            sub = geo.subpoint()
            points.append({
                'time': current,
                'lat': sub.latitude.degrees,
                'lon': sub.longitude.degrees,
                'alt': sub.elevation.km
            })
            current += timedelta(minutes=step)
        return points

    # ------------------------------------------------------------------
    # Main detection method – uses extended display track
    # ------------------------------------------------------------------
    def detect_passes(self, sat_name, norad_id, sat_info, camera_name, camera_info,
                      line1, line2, aoi, start_dt, end_dt, max_ona, fetch_weather=False):
        import logging
        logger = logging.getLogger(__name__)
        t0 = __import__('time').time()

        # Pre-compute AOI bounding box for fast distance checks
        aoi_bounds = aoi.bounds  # (min_lon, min_lat, max_lon, max_lat)
        aoi_centroid = aoi.centroid
        aoi_centroid_lat = aoi_centroid.y
        aoi_centroid_lon = aoi_centroid.x

        track_points = self._compute_track(norad_id, line1, line2, start_dt, end_dt)
        if not track_points:
            return [], []
        t1 = __import__('time').time()
        logger.debug("  _compute_track: %.2fs for %d points", t1 - t0, len(track_points))

        max_ground = self.ground_range_from_ona(track_points[0]['alt'], max_ona)
        swath_km = camera_info["swath_km"]

        # Fast distance check using bounding box approximation
        # This avoids expensive shapely polygon.distance() calls
        km_per_deg_lat = 111.0
        km_per_deg_lon = 111.0 * math.cos(math.radians(aoi_centroid_lat))
        for pt in track_points:
            # Bounding box distance: approximate using center of AOI
            dlat_km = (pt['lat'] - aoi_centroid_lat) * km_per_deg_lat
            dlon_km = (pt['lon'] - aoi_centroid_lon) * km_per_deg_lon
            approx_dist_km = math.sqrt(dlat_km**2 + dlon_km**2)
            pt['dist_km'] = approx_dist_km
            pt['can_see'] = approx_dist_km <= max_ground

        t2 = __import__('time').time()
        logger.debug("  Distance check: %.2fs", t2 - t1)

        passes = []
        i = 0
        while i < len(track_points):
            if not track_points[i]['can_see']:
                i += 1
                continue
            start_idx = i
            while i < len(track_points) and track_points[i]['can_see']:
                i += 1
            end_idx = i - 1
            seg = track_points[start_idx:end_idx+1]
            if len(seg) < 2:
                continue

            # ----- Detection segment (original) -----
            coords = [(p['lon'], p['lat']) for p in seg]
            coords_norm = [(normalize_longitude(lon), lat) for lon, lat in coords]
            ground_track = LineString(coords_norm)
            if ground_track.is_empty or len(ground_track.coords) < 2:
                continue

            footprint = create_swath_ribbon(coords_norm, swath_km)
            if footprint.is_empty:
                continue

            first_lat = seg[0]['lat']
            last_lat = seg[-1]['lat']
            direction = "Ascending" if last_lat > first_lat else "Descending"

            min_dist_km = min(p['dist_km'] for p in seg)
            min_ona = self.ona_from_distance(seg[0]['alt'], min_dist_km)

            pass_id = hashlib.md5(f"{sat_name}{camera_name}{seg[0]['time']}".encode()).hexdigest()[:8]

            # ----- Extended track and footprint (for display) -----
            # OPTIMISATION: Build display track from the detection segment
            # by extending it with a few extra points at each end, rather
            # than recomputing the full track from scratch.
            EXTRA_MINUTES = 10
            extra_steps = max(1, int(EXTRA_MINUTES / self.step_minutes))
            display_start_idx = max(0, start_idx - extra_steps)
            display_end_idx = min(len(track_points) - 1, end_idx + extra_steps)
            display_seg = track_points[display_start_idx:display_end_idx + 1]
            if len(display_seg) >= 2:
                display_coords = [(normalize_longitude(p['lon']), p['lat']) for p in display_seg]
                display_ground_track = LineString(display_coords)
                display_footprint = create_swath_ribbon(display_coords, swath_km)
            else:
                display_ground_track = ground_track
                display_footprint = footprint

            # ----- Create the pass object -----
            sat_pass = SatellitePass(
                id=pass_id,
                satellite_name=sat_name,
                camera_name=camera_name,
                norad_id=norad_id,
                provider=sat_info["provider"],
                pass_time=seg[len(seg)//2]['time'],
                ground_track=ground_track,
                footprint=footprint,
                swath_km=swath_km,
                resolution_m=camera_info["resolution_m"],
                sensor_type=sat_info["type"],
                color=sat_info["color"],
                inclination=sat_info.get("inclination", 98.0),
                orbit_direction=direction,
                track_azimuth=0.0,
                min_ona=min_ona,
                max_ona=max_ona
            )
            sat_pass.display_ground_track = display_ground_track
            sat_pass.display_footprint = display_footprint

            # Compute original offset for tasking
            if aoi and not aoi.is_empty:
                _, offset_km, _ = self.get_perpendicular_distance_to_aoi(sat_pass, aoi_centroid)
                sat_pass.original_offset_km = offset_km if offset_km is not None else 0.0
                sat_pass.current_offset_km = sat_pass.original_offset_km

            passes.append(sat_pass)

        t3 = __import__('time').time()
        logger.debug("  Pass construction: %.2fs for %d passes", t3 - t2, len(passes))
        logger.debug("  Total detect_passes: %.2fs", t3 - t0)

        return passes, []
