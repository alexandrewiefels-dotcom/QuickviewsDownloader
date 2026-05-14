"""
Search configuration save/load (3.19).

Allows users to export and import search configurations as JSON files.
This enables saving/restoring filter configurations for repeatable searches.

Usage:
    from data.search_config import save_search_config, load_search_config
    save_search_config(config, "my_search.json")
    config = load_search_config("my_search.json")
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

# Default config directory
CONFIG_DIR = Path("config/searches")
CONFIG_DIR.mkdir(parents=True, exist_ok=True)


def get_default_config() -> dict:
    """Get a default search configuration template."""
    return {
        "version": 1,
        "name": "New Search Configuration",
        "description": "",
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat(),
        "filters": {
            "date_range": {
                "start": None,
                "end": None,
            },
            "ona_range": {
                "min": 0,
                "max": 90,
            },
            "orbit_direction": "Both",
            "daylight_only": True,
            "providers": [],
            "satellites": [],
            "countries": [],
        },
        "aoi": None,
    }


def save_search_config(config: dict, name: str = None) -> Optional[Path]:
    """
    Save a search configuration to a JSON file.
    
    Args:
        config: Dictionary with search configuration
        name: Filename (without .json) or full path. If None, uses timestamp.
    
    Returns:
        Path to saved file, or None on failure.
    """
    if name is None:
        name = f"search_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    path = Path(name)
    if not path.suffix:
        path = CONFIG_DIR / f"{name}.json"

    # Ensure parent directory exists
    path.parent.mkdir(parents=True, exist_ok=True)

    # Update metadata
    config["updated_at"] = datetime.now().isoformat()
    if "created_at" not in config:
        config["created_at"] = datetime.now().isoformat()
    if "version" not in config:
        config["version"] = 1
    if "name" not in config:
        config["name"] = path.stem

    try:
        with open(path, 'w') as f:
            json.dump(config, f, indent=2)
        logger.info(f"Search config saved to {path}")
        return path
    except Exception as e:
        logger.error(f"Failed to save search config: {e}")
        return None


def load_search_config(path: str | Path) -> Optional[dict]:
    """
    Load a search configuration from a JSON file.
    
    Args:
        path: Path to the JSON file
    
    Returns:
        Configuration dictionary, or None on failure.
    """
    path = Path(path)
    if not path.exists():
        logger.warning(f"Search config not found: {path}")
        return None

    try:
        with open(path, 'r') as f:
            config = json.load(f)
        logger.info(f"Loaded search config from {path}")
        return config
    except Exception as e:
        logger.error(f"Failed to load search config: {e}")
        return None


def list_search_configs() -> list:
    """List all saved search configurations."""
    configs = []
    for path in sorted(CONFIG_DIR.glob("*.json")):
        try:
            with open(path, 'r') as f:
                config = json.load(f)
            configs.append({
                "name": config.get("name", path.stem),
                "path": str(path),
                "description": config.get("description", ""),
                "created_at": config.get("created_at", ""),
                "updated_at": config.get("updated_at", ""),
                "satellite_count": len(config.get("filters", {}).get("satellites", [])),
            })
        except Exception as e:
            configs.append({
                "name": path.stem,
                "path": str(path),
                "error": str(e),
            })
    return configs


def delete_search_config(name: str) -> bool:
    """Delete a saved search configuration."""
    path = CONFIG_DIR / f"{name}.json"
    if not path.exists():
        logger.warning(f"Search config not found: {path}")
        return False
    try:
        path.unlink()
        logger.info(f"Deleted search config: {path}")
        return True
    except Exception as e:
        logger.error(f"Failed to delete search config: {e}")
        return False


def config_to_session_state(config: dict) -> dict:
    """
    Convert a saved config to Streamlit session state values.
    Returns a dict of session_state keys to set.
    """
    filters = config.get("filters", {})
    state_updates = {}

    # Date range
    date_range = filters.get("date_range", {})
    if date_range.get("start"):
        state_updates["date_start"] = date_range["start"]
    if date_range.get("end"):
        state_updates["date_end"] = date_range["end"]

    # ONA range
    ona_range = filters.get("ona_range", {})
    state_updates["ona_min"] = ona_range.get("min", 0)
    state_updates["ona_max"] = ona_range.get("max", 90)

    # Orbit direction
    state_updates["orbit_filter"] = filters.get("orbit_direction", "Both")

    # Daylight filter
    state_updates["daylight_filter"] = filters.get("daylight_only", True)

    # Satellites
    satellites = filters.get("satellites", [])
    if satellites:
        state_updates["selected_satellites"] = satellites

    # Countries
    countries = filters.get("countries", [])
    if countries:
        state_updates["country_selected"] = countries[0] if len(countries) == 1 else countries

    return state_updates


def session_state_to_config() -> dict:
    """
    Convert current Streamlit session state to a search config dict.
    """
    import streamlit as st

    config = get_default_config()

    # Date range
    if st.session_state.get("date_start"):
        config["filters"]["date_range"]["start"] = st.session_state.date_start
    if st.session_state.get("date_end"):
        config["filters"]["date_range"]["end"] = st.session_state.date_end

    # ONA range
    config["filters"]["ona_range"]["min"] = st.session_state.get("ona_min", 0)
    config["filters"]["ona_range"]["max"] = st.session_state.get("ona_max", 90)

    # Orbit direction
    config["filters"]["orbit_direction"] = st.session_state.get("orbit_filter", "Both")

    # Daylight filter
    config["filters"]["daylight_only"] = st.session_state.get("daylight_filter", True)

    # Satellites
    selected = st.session_state.get("selected_satellites", [])
    if selected:
        config["filters"]["satellites"] = selected

    # Country
    country = st.session_state.get("country_selected")
    if country:
        config["filters"]["countries"] = [country]

    return config
