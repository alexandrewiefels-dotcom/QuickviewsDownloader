"""
Shared satellite helper — _create_satellite constructor.

Extracted from config/satellites.py to avoid circular imports.
"""

# ============================================================================
# FILE: config/satellites.py – CORRECTED AND VERIFIED VERSION
# Based on verification across multiple sources (Celestrak, N2YO, Space-Track)
# Last verification date: 2026-04-14
# 
# CORRECTIONS MADE:
# - Fixed duplicate NORAD 40961 (JL101A moved to 40958)
# - Fixed Lutan-1A NORAD: 51394 -> 51284
# - Fixed Lutan-1B NORAD: 51833 -> 51822
# - Fixed SuperView Neo-1 02 NORAD: 52321 -> 52322
# - Fixed SuperView Neo-3 01 NORAD: 59591 -> 59510
# - Fixed SuperView Neo-3 02 NORAD: 63082 -> 63208
# - Fixed Taijing-4 03 NORAD: 58807 -> 58822
# - Added alternative names (EC1-EC10, DV1-DV84, etc.)
# - Added missing series for AIRSAT-01/02 and Taijing-4 02A/03
# - Catalogs: https://sat.huijiwiki.com/wiki/%E5%A4%A9%E4%BB%AA%E7%A0%94%E7%A9%B6%E9%99%A2
#             https://database.eohandbook.com/database/missionsummary.aspx?missionID=959
# ============================================================================
# To include:
## ZY1/3
## GF5
##AIRSAT-1 61240 
##AIRSAT-2 61238 
###AIRSAT-6 63298 
##AIRSAT-7 63297 
##AIRSAT-8 62190 
##AIRSAT-9 59680 
##AIRSAT-10 59679 
##PIESAT2-02 A/B/C/D (SAR, 0,5m)：NORAD=62333/62334/62335/62336 
##PIESAT2-03 A/B/C/D (SAR, 0,5m)：NORAD=61872/61870/61871/61869 

"""
Based on verification across multiple sources:
    - Celestrak (TLE & SATCAT)
    - N2YO.com
    - Space-Track.org
    - USSPACECOM
    - eoPortal directory
    - Gunter's Space Page
    - SpaceMapper.cn, In-The-Sky.org, Heavens-Above
    - Manufacturer data sheets (PIESAT, AIRSAT, Siwei, Chang Guang)

Last full verification: 2026-04-27

This file provides a comprehensive, ready-to-use satellite database with:
    - Complete orbital parameters (period, inclination) for all satellites
    - All SAR tasking modes (Spotlight, Stripmap, ScanSAR, Sliding Spotlight, etc.)
    - Optical camera specifications (panchromatic, multispectral, video, stereo)
    - Band information for SAR (L-band, C-band, X-band, Ku-band)
    - Standardized fields for easy integration into mission planning tools
================================================================================
"""

import math
import json
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple, Union

# -----------------------------------------------------------------------------
# HELPER FUNCTIONS
# -----------------------------------------------------------------------------


def _create_satellite(
    norad: int,
    name: str,
    provider: str,
    sat_type: str,
    series: str,
    launch: Optional[str],
    cameras: Dict[str, Dict[str, Union[float, int]]],
    period_min: float = 94.5,
    inclination: float = 97.5,
    alt_name: Optional[str] = None,
    color: str = "#FF00FF",
    description: Optional[str] = None,
    status: str = "operational",
    altitude: float = 500
) -> Dict[str, Any]:
    """
    Standardised satellite dictionary constructor.

    Parameters
    ----------
    norad : int
        NORAD catalogue ID
    name : str
        Primary commercial name
    provider : str
        Operator/manufacturer
    sat_type : str
        "SAR", "Optical", "Optical (Video)", "Optical (Stereo)", "Hybrid (SAR/Opt)"
    series : str
        Family/series name
    launch : str | None
        Launch date in YYYY-MM-DD format (or None)
    cameras : dict
        Dictionary of camera/tasking modes with swath and resolution
    period_min : float
        Orbital period in minutes
    inclination : float
        Orbital inclination in degrees
    alt_name : str | None
        Alternative name (e.g., EC1, DV1, etc.)
    color : str
        Hex colour code (for visualisation)
    description : str | None
        Optional descriptive text
    status : str
        "operational", "decayed", "standby" (default "operational")
    """
    sat = {
        "norad": norad,
        "name": name,
        "type": sat_type,
        "provider": provider,
        "series": series,
        "launch_date": launch,
        "period_min": period_min,
        "inclination": inclination,
        "cameras": cameras,
        "color": color,
        "status": status
    }
    if altitude:
        sat["altitude"] = altitude
    if alt_name:
        sat["alt_name"] = alt_name
    if description:
        sat["description"] = description
    return sat


# -----------------------------------------------------------------------------
# JL1CONSTELLATION – JILIN / Chang Guang Satellite Technology
# -----------------------------------------------------------------------------

