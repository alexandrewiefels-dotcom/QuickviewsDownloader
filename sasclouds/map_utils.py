# ============================================================================
# FILE: sasclouds/map_utils.py – Map rendering helpers (warp layer, corner ordering)
# ============================================================================
"""
Map rendering utilities for SASClouds API integration.

Extracted from the monolithic sasclouds_api_scraper.py (1438 lines).
"""

import logging
from typing import List, Tuple

logger = logging.getLogger(__name__)


def _order_corners_for_download(corners: List[Tuple[float, float]]) -> List[Tuple[float, float]]:
    """
    Order the four corners of a bounding box in clockwise order starting
    from top-left (NW → NE → SE → SW).

    Parameters
    ----------
    corners : list of (lon, lat) tuples
        Four unordered corner coordinates.

    Returns
    -------
    list of (lon, lat) tuples
        Ordered corners.
    """
    if len(corners) != 4:
        return corners

    # Sort by latitude descending (north first), then longitude ascending
    sorted_north = sorted(corners, key=lambda c: (-c[1], c[0]))
    sorted_south = sorted(corners, key=lambda c: (c[1], c[0]))

    # NW = northernmost with smallest longitude
    nw = sorted_north[0]
    # NE = northernmost with largest longitude
    ne = sorted_north[-1]
    # SW = southernmost with smallest longitude
    sw = sorted_south[0]
    # SE = southernmost with largest longitude
    se = sorted_south[-1]

    return [nw, ne, se, sw]
