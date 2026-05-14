# pages/admin.py – Complete admin page with all tabs

import streamlit as st
from pathlib import Path
import json
from datetime import datetime
from admin_auth import authenticate_admin
from pages.admin_dashboard import (
    render_dashboard_tab,
    render_user_tracking_tab,
    render_messages_tab,
    render_analytics_tab,
    render_activity_history_tab,
    render_tle_stats_tab,
    render_logs_management_tab,
    render_active_users_tab,
    # New tabs
    render_system_health_tab,
    render_cache_management_tab,
    render_session_management_tab,
    render_backup_restore_tab,
    render_api_status_tab,
    render_log_streaming_tab,
    render_custom_satellites_tab,
    render_sasclouds_stats_tab,
    render_tool_usage_tab,
    render_per_user_activity_tab,
)

def safe_load_messages():
    messages = []
    messages_dir = Path("messages")
    if not messages_dir.exists():
        return messages
    for file in messages_dir.glob("message_*.json"):
        try:
            with open(file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if 'timestamp' in data:
                    if isinstance(data['timestamp'], str):
                        try:
                            data['timestamp'] = datetime.fromisoformat(data['timestamp'])
                        except:
                            data['timestamp'] = datetime.fromtimestamp(file.stat().st_mtime)
                else:
                    data['timestamp'] = datetime.fromtimestamp(file.stat().st_mtime)
                data['filename'] = str(file)
                messages.append(data)
        except Exception:
            continue
    return messages

def load_user_tracking():
    tracking_file = Path("navigation_logs.json")
    if not tracking_file.exists():
        return []
    try:
        with open(tracking_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return data if isinstance(data, list) else []
    except:
        return []

def load_aoi_history():
    aoi_dir = Path("aoi_history")
    aoi_history = []
    if not aoi_dir.exists():
        return aoi_history
    for file in aoi_dir.glob("aoi_*.json"):
        try:
            with open(file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                aoi_history.append(data)
        except:
            continue
    return aoi_history

def main():
    if not authenticate_admin():
        st.stop()
    
    if 'admin_timezone' not in st.session_state:
        st.session_state.admin_timezone = 'UTC'
    
    with st.sidebar:
        st.markdown("### ⚙️ Admin Settings")
        st.session_state.admin_timezone = st.selectbox(
            "🕒 Admin Local Timezone",
            options=['UTC', 'Europe/London', 'Europe/Paris', 'America/New_York', 'Asia/Shanghai', 'Australia/Sydney'],
            index=0,
            help="All timestamps will be shown in this timezone."
        )
        st.markdown("---")
    
    st.title("🔧 OrbitShow Admin Dashboard")
    
    messages = safe_load_messages()
    user_tracking = load_user_tracking()
    aoi_history = load_aoi_history()
    
    tabs = st.tabs([
        "📊 Dashboard",          # 0
        "👥 User Tracking",      # 1
        "📋 Activity History",   # 2
        "📨 Messages",           # 3
        "📈 Analytics",          # 4
        "🛰️ TLE Stats",          # 5
        "📁 Logs Management",    # 6
        "🗄️ SASClouds",          # 7
        "🔧 Tool Usage",         # 8
        "👤 Per-User Activity",  # 9
        "🖥️ System Health",      # 10
        "🗄️ Cache Mgmt",         # 11
        "👤 Session Mgmt",       # 12
        "💾 Backup/Restore",     # 13
        "🔑 API Status",         # 14
        "📜 Log Stream",         # 15
        "🛰️ Custom Sats",        # 16
        "👥 Active Users"        # 17
    ])

    with tabs[0]:
        render_dashboard_tab(user_tracking, messages, aoi_history)
    with tabs[1]:
        render_user_tracking_tab(user_tracking)
    with tabs[2]:
        render_activity_history_tab()
    with tabs[3]:
        render_messages_tab(messages)
    with tabs[4]:
        render_analytics_tab(user_tracking)
    with tabs[5]:
        render_tle_stats_tab()
    with tabs[6]:
        render_logs_management_tab()
    with tabs[7]:
        render_sasclouds_stats_tab()
    with tabs[8]:
        render_tool_usage_tab()
    with tabs[9]:
        render_per_user_activity_tab()
    with tabs[10]:
        render_system_health_tab()
    with tabs[11]:
        render_cache_management_tab()
    with tabs[12]:
        render_session_management_tab()
    with tabs[13]:
        render_backup_restore_tab()
    with tabs[14]:
        render_api_status_tab()
    with tabs[15]:
        render_log_streaming_tab()
    with tabs[16]:
        render_custom_satellites_tab()
    with tabs[17]:
        render_active_users_tab()

if __name__ == "__main__":
    from datetime import datetime
    main()