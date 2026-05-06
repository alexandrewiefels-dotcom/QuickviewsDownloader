import streamlit as st
import subprocess
import time
import zipfile
import io
import shutil
import tempfile
from pathlib import Path

# --- Page Configuration ---
st.set_page_config(page_title="SASClouds Scraper", layout="wide")

# --- Password Authentication (using st.secrets) ---
PASSWORD = st.secrets.get("PASSWORD", "default_fallback")
if PASSWORD == "default_fallback":
    st.error("No PASSWORD found in secrets. Please set .streamlit/secrets.toml")
    st.stop()

if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

# --- Session State Initialization (CRITICAL!) ---
# This ensures all keys are created before the thread runs.
if "scraping" not in st.session_state:
    st.session_state.scraping = False
if "proc" not in st.session_state:
    st.session_state.proc = None
if "temp_dir" not in st.session_state:
    st.session_state.temp_dir = None
if "zip_data" not in st.session_state:
    st.session_state.zip_data = None
if "zip_filename" not in st.session_state:
    st.session_state.zip_filename = None

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


# --- Main App Interface ---
st.title("🛰️ SASClouds Satellite Image Scraper")
st.markdown("Extract footprints, images, and georeferenced world files.")

# --- Step-by-Step Tutorial ---
with st.expander("📖 How to Use This Scraper", expanded=False):
    st.markdown("""
    1.  **Click "Start Scraper"** below. A new browser window will open.
    2.  In that browser:
        *   Go to the [SASClouds catalog](https://www.sasclouds.com/english/normal/).
        *   **Log in** if asked.
        *   **Set your search filters** (date range, cloud cover, draw your AOI on the map).
        *   Click the **Search** button.
    3.  **Wait** for your results to load completely.
    4.  Go back to this **Streamlit app** and click the **"✅ Manual Input Completed"** button.
    5.  The scraper will now start automatically.
    6.  After it finishes, a **"📥 Download Results"** button will appear. Click it to save your data as a ZIP file.
    """)
    st.info("💡 **Tip:** The scraping process can take a few minutes. You can watch the live progress in the logs below.")


# --- The Scraper's Logic (Background Process) ---
def run_scraper(status):
    temp_dir = st.session_state.temp_dir
    script_path = Path("sasclouds_scraper.py")
    if not script_path.exists():
        st.error("scraper script not found")
        st.session_state.scraping = False
        return

    # Start the subprocess and capture its output
    process = subprocess.Popen(
        ["python", "-u", str(script_path), "--output", str(temp_dir)], # Pass the temp dir to the scraper
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    st.session_state.proc = process
    log_placeholder = status.empty()
    full_log = []

    # Read output in real-time and update the logs
    for line in iter(process.stdout.readline, ""):
        full_log.append(line)
        # Show the last 20 lines to keep the UI responsive
        log_placeholder.code("\n".join(full_log[-40:]), language="bash")
        status.write(f"Running... Processing {len(full_log)} log lines.")

    process.wait()
    st.session_state.scraping = False
    st.session_state.proc = None

    # Create an in-memory ZIP file for download
    if temp_dir and temp_dir.exists():
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            for file in temp_dir.rglob("*"):
                zf.write(file, arcname=file.relative_to(temp_dir))
        zip_buffer.seek(0)
        st.session_state.zip_data = zip_buffer.getvalue()
        st.session_state.zip_filename = f"scraped_data_{temp_dir.name}.zip"

    # Cleanup: remove the temporary directory after use
    shutil.rmtree(temp_dir, ignore_errors=True)
    status.update(label="✅ Scraping Complete!", state="complete")


# --- Button Control and Status UI ---
col1, col2 = st.columns([1, 4])
with col1:
    if not st.session_state.scraping:
        if st.button("▶️ Start Scraper", type="primary", use_container_width=True):
            st.session_state.scraping = True
            st.session_state.zip_data = None
            st.session_state.zip_filename = None
            st.session_state.temp_dir = Path(tempfile.mkdtemp(prefix="sasclouds_scrape_"))
            # Use `st.status` for a better live feedback experience
            status = st.status("Starting Scraper...", expanded=True)
            # We need to run the scraper in a separate thread to keep the UI alive
            import threading
            threading.Thread(target=run_scraper, args=(status,), daemon=True).start()
            st.rerun()
    else:
        empty, stop_btn_col, empty2 = st.columns([1, 2, 1])
        with stop_btn_col:
            if st.button("⏹️ Stop", use_container_width=True):
                if st.session_state.proc:
                    st.session_state.proc.terminate()
                st.session_state.scraping = False
                st.rerun()

# --- Live Logs Display ---
# This placeholder will be automatically updated by the `st.status` block

# --- Download Results ---
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