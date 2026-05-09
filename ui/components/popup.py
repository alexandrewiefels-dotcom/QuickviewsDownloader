import streamlit as st

def render_how_it_works_popup():
    @st.dialog("✨ How OrbitShow Works – Technical Overview", width="large")
    def howto_dialog():
        st.markdown(r"""
        ### 🛰️ 1. Satellite Data & TLEs
        - **TLE (Two‑Line Element)** – Orbital parameters updated daily from **Space‑Track.org** (primary) and **Celestrak** (fallback).
        - The app caches TLEs locally (CSV) and refreshes automatically if older than 48 hours.
        - Each satellite’s **NORAD ID** is used to fetch its exact orbit.

        ### 📐 2. Off‑Nadir Angle (ONA) & Ground Range
        - ONA is the angle between the satellite’s nadir (straight down) and the target point.
        - **Ground range** \(d\) from nadir is calculated as:  
          \(d = R \cdot \arcsin\left(\frac{r}{R}\sin(\theta)\right) - \theta\)  
          where \(R\) = Earth radius, \(r\) = orbital radius, \(\theta\) = ONA (radians).
        - The app uses this to determine which parts of the orbit can cover your AOI.

        ### 🧮 3. Pass Detection Algorithm
        - **Coarse sampling** (1‑minute steps) to find windows where ONA ≤ max allowed.
        - **Fine sampling** (0.5‑minute steps) inside those windows to compute exact footprints.
        - Footprints are created as **swath ribbons** by buffering the ground track laterally.
        - The algorithm handles **antimeridian crossing** by splitting polygons and normalising longitudes.

        ### 🗺️ 4. Map Visualisation
        - **Folium** + **OpenStreetMap** tiles.
        - Footprints are coloured by satellite and direction (Ascending / Descending).
        - **Antimeridian‑safe** splitting ensures correct display across 180°E/W.
        - **Click on a footprint** to see a detailed popup (satellite, time, ONA, cloud cover, etc.).

        ### ⚙️ 5. Tasking Simulation (Sequential Paving)
        - After detecting passes, the **tasking optimizer**:
          1. Selects a **pivot pass** closest to AOI centroid.
          2. Shifts passes **westward** and **eastward** in geographic order.
          3. Applies a desired **overlap** (default 0 km edge‑to‑edge) to create a continuous coverage strip.
          4. Calculates the **required ONA** for each shift (clamped to max allowed).
        - The algorithm respects **orbit direction** (Ascending/Descending) and only uses passes of the same direction together.

        ### 📥 6. Export Formats
        - **KML** – Full geometry (footprints, ground tracks, metadata) for Google Earth.
        - **CSV** – Tabular data matching the on‑screen table.
        - **PDF** – Report with static maps (requires `cartopy`), tables, and coverage summary.

        ### 🧪 7. Under the Hood
        - **Skyfield** for precise satellite position calculations (SGP4 propagator).
        - **Shapely** + **PyProj** for geometric operations (buffer, intersection, area).
        - **Streamlit** interactive widgets and session state management.
        - **Background threads** for TLE downloads without blocking the UI.
        """)
        st.markdown("---")
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            if st.button("✓ Got it! Let's start", type="primary", use_container_width=True):
                st.session_state.show_howto = False
                st.rerun()
    howto_dialog()