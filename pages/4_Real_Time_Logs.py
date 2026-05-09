import streamlit as st
import json
from pathlib import Path
import pandas as pd
from streamlit_autorefresh import st_autorefresh

st.set_page_config(page_title="Realtime Logs", layout="wide")
st.title("📡 Realtime User Activity Logs")

# Refresh every 2 seconds
st_autorefresh(interval=2000, key="realtime_logs")

log_file = Path("navigation_logs.json")
if log_file.exists():
    with open(log_file, "r") as f:
        logs = json.load(f)
    
    if logs:
        # Show last 50 entries, newest first
        df = pd.DataFrame(logs[-50:][::-1])
        st.dataframe(df, use_container_width=True)
        
        # Show a simple counter
        st.metric("Total logs captured", len(logs))
    else:
        st.info("No log entries yet.")
else:
    st.info("Log file not found. Run the app to generate logs.")