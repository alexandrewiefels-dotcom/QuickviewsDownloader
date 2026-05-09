# pages/2_Satellite_Database.py
"""
Satellite Database – Technical details and live NORAD checkers
"""

import streamlit as st
import pandas as pd
import os
import base64
from config.satellites import SATELLITES

st.set_page_config(page_title="Satellite Database", layout="wide")

# ========== SIDEBAR LOGO + HOME BUTTON ==========
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
logo_path = os.path.join(BASE_DIR, "logo_orbitshow.jpg")

def _get_image_base64(image_path):
    with open(image_path, "rb") as img_file:
        return base64.b64encode(img_file.read()).decode()

st.sidebar.markdown("""
<style>
.sidebar-logo {
    display: flex;
    align-items: center;
    margin-bottom: 0.5rem;
}
.sidebar-logo span {
    font-size: 1.2rem;
    font-weight: bold;
    color: #F8FBFF;
}
.sidebar-home-btn {
    margin-top: 1rem;
    width: 100%;
}
</style>
""", unsafe_allow_html=True)

# Logo as clickable link (full page reload to home)
if os.path.exists(logo_path):
    b64 = _get_image_base64(logo_path)
    st.sidebar.markdown(
        f'<a href="/" style="text-decoration: none;"><img src="data:image/jpg;base64,{b64}" width="100%"></a>',
        unsafe_allow_html=True
    )
else:
    st.sidebar.markdown('<div class="sidebar-logo"><span>🛰️ OrbitShow</span><br><small>Satellite Database</small></div>', unsafe_allow_html=True)

# Streamlit button for home navigation
if st.sidebar.button("🏠 Back to Home", use_container_width=True, key="home_sidebar_btn"):
    st.switch_page("main.py")

st.sidebar.markdown("---")

# ========== FILTERS ==========
st.sidebar.header("🔍 Filter Satellites")

# Load data into DataFrame
records = []
for category_name, category in SATELLITES.items():
    for sat_name, sat_info in category.items():
        norad = sat_info.get("norad")
        provider = sat_info.get("provider", "Unknown")
        series = sat_info.get("series", "Other")
        sat_type = sat_info.get("type", "Unknown")
        launch = sat_info.get("launch_date", "N/A")
        period = sat_info.get("period_min", "N/A")
        inclination = sat_info.get("inclination", "N/A")
        status = sat_info.get("status", "operational")
        alt_name = sat_info.get("alt_name", "")
        
        cameras = sat_info.get("cameras", {})
        if not cameras:
            records.append({
                "Category": category_name,
                "Satellite Name": sat_name,
                "Alternative Name": alt_name,
                "NORAD": norad,
                "Provider": provider,
                "Series": series,
                "Type": sat_type,
                "Launch Date": launch,
                "Period (min)": period,
                "Inclination (°)": inclination,
                "Camera Mode": "N/A",
                "Resolution (m)": "N/A",
                "Swath (km)": "N/A",
                "Status": status,
            })
        else:
            for cam_name, cam_info in cameras.items():
                res = cam_info.get("resolution_m", cam_info.get("resolution", "N/A"))
                swath = cam_info.get("swath_km", "N/A")
                records.append({
                    "Category": category_name,
                    "Satellite Name": sat_name,
                    "Alternative Name": alt_name,
                    "NORAD": norad,
                    "Provider": provider,
                    "Series": series,
                    "Type": sat_type,
                    "Launch Date": launch,
                    "Period (min)": period,
                    "Inclination (°)": inclination,
                    "Camera Mode": cam_name,
                    "Resolution (m)": res,
                    "Swath (km)": swath,
                    "Status": status,
                })

df = pd.DataFrame(records)

categories = st.sidebar.multiselect("Category", options=sorted(df["Category"].unique()), default=sorted(df["Category"].unique()))
providers = st.sidebar.multiselect("Provider", options=sorted(df["Provider"].unique()), default=sorted(df["Provider"].unique()))
types = st.sidebar.multiselect("Type", options=sorted(df["Type"].unique()), default=sorted(df["Type"].unique()))
status_filter = st.sidebar.multiselect("Status", options=["operational", "standby", "decayed", "N/A"], default=["operational"])

# Apply filters
filtered_df = df[
    (df["Category"].isin(categories)) &
    (df["Provider"].isin(providers)) &
    (df["Type"].isin(types)) &
    (df["Status"].isin(status_filter))
].copy()  # .copy() to avoid SettingWithCopyWarning

# ========== MAIN CONTENT ==========
st.title("Satellite Technical Database")
st.markdown(f"**{len(filtered_df)}** satellite/tasking mode rows found (total {len(df)}).")

# Create clickable links
def make_norad_links(row):
    norad = row["NORAD"]
    if pd.isna(norad) or norad == "N/A":
        return "—", "—"
    n2yo_url = f"https://www.n2yo.com/satellite/?s={norad}"
    stl_url = f"https://www.satellitetrackerlive.com/satellites/{norad}"
    return f'<a href="{n2yo_url}" target="_blank">🔗 N2YO</a>', f'<a href="{stl_url}" target="_blank">🛰️ STL</a>'

filtered_df["N2YO"] = ""
filtered_df["Satellite Tracker Live"] = ""
for idx, row in filtered_df.iterrows():
    n2yo_link, stl_link = make_norad_links(row)
    filtered_df.at[idx, "N2YO"] = n2yo_link
    filtered_df.at[idx, "Satellite Tracker Live"] = stl_link

display_cols = ["Satellite Name", "Alternative Name", "NORAD", "Provider", "Series", "Type", 
                "Camera Mode", "Resolution (m)", "Swath (km)", "Launch Date", 
                "Period (min)", "Inclination (°)", "Status", "N2YO", "Satellite Tracker Live"]
display_cols = [c for c in display_cols if c in filtered_df.columns]

st.markdown(
    filtered_df[display_cols].to_html(escape=False, index=False),
    unsafe_allow_html=True
)

csv = filtered_df.to_csv(index=False).encode('utf-8')
st.download_button("📥 Download as CSV", data=csv, file_name="satellite_database.csv", mime="text/csv")

st.caption("Click the N2YO or STL links to check real‑time orbital data and status.")