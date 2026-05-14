"""
API Rate Limiting Dashboard (3.18).

Shows remaining quota for external APIs:
- Space-Track (TLE data)
- N2YO (live satellite tracking)
- OpenWeatherMap (weather data)

Usage:
    from ui.pages.rate_limiting_dashboard import render_rate_limiting_dashboard
    render_rate_limiting_dashboard()
"""

import os
import time
import logging
from datetime import datetime, timedelta
from collections import defaultdict, deque
from typing import Dict, Optional

import streamlit as st
import pandas as pd

logger = logging.getLogger(__name__)


class RateLimiter:
    """
    Tracks API call rates and limits for external services.
    """

    def __init__(self):
        self._calls: Dict[str, deque] = defaultdict(lambda: deque(maxlen=10000))
        self._limits: Dict[str, dict] = {
            "space_track": {
                "name": "Space-Track",
                "max_per_minute": 30,
                "max_per_hour": 1000,
                "max_per_day": 5000,
                "configured": bool(os.environ.get("SPACETRACK_USERNAME")),
            },
            "n2yo": {
                "name": "N2YO",
                "max_per_minute": 10,
                "max_per_hour": 100,
                "max_per_day": 1000,
                "configured": bool(os.environ.get("N2YO_API_KEY")),
            },
            "openweathermap": {
                "name": "OpenWeatherMap",
                "max_per_minute": 60,
                "max_per_hour": 1000,
                "max_per_day": 10000,
                "configured": bool(os.environ.get("OWM_API_KEY")),
            },
        }

    def record_call(self, api_name: str):
        """Record an API call."""
        now = time.time()
        self._calls[api_name].append(now)

    def get_usage(self, api_name: str) -> dict:
        """Get current usage for an API."""
        now = time.time()
        calls = list(self._calls.get(api_name, []))

        # Count calls in different windows
        last_minute = sum(1 for t in calls if now - t < 60)
        last_hour = sum(1 for t in calls if now - t < 3600)
        last_day = sum(1 for t in calls if now - t < 86400)

        limits = self._limits.get(api_name, {})
        return {
            "api_name": api_name,
            "display_name": limits.get("name", api_name),
            "configured": limits.get("configured", False),
            "last_minute": last_minute,
            "last_hour": last_hour,
            "last_day": last_day,
            "max_per_minute": limits.get("max_per_minute", 0),
            "max_per_hour": limits.get("max_per_hour", 0),
            "max_per_day": limits.get("max_per_day", 0),
            "minute_remaining": max(0, limits.get("max_per_minute", 0) - last_minute),
            "hour_remaining": max(0, limits.get("max_per_hour", 0) - last_hour),
            "day_remaining": max(0, limits.get("max_per_day", 0) - last_day),
            "minute_percent": min(100, (last_minute / max(limits.get("max_per_minute", 1), 1)) * 100),
            "hour_percent": min(100, (last_hour / max(limits.get("max_per_hour", 1), 1)) * 100),
            "day_percent": min(100, (last_day / max(limits.get("max_per_day", 1), 1)) * 100),
        }

    def get_all_usage(self) -> Dict[str, dict]:
        """Get usage for all tracked APIs."""
        return {
            api: self.get_usage(api)
            for api in self._limits
        }

    def can_call(self, api_name: str) -> bool:
        """Check if we can make a call to this API."""
        usage = self.get_usage(api_name)
        return (
            usage["minute_remaining"] > 0
            and usage["hour_remaining"] > 0
            and usage["day_remaining"] > 0
        )

    def wait_if_needed(self, api_name: str):
        """Wait if rate limit is close to being hit."""
        usage = self.get_usage(api_name)
        if usage["minute_remaining"] <= 2:
            wait_time = 60 - (time.time() - min(self._calls.get(api_name, [time.time()])[-1:], default=time.time()))
            if wait_time > 0:
                logger.info(f"Rate limit approaching for {api_name}, waiting {wait_time:.1f}s")
                time.sleep(min(wait_time, 5))


# Global rate limiter instance
_rate_limiter = None


def get_rate_limiter() -> RateLimiter:
    """Get or create the global RateLimiter instance."""
    global _rate_limiter
    if _rate_limiter is None:
        _rate_limiter = RateLimiter()
    return _rate_limiter


def render_rate_limiting_dashboard():
    """Render the rate limiting dashboard in Streamlit."""
    st.markdown("### ⏱️ API Rate Limits")
    st.markdown("Monitor usage of external API services.")

    limiter = get_rate_limiter()
    usage_data = limiter.get_all_usage()

    for api_name, usage in usage_data.items():
        with st.container(border=True):
            col1, col2, col3 = st.columns([1, 2, 1])

            with col1:
                status = "✅" if usage["configured"] else "⚠️"
                st.markdown(f"**{status} {usage['display_name']}**")
                st.caption(f"API: `{api_name}`")

            with col2:
                # Minute usage bar
                st.markdown(f"**Minute:** {usage['last_minute']}/{usage['max_per_minute']}")
                st.progress(min(usage["minute_percent"] / 100, 1.0),
                           text=f"{usage['minute_remaining']} remaining")

                # Hour usage bar
                st.markdown(f"**Hour:** {usage['last_hour']}/{usage['max_per_hour']}")
                st.progress(min(usage["hour_percent"] / 100, 1.0),
                           text=f"{usage['hour_remaining']} remaining")

                # Day usage bar
                st.markdown(f"**Day:** {usage['last_day']}/{usage['max_per_day']}")
                st.progress(min(usage["day_percent"] / 100, 1.0),
                           text=f"{usage['day_remaining']} remaining")

            with col3:
                if not usage["configured"]:
                    st.warning("Not configured")
                elif usage["minute_remaining"] <= 2:
                    st.error("Rate limit critical!")
                elif usage["minute_remaining"] <= 10:
                    st.warning("Approaching limit")
                else:
                    st.success("Healthy")

    # Summary table
    st.markdown("#### Summary")
    summary_data = []
    for usage in usage_data.values():
        summary_data.append({
            "API": usage["display_name"],
            "Configured": "✅" if usage["configured"] else "❌",
            "Minute": f"{usage['last_minute']}/{usage['max_per_minute']}",
            "Hour": f"{usage['last_hour']}/{usage['max_per_hour']}",
            "Day": f"{usage['last_day']}/{usage['max_per_day']}",
        })

    if summary_data:
        st.dataframe(summary_data, use_container_width=True, hide_index=True)
