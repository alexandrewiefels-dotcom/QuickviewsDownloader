import streamlit as st
import subprocess
import threading
import time
import zipfile
import json
import shutil
import tempfile
from pathlib import Path
from datetime import datetime

# -------------------------------
# Password from secrets
PASSWORD = st.secrets.get("PASSWORD", "default_fallback")
if PASSWORD == "default_fallback":
    st.error("No PASSWORD found in secrets. Please set .streamlit/secrets.toml")
    st.stop()

# -------------------------------
# Session state
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False
if "scraping" not in st.session_state:
    st.session_state.scraping = False
if "log_output" not in st.session_state:
    st.session_state.log_output = []
if "process" not in st.session_state:
    st.session_state.process = None
if "temp_dir" not in st.session_state:
    st.session_state.temp_dir = None
if "zip_ready" not in st.session_state:
    st.session_state.zip_ready = False
if "zip_data" not in st.session_state:
    st.session_state.zip_data = None
if "zip_filename" not in st.session_state:
    st.session_state.zip_filename = None

# -------------------------------
# Authentication
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

# -------------------------------
# Scraper Page (no admin sidebar options)
st.set_page_config(page_title="SASClouds Scraper", layout="wide")
st.title("🛰️ SASClouds Satellite Image Scraper")
st.markdown("Extract footprints, full‑size quickviews, and georeferenced images.")

with st.sidebar:
    st.header("📋 Instructions")
    st.markdown("""
    1. **Log in** to SASClouds (if needed).
    2. **Apply filters** (date range, cloud cover, draw AOI on map).
    3. **Click Search** – wait for the first page of results.
    4. **Return here** and press **Start Scraping**.
    """)
    st.divider()
    st.info("The scraper will open a browser window for steps 1‑3. It will automatically start after a 10 sec delay.")
    st.markdown("---")
    st.markdown("**Admin Dashboard** → available from the sidebar after login.")

col1, col2 = st.columns([1, 4])
with col1:
    if not st.session_state.scraping and not st.session_state.zip_ready:
        if st.button("▶️ Start Scraping", type="primary", use_container_width=True):
            st.session_state.scraping = True
            st.session_state.log_output = []
            st.session_state.zip_ready = False
            st.session_state.zip_data = None
            st.session_state.temp_dir = tempfile.mkdtemp(prefix="sasclouds_")
            
            def run_scraper():
                script_path = Path("sasclouds_scraper.py")
                if not script_path.exists():
                    st.session_state.log_output.append("❌ scraper script not found: sasclouds_scraper.py")
                    st.session_state.scraping = False
                    return
                process = subprocess.Popen(
                    ["python", "-u", str(script_path)],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                )
                st.session_state.process = process
                for line in iter(process.stdout.readline, ""):
                    st.session_state.log_output.append(line.rstrip())
                    if len(st.session_state.log_output) > 200:
                        st.session_state.log_output = st.session_state.log_output[-200:]
                process.wait()
                # After script finishes, find the most recent folder in sasclouds_scrapes
                base_dir = Path("./sasclouds_scrapes")
                if base_dir.exists():
                    folders = sorted([d for d in base_dir.iterdir() if d.is_dir()], key=lambda p: p.stat().st_mtime, reverse=True)
                    if folders:
                        latest = folders[0]
                        dest = Path(st.session_state.temp_dir) / latest.name
                        shutil.move(str(latest), str(dest))
                        shutil.rmtree(base_dir, ignore_errors=True)
                        zip_path = Path(st.session_state.temp_dir) / f"{latest.name}.zip"
                        with zipfile.ZipFile(zip_path, "w") as zf:
                            for file in dest.rglob("*"):
                                if file.is_file():
                                    zf.write(file, arcname=file.relative_to(dest))
                        with open(zip_path, "rb") as f:
                            st.session_state.zip_data = f.read()
                        st.session_state.zip_filename = f"{latest.name}.zip"
                        st.session_state.zip_ready = True
                st.session_state.scraping = False
                st.session_state.process = None
                # Clean up temp_dir after download is initiated? We'll keep until next run.
            threading.Thread(target=run_scraper, daemon=True).start()
            st.rerun()
    elif st.session_state.scraping:
        if st.button("⏹️ Stop Scraping", use_container_width=True):
            if st.session_state.process:
                st.session_state.process.terminate()
            st.session_state.scraping = False
            st.rerun()
    else:
        if st.button("🗑️ Clear Logs", use_container_width=True):
            st.session_state.log_output = []
            st.rerun()

# Live logs
log_placeholder = st.empty()
def display_logs():
    with log_placeholder.container():
        st.subheader("📡 Scraper Log")
        if st.session_state.log_output:
            st.code("\n".join(st.session_state.log_output[-50:]), language="bash")
        else:
            st.info("Logs will appear here after starting.")
display_logs()
if st.session_state.scraping:
    time.sleep(1)
    st.rerun()

# Download block
if st.session_state.zip_ready and st.session_state.zip_data:
    st.success("✅ Scraping completed! Click below to download the results.")
    st.download_button(
        label="📥 Download All Data (ZIP)",
        data=st.session_state.zip_data,
        file_name=st.session_state.zip_filename,
        mime="application/zip",
        use_container_width=True,
    )