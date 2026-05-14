"""
Satellite database — master dictionary, utility functions, and exports.

Imports data lists from config/satellites_data.py.
The _create_satellite helper is in config/satellites_common.py.
"""

import json
from typing import Any, Dict, List, Optional, Tuple

from config.satellites_common import _create_satellite
from config.satellites_data import (
    JILIN_SATELLITES,
    CHINESE_SAR_OPTICAL,
    HIGH_RES_OPTICAL,
    MEDIUM_RES_OPTICAL,
    COMMERCIAL_CONSTELLATIONS,
)

SATELLITES = {
    "JL1Constellation": {},
    "Chinese SAR & Optical": {},
    "High Resolution Optical": {},
    "Medium Resolution Optical": {},
    "Commercial Constellations": {},
    "User Satellites": {},
}

# Populate Jilin‑1 constellation
for sat in JILIN_SATELLITES:
    name = sat.pop("name")
    SATELLITES["JL1Constellation"][name] = sat

# Populate Chinese SAR & Optical
for sat in CHINESE_SAR_OPTICAL:
    name = sat.pop("name")
    SATELLITES["Chinese SAR & Optical"][name] = sat

# Populate other categories
for sat in HIGH_RES_OPTICAL:
    name = sat.pop("name")
    SATELLITES["High Resolution Optical"][name] = sat
for sat in MEDIUM_RES_OPTICAL:
    name = sat.pop("name")
    SATELLITES["Medium Resolution Optical"][name] = sat
for sat in COMMERCIAL_CONSTELLATIONS:
    name = sat.pop("name")
    SATELLITES["Commercial Constellations"][name] = sat

# -----------------------------------------------------------------------------
# UTILITY FUNCTIONS
# -----------------------------------------------------------------------------

def get_satellite_by_norad(norad: int) -> Optional[Dict[str, Any]]:
    """Return satellite dictionary for a given NORAD ID."""
    for category in SATELLITES.values():
        for sat in category.values():
            if sat["norad"] == norad:
                return sat
    return None

def get_satellites_by_provider(provider: str) -> List[Dict[str, Any]]:
    """Return list of satellites from a specific provider."""
    results = []
    for category in SATELLITES.values():
        for sat in category.values():
            if sat["provider"].lower() == provider.lower():
                results.append(sat)
    return results

def get_satellites_by_type(sat_type: str) -> List[Dict[str, Any]]:
    """Return list of satellites of a specific type."""
    results = []
    for category in SATELLITES.values():
        for sat in category.values():
            if sat["type"].lower() == sat_type.lower():
                results.append(sat)
    return results

def get_all_sar_satellites() -> List[Dict[str, Any]]:
    """Return all SAR satellites (including hybrid)."""
    results = []
    for category in SATELLITES.values():
        for sat in category.values():
            if sat["type"] == "SAR" or "Hybrid" in sat["type"]:
                results.append(sat)
    return results

def get_all_optical_satellites() -> List[Dict[str, Any]]:
    """Return all optical satellites."""
    results = []
    for category in SATELLITES.values():
        for sat in category.values():
            if sat["type"] in ["Optical", "Optical (Video)", "Optical (Stereo)"]:
                results.append(sat)
    return results

def get_all_cameras() -> List[Tuple[str, str, str, Dict]]:
    """Return list of all camera modes across all satellites."""
    cameras = []
    for category_name, category in SATELLITES.items():
        for sat_name, sat in category.items():
            for cam_name, cam_info in sat["cameras"].items():
                cameras.append((category_name, sat_name, cam_name, cam_info))
    return cameras

def get_satellite_count() -> int:
    """Return total number of satellites in the database."""
    count = 0
    for category in SATELLITES.values():
        count += len(category)
    return count

def export_to_json(filepath: str) -> None:
    """Export entire satellite database to JSON file."""
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(SATELLITES, f, indent=2, ensure_ascii=False)

def add_custom_satellite(
    norad: int,
    name: str,
    provider: str = "User",
    sat_type: str = "Optical",
    series: str = "Custom",
    launch: Optional[str] = None,
    cameras: Optional[Dict] = None,
    period_min: float = 94.5,
    inclination: float = 97.5,
    color: str = "#FFA500"
) -> None:
    """
    Add a custom satellite to the User Satellites category.

    Parameters
    ----------
    norad : int
        NORAD catalogue ID
    name : str
        Satellite name
    provider : str
        Operator/manufacturer
    sat_type : str
        "SAR", "Optical", "Optical (Video)", etc.
    series : str
        Family/series name
    launch : str | None
        Launch date in YYYY-MM-DD format
    cameras : dict | None
        Dictionary of camera/tasking modes. If None, a default camera is created.
    period_min : float
        Orbital period in minutes
    inclination : float
        Orbital inclination in degrees
    color : str
        Hex colour code for visualisation
    """
    if cameras is None:
        if sat_type == "SAR":
            cameras = {"Stripmap": {"swath_km": 30, "resolution_m": 3}}
        else:
            cameras = {"Panchromatic": {"swath_km": 15, "resolution_m": 0.5}}
    sat = _create_satellite(
        norad=norad, name=name, provider=provider, sat_type=sat_type,
        series=series, launch=launch, cameras=cameras,
        period_min=period_min, inclination=inclination, color=color
    )
    SATELLITES["User Satellites"][name] = sat

# -----------------------------------------------------------------------------
# MAIN – Demonstration & Self‑Test
# -----------------------------------------------------------------------------

if __name__ == "__main__":
    print(f"Loaded {get_satellite_count()} satellites across 6 categories.")
    print(f"  - SAR satellites: {len(get_all_sar_satellites())}")
    print(f"  - Optical satellites: {len(get_all_optical_satellites())}")
    print("\nExample: Gaofen-3 01 tasking modes (12 modes):")
    gf3 = get_satellite_by_norad(41727)
    if gf3:
        for mode, params in gf3["cameras"].items():
            print(f"    - {mode}: {params['swath_km']} km swath, {params['resolution_m']} m resolution")
    print("\nDatabase ready for import.")
