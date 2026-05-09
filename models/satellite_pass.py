# ============================================================================
# FILE: models/satellite_pass.py – with original_offset_km, tasking attributes,
# and footprint_parts (pre‑split antimeridian parts)
# ============================================================================
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional, List, Tuple
from shapely.geometry import Point, Polygon, LineString
from config.constants import CET
import pytz

@dataclass
class SatellitePass:
    id: str
    satellite_name: str
    camera_name: str
    norad_id: int
    provider: str
    pass_time: datetime
    ground_track: Optional[LineString]          # detection segment (original)
    footprint: Polygon
    swath_km: float
    resolution_m: float
    sensor_type: str
    color: str
    inclination: float
    orbit_direction: str
    track_azimuth: float
    min_ona: float
    max_ona: float
    approach_track: Optional[LineString] = None
    selected: bool = False
    aoi_center: Optional[Point] = None
    tle_age_days: Optional[float] = None
    mean_cloud_cover: Optional[float] = None
    tasked_ona: Optional[float] = None
    tasked_footprint: Optional[Polygon] = None

    # Attributes for paving tasking
    original_offset_km: float = 0.0
    current_offset_km: float = 0.0
    tasked_shift_km: Optional[float] = None
    y_center: Optional[float] = None
    is_central: bool = False
    max_ona_reached: bool = False

    # NEW: Store extended display track and footprint
    display_ground_track: Optional[LineString] = None
    display_footprint: Optional[Polygon] = None

    # Pre‑split antimeridian parts (computed once at creation)
    footprint_parts: Optional[List[Polygon]] = field(default_factory=list)

    @property
    def time_cet(self) -> str:
        return self.pass_time.astimezone(CET).strftime("%I:%M %p CET")

    @property
    def date_cet(self) -> str:
        return self.pass_time.astimezone(CET).strftime("%Y-%m-%d")

    @property
    def datetime_cet(self) -> str:
        return self.pass_time.astimezone(CET).strftime("%Y-%m-%d %H:%M:%S CET")

    @property
    def datetime_utc(self) -> str:
        return self.pass_time.strftime("%Y-%m-%d %H:%M:%S UTC")

    @property
    def time_utc(self) -> str:
        return self.pass_time.strftime("%H:%M UTC")

    @property
    def date_utc(self) -> str:
        return self.pass_time.strftime("%Y-%m-%d")

    @property
    def datetime_utc8(self) -> str:
        return (self.pass_time + timedelta(hours=8)).strftime("%Y-%m-%d %H:%M:%S UTC+8")

    @property
    def date_utc8(self) -> str:
        return (self.pass_time + timedelta(hours=8)).strftime("%Y-%m-%d")

    @property
    def time_utc8(self) -> str:
        return (self.pass_time + timedelta(hours=8)).strftime("%H:%M UTC+8")

    @property
    def local_time_approx(self) -> str:
        if self.aoi_center is None:
            return self.datetime_utc8
        lon = self.aoi_center.x
        offset_hours = round(lon / 15)
        offset_hours = max(-12, min(12, offset_hours))
        sign = '+' if offset_hours >= 0 else '-'
        tz_name = f"Etc/GMT{sign}{abs(offset_hours)}"
        try:
            tz = pytz.timezone(tz_name)
            return self.pass_time.astimezone(tz).strftime("%Y-%m-%d %H:%M")
        except Exception:
            return self.datetime_utc8


@dataclass
class SatelliteOpportunity:
    id: str
    satellite_name: str
    camera_name: str
    norad_id: int
    provider: str
    time: datetime
    ona: float
    sat_lat: float
    sat_lon: float
    sat_alt: float
    target_lat: float
    target_lon: float
    track_azimuth: float
    swath_km: float
    resolution_m: float
    color: str
    selected: bool = False
    aoi_center: Optional[Point] = None
    tle_age_days: Optional[float] = None
    mean_cloud_cover: Optional[float] = None

    @property
    def time_cet(self) -> str:
        return self.time.astimezone(CET).strftime("%I:%M %p CET")

    @property
    def date_cet(self) -> str:
        return self.time.astimezone(CET).strftime("%Y-%m-%d")

    @property
    def datetime_cet(self) -> str:
        return self.time.astimezone(CET).strftime("%Y-%m-%d %H:%M:%S CET")

    @property
    def datetime_utc(self) -> str:
        return self.time.strftime("%Y-%m-%d %H:%M:%S UTC")

    @property
    def time_utc(self) -> str:
        return self.time.strftime("%H:%M UTC")

    @property
    def date_utc(self) -> str:
        return self.time.strftime("%Y-%m-%d")

    @property
    def datetime_utc8(self) -> str:
        return (self.time + timedelta(hours=8)).strftime("%Y-%m-%d %H:%M:%S UTC+8")

    @property
    def date_utc8(self) -> str:
        return (self.time + timedelta(hours=8)).strftime("%Y-%m-%d")

    @property
    def time_utc8(self) -> str:
        return (self.time + timedelta(hours=8)).strftime("%H:%M UTC+8")

    @property
    def local_time_approx(self) -> str:
        if self.aoi_center is None:
            return self.datetime_utc8
        lon = self.aoi_center.x
        offset_hours = round(lon / 15)
        offset_hours = max(-12, min(12, offset_hours))
        sign = '+' if offset_hours >= 0 else '-'
        tz_name = f"Etc/GMT{sign}{abs(offset_hours)}"
        try:
            tz = pytz.timezone(tz_name)
            return self.time.astimezone(tz).strftime("%Y-%m-%d %H:%M")
        except Exception:
            return self.datetime_utc8