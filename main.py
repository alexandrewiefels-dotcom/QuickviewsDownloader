import streamlit as st
import subprocess
import tempfile
import zipfile
import io
import shutil
from pathlib import Path

st.set_page_config(page_title="SASClouds Scraper", layout="wide")

# --- Authentication (unchanged) ---
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

# --- Main UI ---
st.title("🛰️ SASClouds Satellite Image Scraper")
st.markdown("Extract footprints, full images, and georeferenced world files.")

with st.expander("📖 How to Use This Scraper", expanded=False):
    st.markdown("""
    1. Click **Start Scraper** below – a new browser window will open.
    2. In that browser:
       * Go to [SASClouds catalog](https://www.sasclouds.com/english/normal/)
       * Log in if needed
       * Set your filters (date range, cloud cover, draw AOI on map)
       * Click **Search** and wait for results to load
    3. **Return here** and press **✅ I have finished my manual search**.
    4. The scraper will then run automatically (this may take several minutes).
    5. When finished, a **Download** button appears – click to get your ZIP.
    """)

# --- State for the button ---
if "scraper_started" not in st.session_state:
    st.session_state.scraper_started = False
if "scraper_done" not in st.session_state:
    st.session_state.scraper_done = False
if "zip_data" not in st.session_state:
    st.session_state.zip_data = None
if "zip_filename" not in st.session_state:
    st.session_state.zip_filename = None

# --- The actual scraper execution (synchronous) ---
def run_scraper_sync():
    """Run the scraper synchronously, capturing output in a status container."""
    with st.status("🚀 Scraper is running...", expanded=True) as status:
        # Create a temporary directory for this run
        temp_dir = Path(tempfile.mkdtemp(prefix="sasclouds_scrape_"))
        status.write(f"📁 Temporary folder: {temp_dir}")

        script_path = Path("sasclouds_scraper.py")
        if not script_path.exists():
            st.error("❌ scraper script not found: sasclouds_scraper.py")
            st.session_state.scraper_started = False
            return

        # Launch subprocess
        process = subprocess.Popen(
            ["python", "-u", str(script_path), "--output", str(temp_dir)],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )

        # Stream output line by line into the status container
        logs = []
        for line in iter(process.stdout.readline, ""):
            logs.append(line.rstrip())
            # Keep the last 40 lines visible
            status.write("\n".join(logs[-40:]))
        process.wait()

        if process.returncode != 0:
            status.update(label="❌ Scraper failed", state="error")
            st.session_state.scraper_started = False
            return

        # Create ZIP file in memory
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            for file in temp_dir.rglob("*"):
                zf.write(file, arcname=file.relative_to(temp_dir))
        zip_buffer.seek(0)

        # Store results in session state
        st.session_state.zip_data = zip_buffer.getvalue()
        st.session_state.zip_filename = f"scraped_data_{temp_dir.name}.zip"

        # Cleanup temp directory
        shutil.rmtree(temp_dir, ignore_errors=True)

        status.update(label="✅ Scraping completed!", state="complete")
        st.session_state.scraper_started = False
        st.session_state.scraper_done = True

# --- Button logic ---
col1, col2 = st.columns([1, 4])
with col1:
    if not st.session_state.scraper_started and not st.session_state.scraper_done:
        if st.button("▶️ Start Scraper", type="primary", use_container_width=True):
            st.session_state.scraper_started = True
            st.session_state.scraper_done = False
            st.rerun()
    elif st.session_state.scraper_started:
        # A placeholder – the scraper is already running synchronously,
        # but we need to show the "I have finished my manual search" button.
        # However, the synchronously running function would block the UI,
        # so we cannot show it. We'll use a different approach:
        pass

# --- Manual input confirmation (separate button) ---
if not st.session_state.scraper_started and not st.session_state.scraper_done:
    if st.button("✅ I have finished my manual search", type="secondary", use_container_width=True):
        # Run the scraper synchronously – this will block the UI but show live logs
        run_scraper_sync()
        st.rerun()

# --- Download button ---
if st.session_state.zip_data and st.session_state.scraper_done:
    st.divider()
    st.success("✅ Scraping completed! Click below to download the results.")
    st.download_button(
        label="📥 Download Results (ZIP)",
        data=st.session_state.zip_data,
        file_name=st.session_state.zip_filename,
        mime="application/zip",
        use_container_width=True,
    )
    # Clear the done flag so the download button disappears after use? Optionally keep it.