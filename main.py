# File: main.py
import streamlit as st
import uuid
from sidebar import render_sidebar
from map_utils import show_aoi_map
from search_logic import run_search, create_download_zip

st.set_page_config(page_title="SASClouds API Scraper", layout="wide")

# ----------------------------------------------------------------------
# Authentication (app password)
# ----------------------------------------------------------------------
PASSWORD = st.secrets.get("PASSWORD", "default_fallback")
if PASSWORD == "default_fallback":
    st.error("No PASSWORD found in secrets. Please set .streamlit/secrets.toml")
    st.stop()

if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

if not st.session_state.authenticated:
    st.title("🔐 Authentication Required")
    password_input = st.text_input("Enter Password", type="password")
    if st.button("Login"):
        if password_input == PASSWORD:
            st.session_state.authenticated = True
            st.rerun()
        else:
            st.error("Incorrect password")
    st.stop()

# ----------------------------------------------------------------------
# Session ID for logging
# ----------------------------------------------------------------------
if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())

# ----------------------------------------------------------------------
# Main content area
# ----------------------------------------------------------------------
st.title("🛰️ SASClouds API Scraper")
st.markdown("Fast, cloud‑compatible search using the official API. No browser needed.")

# Render sidebar and get parameters
sidebar_params = render_sidebar()

# Display AOI preview if defined
if sidebar_params["polygon_geojson"]:
    st.subheader("📍 Area of Interest (AOI)")
    show_aoi_map(sidebar_params["polygon_geojson"])

# Execute search when button clicked
if sidebar_params["search_clicked"]:
    if not sidebar_params["polygon_geojson"]:
        st.error("Please provide an AOI (bounding box or valid file).")
    elif not sidebar_params["selected_satellites"]:
        st.warning("No satellites selected. Please choose at least one.")
    else:
        log_container = st.empty()
        run_search(
            polygon_geojson=sidebar_params["polygon_geojson"],
            aoi_filename=sidebar_params["aoi_filename"],
            start_date=sidebar_params["start_date"],
            end_date=sidebar_params["end_date"],
            max_cloud=sidebar_params["max_cloud"],
            selected_satellites=sidebar_params["selected_satellites"],
            session_id=st.session_state.session_id,
            log_container=log_container
        )

# Download button (appears after search)
create_download_zip()