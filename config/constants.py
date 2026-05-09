# ============================================================================
# FILE: config/constants.py
# ============================================================================
import pytz

EARTH_RADIUS_KM = 6371.0
EARTH_EQUATORIAL_RADIUS_KM = 6378.137
EARTH_POLAR_RADIUS_KM = 6356.752

CET = pytz.timezone('CET')

MAP_TILES = "OpenStreetMap"
DEFAULT_CENTER = [30, 0]
DEFAULT_ZOOM = 2
AOI_ZOOM = 10

SENSOR_COLORS = {
    "optical": "#00FF00",
    "sar": "#FF4500",
    "weather": "#00CED1"
}
