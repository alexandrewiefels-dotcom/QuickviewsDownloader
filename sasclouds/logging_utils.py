# ============================================================================
# FILE: sasclouds/logging_utils.py – Activity log helpers (JSONL)
# ============================================================================
"""
Logging utilities for SASClouds API interactions.

Extracted from the monolithic sasclouds_api_scraper.py (1438 lines).
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from sasclouds.constants import LOG_DIR

logger = logging.getLogger(__name__)


def _log_event(event_type: str, details: Dict[str, Any]) -> None:
    """Write a structured JSONL event to the API interactions log."""
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event_type": event_type,
        **details,
    }
    log_path = LOG_DIR / "api_interactions.jsonl"
    try:
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, default=str) + "\n")
    except OSError as e:
        logger.warning("Failed to write API log: %s", e)


def log_search(
    aoi_geojson: Any,
    satellites: list,
    start_date: str,
    end_date: str,
    result_count: int,
    duration_ms: float,
) -> None:
    """Log a scene search event."""
    _log_event("search", {
        "aoi": aoi_geojson,
        "satellites": satellites,
        "start_date": start_date,
        "end_date": end_date,
        "result_count": result_count,
        "duration_ms": duration_ms,
    })


def log_aoi_upload(
    filename: str,
    file_type: str,
    area_km2: Optional[float],
    success: bool,
    error: Optional[str] = None,
) -> None:
    """Log an AOI upload event."""
    _log_event("aoi_upload", {
        "filename": filename,
        "file_type": file_type,
        "area_km2": area_km2,
        "success": success,
        "error": error,
    })
