# /ui/pages/faq.py

import streamlit as st
from datetime import datetime

def render_faq_page():
    """Render a comprehensive FAQ page with search functionality and categories"""
    
    # Page header with animation
    st.markdown("""
    <style>
    .faq-header {
        text-align: center;
        padding: 2rem 0;
        background: linear-gradient(135deg, #1a2a4a 0%, #0f1a2e 100%);
        border-radius: 20px;
        margin-bottom: 2rem;
    }
    .faq-header h1 {
        font-size: 2.5rem;
        margin-bottom: 0.5rem;
    }
    .faq-header p {
        font-size: 1.1rem;
        opacity: 0.9;
    }
    .faq-category {
        background: rgba(46, 204, 113, 0.1);
        border-left: 4px solid #2ecc71;
        padding: 1rem;
        margin: 1.5rem 0 1rem 0;
        border-radius: 10px;
    }
    .faq-category h2 {
        margin: 0;
        font-size: 1.5rem;
        color: #2ecc71;
    }
    .faq-question {
        cursor: pointer;
        padding: 1rem;
        margin: 0.5rem 0;
        background: rgba(255,255,255,0.05);
        border-radius: 10px;
        transition: all 0.3s ease;
    }
    .faq-question:hover {
        background: rgba(46, 204, 113, 0.1);
        transform: translateX(5px);
    }
    .faq-question h3 {
        margin: 0;
        font-size: 1.1rem;
        display: flex;
        align-items: center;
        gap: 10px;
    }
    .faq-question .icon {
        font-size: 1.3rem;
    }
    .faq-answer {
        padding: 0.5rem 1rem 1rem 3rem;
        color: #cccccc;
        line-height: 1.6;
        border-left: 2px solid #2ecc71;
        margin-left: 1.5rem;
        margin-top: 0.5rem;
        margin-bottom: 1rem;
    }
    .faq-answer code {
        background: #1e1e1e;
        padding: 0.2rem 0.4rem;
        border-radius: 4px;
        font-size: 0.9rem;
    }
    .faq-answer pre {
        background: #1e1e1e;
        padding: 1rem;
        border-radius: 8px;
        overflow-x: auto;
    }
    .search-box {
        margin-bottom: 2rem;
    }
    .back-button {
        margin-top: 2rem;
        text-align: center;
    }
    .stats {
        display: flex;
        justify-content: space-around;
        margin: 2rem 0;
        gap: 1rem;
        flex-wrap: wrap;
    }
    .stat-card {
        background: rgba(46, 204, 113, 0.1);
        border-radius: 10px;
        padding: 1rem;
        text-align: center;
        flex: 1;
        min-width: 120px;
    }
    .stat-number {
        font-size: 2rem;
        font-weight: bold;
        color: #2ecc71;
    }
    .stat-label {
        font-size: 0.9rem;
        opacity: 0.8;
    }
    </style>
    """, unsafe_allow_html=True)
    
    # Header
    st.markdown("""
    <div class="faq-header">
        <h1>❓ Frequently Asked Questions</h1>
        <p>Find answers to common questions about OrbitShow</p>
    </div>
    """, unsafe_allow_html=True)
    
    # Search functionality
    search_term = st.text_input("🔍 Search FAQs", placeholder="Type your question or keyword...", key="faq_search")
    
    # Stats
    st.markdown("""
    <div class="stats">
        <div class="stat-card">
            <div class="stat-number">7</div>
            <div class="stat-label">Satellites</div>
        </div>
        <div class="stat-card">
            <div class="stat-number">0.5m</div>
            <div class="stat-label">Resolution</div>
        </div>
        <div class="stat-card">
            <div class="stat-number">14</div>
            <div class="stat-label">Days Max Range</div>
        </div>
        <div class="stat-card">
            <div class="stat-number">30°</div>
            <div class="stat-label">Max ONA</div>
        </div>
        <div class="stat-card">
            <div class="stat-number">150+</div>
            <div class="stat-label">Satellites in DB</div>
        </div>
    </div>
    """, unsafe_allow_html=True)
    
    # FAQ Categories and Questions - Expanded with 20+ new questions
    faqs = {
        "Getting Started": [
            {
                "question": "What is OrbitShow?",
                "answer": """
                OrbitShow is a satellite tasking simulation platform that helps you:
                - **Find optimal satellite overpasses** for any location on Earth
                - **Simulate satellite tasking** with adjustable Off-Nadir Angles (ONA)
                - **Visualize satellite footprints** on an interactive map
                - **Export results** to KML for use in Google Earth
                
                The platform uses real-time TLE (Two-Line Element) data to calculate precise satellite positions and trajectories.
                """
            },
            {
                "question": "Which satellites are available?",
                "answer": """
                OrbitShow includes **7 high-resolution satellites** from the JL1KF constellation:
                
                | Satellite | NORAD ID | Camera | Resolution |
                |----------|----------|--------|------------|
                | JL1KF 01B | 49003 | Wide | 0.5m |
                | JL1KF 01 | 45016 | Wide | 0.5m |
                | JL1KF 01C | 52443 | Wide | 0.5m |
                | JL1KF 02A | 57696 | Wide | 0.5m |
                | JL1KF 02B 1 | 61189 | Wide | 0.5m |
                | JL1KF 02B 2 | 61190 | Wide | 0.5m |
                | JL1KF 02B 3 | 61191 | Wide | 0.5m |
                
                All satellites feature a **0.5m resolution wide camera** for Earth observation.
                """
            },
            {
                "question": "How do I define an Area of Interest (AOI)?",
                "answer": """
                You can define your AOI in **three ways**:
                
                1. **Draw on Map**: Use the drawing tool in the top-right corner of the map to draw a polygon
                2. **Search Country**: Type a country name in the sidebar search box
                3. **Upload GeoJSON**: Upload a GeoJSON file with your polygon coordinates
                
                **Tip**: Click the 🎯 button on the map to zoom to your AOI after drawing.
                """
            },
            {
                "question": "Do I need an account to use OrbitShow?",
                "answer": """
                **No account is required** for basic features! OrbitShow is completely free to use:
                
                - ✅ Draw AOIs and search for satellite passes
                - ✅ Simulate tasking and drag footprints
                - ✅ Export results to KML
                - ✅ Live satellite tracking
                
                An account may be required in the future for advanced features like saving configurations or accessing historical data.
                """
            }
        ],
        
        "Technical": [
            {
                "question": "What is Off-Nadir Angle (ONA)?",
                "answer": """
                **Off-Nadir Angle (ONA)** is the angle between the satellite's nadir point (directly below) and the target point on Earth.
                
                - **Lower ONA (0-10°)**: Better image quality, fewer passes available
                - **Higher ONA (15-30°)**: More passes available, slightly lower image quality
                
                OrbitShow uses a **default ONA of 15°**, which provides a good balance between coverage and quality.
                
                The maximum ONA affects the ground range:
                - At 15° ONA: ~150 km from nadir
                - At 30° ONA: ~318 km from nadir
                """
            },
            {
                "question": "How does the pass detection algorithm work?",
                "answer": """
                The pass detection algorithm works in **several steps**:
                
                1. **TLE Loading**: Fetches current orbital elements for selected satellites
                2. **Orbit Propagation**: Calculates satellite positions at 1-minute intervals
                3. **Footprint Generation**: Creates ground footprints based on ONA
                4. **AOI Intersection**: Checks if footprints intersect your AOI
                5. **Pass Filtering**: Filters passes by ONA, orbit direction, and date range
                
                The algorithm uses Skyfield for precise astronomical calculations and Shapely for geometric operations.
                """
            },
            {
                "question": "How accurate are the satellite positions?",
                "answer": """
                Satellite position accuracy depends on **TLE age**:
                
                - **< 24 hours old**: ~1-3 km accuracy
                - **24-48 hours old**: ~3-10 km accuracy  
                - **> 48 hours old**: Accuracy degrades rapidly
                
                OrbitShow automatically:
                - Checks TLE age before each detection run
                - Triggers background downloads if TLEs are older than 48 hours
                - Never shows progress bars or notifications to users
                
                For mission-critical applications, always use fresh TLEs (less than 24 hours old).
                """
            },
            {
                "question": "What is a NORAD ID?",
                "answer": """
                A **NORAD ID** (also called NORAD Catalog Number or SATCAT number) is a unique 5-digit identifier assigned to each artificial satellite orbiting Earth.
                
                - Assigned by NORAD (North American Aerospace Defense Command)
                - Used to track and identify satellites globally
                - Required to fetch TLE data for specific satellites
                
                You can add custom satellites by providing their NORAD ID in the sidebar.
                """
            }
        ],
        
        "Map & Visualization": [
            {
                "question": "What do the different colors on the map mean?",
                "answer": """
                The map uses a **color-coded system** for satellite footprints:
                
                - 🟢 **Green footprints**: Ascending passes (North to South)
                - 🔴 **Red footprints**: Descending passes (South to North)
                - 🟡 **Yellow highlight**: Currently selected/highlighted pass
                - 📍 **Blue polygon**: Your Area of Interest (AOI)
                - ⚪ **White dots**: Live satellite positions (when tracking)
                - 🟣 **Magenta lines**: Live satellite orbit tracks
                
                **Hover** over any footprint to see detailed pass information including satellite name, time, and ONA.
                """
            },
            {
                "question": "How do I use the live tracking feature?",
                "answer": """
                **Live Tracking** shows real-time satellite positions on the map:
                
                1. Go to **Sidebar → Live Tracking**
                2. Select satellites you want to track from the dropdown
                3. Choose between **"Current time"** (auto-refresh) or **"Manual"** time modes
                4. Click **"Refresh satellite positions"** to update
                
                **Note**: Live tracking requires an active internet connection to fetch TLE data. The satellite icon appears at the **end of the track line** showing the most recent position.
                """
            },
            {
                "question": "Can I export the results?",
                "answer": """
                Yes! OrbitShow supports **KML export**:
                
                1. After running pass detection, click **"Export to KML"** button
                2. The KML file contains:
                   - Satellite footprints as polygons
                   - Ground tracks as lines
                   - Metadata (satellite name, time, ONA, NORAD ID)
                3. Open the KML in **Google Earth Pro** or **Google Earth Web**
                
                The KML export is compatible with most GIS applications.
                """
            },
            {
                "question": "Why does the map sometimes show fragmented polygons?",
                "answer": """
                Fragmented polygons occur when a satellite footprint crosses the **antimeridian** (180° longitude line).
                
                OrbitShow automatically:
                - Detects when footprints cross the antimeridian
                - Splits them into multiple polygons for correct display
                - Ensures proper visualization without wrapping artifacts
                
                This is normal behavior and doesn't affect the accuracy of the pass detection.
                """
            }
        ],
        
        "Tasking & Simulation": [
            {
                "question": "How does the tasking simulation work?",
                "answer": """
                The tasking simulation allows you to **virtually task satellites**:
                
                1. Run pass detection to find available passes
                2. Click **"Task"** next to any pass in the results table
                3. The pass footprint turns **orange** (tasked)
                4. **Drag the footprint** on the map to adjust its position
                5. The system calculates the required ONA for the new position
                
                This simulates how satellite operators adjust acquisition windows for specific targets.
                """
            },
            {
                "question": "What is the drag-and-drop feature?",
                "answer": """
                The **drag-and-drop** feature lets you reposition tasked footprints:
                
                - **Click** on a tasked (orange) footprint
                - **Drag** it perpendicular to the satellite's ground track
                - The system calculates the **new ONA** required
                - If ONA exceeds the maximum, the move is blocked
                
                This simulates real satellite tasking where you can adjust the acquisition window along the cross-track direction.
                """
            },
            {
                "question": "What is the difference between Ascending and Descending passes?",
                "answer": """
                **Orbit direction** refers to the satellite's movement relative to Earth's rotation:
                
                - **Ascending (🟢 Green)**: Satellite moves North to South
                  - Better for morning observations
                  - Sun illumination from the east
                  
                - **Descending (🔴 Red)**: Satellite moves South to North
                  - Better for afternoon observations
                  - Sun illumination from the west
                
                You can filter passes by direction using the **Orbit Filter** in the sidebar.
                """
            },
            {
                "question": "What happens when I simulate tasking multiple passes?",
                "answer": """
                When you simulate tasking multiple passes, OrbitShow performs **sequential paving**:
                
                1. Selects a **pivot pass** (closest to AOI center)
                2. Shifts passes **westward** from the pivot
                3. Shifts passes **eastward** from the pivot
                4. Calculates **gaps and overlaps** between footprints
                5. Reports **AOI coverage percentage**
                
                This simulates creating a continuous coverage strip over your Area of Interest.
                """
            }
        ],
        
        "Troubleshooting": [
            {
                "question": "Why am I getting 'No passes found'?",
                "answer": """
                Common reasons for **"No passes found"**:
                
                1. **AOI not defined**: Draw or load an AOI first
                2. **No satellites selected**: Select at least one satellite in the sidebar
                3. **Date range too short**: Extend the date range (max 14 days)
                4. **ONA too low**: Increase the maximum ONA (try 20-30°)
                5. **Orbit filter active**: Set orbit filter to "Both"
                6. **Remote area**: Some areas have fewer passes; try more satellites
                
                **Tip**: Start with all satellites, 14-day range, and 30° ONA to see available passes.
                """
            },
            {
                "question": "The map is not loading properly. What should I do?",
                "answer": """
                **Map loading issues** can be resolved by:
                
                1. **Clear browser cache**: Ctrl+Shift+Delete (Windows) or Cmd+Shift+Delete (Mac)
                2. **Refresh the page**: Press F5 or Ctrl+R
                3. **Check internet connection**: The map requires loading Leaflet libraries
                4. **Disable ad blockers**: Some ad blockers interfere with map tiles
                5. **Try a different browser**: Chrome or Firefox recommended
                
                If the issue persists, check the browser console (F12) for errors.
                """
            },
            {
                "question": "Live tracking shows no satellite positions. Why?",
                "answer": """
                **Live tracking issues** can be caused by:
                
                1. **No satellites selected**: Select satellites in the Live Tracking tab
                2. **TLE data missing**: Wait for background TLE download to complete
                3. **Time mode issue**: Try switching between "Current time" and "Manual"
                4. **Refresh not clicked**: Click "Refresh satellite positions" after enabling tracking
                5. **NORAD ID mismatch**: Verify satellite NORAD IDs are correct
                
                **Check logs**: Look for warnings about "Using generated approximate TLE" - these indicate missing TLE data.
                """
            },
            {
                "question": "Why are some satellites showing 'generated approximate TLE'?",
                "answer": """
                This warning appears when OrbitShow cannot find real TLE data for a satellite:
                
                **Causes**:
                - Satellite NORAD ID not in the database
                - Space-Track.org or N2YO.com API unavailable
                - Network connectivity issues
                
                **Solutions**:
                - Check your internet connection
                - Add Space-Track credentials to `.streamlit/secrets.toml`
                - Wait for background TLE download to complete
                - The satellite will still work with approximate TLEs (lower accuracy)
                
                Generated TLEs provide approximate positions but may be less accurate than real TLEs.
                """
            }
        ],
        
        "Data & Privacy": [
            {
                "question": "Where does the satellite data come from?",
                "answer": """
                OrbitShow uses **multiple data sources**:
                
                1. **TLE Data**: 
                   - Primary: Space-Track.org (requires account)
                   - Fallback: N2YO.com API
                   - Local: CSV cache for offline use
                
                2. **Satellite Database**: 
                   - CSV file with 150+ satellites
                   - Includes NORAD IDs and basic info
                
                3. **Geographic Data**:
                   - World countries GeoJSON for country search
                   - Local AOI history storage
                
                All data is **cached locally** to minimize API calls.
                """
            },
            {
                "question": "Is my data private?",
                "answer": """
                **Privacy is important to OrbitShow**:
                
                - **No data sent to external servers** (except TLE API calls)
                - **AOIs are stored locally** in `aoi_history/` folder
                - **No user tracking** (except anonymous action counts)
                - **No account required** for basic features
                
                The only external calls are:
                - TLE downloads (Space-Track.org or N2YO.com)
                - Map tile loading (OpenStreetMap)
                
                Your AOI and tasking data never leave your computer.
                """
            },
            {
                "question": "Can I delete my AOI history?",
                "answer": """
                Yes! AOI history is stored locally in the `aoi_history/` folder.
                
                **To delete AOI history**:
                1. Navigate to your OrbitShow installation folder
                2. Open the `aoi_history/` directory
                3. Delete individual JSON files or the entire folder
                
                The folder will be recreated automatically when you draw new AOIs.
                """
            }
        ],
        "Technical Deep Dive": [
            {
                "question": "How accurate are the satellite positions?",
                "answer": """
                Position accuracy depends on TLE age and the SGP4 propagator:
                - **TLE < 24h** → 1‑3 km error
                - **TLE 24‑48h** → 3‑10 km error  
                - **TLE > 48h** → error grows rapidly (not recommended)
        
                The app triggers a background TLE update if the cache is older than 48 hours or if some satellites have no valid TLE.
                """
            },
            {
                "question": "How is the Off‑Nadir Angle (ONA) calculated?",
                "answer": """
                The ONA is computed using spherical geometry:
        
                \\[ \\text{ONA} = \\arctan\\left(\\frac{R \\sin(\\theta)}{r - R \\cos(\\theta)}\\right) \\]
        
                Where:
                - \\(R\\) = Earth radius (6371 km)
                - \\(r\\) = orbital radius (e.g., 6921 km for 550 km altitude)
                - \\(\\theta\\) = central angle between subpoint and target
        
                The ground range \\(d\\) is related by \\(d = R \\cdot \\theta\\).  
                The algorithm inverts this relationship when shifting footprints during tasking.
                """
            },
            {
                "question": "How does the tasking algorithm decide which passes to shift?",
                "answer": """
                The **sequential paving** algorithm works as follows:
        
                1. **Sort passes by cross‑track offset** (distance from AOI centroid to ground track).
                2. **Select a pivot pass** – the one with smallest absolute offset.
                3. **Shift passes westwards** from the pivot:
                   - Desired centre = previous centre – (half swath1 + half swath2) + overlap
                4. **Shift passes eastwards** similarly but subtracting overlap.
                5. **Clamp shifts** to the maximum allowed by the ONA limit.
                6. **Re‑compute footprints** for the shifted ground tracks.
        
                This creates a continuous (or overlapping) coverage strip that maximises AOI coverage with minimal ONA.
                """
            },
            {
                "question": "What is the antimeridian and how does the app handle it?",
                "answer": """
                The antimeridian is the 180° longitude line. Polygons or lines that cross it would wrap around the map incorrectly.
        
                OrbitShow **splits** any footprint or ground track that crosses the antimeridian:
                - Polygons are split into multiple parts, each staying within -180° to 180°.
                - Lines are broken at the crossing point.
                - Longitude values are normalised to [-180°, 180°] using `((lon + 180) % 360) - 180`.
        
                This ensures correct visualisation on all maps (Folium, KML, static maps).
                """
            },
            {
                "question": "Why do some satellites show 'generated approximate TLE'?",
                "answer": """
                If **all** data sources (Space‑Track, Celestrak, N2YO) fail to provide a TLE for a NORAD ID, the app generates a **placeholder TLE**:
                - Mean motion = 15.2 rev/day (≈ 550 km altitude)
                - Inclination = 97.5° (typical SSO)
                - Epoch = current date
        
                This allows the satellite to appear in lists, but pass predictions will be very inaccurate.  
                The app schedules a **background re‑attempt** every few hours. Once a real TLE is found, it replaces the placeholder.
                """
            },
            {
                "question": "How does the daylight filter work?",
                "answer": """
                The filter uses **local solar time** estimated from longitude:
        
                \\[ \\text{Local solar hour} = \\text{UTC hour} + \\frac{\\text{longitude}}{15} \\pmod{24} \\]
        
                No political timezones or daylight saving are used – it’s purely astronomical.  
                A pass is kept if the local solar hour is between 09:00 and 15:00 (default range), which roughly corresponds to good illumination for optical imaging.
                """
            },
            {
                "question": "What coordinate system and projection are used for maps?",
                "answer": """
                - **Folium interactive map** uses **Web Mercator** (EPSG:3857) but expects coordinates in **WGS84** (EPSG:4326) latitude/longitude.
                - **Static maps** (PDF export) use **Plate Carrée** (EPSG:4326) via Cartopy, which is a simple cylindrical projection.
                - **Area calculations** (AOI size, coverage) use **geodesic** area via `pyproj.Geod` for accuracy, not planar approximations.
                - **Distances** (ground range, offset) are computed using great‑circle formulas.
                """
            }
        ],
        "Advanced Features": [
            {
                "question": "Can I add my own satellites?",
                "answer": """
                **Yes!** You can add custom satellites using their NORAD ID:
                
                1. Go to **Sidebar → Pass Prediction**
                2. Expand **"Add custom satellite (NORAD)"**
                3. Enter the **NORAD ID** (5-digit number)
                4. Optional: Give it a custom name
                5. Set the **swath width** and **resolution**
                6. Click **"Add satellite"**
                
                The satellite will appear in the selection list for future searches.
                """
            },
            {
                "question": "What is the maximum date range for pass detection?",
                "answer": """
                The **maximum date range** is **14 days** between start and end dates.
                
                **Why 14 days?**
                - TLE accuracy degrades beyond 14 days
                - Performance optimization
                - Most satellite revisit periods are shorter
                
                For longer-term planning, run multiple searches with overlapping date ranges.
                """
            },
            {
                "question": "Does OrbitShow work offline?",
                "answer": """
                OrbitShow has **limited offline capabilities**:
                
                **Works offline**:
                - Viewing previously detected passes (cached)
                - Viewing the map (if tiles are cached)
                
                **Requires internet**:
                - Fetching fresh TLE data
                - Loading map tiles for new areas
                - Adding new satellites by NORAD ID
                
                Once TLEs are cached, you can run pass detection without internet for up to 48 hours.
                """
            },
            {
                "question": "How often are TLEs updated?",
                "answer": """
                TLEs are updated automatically:
                
                - **Background check**: Every time you run pass detection
                - **Auto-refresh**: Triggered if TLEs are older than 48 hours
                - **Silent updates**: You never see progress bars or notifications
                
                For the most accurate positions, ensure your computer has an internet connection when running pass detection.
                """
            },
            {
                "question": "Can I use OrbitShow for commercial purposes?",
                "answer": """
                OrbitShow is currently **free for all users**, including commercial use.
                
                **Allowed uses**:
                - Mission planning
                - Satellite tasking simulation
                - Educational purposes
                - Research and development
                
                **Limitations**:
                - No warranty on TLE accuracy
                - Rate limits on external APIs
                - Not for real-time satellite control
                
                For dedicated commercial support, please contact the development team.
                """
            }
        ]
    }
    
    # Filter FAQs based on search term
    filtered_faqs = {}
    if search_term:
        search_term_lower = search_term.lower()
        for category, questions in faqs.items():
            filtered_questions = []
            for qa in questions:
                if search_term_lower in qa["question"].lower() or search_term_lower in qa["answer"].lower():
                    filtered_questions.append(qa)
            if filtered_questions:
                filtered_faqs[category] = filtered_questions
    else:
        filtered_faqs = faqs
    
    # Display FAQs by category
    if not filtered_faqs:
        st.info(f"No FAQs found matching '{search_term}'. Try a different search term.")
    
    # Use expanders for each category
    for category, questions in filtered_faqs.items():
        with st.expander(f"📁 {category} ({len(questions)} questions)", expanded=not search_term):
            for i, qa in enumerate(questions):
                # Use columns for better layout
                col1, col2 = st.columns([1, 20])
                with col1:
                    st.markdown("**Q:**")
                with col2:
                    st.markdown(f"**{qa['question']}**")
                
                col1, col2 = st.columns([1, 20])
                with col1:
                    st.markdown("**A:**")
                with col2:
                    st.markdown(qa['answer'])
                
                if i < len(questions) - 1:
                    st.divider()
    
    # Contact section
    st.markdown("---")
    st.markdown("""
    ### ❓ Still have questions?
    
    If you couldn't find the answer you're looking for, please reach out to us:
    
    - 📧 **Email**: support@orbitshow.com
    - 💬 **GitHub**: [Report an issue](https://github.com/yourrepo/orbitshow/issues)
    - 📚 **Documentation**: [User Guide](https://docs.orbitshow.com)
    """)
    
    # Back button
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        if st.button("← Back to Main App", type="primary", use_container_width=True, key="back_from_faq_page"):  # Changed key
            st.session_state.show_faq = False
            st.rerun()
