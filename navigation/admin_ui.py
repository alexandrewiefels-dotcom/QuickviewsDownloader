# ============================================================================
# FILE: navigation/admin_ui.py – Admin sidebar display helpers
# ============================================================================
"""
Admin UI helpers for navigation tracking display.

Extracted from the monolithic navigation_tracker.py (1089 lines).
"""

import logging
from datetime import datetime

import pandas as pd
import streamlit as st

from navigation.tracker import init_navigation_tracker
from navigation.analytics import get_navigation_stats

logger = logging.getLogger(__name__)


def display_navigation_info_sidebar():
    """
    Affiche les informations de navigation dans la sidebar
    UNIQUEMENT POUR ADMIN
    """
    from admin_auth import is_admin

    if not is_admin():
        return

    init_navigation_tracker()

    st.sidebar.markdown("---")
    st.sidebar.markdown("### 🧭 Navigation Info (Admin)")

    stats = get_navigation_stats()

    col1, col2 = st.sidebar.columns(2)
    with col1:
        st.metric("Pages visitées", stats['total_views'])
    with col2:
        st.metric("Session", f"{stats['session_duration_min']:.0f} min")

    st.sidebar.markdown(f"**Page actuelle:** `{st.session_state.current_page}`")
    st.sidebar.markdown(f"**Session ID:** `{st.session_state.session_id}`")
    st.sidebar.markdown(f"**IP:** `{get_user_ip()}`")
    st.sidebar.markdown(f"**Country:** `{get_user_country()}`")

    if st.sidebar.button("📊 Voir l'historique", key="show_history_btn"):
        st.session_state.show_history = not st.session_state.get("show_history", False)

    if st.session_state.get("show_history", False):
        st.sidebar.markdown("#### Historique récent")
        if st.session_state.navigation_history:
            recent = st.session_state.navigation_history[-5:]
            for entry in recent:
                timestamp = entry.get("timestamp")
                if isinstance(timestamp, str):
                    try:
                        timestamp = datetime.fromisoformat(timestamp)
                    except Exception:
                        timestamp = datetime.now()
                elif not isinstance(timestamp, datetime):
                    timestamp = datetime.now()
                time_str = timestamp.strftime("%H:%M:%S")
                st.sidebar.markdown(f"- {time_str} → **{entry.get('page', 'unknown')}**")

        if st.sidebar.button("📥 Exporter", key="export_history_btn"):
            export_navigation_history()


def export_navigation_history():
    """Exporte l'historique de navigation en CSV."""
    init_navigation_tracker()

    if not st.session_state.navigation_history:
        st.warning("Aucun historique à exporter")
        return

    df_history = pd.DataFrame(st.session_state.navigation_history)
    export_df = df_history.copy()

    if 'timestamp' in export_df.columns:
        export_df['timestamp'] = pd.to_datetime(export_df['timestamp']).dt.strftime('%Y-%m-%d %H:%M:%S')

    csv = export_df.to_csv(index=False)

    st.download_button(
        label="📥 Télécharger (CSV)",
        data=csv,
        file_name=f"navigation_history_{st.session_state.session_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
        mime="text/csv",
        key="download_history_btn",
    )


# ── Re-export helpers used by admin_ui ──────────────────────────────────────

def get_user_ip() -> str:
    """Get the user's IP address from Streamlit's server context."""
    try:
        return st.context.headers.get("X-Forwarded-For", "unknown")
    except Exception:
        return "unknown"


def get_user_country() -> str:
    """Get the user's country (placeholder — requires GeoIP service)."""
    return "Unknown"
