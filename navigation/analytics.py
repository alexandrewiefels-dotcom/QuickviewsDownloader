# ============================================================================
# FILE: navigation/analytics.py – Analytics queries (load, stats, export)
# ============================================================================
"""
Analytics queries for navigation tracking data.

Extracted from the monolithic navigation_tracker.py (1089 lines).
"""

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd

from navigation.tracker import ADMIN_DATA_DIR, NAVIGATION_LOG_FILE

logger = logging.getLogger(__name__)


# ── Data loaders ────────────────────────────────────────────────────────────

def load_all_tracking_data(days: int = 30) -> pd.DataFrame:
    """Charge toutes les données de tracking des derniers jours."""
    all_entries = []
    cutoff_date = datetime.now() - timedelta(days=days)

    for file in ADMIN_DATA_DIR.glob("tracking_*.jsonl"):
        try:
            with open(file, "r", encoding="utf-8") as f:
                for line in f:
                    entry = json.loads(line)
                    entry_time = datetime.fromisoformat(entry["timestamp"])
                    if entry_time >= cutoff_date:
                        all_entries.append(entry)
        except Exception as e:
            logger.warning("Erreur lecture %s: %s", file, e)

    return pd.DataFrame(all_entries) if all_entries else pd.DataFrame()


def load_aoi_uploads(days: int = 30) -> pd.DataFrame:
    """Charge l'historique des uploads AOI."""
    return _load_jsonl("aoi_uploads.jsonl", days)


def load_country_selections(days: int = 30) -> pd.DataFrame:
    """Charge l'historique des sélections de pays."""
    return _load_jsonl("country_selections.jsonl", days)


def load_searches(days: int = 30) -> pd.DataFrame:
    """Charge l'historique des recherches."""
    return _load_jsonl("searches.jsonl", days)


def load_satellites_selected(days: int = 30) -> pd.DataFrame:
    """Charge l'historique des sélections de satellites."""
    return _load_jsonl("satellites_selected.jsonl", days)


def load_tasking_sessions(days: int = 30) -> pd.DataFrame:
    """Charge l'historique des sessions de tasking."""
    return _load_jsonl("tasking_sessions.jsonl", days)


def load_user_sessions(days: int = 30) -> pd.DataFrame:
    """Charge l'historique des sessions utilisateur."""
    return _load_jsonl("user_sessions.jsonl", days)


def _load_jsonl(filename: str, days: int) -> pd.DataFrame:
    """Load entries from a JSONL file within the given number of days."""
    entries = []
    cutoff_date = datetime.now() - timedelta(days=days)
    filepath = ADMIN_DATA_DIR / filename
    if filepath.exists():
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                for line in f:
                    entry = json.loads(line)
                    entry_time = datetime.fromisoformat(entry["timestamp"])
                    if entry_time >= cutoff_date:
                        entries.append(entry)
        except Exception as e:
            logger.warning("Erreur lecture %s: %s", filename, e)
    return pd.DataFrame(entries) if entries else pd.DataFrame()


def load_messages() -> List[Dict]:
    """Charge les messages de contact."""
    messages = []
    messages_dir = Path("messages")
    if not messages_dir.exists():
        return []

    for file in sorted(messages_dir.glob("message_*.json"), reverse=True):
        try:
            with open(file, "r", encoding="utf-8") as f:
                msg = json.load(f)
                msg["filename"] = str(file)
                messages.append(msg)
        except Exception as e:
            logger.warning("Erreur lecture %s: %s", file, e)

    return messages


# ── Statistics ──────────────────────────────────────────────────────────────

def get_navigation_stats() -> Dict[str, Any]:
    """Retourne les statistiques de navigation de la session courante."""
    import streamlit as st

    from navigation.tracker import init_navigation_tracker
    init_navigation_tracker()

    if not st.session_state.navigation_history:
        return {
            "total_views": 0,
            "unique_pages": 0,
            "most_viewed": None,
            "session_duration_min": 0,
            "page_breakdown": {},
            "total_actions": 0,
        }

    df = pd.DataFrame(st.session_state.navigation_history)
    action_count = len(st.session_state.get("action_history", []))

    return {
        "total_views": len(df),
        "unique_pages": df['page'].nunique() if 'page' in df.columns else 0,
        "most_viewed": df['page'].mode().iloc[0] if not df.empty and 'page' in df.columns else None,
        "session_duration_min": (datetime.now() - st.session_state.session_start).total_seconds() / 60,
        "page_breakdown": df['page'].value_counts().to_dict() if 'page' in df.columns else {},
        "total_actions": action_count,
        "last_page": df['page'].iloc[-1] if not df.empty and 'page' in df.columns else None,
        "session_id": st.session_state.session_id,
    }


def get_user_analytics():
    """Get analytics data for admin dashboard."""
    if not NAVIGATION_LOG_FILE.exists():
        return []

    try:
        with open(NAVIGATION_LOG_FILE, 'r', encoding='utf-8') as f:
            logs = json.load(f)
            return logs if isinstance(logs, list) else []
    except Exception:
        return []


def export_all_data(format: str = "csv") -> Dict[str, bytes]:
    """Exporte toutes les données pour téléchargement."""
    exports = {}

    data_sources = {
        "tracking": load_all_tracking_data,
        "aoi_uploads": load_aoi_uploads,
        "country_selections": load_country_selections,
        "searches": load_searches,
        "satellites_selected": load_satellites_selected,
        "tasking_sessions": load_tasking_sessions,
        "user_sessions": load_user_sessions,
    }

    for name, loader in data_sources.items():
        df = loader(days=365)
        if not df.empty:
            if format == "csv":
                exports[f"{name}.csv"] = df.to_csv(index=False).encode('utf-8')
            elif format == "json":
                exports[f"{name}.json"] = df.to_json(orient="records", indent=2).encode('utf-8')

    return exports


def get_user_statistics() -> Dict[str, Any]:
    """Retourne des statistiques globales sur les utilisateurs."""
    df_tracking = load_all_tracking_data(days=30)
    df_aoi = load_aoi_uploads(days=30)
    df_searches = load_searches(days=30)

    return {
        "total_events": len(df_tracking),
        "unique_sessions": df_tracking['session_id'].nunique() if not df_tracking.empty else 0,
        "total_aoi_uploads": len(df_aoi),
        "total_searches": len(df_searches),
        "unique_browsers": df_tracking['browser'].nunique() if not df_tracking.empty and 'browser' in df_tracking.columns else 0,
        "unique_platforms": df_tracking['platform'].nunique() if not df_tracking.empty and 'platform' in df_tracking.columns else 0,
    }


def get_top_countries(limit: int = 10) -> pd.DataFrame:
    """Retourne les pays les plus sélectionnés."""
    df_countries = load_country_selections(days=90)
    if df_countries.empty:
        return pd.DataFrame()

    top_countries = df_countries['country_name'].value_counts().reset_index()
    top_countries.columns = ['Country', 'Selections']
    return top_countries.head(limit)


def get_top_satellites(limit: int = 15) -> pd.DataFrame:
    """Retourne les satellites les plus sélectionnés."""
    df_sats = load_satellites_selected(days=90)
    if df_sats.empty:
        return pd.DataFrame()

    all_sats = []
    for sats in df_sats['satellites']:
        if isinstance(sats, list):
            for sat in sats:
                if isinstance(sat, dict) and 'name' in sat:
                    all_sats.append(sat['name'])

    if not all_sats:
        return pd.DataFrame()

    sat_counts = pd.Series(all_sats).value_counts().reset_index()
    sat_counts.columns = ['Satellite', 'Selections']
    return sat_counts.head(limit)


def get_daily_activity(days: int = 30) -> pd.DataFrame:
    """Retourne l'activité quotidienne."""
    df_tracking = load_all_tracking_data(days=days)
    if df_tracking.empty:
        return pd.DataFrame()

    df_tracking['date'] = pd.to_datetime(df_tracking['timestamp']).dt.date
    daily_activity = df_tracking.groupby('date').size().reset_index(name='count')
    return daily_activity


def get_user_stats_by_ip(days=30) -> pd.DataFrame:
    """Return statistics grouped by IP address."""
    df = load_all_tracking_data(days)
    if df.empty:
        return pd.DataFrame()
    stats = df.groupby('ip').agg({
        'session_id': 'nunique',
        'timestamp': 'count',
        'country': 'first',
    }).rename(columns={'session_id': 'sessions', 'timestamp': 'actions'})
    return stats
