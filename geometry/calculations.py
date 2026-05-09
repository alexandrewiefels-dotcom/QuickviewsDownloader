# ============================================================================
# FILE: geometry/calculations.py (corrigé pour le wrap de longitude)
# ============================================================================
import math
from config.constants import EARTH_RADIUS_KM

def calculate_ona(sat_lat: float, sat_lon: float, sat_alt: float,
                 target_lat: float, target_lon: float) -> float:
    sat_lat_r = math.radians(sat_lat)
    sat_lon_r = math.radians(sat_lon)
    target_lat_r = math.radians(target_lat)
    target_lon_r = math.radians(target_lon)
    
    r_sat = EARTH_RADIUS_KM + sat_alt
    sx = r_sat * math.cos(sat_lat_r) * math.cos(sat_lon_r)
    sy = r_sat * math.cos(sat_lat_r) * math.sin(sat_lon_r)
    sz = r_sat * math.sin(sat_lat_r)
    
    tx = EARTH_RADIUS_KM * math.cos(target_lat_r) * math.cos(target_lon_r)
    ty = EARTH_RADIUS_KM * math.cos(target_lat_r) * math.sin(target_lon_r)
    tz = EARTH_RADIUS_KM * math.sin(target_lat_r)
    
    dx = tx - sx
    dy = ty - sy
    dz = tz - sz
    dist_target = math.sqrt(dx*dx + dy*dy + dz*dz)
    
    nx = -sx
    ny = -sy
    nz = -sz
    dist_nadir = math.sqrt(nx*nx + ny*ny + nz*nz)
    
    if dist_target == 0 or dist_nadir == 0:
        return 0.0
    
    cos_angle = (dx*nx + dy*ny + dz*nz) / (dist_target * dist_nadir)
    cos_angle = max(-1, min(1, cos_angle))
    
    return math.degrees(math.acos(cos_angle))

def calculate_bearing(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    diff_lon = lon2 - lon1
    if diff_lon > 180:
        diff_lon -= 360
    elif diff_lon < -180:
        diff_lon += 360
    dlon_rad = math.radians(diff_lon)

    x = math.sin(dlon_rad) * math.cos(lat2_rad)
    y = math.cos(lat1_rad) * math.sin(lat2_rad) - math.sin(lat1_rad) * math.cos(lat2_rad) * math.cos(dlon_rad)
    bearing_rad = math.atan2(x, y)
    bearing_deg = math.degrees(bearing_rad)
    return (bearing_deg + 360) % 360

def great_circle_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = EARTH_RADIUS_KM
    lat1_r = math.radians(lat1)
    lat2_r = math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    
    a = math.sin(dlat/2)**2 + math.cos(lat1_r) * math.cos(lat2_r) * math.sin(dlon/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

def compute_effective_swath(swath_nadir_km: float, ona_deg: float, altitude_km: float) -> float:
    ona_rad = math.radians(ona_deg)
    ground_range = altitude_km * math.tan(ona_rad)
    incidence_factor = math.sqrt(1 + (ground_range / altitude_km)**2)
    return swath_nadir_km / incidence_factor

def compute_ona_from_ground_distance(altitude_km: float, ground_dist_km: float) -> float:
    if ground_dist_km <= 0:
        return 0.0
    theta = ground_dist_km / EARTH_RADIUS_KM
    sin_ona = (EARTH_RADIUS_KM / (EARTH_RADIUS_KM + altitude_km)) * math.sin(theta)
    sin_ona = max(-1.0, min(1.0, sin_ona))
    return math.degrees(math.asin(sin_ona))
