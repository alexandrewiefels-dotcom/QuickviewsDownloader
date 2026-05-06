import streamlit as st
import subprocess
import time
import zipfile
import io
import shutil
import tempfile
from pathlib import Path
import threading

st.set_page_config(page_title="SASClouds Scraper", layout="wide")

# ----- Authentication -----
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

# ----- Session state initialisation -----
if "scraping" not in st.session_state:
    st.session_state.scraping = False
if "proc" not in st.session_state:
    st.session_state.proc = None
if "zip_data" not in st.session_state:
    st.session_state.zip_data = None
if "zip_filename" not in st.session_state:
    st.session_state.zip_filename = None
if "logs" not in st.session_state:
    st.session_state.logs = []

# ----- Main UI -----
st.title("🛰️ SASClouds Satellite Image Scraper")
st.markdown("Extract footprints, images, and georeferenced world files.")

with st.expander("📖 How to Use This Scraper", expanded=False):
    st.markdown("""
    1. Click **Start Scraper** below.
    2. A browser window will open.
    3. In that browser:
       * Go to [SASClouds catalog](https://www.sasclouds.com/english/normal/)
       * Log in if needed
       * Set your filters (date, cloud cover, draw AOI on map)
       * Click **Search** and wait for results
    4. Return here and click **✅ Manual Input Completed**.
    5. The scraper will run. Wait for completion (watch logs).
    6. When finished, a **Download** button appears.
    """)

# Log placeholder (created once)
log_placeholder = st.empty()

# Button and status
col1, col2 = st.columns([1, 4])
with col1:
    if not st.session_state.scraping:
        if st.button("▶️ Start Scraper", type="primary", use_container_width=True):
            st.session_state.scraping = True
            st.session_state.zip_data = None
            st.session_state.zip_filename = None
            st.session_state.logs = []   # clear logs
            # Create temp dir
            temp_dir = Path(tempfile.mkdtemp(prefix="sasclouds_scrape_"))
            st.session_state.temp_dir = temp_dir  # store for later
            # Start thread
            def run():
                script_path = Path("sasclouds_scraper.py")
                if not script_path.exists():
                    st.session_state.logs.append("❌ scraper script not found: sasclouds_scraper.py")
                    st.session_state.scraping = False
                    return
                process = subprocess.Popen(
                    ["python", "-u", str(script_path), "--output", str(temp_dir)],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                )
                st.session_state.proc = process
                for line in iter(process.stdout.readline, ""):
                    st.session_state.logs.append(line.rstrip())
                process.wait()
                # Create ZIP in memory
                zip_buffer = io.BytesIO()
                with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
                    for file in temp_dir.rglob("*"):
                        zf.write(file, arcname=file.relative_to(temp_dir))
                zip_buffer.seek(0)
                st.session_state.zip_data = zip_buffer.getvalue()
                st.session_state.zip_filename = f"scraped_data_{temp_dir.name}.zip"
                # Cleanup
                shutil.rmtree(temp_dir, ignore_errors=True)
                st.session_state.scraping = False
                st.session_state.proc = None
            threading.Thread(target=run, daemon=True).start()
            st.rerun()
    else:
        if st.button("⏹️ Stop Scraper", use_container_width=True):
            if st.session_state.proc:
                st.session_state.proc.terminate()
            st.session_state.scraping = False
            st.rerun()

# Display logs (if any)
if st.session_state.logs:
    log_placeholder.code("\n".join(st.session_state.logs[-60:]), language="bash")
else:
    log_placeholder.info("Logs will appear here after starting the scraper.")

# If scraping is active, auto-refresh to show logs
if st.session_state.scraping:
    time.sleep(1)
    st.rerun()

# Download button
if st.session_state.zip_data:
    st.divider()
    st.success("✅ Scraping completed! Click below to download the results.")
    st.download_button(
        label="📥 Download Results (ZIP)",
        data=st.session_state.zip_data,
        file_name=st.session_state.zip_filename,
        mime="application/zip",
        use_container_width=True,
    )