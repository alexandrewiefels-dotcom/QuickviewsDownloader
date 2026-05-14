# navigation package — User navigation tracking and analytics
"""
Navigation tracking and analytics for the OrbitShow application.

This package replaces the monolithic navigation_tracker.py (1089 lines)
with a modular structure:

    navigation/
        __init__.py          — Package exports
        tracker.py           — Core tracking functions (page views, actions, AOI, search)
        analytics.py         — Analytics queries (load, stats, export)
        admin_ui.py          — Admin sidebar display helpers
"""

from navigation.tracker import (
    init_navigation_tracker,
    track_page_view,
    track_user_action,
    track_aoi_upload,
    track_country_selection,
    track_search,
    track_satellites_selected,
    track_tasking_session,
    track_custom_satellite,
    track_page_view_simple,
    track_user_action_simple,
    get_client_info,
    get_user_ip,
    get_user_country,
    get_user_browser,
    get_user_platform,
    save_search_result,
)
from navigation.analytics import (
    load_all_tracking_data,
    load_aoi_uploads,
    load_country_selections,
    load_searches,
    load_satellites_selected,
    load_tasking_sessions,
    load_user_sessions,
    load_messages,
    get_navigation_stats,
    get_user_analytics,
    export_all_data,
    get_user_statistics,
    get_top_countries,
    get_top_satellites,
    get_daily_activity,
    get_user_stats_by_ip,
)
from navigation.admin_ui import display_navigation_info_sidebar, export_navigation_history

__all__ = [
    "init_navigation_tracker",
    "track_page_view",
    "track_user_action",
    "track_aoi_upload",
    "track_country_selection",
    "track_search",
    "track_satellites_selected",
    "track_tasking_session",
    "track_custom_satellite",
    "track_page_view_simple",
    "track_user_action_simple",
    "get_client_info",
    "get_user_ip",
    "get_user_country",
    "get_user_browser",
    "get_user_platform",
    "save_search_result",
    "load_all_tracking_data",
    "load_aoi_uploads",
    "load_country_selections",
    "load_searches",
    "load_satellites_selected",
    "load_tasking_sessions",
    "load_user_sessions",
    "load_messages",
    "get_navigation_stats",
    "get_user_analytics",
    "export_all_data",
    "get_user_statistics",
    "get_top_countries",
    "get_top_satellites",
    "get_daily_activity",
    "get_user_stats_by_ip",
    "display_navigation_info_sidebar",
    "export_navigation_history",
]
