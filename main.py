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
    **Important:** The scraper runs in **headless mode** on Streamlit Cloud.  
    You **cannot** interact with the browser window.  
    Therefore, you must have already logged into SASClouds and set your filters in a **separate regular browser** (not through this app).  
    The scraper will only work if you have a persistent login session (cookies).  
    We recommend running this app **locally** instead of on Streamlit Cloud for full interactive control.

    If you still wish to try on Cloud:
    1. Click **Start Scraper**.
    2. The scraper will try to load the catalog page.
    3. It will wait for **5 minutes** for results to appear.
    4. You cannot manually click "Search" – so the scraper will time out.
    """)

# --- Session state for the button and results ---
if "scraper_running" not in st.session_state:
    st.session_state.scraper_running = False
if "scraper_done" not in st.session_state:
    st.session_state.scraper_done = False
if "zip_data" not in st.session_state:
    st.session_state.zip_data = None
if "zip_filename" not in st.session_state:
    st.session_state.zip_filename = None

# --- Run scraper (synchronous) with live logs ---
def run_scraper():
    with st.status("🚀 Running scraper...", expanded=True) as status:
        temp_dir = Path(tempfile.mkdtemp(prefix="sasclouds_scrape_"))
        status.write(f"📁 Temporary folder: {temp_dir}")

        script_path = Path("sasclouds_scraper.py")
        if not script_path.exists():
            st.error("❌ scraper script not found")
            return

        # Start the subprocess
        process = subprocess.Popen(
            ["python", "-u", str(script_path), "--output", str(temp_dir)],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )

        # Capture and display output line by line
        lines = []
        for line in iter(process.stdout.readline, ""):
            lines.append(line.rstrip())
            # Show last 50 lines
            status.write("\n".join(lines[-50:]))
        process.wait()

        if process.returncode != 0:
            status.update(label="❌ Scraper failed", state="error")
            return

        # Create ZIP
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            for file in temp_dir.rglob("*"):
                zf.write(file, arcname=file.relative_to(temp_dir))
        zip_buffer.seek(0)

        st.session_state.zip_data = zip_buffer.getvalue()
        st.session_state.zip_filename = f"scraped_data_{temp_dir.name}.zip"
        shutil.rmtree(temp_dir, ignore_errors=True)

        status.update(label="✅ Scraping completed!", state="complete")
        st.session_state.scraper_done = True

# --- Buttons ---
if not st.session_state.scraper_running and not st.session_state.scraper_done:
    if st.button("▶️ Start Scraper", type="primary", use_container_width=True):
        st.session_state.scraper_running = True
        run_scraper()
        st.session_state.scraper_running = False
        st.rerun()

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