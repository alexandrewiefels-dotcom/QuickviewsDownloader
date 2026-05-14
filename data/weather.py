# ============================================================================
# FILE: data/weather.py – OPTIMIZED with aggressive caching
# + Cached weather data to avoid repeated API calls
# + Batch processing support
# ============================================================================
import requests
import streamlit as st
from datetime import datetime, timezone, timedelta
import logging
import os
from shapely.geometry import Polygon
import hashlib

logger = logging.getLogger(__name__)


def _get_secret(key, default=None):
    try:
        return st.secrets[key]
    except (FileNotFoundError, KeyError):
        return os.environ.get(key, default)


# WARNING: Do NOT hardcode API keys. Set OWM_API_KEY in Streamlit secrets or env vars.
OWM_API_KEY = _get_secret("OWM_API_KEY", None)

# Cache for weather data (TTL 1 hour)
_weather_cache = {}
_CACHE_TTL_SECONDS = 3600
_weather_session_initialized = False


def _ensure_session_state():
    """Lazy-initialize Streamlit session state for weather tracking.
    Safe to call outside Streamlit runtime (no-op if session_state unavailable)."""
    global _weather_session_initialized
    if _weather_session_initialized:
        return
    try:
        if "weather_api_exhausted" not in st.session_state:
            st.session_state.weather_api_exhausted = False
        _weather_session_initialized = True
    except (AttributeError, KeyError):
        # Not running inside Streamlit — session_state not available
        pass


def _get_cache_key(lat: float, lon: float, dt: datetime) -> str:
    """Generate cache key for weather request"""
    date_str = dt.strftime("%Y-%m-%d")
    return hashlib.md5(f"{lat:.2f}_{lon:.2f}_{date_str}".encode()).hexdigest()


@st.cache_data(ttl=1800, show_spinner=False)
def get_cloud_cover_onecall(lat: float, lon: float, dt: datetime) -> float:
    """
    Retourne la couverture nuageuse (%) pour les coordonnées à l'instant donné.
    Utilise l'API One Call 3.0 (endpoint /timemachine).
    Retourne None si la date est hors de la plage ou si l'API échoue.
    """
    _ensure_session_state()

    if not OWM_API_KEY:
        logger.warning("OpenWeatherMap API key not set")
        return None

    # Check memory cache first
    cache_key = _get_cache_key(lat, lon, dt)
    if cache_key in _weather_cache:
        cache_time, cache_value = _weather_cache[cache_key]
        if (datetime.now() - cache_time).total_seconds() < _CACHE_TTL_SECONDS:
            return cache_value

    now = datetime.now(timezone.utc)
    
    # L'API timemachine couvre du 1979-01-01 à +5 jours
    if dt < datetime(1979, 1, 1, tzinfo=timezone.utc):
        logger.debug(f"Weather not available for date before 1979: {dt}")
        return None
    
    result = None
    
    # Pour les dates futures, utiliser l'API One Call (prévisions)
    if dt > now:
        url = "https://api.openweathermap.org/data/3.0/onecall"
        params = {
            'lat': lat,
            'lon': lon,
            'exclude': 'current,minutely,hourly,alerts',
            'appid': OWM_API_KEY,
            'units': 'metric'
        }
        
        try:
            response = requests.get(url, params=params, timeout=10)
            if response.status_code == 200:
                data = response.json()
                if 'daily' in data and data['daily']:
                    for day in data['daily']:
                        day_dt = datetime.fromtimestamp(day['dt'], tz=timezone.utc)
                        if day_dt.date() == dt.date():
                            result = day.get('clouds', 0)
                            break
                    if result is None and data['daily']:
                        result = data['daily'][0].get('clouds', 0)
            elif response.status_code == 429:
                logger.error("Weather API quota exceeded (429).")
                st.session_state.weather_api_exhausted = True
                return None
        except Exception as e:
            logger.error(f"Weather API exception: {e}")
            return None
    else:
        # Pour les dates passées, utiliser timemachine
        url = "https://api.openweathermap.org/data/3.0/onecall/timemachine"
        params = {
            'lat': lat,
            'lon': lon,
            'dt': int(dt.timestamp()),
            'appid': OWM_API_KEY,
            'units': 'metric'
        }

        try:
            response = requests.get(url, params=params, timeout=10)
            if response.status_code == 200:
                data = response.json()
                if 'data' in data and data['data']:
                    entry = data['data'][0]
                    result = entry.get('clouds')
            elif response.status_code == 429:
                logger.error("Weather API quota exceeded (429).")
                st.session_state.weather_api_exhausted = True
        except Exception as e:
            logger.error(f"Weather API exception: {e}")
    
    if result is not None:
        st.session_state.weather_api_exhausted = False
        # Store in memory cache
        _weather_cache[cache_key] = (datetime.now(), result)
    
    return result


def get_cloud_cover_at_intersection(footprint: Polygon, aoi: Polygon, dt: datetime) -> float:
    """
    Calcule la couverture nuageuse au centroïde de l'intersection entre l'empreinte
    du passage et l'AOI.
    """
    if aoi is None or aoi.is_empty:
        return None

    if footprint is None or footprint.is_empty:
        return None

    try:
        intersection = footprint.intersection(aoi)
    except Exception as e:
        logger.error(f"Intersection failed: {e}")
        return None

    if intersection.is_empty:
        return None

    centroid = intersection.centroid
    lat, lon = centroid.y, centroid.x
    logger.info(f"Using intersection centroid: ({lat:.4f}, {lon:.4f})")

    return get_cloud_cover_onecall(lat, lon, dt)
