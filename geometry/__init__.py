# geometry package — Orbital mechanics and geometric calculations
from geometry.calculations import (
    great_circle_distance,
    calculate_bearing,
    calculate_ona,
    compute_effective_swath,
    compute_ona_from_ground_distance,
)
from geometry.footprint import (
    create_swath_ribbon,
    create_swath_ribbon_spherical,
    create_offset_swath_ribbon,
    offset_line_east_west,
    shift_linestring,
    clip_geometry_to_latitude_band,
)
from geometry.utils import (
    normalize_longitude,
    expand_longitude_range,
    split_polygon_at_antimeridian,
    split_line_at_antimeridian,
    clip_geometry_to_bbox,
    clip_geometry_to_latitude_band as clip_geom_to_lat_band,
    shapely_coords_to_folium,
)
from geometry.orbit_math import (
    altitude_from_mean_motion,
    mean_motion_from_altitude,
)

__all__ = [
    "great_circle_distance",
    "calculate_bearing",
    "calculate_ona",
    "compute_effective_swath",
    "compute_ona_from_ground_distance",
    "create_swath_ribbon",
    "create_swath_ribbon_spherical",
    "create_offset_swath_ribbon",
    "offset_line_east_west",
    "shift_linestring",
    "clip_geometry_to_latitude_band",
    "normalize_longitude",
    "expand_longitude_range",
    "split_polygon_at_antimeridian",
    "split_line_at_antimeridian",
    "clip_geometry_to_bbox",
    "shapely_coords_to_folium",
    "altitude_from_mean_motion",
    "mean_motion_from_altitude",
]
