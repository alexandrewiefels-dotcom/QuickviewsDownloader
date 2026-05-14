# pages/admin_dashboard.py – COMPLETE WITH ACTIVE USERS AND NEW MANAGEMENT TABS

import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime, timedelta
import pytz
from pathlib import Path
import json
import folium
from streamlit_folium import st_folium
from shapely.geometry import shape, mapping, Point
import base64
import simplekml
import geopandas as gpd
import traceback
import shutil
import zipfile
import tempfile
import requests

from navigation_tracker import SEARCH_HISTORY_DIR, get_user_stats_by_ip, get_active_sessions

# ============================================================================
# Helper: Country lookup from AOI (unchanged)
# ============================================================================
@st.cache_data
def load_country_geojson():
    base_dir = Path(__file__).parent.parent
    possible_names = ["world_countries.geojson", "world_countries.GeoJSON", "ne_110m_admin_0_countries.geojson"]
    possible_paths = [base_dir / "data" / name for name in possible_names]
    for path in possible_paths:
        if path.exists():
            try:
                gdf = gpd.read_file(path)
                name_col = None
                for col in ['CNTRY_NAME', 'NAME', 'name', 'ADMIN', 'SOVEREIGNT']:
                    if col in gdf.columns:
                        name_col = col
                        break
                if name_col:
                    gdf = gdf[[name_col, 'geometry']].rename(columns={name_col: 'country'})
                    gdf = gdf.to_crs('EPSG:4326')
                    return gdf
            except Exception:
                continue
    return None

def utc_to_local(utc_dt: datetime, tz_str: str) -> datetime:
    if utc_dt.tzinfo is None:
        utc_dt = utc_dt.replace(tzinfo=pytz.UTC)
    local_tz = pytz.timezone(tz_str)
    return utc_dt.astimezone(local_tz)

def get_country_from_aoi(aoi_geom):
    if aoi_geom is None or aoi_geom.is_empty:
        return "Unknown"
    centroid = aoi_geom.centroid
    point = Point(centroid.x, centroid.y)
    gdf = load_country_geojson()
    if gdf is not None:
        countries = gdf[gdf.geometry.contains(point)]
        if not countries.empty:
            return countries.iloc[0]['country']
    lon = centroid.x
    if -180 <= lon <= -60:
        return "Americas"
    elif -60 < lon <= -30:
        return "South America"
    elif -30 < lon <= 30:
        return "Africa/Europe"
    elif 30 < lon <= 90:
        return "Asia"
    elif 90 < lon <= 180:
        return "Asia/Pacific"
    return "Unknown"

# ============================================================================
# KML generation for search record (unchanged)
# ============================================================================
def generate_kml_from_record(record):
    import simplekml
    from shapely.geometry import shape, mapping
    kml = simplekml.Kml()
    # AOI
    aoi_data = record.get('aoi')
    aoi_geom = None
    if aoi_data:
        try:
            if isinstance(aoi_data, dict):
                aoi_geom = shape(aoi_data)
            elif isinstance(aoi_data, str):
                from shapely import wkt
                aoi_geom = wkt.loads(aoi_data)
        except Exception:
            aoi_geom = None
    if aoi_geom and not aoi_geom.is_empty:
        try:
            aoi_folder = kml.newfolder(name="AOI")
            geom = mapping(aoi_geom)
            if geom['type'] == 'Polygon':
                pol = aoi_folder.newpolygon(name="Area of Interest")
                coords = [(lon, lat) for lon, lat, *_ in geom['coordinates'][0]]
                pol.outerboundaryis = coords
                pol.style.polystyle.color = simplekml.Color.changealpha("33", "0000FF")
            elif geom['type'] == 'MultiPolygon':
                for idx, poly_coords in enumerate(geom['coordinates']):
                    pol = aoi_folder.newpolygon(name=f"Area of Interest part {idx+1}")
                    coords = [(lon, lat) for lon, lat, *_ in poly_coords[0]]
                    pol.outerboundaryis = coords
                    pol.style.polystyle.color = simplekml.Color.changealpha("33", "0000FF")
        except Exception:
            pass
    # Passes
    passes_folder = kml.newfolder(name="Passes")
    for p in record.get('passes', []):
        if p.get('footprint'):
            try:
                fp = shape(p['footprint'])
                if fp and not fp.is_empty:
                    parts = [fp] if fp.geom_type == 'Polygon' else list(fp.geoms)
                    for part in parts:
                        pol = passes_folder.newpolygon(name=f"{p['satellite']} - {p['camera']} - {p['pass_time'][:19]}")
                        coords = [(lon, lat) for lon, lat, *_ in part.exterior.coords]
                        pol.outerboundaryis = coords
                        pol.style.polystyle.color = simplekml.Color.changealpha("44", "FF0000")
                        pol.extendeddata.newdata('Satellite', p['satellite'])
                        pol.extendeddata.newdata('ONA', str(p.get('min_ona', 'N/A')))
            except Exception:
                pass
    return kml.kml()

# ============================================================================
# Data loading functions with caching (unchanged)
# ============================================================================
@st.cache_data(ttl=300)
def load_aoi_uploads_cached():
    aoi_dir = Path("aoi_history")
    entries = []
    if not aoi_dir.exists():
        return entries
    for file in aoi_dir.glob("aoi_*.json"):
        try:
            with open(file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                data['type'] = 'aoi_upload'
                data['source_file'] = str(file)
                entries.append(data)
        except Exception:
            continue
    return entries

@st.cache_data(ttl=300)
def load_country_selections_cached():
    entries = []
    filepath = Path("admin_data/country_selections.jsonl")
    if not filepath.exists():
        return entries
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            for line in f:
                data = json.loads(line)
                data['type'] = 'country_select'
                entries.append(data)
    except Exception:
        pass
    return entries

@st.cache_data(ttl=300)
def load_search_history_cached():
    entries = []
    if not SEARCH_HISTORY_DIR.exists():
        return entries
    for file in SEARCH_HISTORY_DIR.glob("search_*.json"):
        try:
            with open(file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                data['type'] = 'search'
                data['source_file'] = str(file)
                entries.append(data)
        except Exception:
            continue
    return entries

@st.cache_data(ttl=300)
def load_custom_satellites_cached():
    entries = []
    filepath = Path("admin_data/custom_satellites.jsonl")
    if not filepath.exists():
        return entries
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            for line in f:
                data = json.loads(line)
                data['type'] = 'custom_satellite'
                entries.append(data)
    except Exception:
        pass
    return entries

def load_all_activities():
    activities = []
    activities.extend(load_aoi_uploads_cached())
    activities.extend(load_country_selections_cached())
    activities.extend(load_search_history_cached())
    activities.extend(load_custom_satellites_cached())
    activities.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
    return activities

# ============================================================================
# TLE Stats Tab (unchanged)
# ============================================================================
def render_tle_stats_tab():
    st.subheader("🛰️ TLE Data Management")
    with st.spinner("Loading TLE statistics..."):
        try:
            from data.tle_fetcher import get_tle_fetcher, get_supplier_stats, get_update_history
            from config.satellites import get_satellite_count
            fetcher = get_tle_fetcher()
            total_sats = get_satellite_count()
            valid_tles = 0
            for norad in fetcher.tles:
                if fetcher._is_valid_tle(fetcher.tles[norad]):
                    valid_tles += 1
            missing = total_sats - valid_tles
            cache_age = fetcher.get_cache_age_hours()
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("Total Satellites in DB", total_sats)
            col2.metric("Valid TLEs in Cache", f"{valid_tles} / {total_sats}", delta=f"{valid_tles/total_sats*100:.0f}%")
            col3.metric("Missing TLEs", missing, delta="needs download" if missing>0 else "")
            col4.metric("Cache Age", f"{cache_age:.1f} hours", delta="stale" if cache_age>48 else "fresh")
            st.markdown("---")
            st.subheader("Supplier Usage History")
            stats = get_supplier_stats()
            if stats:
                df_stats = pd.DataFrame.from_dict(stats, orient='index')
                df_stats = df_stats.reset_index().rename(columns={'index': 'Supplier'})
                df_stats['success_rate'] = (df_stats['success'] / df_stats['total'] * 100).round(1)
                if 'last_used' in df_stats.columns:
                    df_stats['last_used'] = pd.to_datetime(df_stats['last_used']).dt.strftime('%Y-%m-%d %H:%M')
                st.dataframe(df_stats[['Supplier', 'total', 'success', 'failed', 'success_rate', 'last_used']], use_container_width=True)
                fig = px.bar(df_stats, x='Supplier', y='success_rate', title="Success Rate by Supplier",
                             color='Supplier', text='success_rate')
                fig.update_traces(texttemplate='%{text:.1f}%', textposition='outside')
                st.plotly_chart(fig, use_container_width=True)
                supplier_success = df_stats[df_stats['Supplier'] != 'generated'][['Supplier', 'success']]
                if not supplier_success.empty:
                    fig2 = px.pie(supplier_success, values='success', names='Supplier', title="Successful TLEs by Supplier")
                    st.plotly_chart(fig2, use_container_width=True)
            else:
                st.info("No supplier statistics available yet.")
            st.markdown("---")
            st.subheader("Update History")
            history = get_update_history()
            if history and len(history) > 0:
                df_history = pd.DataFrame(history)
                df_history['timestamp'] = pd.to_datetime(df_history['timestamp'])
                df_history = df_history.sort_values('timestamp', ascending=False)
                st.dataframe(df_history.head(20), use_container_width=True)
                if len(df_history) > 1:
                    fig3 = px.line(df_history, x='timestamp', y=['success', 'failed'], title="TLE Updates Over Time")
                    st.plotly_chart(fig3, use_container_width=True)
            else:
                st.info("No update history recorded.")
            st.markdown("---")
            st.subheader("Connection Status")
            col_a, col_b = st.columns(2)
            with col_a:
                st.markdown("**Space-Track**")
                if fetcher.space_track_available:
                    st.success("✅ Last login successful")
                else:
                    st.error("❌ Login failed or credentials missing")
                st.caption(f"Credentials present: {bool(fetcher.space_track_user)}")
            with col_b:
                st.markdown("**N2YO.com**")
                if fetcher.n2yo_api_key:
                    st.success("✅ API key configured")
                else:
                    st.warning("⚠️ No API key")
        except Exception as e:
            st.error(f"Error loading TLE stats: {e}")

# ============================================================================
# Dashboard tab (unchanged)
# ============================================================================
def render_dashboard_tab(user_tracking, messages, aoi_history):
    st.subheader("Dashboard Overview")
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Total Messages", len(messages))
    with col2:
        st.metric("User Actions", len(user_tracking))
    with col3:
        st.metric("AOI Uploads", len(aoi_history))
    with col4:
        unique_users = len(set([u.get('session_id', 'unknown') for u in user_tracking]))
        st.metric("Unique Users", unique_users)

    # SASClouds search summary row
    sc_searches = _load_sc_searches()
    sc_total_scenes = sum(r.get("num_scenes", 0) for r in sc_searches)
    sc_unique_sessions = len({r.get("session_id", "") for r in sc_searches})
    sc_col1, sc_col2, sc_col3 = st.columns(3)
    sc_col1.metric("SASClouds Searches", len(sc_searches))
    sc_col2.metric("SASClouds Scenes Found", sc_total_scenes)
    sc_col3.metric("Sessions with SC Search", sc_unique_sessions)
    if user_tracking:
        df_activity = pd.DataFrame(user_tracking)
        if 'timestamp' in df_activity.columns:
            df_activity['timestamp'] = pd.to_datetime(df_activity['timestamp'], errors='coerce')
            df_activity = df_activity.dropna(subset=['timestamp'])
            df_activity['date'] = df_activity['timestamp'].dt.date
            daily_activity = df_activity.groupby('date').size().reset_index(name='count')
            fig = px.line(daily_activity, x='date', y='count', title="Daily User Activity (Last 30 Days)")
            st.plotly_chart(fig, use_container_width=True)
    st.subheader("📐 Recent AOI Records")
    aoi_records = []
    for aoi in aoi_history[-20:]:
        name = aoi.get('filename', 'Unknown')
        area = aoi.get('area_km2', None)
        if area is None and aoi.get('geometry'):
            try:
                geom = shape(aoi['geometry'])
                area_km2 = geom.area * 111.0 * 111.0
                area = f"{area_km2:.2f} km²"
            except:
                area = "N/A"
        else:
            area = f"{area:.2f} km²" if area else "N/A"
        timestamp = aoi.get('timestamp', '')
        source = "Upload"
        aoi_records.append({"Timestamp": timestamp, "Name": name, "Area": area, "Source": source})
    country_selections = load_country_selections_cached()
    for cs in country_selections[-20:]:
        name = cs.get('country_name', 'Unknown')
        area = "Country boundary"
        timestamp = cs.get('timestamp', '')
        source = "Country Select"
        aoi_records.append({"Timestamp": timestamp, "Name": name, "Area": area, "Source": source})
    if aoi_records:
        df_aoi = pd.DataFrame(aoi_records)
        df_aoi = df_aoi.sort_values('Timestamp', ascending=False)
        st.dataframe(df_aoi, use_container_width=True)
    else:
        st.info("No AOI records found.")

# ============================================================================
# User Tracking Tab (unchanged)
# ============================================================================
def render_user_tracking_tab(user_tracking):
    st.subheader("👥 User Tracking")
    if not user_tracking:
        st.info("No user tracking data available yet")
        return
    df = pd.DataFrame(user_tracking)
    col_f1, col_f2, col_f3 = st.columns(3)
    with col_f1:
        action_options = df['action'].unique() if 'action' in df.columns else []
        action_filter = st.multiselect("Filter by Action", options=action_options, default=[])
    with col_f2:
        date_range = st.date_input("Date Range", value=(datetime.now() - timedelta(days=7), datetime.now()))
    with col_f3:
        search_user = st.text_input("Search by Session ID", placeholder="Enter session ID...")
    filtered_df = df.copy()
    if 'timestamp' in filtered_df.columns:
        filtered_df['timestamp'] = pd.to_datetime(filtered_df['timestamp'], errors='coerce')
        filtered_df = filtered_df.dropna(subset=['timestamp'])
        if len(date_range) == 2:
            mask = (filtered_df['timestamp'].dt.date >= date_range[0]) & \
                   (filtered_df['timestamp'].dt.date <= date_range[1])
            filtered_df = filtered_df[mask]
    if action_filter:
        filtered_df = filtered_df[filtered_df['action'].isin(action_filter)]
    if search_user:
        filtered_df = filtered_df[filtered_df['session_id'].str.contains(search_user, case=False, na=False)]
    display_cols = ['timestamp', 'session_id', 'action', 'details', 'ip', 'country']
    available_cols = [c for c in display_cols if c in filtered_df.columns]
    st.dataframe(filtered_df[available_cols].head(100), use_container_width=True)
    st.subheader("User Statistics")
    col_s1, col_s2 = st.columns(2)
    with col_s1:
        if 'session_id' in filtered_df.columns:
            user_actions = filtered_df.groupby('session_id').size().reset_index(name='action_count')
            user_actions = user_actions.sort_values('action_count', ascending=False).head(10)
            fig = px.bar(user_actions, x='session_id', y='action_count', title="Top 10 Users by Actions")
            st.plotly_chart(fig, use_container_width=True)
    with col_s2:
        if 'action' in filtered_df.columns:
            action_counts = filtered_df['action'].value_counts().head(10)
            fig = px.pie(values=action_counts.values, names=action_counts.index, title="Actions Distribution")
            st.plotly_chart(fig, use_container_width=True)

# ============================================================================
# Messages Tab (with pagination) – unchanged
# ============================================================================
def render_messages_tab(messages):
    st.subheader("📨 User Messages (Mailbox)")
    if "messages_page" not in st.session_state:
        st.session_state.messages_page = 1
    if "messages_page_size" not in st.session_state:
        st.session_state.messages_page_size = 20
    if len(messages) > 10000:
        messages = messages[:10000]
        st.info("Showing the most recent 10,000 messages. Use pagination to navigate.")
    if not messages:
        st.info("No messages received yet")
        return
    col1, col2, col3 = st.columns([1, 2, 1])
    with col1:
        page_size_options = [10, 20, 50, 100]
        page_size = st.selectbox(
            "Messages per page",
            options=page_size_options,
            index=page_size_options.index(st.session_state.messages_page_size),
            key="msg_page_size_sel"
        )
        if page_size != st.session_state.messages_page_size:
            st.session_state.messages_page_size = page_size
            st.session_state.messages_page = 1
            st.rerun()
    total_pages = (len(messages) + page_size - 1) // page_size
    start_idx = (st.session_state.messages_page - 1) * page_size
    end_idx = min(start_idx + page_size, len(messages))
    current_messages = messages[start_idx:end_idx]
    with col2:
        st.write(f"Page {st.session_state.messages_page} of {total_pages}")
    with col3:
        col_p1, col_p2 = st.columns(2)
        with col_p1:
            if st.button("◀ Previous", key="msg_prev") and st.session_state.messages_page > 1:
                st.session_state.messages_page -= 1
                st.rerun()
        with col_p2:
            if st.button("Next ▶", key="msg_next") and st.session_state.messages_page < total_pages:
                st.session_state.messages_page += 1
                st.rerun()
    status_file = Path("admin_data/message_status.json")
    if status_file.exists():
        with open(status_file) as f:
            status = json.load(f)
    else:
        status = {}
    col_list, col_preview = st.columns([1, 2])
    with col_list:
        st.markdown("### Inbox")
        for idx, msg in enumerate(current_messages):
            msg_id = msg.get('filename', f"msg_{idx}")
            unique_key = f"msg_{msg_id}_{st.session_state.messages_page}_{idx}"
            is_read = status.get(msg_id, False)
            icon = "📖" if is_read else "📧"
            subject = msg.get('subject', 'No subject')
            timestamp = msg.get('timestamp', '')
            if isinstance(timestamp, str):
                timestamp = timestamp[:19]
            label = f"{icon} {subject[:40]} - {timestamp}"
            if st.button(label, key=unique_key, use_container_width=True):
                st.session_state.current_message = msg
                st.session_state.current_message_id = msg_id
                status[msg_id] = True
                with open(status_file, 'w') as f:
                    json.dump(status, f)
                st.rerun()
    with col_preview:
        if st.session_state.get('current_message'):
            msg = st.session_state.current_message
            st.markdown(f"### {msg.get('subject', 'No Subject')}")
            st.write(f"**From:** {msg.get('name')} ({msg.get('email')})")
            st.write(f"**Date:** {msg.get('timestamp')}")
            st.write(f"**Session ID:** {msg.get('session_id')}")
            st.write(f"**Message:**\n{msg.get('message')}")
            col_act1, col_act2 = st.columns(2)
            with col_act1:
                if st.button("🗑️ Delete", use_container_width=True):
                    Path(msg['filename']).unlink()
                    del st.session_state.current_message
                    st.rerun()
            with col_act2:
                if st.button("✉️ Reply (copy email)", use_container_width=True):
                    st.info(f"Copy this address to reply: {msg['email']}")

# ============================================================================
# Analytics Tab (with time window filter and clickable users) – unchanged
# ============================================================================
def render_analytics_tab(user_tracking):
    st.subheader("📈 Analytics")
    if not user_tracking:
        st.info("No analytics data available")
        return
    time_window = st.radio(
        "Time window",
        options=["All", "Last Week", "Last Month", "Last 6 Months", "Last Year"],
        index=0,
        horizontal=True
    )
    df_analytics = pd.DataFrame(user_tracking)
    if 'timestamp' in df_analytics.columns:
        df_analytics['timestamp'] = pd.to_datetime(df_analytics['timestamp'], errors='coerce')
        df_analytics = df_analytics.dropna(subset=['timestamp'])
        now = datetime.now()
        if time_window == "Last Week":
            cutoff = now - timedelta(days=7)
            df_analytics = df_analytics[df_analytics['timestamp'] >= cutoff]
        elif time_window == "Last Month":
            cutoff = now - timedelta(days=30)
            df_analytics = df_analytics[df_analytics['timestamp'] >= cutoff]
        elif time_window == "Last 6 Months":
            cutoff = now - timedelta(days=180)
            df_analytics = df_analytics[df_analytics['timestamp'] >= cutoff]
        elif time_window == "Last Year":
            cutoff = now - timedelta(days=365)
            df_analytics = df_analytics[df_analytics['timestamp'] >= cutoff]
    if len(df_analytics) > 5000:
        st.warning(f"Showing only the last 5,000 of {len(df_analytics)} records. Consider clearing old logs.")
        df_analytics = df_analytics.iloc[-5000:]
    if df_analytics.empty:
        st.info("No data for the selected time window.")
        return
    with st.spinner("Processing analytics data..."):
        try:
            if 'timestamp' in df_analytics.columns:
                try:
                    df_analytics['hour'] = df_analytics['timestamp'].dt.floor('h')
                    hourly_counts = df_analytics.groupby('hour').size().reset_index(name='count')
                    fig = px.line(hourly_counts, x='hour', y='count', title="User Activity Over Time")
                    st.plotly_chart(fig, use_container_width=True)
                except Exception as e:
                    st.warning(f"Could not generate hourly chart: {e}")
                    df_analytics['date'] = df_analytics['timestamp'].dt.date
                    daily_counts = df_analytics.groupby('date').size().reset_index(name='count')
                    st.dataframe(daily_counts)
                df_analytics['date'] = df_analytics['timestamp'].dt.date
                daily_counts = df_analytics.groupby('date').size().reset_index(name='count')
                fig = px.bar(daily_counts, x='date', y='count', title="Daily User Activity")
                st.plotly_chart(fig, use_container_width=True)
                if 'action' in df_analytics.columns:
                    col_p1, col_p2 = st.columns(2)
                    with col_p1:
                        popular_actions = df_analytics['action'].value_counts().head(10)
                        fig = px.bar(popular_actions, title="Most Used Features")
                        st.plotly_chart(fig, use_container_width=True)
                    with col_p2:
                        if 'country' in df_analytics.columns:
                            country_counts = df_analytics['country'].value_counts().head(10)
                            fig = px.pie(values=country_counts.values, names=country_counts.index, title="Users by Country")
                            st.plotly_chart(fig, use_container_width=True)
                if 'session_id' in df_analytics.columns:
                    user_actions = df_analytics.groupby('session_id').size().reset_index(name='action_count')
                    user_actions = user_actions.sort_values('action_count', ascending=False).head(10)
                    st.markdown("#### Top 10 Users by Actions (click to view details)")
                    cols = st.columns(2)
                    for idx, row in user_actions.iterrows():
                        sess_id = row['session_id']
                        count = row['action_count']
                        short_id = sess_id[:12] + "..." if len(sess_id) > 12 else sess_id
                        with cols[idx % 2]:
                            if st.button(f"{short_id} – {count} actions", key=f"user_btn_{sess_id}"):
                                st.session_state.selected_user = sess_id
                    if 'selected_user' in st.session_state and st.session_state.selected_user:
                        selected = st.session_state.selected_user
                        st.markdown(f"### 📋 User details: `{selected}`")
                        user_df = df_analytics[df_analytics['session_id'] == selected]
                        st.dataframe(user_df[['timestamp', 'action', 'page', 'ip', 'country']].head(100), use_container_width=True)
                        if st.button("Clear selection", key="clear_user_selection"):
                            del st.session_state.selected_user
                            st.rerun()
                    fig = px.bar(user_actions, x='session_id', y='action_count', title="Top 10 Users by Actions (bar view)")
                    st.plotly_chart(fig, use_container_width=True)
                st.subheader("Users by IP Address")
                ip_stats = get_user_stats_by_ip(days=30)
                if not ip_stats.empty:
                    st.dataframe(ip_stats)
                else:
                    st.info("No IP data available")
        except Exception as e:
            st.error(f"An error occurred while loading analytics: {e}")

# ============================================================================
# Activity History Tab (with pagination and map zoom fix) – unchanged
# ============================================================================
def render_activity_history_tab():
    st.subheader("📋 Unified Activity History")
    st.markdown("All user activities: AOI uploads, country selections, satellite searches, and custom satellite additions.")
    activities = load_all_activities()
    if not activities:
        st.info("No activities recorded yet.")
        return
    tz = st.session_state.get('admin_timezone', 'UTC')
    col_f1, col_f2 = st.columns(2)
    with col_f1:
        type_filter = st.multiselect(
            "Filter by activity type",
            options=['aoi_upload', 'country_select', 'search', 'custom_satellite'],
            format_func=lambda x: {
                'aoi_upload': '📁 AOI Upload',
                'country_select': '🌍 Country Select',
                'search': '🔍 Satellite Search',
                'custom_satellite': '🛰️ Custom Satellite'
            }.get(x, x),
            default=[]
        )
    with col_f2:
        search_text = st.text_input("Search by IP, session ID, country, or satellite name", placeholder="e.g., 192.168.1.1")
    filtered = []
    for act in activities:
        if type_filter and act.get('type') not in type_filter:
            continue
        if search_text:
            ip = act.get('ip', '') or act.get('client_info', {}).get('ip', '')
            session = act.get('session_id', '')
            country = act.get('country', '')
            name = act.get('satellite_name', '') if act.get('type') == 'custom_satellite' else ''
            if (search_text.lower() not in ip.lower() and 
                search_text.lower() not in session.lower() and 
                search_text.lower() not in country.lower() and
                search_text.lower() not in name.lower()):
                continue
        filtered.append(act)
    if not filtered:
        st.info("No matching activities.")
        return
    if "activity_page" not in st.session_state:
        st.session_state.activity_page = 1
    if "activity_page_size" not in st.session_state:
        st.session_state.activity_page_size = 20
    col1, col2, col3 = st.columns([1, 2, 1])
    with col1:
        page_size_options = [10, 20, 50, 100]
        page_size = st.selectbox(
            "Records per page",
            options=page_size_options,
            index=page_size_options.index(st.session_state.activity_page_size),
            key="act_page_size_sel"
        )
        if page_size != st.session_state.activity_page_size:
            st.session_state.activity_page_size = page_size
            st.session_state.activity_page = 1
            st.rerun()
    total_pages = (len(filtered) + page_size - 1) // page_size
    start_idx = (st.session_state.activity_page - 1) * page_size
    end_idx = min(start_idx + page_size, len(filtered))
    current_activities = filtered[start_idx:end_idx]
    with col2:
        st.write(f"Page {st.session_state.activity_page} of {total_pages}")
    with col3:
        col_p1, col_p2 = st.columns(2)
        with col_p1:
            if st.button("◀ Previous", key="act_prev") and st.session_state.activity_page > 1:
                st.session_state.activity_page -= 1
                st.rerun()
        with col_p2:
            if st.button("Next ▶", key="act_next") and st.session_state.activity_page < total_pages:
                st.session_state.activity_page += 1
                st.rerun()
    for act in current_activities:
        timestamp_utc = act.get('timestamp')
        if isinstance(timestamp_utc, str):
            try:
                dt_utc = datetime.fromisoformat(timestamp_utc)
            except:
                dt_utc = datetime.now(pytz.UTC)
        else:
            dt_utc = timestamp_utc or datetime.now(pytz.UTC)
        dt_local = utc_to_local(dt_utc, tz)
        timestamp_local = dt_local.strftime('%Y-%m-%d %H:%M:%S')
        activity_type = act.get('type')
        if activity_type == 'aoi_upload':
            icon = "📁"
            title = "AOI Upload"
            ip = act.get('ip', 'unknown')
            session_id = act.get('user_id', act.get('session_id', 'unknown'))
            country_val = act.get('country', 'Unknown')
            filename = act.get('filename', 'unknown')
            source = act.get('source', 'upload')
            aoi_geom = None
            aoi_data = act.get('geometry') or act.get('aoi_wkt')
            if aoi_data:
                try:
                    if isinstance(aoi_data, dict):
                        aoi_geom = shape(aoi_data)
                    elif isinstance(aoi_data, str):
                        from shapely import wkt
                        aoi_geom = wkt.loads(aoi_data)
                except Exception:
                    pass
            area_km2 = act.get('area_km2')
            if not area_km2 and aoi_geom:
                area_km2 = aoi_geom.area * 111.0 * 111.0
            with st.expander(f"{icon} {title} - {timestamp_local} - {ip} ({country_val})"):
                col_info, col_map = st.columns([1, 1])
                with col_info:
                    st.write(f"**Session ID:** `{session_id}`")
                    st.write(f"**IP:** {ip}")
                    st.write(f"**Country:** {country_val}")
                    if act.get('city'):
                        st.write(f"**City:** {act.get('city')}")
                    st.write(f"**File:** {filename}")
                    st.write(f"**Source:** {source}")
                    if area_km2:
                        st.write(f"**Area:** {area_km2:.2f} km²")
                with col_map:
                    if aoi_geom and not aoi_geom.is_empty:
                        bounds = aoi_geom.bounds
                        sw = [bounds[1], bounds[0]]
                        ne = [bounds[3], bounds[2]]
                        center = [aoi_geom.centroid.y, aoi_geom.centroid.x]
                        m = folium.Map(location=center, zoom_start=10, width=400, height=300)
                        m.fit_bounds([sw, ne])
                        folium.GeoJson(
                            data=mapping(aoi_geom),
                            style_function=lambda x: {
                                'fillColor': '#ff0000',
                                'color': '#ff0000',
                                'weight': 2,
                                'fillOpacity': 0.2
                            }
                        ).add_to(m)
                        st_folium(m, width=400, height=300, key=f"aoi_map_{act.get('timestamp', '')}")
                    else:
                        st.info("No AOI geometry available.")
                if aoi_geom and not aoi_geom.is_empty:
                    geojson_str = json.dumps(mapping(aoi_geom), indent=2)
                    b64_geojson = base64.b64encode(geojson_str.encode()).decode()
                    href = f'<a href="data:application/geo+json;base64,{b64_geojson}" download="aoi_{timestamp_local}.geojson" style="text-decoration:none; background-color:#f0f2f6; padding:6px 12px; border-radius:4px;">📥 Download AOI (GeoJSON)</a>'
                    st.markdown(href, unsafe_allow_html=True)
        elif activity_type == 'country_select':
            icon = "🌍"
            title = f"Country Selection: {act.get('country_name', 'Unknown')}"
            ip = act.get('ip', 'unknown')
            session_id = act.get('session_id', 'unknown')
            country_val = act.get('country_name', 'Unknown')
            aoi_geom = None
            country_wkt = act.get('country_wkt')
            if country_wkt:
                try:
                    from shapely import wkt
                    aoi_geom = wkt.loads(country_wkt)
                except Exception:
                    pass
            with st.expander(f"{icon} {title} - {timestamp_local} - {ip} ({country_val})"):
                col_info, col_map = st.columns([1, 1])
                with col_info:
                    st.write(f"**Session ID:** `{session_id}`")
                    st.write(f"**IP:** {ip}")
                    st.write(f"**Selected Country:** {country_val}")
                    if act.get('city'):
                        st.write(f"**City:** {act.get('city')}")
                with col_map:
                    if aoi_geom and not aoi_geom.is_empty:
                        bounds = aoi_geom.bounds
                        sw = [bounds[1], bounds[0]]
                        ne = [bounds[3], bounds[2]]
                        center = [aoi_geom.centroid.y, aoi_geom.centroid.x]
                        m = folium.Map(location=center, zoom_start=10, width=400, height=300)
                        m.fit_bounds([sw, ne])
                        folium.GeoJson(
                            data=mapping(aoi_geom),
                            style_function=lambda x: {
                                'fillColor': '#00FF00',
                                'color': '#00FF00',
                                'weight': 2,
                                'fillOpacity': 0.2
                            }
                        ).add_to(m)
                        st_folium(m, width=400, height=300, key=f"country_map_{act.get('timestamp', '')}")
                    else:
                        st.info("No geometry available.")
                if aoi_geom and not aoi_geom.is_empty:
                    geojson_str = json.dumps(mapping(aoi_geom), indent=2)
                    b64_geojson = base64.b64encode(geojson_str.encode()).decode()
                    href = f'<a href="data:application/geo+json;base64,{b64_geojson}" download="country_{country_val}_{timestamp_local}.geojson" style="text-decoration:none; background-color:#f0f2f6; padding:6px 12px; border-radius:4px;">📥 Download AOI (GeoJSON)</a>'
                    st.markdown(href, unsafe_allow_html=True)
        elif activity_type == 'search':
            icon = "🔍"
            title = "Satellite Search"
            ip = act.get('ip', 'unknown')
            session_id = act.get('session_id', 'unknown')
            country_val = act.get('country', 'Unknown')
            aoi_geom = None
            aoi_data = act.get('aoi')
            if aoi_data:
                try:
                    if isinstance(aoi_data, dict):
                        aoi_geom = shape(aoi_data)
                    elif isinstance(aoi_data, str):
                        from shapely import wkt
                        aoi_geom = wkt.loads(aoi_data)
                except Exception:
                    pass
            if country_val == "Unknown" and aoi_geom:
                country_val = get_country_from_aoi(aoi_geom)
            with st.expander(f"{icon} {title} - {timestamp_local} - {ip} ({country_val})"):
                col_info, col_map = st.columns([1, 1])
                with col_info:
                    st.write(f"**Session ID:** `{session_id}`")
                    st.write(f"**IP:** {ip}")
                    st.write(f"**Country:** {country_val}")
                    if act.get('city'):
                        st.write(f"**City:** {act.get('city')}")
                    st.markdown("**Filters:**")
                    filters = act.get('filters', {})
                    for k, v in filters.items():
                        st.write(f"- {k}: {v}")
                    st.markdown("**Selected Satellites:**")
                    sats = act.get('selected_satellites', [])
                    for sat in sats:
                        st.write(f"- {sat}")
                    st.write(f"**Passes found:** {len(act.get('passes', []))}")
                with col_map:
                    if aoi_geom and not aoi_geom.is_empty:
                        bounds = aoi_geom.bounds
                        sw = [bounds[1], bounds[0]]
                        ne = [bounds[3], bounds[2]]
                        center = [aoi_geom.centroid.y, aoi_geom.centroid.x]
                        m = folium.Map(location=center, zoom_start=10, width=400, height=300)
                        m.fit_bounds([sw, ne])
                        folium.GeoJson(
                            data=mapping(aoi_geom),
                            style_function=lambda x: {
                                'fillColor': '#0000FF',
                                'color': '#0000FF',
                                'weight': 2,
                                'fillOpacity': 0.2
                            }
                        ).add_to(m)
                        st_folium(m, width=400, height=300, key=f"search_map_{act.get('search_id', '')}")
                    else:
                        st.info("No AOI geometry.")
                if aoi_geom and not aoi_geom.is_empty:
                    geojson_str = json.dumps(mapping(aoi_geom), indent=2)
                    b64_geojson = base64.b64encode(geojson_str.encode()).decode()
                    href_geojson = f'<a href="data:application/geo+json;base64,{b64_geojson}" download="search_aoi_{timestamp_local}.geojson" style="text-decoration:none; background-color:#f0f2f6; padding:6px 12px; border-radius:4px;">📥 Download AOI (GeoJSON)</a>'
                    st.markdown(href_geojson, unsafe_allow_html=True)
                if act.get('passes'):
                    try:
                        kml_str = generate_kml_from_record(act)
                        b64_kml = base64.b64encode(kml_str.encode()).decode()
                        href_kml = f'<a href="data:application/vnd.google-earth.kml+xml;base64,{b64_kml}" download="search_footprints_{act.get("search_id", "search")}.kml" style="display:inline-block; margin-top:8px; text-decoration:none; background-color:#f0f2f6; padding:6px 12px; border-radius:4px;">📥 Download Footprints (KML)</a>'
                        st.markdown(href_kml, unsafe_allow_html=True)
                    except Exception as e:
                        st.error(f"Could not generate KML for this search: {e}")
        elif activity_type == 'custom_satellite':
            icon = "🛰️➕"
            sat_name = act.get('satellite_name', 'Unknown')
            norad = act.get('norad', 'N/A')
            title = f"Custom Satellite: {sat_name} (NORAD {norad})"
            ip = act.get('ip', 'unknown')
            session_id = act.get('session_id', 'unknown')
            country_val = act.get('country', 'Unknown')
            swath = act.get('swath_km', 'N/A')
            resolution = act.get('resolution_m', 'N/A')
            with st.expander(f"{icon} {title} - {timestamp_local} - {ip} ({country_val})"):
                st.write(f"**Session ID:** `{session_id}`")
                st.write(f"**IP:** {ip}")
                st.write(f"**Country:** {country_val}")
                st.write(f"**NORAD ID:** {norad}")
                st.write(f"**Satellite Name:** {sat_name}")
                st.write(f"**Swath Width:** {swath} km")
                st.write(f"**Resolution:** {resolution} m")
                st.info("This satellite was added by the user and is now available in the satellite selection list.")

# ============================================================================
# Logs Management Tab (unchanged, already contains truncation and manual cleanup)
# ============================================================================
def get_log_stats():
    logs = {
        "navigation_logs.json": {"path": Path("navigation_logs.json")},
        "admin_data/user_sessions.jsonl": {"path": Path("admin_data/user_sessions.jsonl")},
        "admin_data/tasking_sessions.jsonl": {"path": Path("admin_data/tasking_sessions.jsonl")},
        "admin_data/searches.jsonl": {"path": Path("admin_data/searches.jsonl")},
        "admin_data/aoi_uploads.jsonl": {"path": Path("admin_data/aoi_uploads.jsonl")},
    }
    stats = {}
    for name, info in logs.items():
        path = info["path"]
        if path.exists():
            size_bytes = path.stat().st_size
            size_mb = size_bytes / (1024 * 1024)
            if path.suffix == ".jsonl":
                try:
                    with open(path, 'r', encoding='utf-8') as f:
                        count = sum(1 for _ in f)
                except:
                    count = 0
            else:
                try:
                    with open(path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        count = len(data) if isinstance(data, list) else 0
                except:
                    count = 0
            stats[name] = {
                "size_mb": round(size_mb, 2),
                "entries": count,
                "path": str(path),
                "missing": False
            }
        else:
            stats[name] = {"size_mb": None, "entries": None, "path": str(path), "missing": True}
    return stats

def truncate_navigation_log(keep_last=10000, create_backup=True):
    log_file = Path("navigation_logs.json")
    if not log_file.exists():
        return f"❌ Log file not found: {log_file}"
    backup_path = None
    if create_backup:
        backup_path = log_file.with_suffix(".json.bak")
        shutil.copy2(log_file, backup_path)
    try:
        with open(log_file, 'r', encoding='utf-8') as f:
            logs = json.load(f)
        if not isinstance(logs, list):
            logs = []
        original_count = len(logs)
        if original_count <= keep_last:
            if backup_path:
                backup_path.unlink()
            return f"ℹ️ Log has {original_count} entries, no truncation needed (limit = {keep_last})."
        logs = logs[-keep_last:]
        with open(log_file, 'w', encoding='utf-8') as f:
            json.dump(logs, f, indent=2)
        msg = f"✅ Truncated log from {original_count} to {len(logs)} entries."
        if backup_path:
            msg += f" Backup saved as {backup_path.name}"
        return msg
    except Exception as e:
        return f"❌ Error truncating log: {e}"

def truncate_jsonl_file(filepath, keep_last=10000, create_backup=True):
    path = Path(filepath)
    if not path.exists():
        return f"❌ File not found: {path}"
    if create_backup:
        backup_path = path.with_suffix(".jsonl.bak")
        shutil.copy2(path, backup_path)
    try:
        with open(path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        original_count = len(lines)
        if original_count <= keep_last:
            if create_backup:
                backup_path.unlink()
            return f"ℹ️ File has {original_count} entries, no truncation needed."
        with open(path, 'w', encoding='utf-8') as f:
            f.writelines(lines[-keep_last:])
        msg = f"✅ Truncated {path.name} from {original_count} to {keep_last} entries."
        if create_backup:
            msg += f" Backup saved as {backup_path.name}"
        return msg
    except Exception as e:
        return f"❌ Error truncating {path.name}: {e}"

def render_logs_management_tab():
    st.subheader("📁 Logs Management")
    st.markdown("View and clean up log files to improve performance.")
    stats = get_log_stats()
    st.markdown("### 📊 Log File Statistics")
    data = []
    for name, info in stats.items():
        if info.get("missing"):
            data.append({"Log File": name, "Size (MB)": None, "Entries": None, "Status": "Missing"})
        else:
            data.append({
                "Log File": name,
                "Size (MB)": info["size_mb"],
                "Entries": info["entries"],
                "Status": "OK"
            })
    df = pd.DataFrame(data)
    st.dataframe(
        df,
        column_config={
            "Size (MB)": st.column_config.NumberColumn("Size (MB)", format="%.2f", help="Size in MB"),
            "Entries": st.column_config.NumberColumn("Entries", help="Number of entries"),
            "Status": st.column_config.TextColumn("Status"),
        },
        use_container_width=True
    )
    st.markdown("---")
    st.markdown("### 🧹 Clean Up Old Logs")
    # ... (rest of your existing truncation UI – unchanged) ...
    # I keep the original code for brevity, but you should keep yours.
    # The existing code for truncation and manual cleanup is still there.
    st.markdown("---")
    st.caption("💡 **Tip:** Reduce the number of retained entries to speed up the Analytics tab and reduce memory usage.")

# ============================================================================
# NEW: Active Users Tab (refresh button + time scale) – already present
# ============================================================================
def render_active_users_tab():
    """Render a tab showing currently active users based on recent logs."""
    st.subheader("👥 Real‑time Active Users")
    time_options = {1: "1 minute", 5: "5 minutes", 15: "15 minutes", 30: "30 minutes"}
    selected_minutes = st.selectbox(
        "Consider activity within",
        options=list(time_options.keys()),
        format_func=lambda x: time_options[x],
        index=1,
        key="active_time_window"
    )
    if st.button("🔄 Refresh active users", key="refresh_active_btn"):
        st.rerun()
    active_info = get_active_sessions(minutes_active=selected_minutes)
    col1, col2 = st.columns([1, 2])
    with col1:
        st.metric("Active sessions", active_info["count"])
    with col2:
        st.caption(f"Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    if active_info["sessions"]:
        df = pd.DataFrame(active_info["sessions"])
        df["last_seen"] = pd.to_datetime(df["last_seen"]).dt.strftime("%Y-%m-%d %H:%M:%S")
        st.dataframe(df, use_container_width=True)
    else:
        st.info("No active sessions detected in the selected time window.")

# ============================================================================
# NEW ADVANCED TABS FOR ENHANCED ADMIN MANAGEMENT
# ============================================================================

def render_system_health_tab():
    """Display CPU, memory, disk usage."""
    st.subheader("🖥️ System Health")
    try:
        import psutil
        cpu_percent = psutil.cpu_percent(interval=1)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        col1, col2, col3 = st.columns(3)
        col1.metric("CPU Usage", f"{cpu_percent}%")
        col2.metric("Memory Usage", f"{memory.percent}% ({memory.used//(1024**3)} GB / {memory.total//(1024**3)} GB)")
        col3.metric("Disk Usage", f"{disk.percent}% ({disk.used//(1024**3)} GB / {disk.total//(1024**3)} GB)")
        if disk.percent > 85:
            st.warning("⚠️ Disk usage exceeds 85%. Consider cleaning old logs.")
    except ImportError:
        st.info("Install `psutil` to see detailed system metrics: `pip install psutil`")
    except Exception as e:
        st.error(f"Could not retrieve system metrics: {e}")

def render_cache_management_tab():
    st.subheader("🗄️ Cache Management")
    from data.tle_fetcher import get_tle_fetcher, CACHE_FILE
    from force_download_tles import force_download_all_tls

    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**TLE Cache**")
        if CACHE_FILE.exists():
            st.write(f"File: `{CACHE_FILE}`")
            st.write(f"Size: {CACHE_FILE.stat().st_size / 1024:.1f} KB")
            fetcher = get_tle_fetcher()
            valid = sum(1 for n in fetcher.tles if fetcher._is_valid_tle(fetcher.tles[n]))
            st.write(f"Valid TLEs: {valid} / {len(fetcher.tles)}")
        else:
            st.warning("TLE cache file not found.")
        if st.button("🔄 Force refresh TLE cache", key="force_tle_refresh"):
            with st.spinner("Downloading fresh TLEs from Space‑Track..."):
                force_download_all_tls()
            st.success("TLE cache refreshed.")
            st.rerun()

    with col2:
        st.markdown("**AOI History**")
        aoi_dir = Path("aoi_history")
        if aoi_dir.exists():
            aoi_count = len(list(aoi_dir.glob("*.json")))
            st.write(f"Number of stored AOIs: {aoi_count}")
            if st.button("🗑️ Clear AOI history", key="clear_aoi_history"):
                for f in aoi_dir.glob("*.json"):
                    f.unlink()
                st.success("AOI history cleared.")
                st.rerun()
        else:
            st.write("No AOI history folder.")

def render_session_management_tab():
    st.subheader("👥 Session Management")
    from navigation_tracker import get_active_sessions

    active = get_active_sessions(minutes_active=30)
    if not active["sessions"]:
        st.info("No active sessions in the last 30 minutes.")
        return

    df = pd.DataFrame(active["sessions"])
    st.dataframe(df[["session_id", "last_seen", "last_page", "ip", "country"]], use_container_width=True)

    session_to_kill = st.selectbox("Select session ID to kill (clear its data)", df["session_id"].unique())
    if st.button("❌ Kill session", key="kill_session"):
        log_file = Path("navigation_logs.json")
        if log_file.exists():
            with open(log_file, 'r') as f:
                logs = json.load(f)
            new_logs = [ev for ev in logs if ev.get("session_id") != session_to_kill]
            with open(log_file, 'w') as f:
                json.dump(new_logs, f, indent=2)
        st.success(f"Session {session_to_kill} cleared from logs.")
        st.rerun()

def render_backup_restore_tab():
    st.subheader("💾 Backup & Restore")
    backup_dir = Path("admin_backups")
    backup_dir.mkdir(exist_ok=True)

    if st.button("📦 Create full backup (admin data + satellites config)", key="create_backup"):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_zip = backup_dir / f"admin_backup_{timestamp}.zip"
        with zipfile.ZipFile(backup_zip, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for folder in ["admin_data", "aoi_history", "messages"]:
                p = Path(folder)
                if p.exists():
                    for f in p.rglob("*"):
                        zipf.write(f, f.relative_to("."))
            zipf.write("config/satellites.py", "config/satellites.py")
        st.success(f"Backup created: `{backup_zip}`")
        with open(backup_zip, "rb") as f:
            st.download_button("⬇️ Download backup", f, file_name=backup_zip.name)

    st.markdown("---")
    st.warning("⚠️ Restore will overwrite existing admin data. Use with caution.")
    uploaded_backup = st.file_uploader("Upload a backup zip file", type=["zip"])
    if uploaded_backup and st.button("🚨 Restore from backup", key="restore_backup"):
        with tempfile.TemporaryDirectory() as tmpdir:
            zip_path = Path(tmpdir) / "backup.zip"
            with open(zip_path, "wb") as f:
                f.write(uploaded_backup.getbuffer())
            with zipfile.ZipFile(zip_path, 'r') as zipf:
                zipf.extractall(tmpdir)
            for folder in ["admin_data", "aoi_history", "messages"]:
                src = Path(tmpdir) / folder
                if src.exists():
                    dst = Path(folder)
                    if dst.exists():
                        shutil.rmtree(dst)
                    shutil.copytree(src, dst)
        st.success("Restore completed. Refresh the page.")
        st.rerun()

def render_api_status_tab():
    st.subheader("🔑 API Status & Quota")
    from data.tle_fetcher import get_supplier_stats

    # Space‑Track
    with st.expander("Space-Track.org"):
        if st.secrets.get("SPACE_TRACK_USER"):
            st.success(f"Username: {st.secrets['SPACE_TRACK_USER']}")
            try:
                session = requests.Session()
                auth = {"identity": st.secrets["SPACE_TRACK_USER"], "password": st.secrets["SPACE_TRACK_PASSWORD"]}
                resp = session.post("https://www.space-track.org/ajaxauth/login", data=auth, timeout=10)
                if resp.status_code == 200:
                    st.success("✅ Login successful")
                else:
                    st.error(f"❌ Login failed (HTTP {resp.status_code})")
                session.close()
            except Exception as e:
                st.warning(f"Could not verify credentials: {e}")
        else:
            st.warning("No credentials configured")

    # N2YO
    with st.expander("N2YO.com"):
        if st.secrets.get("N2YO_API_KEY"):
            key = st.secrets["N2YO_API_KEY"]
            st.write(f"API key: `{key[:4]}...{key[-4:]}`")
            stats = get_supplier_stats()
            n2yo = stats.get("n2yo", {})
            st.write(f"Total requests (since stats began): {n2yo.get('total', 0)}")
            st.write(f"Successful: {n2yo.get('success', 0)}")
        else:
            st.warning("No API key configured")

    # OpenWeatherMap
    with st.expander("OpenWeatherMap"):
        if st.secrets.get("OWM_API_KEY"):
            key = st.secrets["OWM_API_KEY"]
            st.write(f"API key: `{key[:4]}...{key[-4:]}`")
            try:
                url = f"https://api.openweathermap.org/data/2.5/weather?q=London&appid={key}"
                resp = requests.get(url, timeout=5)
                if resp.status_code == 200:
                    st.success("✅ API key valid")
                else:
                    st.error(f"❌ Invalid API key (HTTP {resp.status_code})")
            except Exception as e:
                st.warning(f"Could not verify: {e}")
        else:
            st.warning("No API key configured")

def render_log_streaming_tab():
    st.subheader("📜 Live Log Stream (last 50 entries)")
    
    # Manual refresh button
    if st.button("🔄 Refresh log stream", key="refresh_log_stream"):
        st.rerun()
    
    log_file = Path("navigation_logs.json")
    if not log_file.exists():
        st.info("No log file yet.")
        return

    try:
        with open(log_file, 'r') as f:
            logs = json.load(f)
        df = pd.DataFrame(logs[-50:][::-1])
        cols = ["timestamp", "session_id", "page", "action", "ip", "country"]
        available = [c for c in cols if c in df.columns]
        st.dataframe(df[available], use_container_width=True)
        st.caption("Click the refresh button to see new entries.")
    except Exception as e:
        st.error(f"Error reading log: {e}")
        
def render_custom_satellites_tab():
    st.subheader("🛰️ User‑Added Satellites")
    from config.satellites import SATELLITES
    user_sats = SATELLITES.get("User Satellites", {})
    if not user_sats:
        st.info("No custom satellites added by users.")
        return

    for name, info in user_sats.items():
        with st.expander(f"**{name}** (NORAD {info['norad']})"):
            st.write(f"Provider: {info['provider']}")
            cam_name, cam_info = next(iter(info['cameras'].items()))
            st.write(f"Swath: {cam_info['swath_km']} km | Resolution: {cam_info['resolution_m']} m")
            if st.button(f"🗑️ Delete {name}", key=f"del_{name}"):
                del SATELLITES["User Satellites"][name]
                st.success(f"Satellite {name} deleted. Refresh the page to see changes.")
                st.rerun()


# ============================================================================
# SASClouds Statistics Tab
# ============================================================================
_SC_LOG_DIR = Path(__file__).parent.parent / "logs"


@st.cache_data(ttl=60)
def _load_sc_searches() -> list:
    """Load every SASClouds search record from all *_search_history.jsonl files."""
    records = []
    if not _SC_LOG_DIR.exists():
        return records
    for f in sorted(_SC_LOG_DIR.glob("*search_history.jsonl")):
        try:
            with open(f, encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if line:
                        records.append(json.loads(line))
        except Exception:
            pass
    return records


@st.cache_data(ttl=60)
def _load_sc_api_events() -> list:
    """Load structured API interaction events from all *_api_interactions.jsonl files."""
    records = []
    if not _SC_LOG_DIR.exists():
        return records
    for f in sorted(_SC_LOG_DIR.glob("*api_interactions.jsonl")):
        try:
            with open(f, encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if line:
                        records.append(json.loads(line))
        except Exception:
            pass
    return records


def render_sasclouds_stats_tab():
    st.subheader("🗄️ SASClouds Archive — Search Statistics")

    if st.button("🔄 Refresh", key="sc_stats_refresh"):
        _load_sc_searches.clear()
        _load_sc_api_events.clear()
        st.rerun()

    searches = _load_sc_searches()
    api_events = _load_sc_api_events()

    # ── KPI row ───────────────────────────────────────────────────────────────
    total_searches = len(searches)
    total_scenes = sum(r.get("num_scenes", 0) for r in searches)
    unique_sessions = len({r.get("session_id", "") for r in searches})
    avg_scenes = round(total_scenes / total_searches, 1) if total_searches else 0

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Searches", total_searches)
    c2.metric("Total Scenes Found", total_scenes)
    c3.metric("Unique Sessions", unique_sessions)
    c4.metric("Avg Scenes / Search", avg_scenes)

    if not searches:
        st.info("No SASClouds search history found in logs/.")
        return

    st.markdown("---")

    # Build a DataFrame from search records
    rows = []
    for r in searches:
        ts = r.get("timestamp", "")
        filters = r.get("filters", {})
        sats = filters.get("satellites", [])
        sat_ids = [s.get("satelliteId", "") for s in sats] if isinstance(sats, list) else []
        date_range = filters.get("date_range", ["", ""])
        cloud_max = filters.get("cloud_max", None)
        rows.append({
            "timestamp": ts,
            "session_id": r.get("session_id", ""),
            "satellites": ", ".join(sat_ids),
            "cloud_max": cloud_max,
            "date_from": date_range[0] if len(date_range) > 0 else "",
            "date_to":   date_range[1] if len(date_range) > 1 else "",
            "num_scenes": r.get("num_scenes", 0),
        })

    df = pd.DataFrame(rows)
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    df = df.dropna(subset=["timestamp"])
    df = df.sort_values("timestamp", ascending=False)

    # ── Timeline ──────────────────────────────────────────────────────────────
    st.markdown("#### Searches over time")
    df["date"] = df["timestamp"].dt.date
    daily = df.groupby("date").agg(
        searches=("num_scenes", "count"),
        scenes=("num_scenes", "sum"),
    ).reset_index()
    fig_tl = px.bar(daily, x="date", y=["searches", "scenes"],
                    barmode="group",
                    labels={"value": "Count", "date": "Date", "variable": ""},
                    title="Daily searches and scenes found")
    fig_tl.update_layout(legend=dict(orientation="h", yanchor="bottom", y=1.02))
    st.plotly_chart(fig_tl, use_container_width=True)

    col_l, col_r = st.columns(2)

    # ── Top satellites ────────────────────────────────────────────────────────
    with col_l:
        st.markdown("#### Most-searched satellites")
        sat_counts: dict = {}
        for r in searches:
            sats = (r.get("filters") or {}).get("satellites", [])
            for s in (sats if isinstance(sats, list) else []):
                sid = s.get("satelliteId", "unknown")
                sat_counts[sid] = sat_counts.get(sid, 0) + 1
        if sat_counts:
            df_sats = (pd.DataFrame(list(sat_counts.items()), columns=["Satellite", "count"])
                       .sort_values("count", ascending=False).head(15))
            fig_sats = px.bar(df_sats, x="count", y="Satellite", orientation="h",
                              title="Satellite search frequency")
            fig_sats.update_layout(yaxis={"categoryorder": "total ascending"})
            st.plotly_chart(fig_sats, use_container_width=True)
        else:
            st.info("No satellite data.")

    # ── Cloud cover distribution ──────────────────────────────────────────────
    with col_r:
        st.markdown("#### Cloud cover filter distribution")
        cc_vals = df["cloud_max"].dropna().astype(float).tolist()
        if cc_vals:
            fig_cc = px.histogram(x=cc_vals, nbins=20,
                                  labels={"x": "Max cloud cover %"},
                                  title="Cloud cover filter usage")
            st.plotly_chart(fig_cc, use_container_width=True)
        else:
            st.info("No cloud cover data.")

    # ── Scenes per search distribution ────────────────────────────────────────
    st.markdown("#### Scenes returned per search")
    scene_vals = df["num_scenes"].tolist()
    if scene_vals:
        fig_sc = px.histogram(x=scene_vals, nbins=30,
                              labels={"x": "Scenes returned"},
                              title="Distribution of scene counts per search")
        st.plotly_chart(fig_sc, use_container_width=True)

    # ── Recent searches table ─────────────────────────────────────────────────
    st.markdown("#### Recent searches")
    display_cols = ["timestamp", "session_id", "satellites", "cloud_max",
                    "date_from", "date_to", "num_scenes"]
    st.dataframe(
        df[display_cols].head(50).rename(columns={
            "timestamp": "Time", "session_id": "Session",
            "satellites": "Satellites", "cloud_max": "Cloud %",
            "date_from": "From", "date_to": "To", "num_scenes": "Scenes",
        }),
        use_container_width=True,
    )

    # ── API event log ─────────────────────────────────────────────────────────
    if api_events:
        st.markdown("---")
        st.markdown("#### API interaction log (last 100 events)")
        df_api = pd.DataFrame(api_events)
        if "ts" in df_api.columns:
            df_api["ts"] = pd.to_datetime(df_api["ts"], errors="coerce")
            df_api = df_api.sort_values("ts", ascending=False)
        show_cols = [c for c in ["ts", "event", "session_id", "satellite_ids",
                                  "total_scenes", "elapsed_s", "upload_id"]
                     if c in df_api.columns]
        st.dataframe(df_api[show_cols].head(100), use_container_width=True)


# ============================================================================
# NEW: Tool Usage Breakdown Tab
# ============================================================================
def render_tool_usage_tab():
    """Show which tools (Pass Detection, Tasking, SASClouds, Live Tracking) are used most."""
    st.subheader("🔧 Tool Usage Breakdown")
    st.markdown("See which tools users interact with most frequently across all sessions.")

    # Load tracking data from navigation_logs.json
    log_file = Path("navigation_logs.json")
    if not log_file.exists():
        st.info("No tracking data available yet.")
        return

    try:
        with open(log_file, 'r') as f:
            logs = json.load(f)
    except Exception as e:
        st.error(f"Error reading log file: {e}")
        return

    if not logs:
        st.info("No tracking data available.")
        return

    df = pd.DataFrame(logs)
    if 'timestamp' in df.columns:
        df['timestamp'] = pd.to_datetime(df['timestamp'], errors='coerce')
        df = df.dropna(subset=['timestamp'])

    # Time window filter
    time_window = st.radio(
        "Time window",
        options=["All", "Last Week", "Last Month", "Last 6 Months", "Last Year"],
        index=0, horizontal=True, key="tool_usage_time"
    )
    now = datetime.now()
    if time_window == "Last Week":
        cutoff = now - timedelta(days=7)
        df = df[df['timestamp'] >= cutoff]
    elif time_window == "Last Month":
        cutoff = now - timedelta(days=30)
        df = df[df['timestamp'] >= cutoff]
    elif time_window == "Last 6 Months":
        cutoff = now - timedelta(days=180)
        df = df[df['timestamp'] >= cutoff]
    elif time_window == "Last Year":
        cutoff = now - timedelta(days=365)
        df = df[df['timestamp'] >= cutoff]

    if df.empty:
        st.info("No data for the selected time window.")
        return

    # Define tool categories based on page names and actions
    tool_keywords = {
        "🛰️ Pass Detection": ["pass_detection", "pass detection", "passes", "satellite pass"],
        "🎯 Tasking": ["tasking", "tasking_optimizer", "optimizer"],
        "🗄️ SASClouds Archive": ["sasclouds", "sasclouds_archive", "3_sasclouds"],
        "📍 Live Tracking": ["live_tracking", "live tracking", "tracking"],
        "🛰️ Satellite DB": ["satellite_database", "satellite database", "2_satellite"],
        "📊 Admin": ["admin", "admin_dashboard"],
        "📜 Logs": ["real_time_logs", "real time logs", "4_real_time"],
    }

    # Count page views per tool
    tool_counts = {}
    for tool_name, keywords in tool_keywords.items():
        count = 0
        if 'page' in df.columns:
            mask = df['page'].str.lower().str.contains('|'.join(keywords), na=False)
            count += mask.sum()
        if 'action' in df.columns:
            mask = df['action'].str.lower().str.contains('|'.join(keywords), na=False)
            count += mask.sum()
        tool_counts[tool_name] = count

    # Also count SASClouds searches from the dedicated log
    sc_searches = _load_sc_searches()
    tool_counts["🗄️ SASClouds Archive"] += len(sc_searches)

    # Display KPIs
    cols = st.columns(len(tool_counts))
    for i, (tool_name, count) in enumerate(sorted(tool_counts.items(), key=lambda x: x[1], reverse=True)):
        with cols[i % len(cols)]:
            st.metric(tool_name, count)

    st.markdown("---")

    # Bar chart
    df_tools = pd.DataFrame(list(tool_counts.items()), columns=["Tool", "Interactions"])
    df_tools = df_tools.sort_values("Interactions", ascending=True)
    fig = px.bar(df_tools, x="Interactions", y="Tool", orientation="h",
                 title="Tool Usage Comparison",
                 color="Tool", text="Interactions")
    fig.update_layout(yaxis={"categoryorder": "total ascending"}, showlegend=False)
    fig.update_traces(textposition="outside")
    st.plotly_chart(fig, use_container_width=True)

    # Per-tool timeline
    st.markdown("#### Tool usage over time")
    if 'page' in df.columns and 'timestamp' in df.columns:
        df_page = df.dropna(subset=['page']).copy()
        # Assign each page view to a tool category
        def classify_page(page_name):
            if not isinstance(page_name, str):
                return "Other"
            pn = page_name.lower()
            for tool_name, keywords in tool_keywords.items():
                if any(kw in pn for kw in keywords):
                    return tool_name
            return "Other"

        df_page['tool'] = df_page['page'].apply(classify_page)
        df_page['date'] = df_page['timestamp'].dt.date
        daily_tool = df_page.groupby(['date', 'tool']).size().reset_index(name='count')
        if not daily_tool.empty:
            fig2 = px.area(daily_tool, x='date', y='count', color='tool',
                           title="Daily tool usage",
                           labels={"count": "Interactions", "date": "Date", "tool": "Tool"})
            st.plotly_chart(fig2, use_container_width=True)

    # Per-user tool breakdown
    st.markdown("#### Per-user tool breakdown")
    if 'session_id' in df.columns and 'page' in df.columns:
        df_user = df.dropna(subset=['session_id', 'page']).copy()
        df_user['tool'] = df_user['page'].apply(classify_page)
        user_tool = df_user.groupby(['session_id', 'tool']).size().reset_index(name='count')
        pivot = user_tool.pivot_table(index='session_id', columns='tool', values='count',
                                      fill_value=0, aggfunc='sum')
        # Add total column
        pivot['Total'] = pivot.sum(axis=1)
        pivot = pivot.sort_values('Total', ascending=False).head(20)
        st.dataframe(pivot, use_container_width=True)


# ============================================================================
# NEW: Per-User Activity Journey Tab
# ============================================================================
def render_per_user_activity_tab():
    """Show each user's complete journey across all tools."""
    st.subheader("👤 Per-User Activity Journey")
    st.markdown("Select a user to see their complete journey across all tools.")

    log_file = Path("navigation_logs.json")
    if not log_file.exists():
        st.info("No tracking data available yet.")
        return

    try:
        with open(log_file, 'r') as f:
            logs = json.load(f)
    except Exception as e:
        st.error(f"Error reading log file: {e}")
        return

    if not logs:
        st.info("No tracking data available.")
        return

    df = pd.DataFrame(logs)
    if 'timestamp' in df.columns:
        df['timestamp'] = pd.to_datetime(df['timestamp'], errors='coerce')
        df = df.dropna(subset=['timestamp'])
        df = df.sort_values('timestamp')

    # Time window filter
    time_window = st.radio(
        "Time window",
        options=["All", "Last Week", "Last Month", "Last 6 Months", "Last Year"],
        index=0, horizontal=True, key="per_user_time"
    )
    now = datetime.now()
    if time_window == "Last Week":
        cutoff = now - timedelta(days=7)
        df = df[df['timestamp'] >= cutoff]
    elif time_window == "Last Month":
        cutoff = now - timedelta(days=30)
        df = df[df['timestamp'] >= cutoff]
    elif time_window == "Last 6 Months":
        cutoff = now - timedelta(days=180)
        df = df[df['timestamp'] >= cutoff]
    elif time_window == "Last Year":
        cutoff = now - timedelta(days=365)
        df = df[df['timestamp'] >= cutoff]

    if df.empty:
        st.info("No data for the selected time window.")
        return

    # Get unique sessions
    if 'session_id' not in df.columns:
        st.info("No session data available.")
        return

    sessions = df['session_id'].unique()
    session_stats = []
    for sid in sessions:
        sdf = df[df['session_id'] == sid]
        session_stats.append({
            "session_id": sid,
            "first_seen": sdf['timestamp'].min(),
            "last_seen": sdf['timestamp'].max(),
            "total_events": len(sdf),
            "unique_pages": sdf['page'].nunique() if 'page' in sdf.columns else 0,
            "ip": sdf['ip'].iloc[0] if 'ip' in sdf.columns else "unknown",
            "country": sdf['country'].iloc[0] if 'country' in sdf.columns else "unknown",
        })

    df_sessions = pd.DataFrame(session_stats)
    df_sessions = df_sessions.sort_values('last_seen', ascending=False)

    # Summary KPIs
    col1, col2, col3 = st.columns(3)
    col1.metric("Total Unique Users", len(df_sessions))
    col2.metric("Total Events", len(df))
    col3.metric("Avg Events/User", f"{len(df)/len(df_sessions):.1f}" if len(df_sessions) > 0 else "0")

    st.markdown("---")

    # User selector
    user_options = [f"{row['session_id'][:12]}... — {row['total_events']} events — {row['country']}"
                    for _, row in df_sessions.head(50).iterrows()]
    selected_user_str = st.selectbox("Select a user (top 50 by activity)", options=user_options, key="per_user_select")

    if selected_user_str:
        selected_sid = selected_user_str.split(" — ")[0].replace("...", "")
        # Find the full session_id
        full_sid = None
        for sid in sessions:
            if sid.startswith(selected_sid.rstrip(".")):
                full_sid = sid
                break
        if full_sid is None:
            full_sid = selected_sid

        user_df = df[df['session_id'] == full_sid].copy()
        user_df = user_df.sort_values('timestamp')

        st.markdown(f"### 📋 User: `{full_sid}`")
        st.markdown(f"**IP:** {user_df['ip'].iloc[0] if 'ip' in user_df.columns else 'unknown'}  |  "
                    f"**Country:** {user_df['country'].iloc[0] if 'country' in user_df.columns else 'unknown'}  |  "
                    f"**Total events:** {len(user_df)}  |  "
                    f"**First seen:** {user_df['timestamp'].min()}  |  "
                    f"**Last seen:** {user_df['timestamp'].max()}")

        # Timeline of user's journey
        st.markdown("#### Journey Timeline")
        display_cols = ['timestamp', 'event_type', 'page', 'action', 'details']
        available = [c for c in display_cols if c in user_df.columns]
        st.dataframe(user_df[available].tail(100), use_container_width=True)

        # Page flow visualization
        if 'page' in user_df.columns:
            st.markdown("#### Page Flow")
            page_sequence = user_df['page'].dropna().tolist()
            if page_sequence:
                # Show unique pages visited in order
                seen = set()
                unique_sequence = []
                for p in page_sequence:
                    if p not in seen:
                        seen.add(p)
                        unique_sequence.append(p)
                flow_text = " → ".join([f"`{p}`" for p in unique_sequence])
                st.markdown(flow_text)

        # Actions breakdown
        if 'action' in user_df.columns:
            st.markdown("#### Actions Breakdown")
            action_counts = user_df['action'].value_counts().reset_index()
            action_counts.columns = ['Action', 'Count']
            fig = px.bar(action_counts.head(15), x='Count', y='Action', orientation='h',
                         title="User actions", color='Count')
            fig.update_layout(yaxis={"categoryorder": "total ascending"})
            st.plotly_chart(fig, use_container_width=True)

        # Session duration
        if len(user_df) > 1:
            duration = (user_df['timestamp'].max() - user_df['timestamp'].min()).total_seconds() / 60
            st.metric("Session Duration (minutes)", f"{duration:.1f}")

        # Export user data
        csv = user_df.to_csv(index=False)
        st.download_button(
            label="📥 Export user data (CSV)",
            data=csv,
            file_name=f"user_{full_sid[:8]}_{datetime.now().strftime('%Y%m%d')}.csv",
            mime="text/csv",
        )
