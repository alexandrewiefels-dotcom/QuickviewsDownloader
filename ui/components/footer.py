import streamlit as st
from navigation_tracker import track_user_action

def render_footer():
    st.markdown("---")
    
    col_left, col_center, col_right = st.columns([1, 1, 1])
    
    with col_center:
        # Change from 3 to 4 columns to accommodate the new button
        col_btn1, col_btn2, col_btn3, col_btn4 = st.columns(4, gap="small")
        
        with col_btn1:
            if st.button("❓ FAQ", key="footer_faq_btn", use_container_width=True):
                track_user_action("footer_faq_clicked")
                st.session_state.show_faq = not st.session_state.get("show_faq", False)
                st.rerun()
        
        with col_btn2:
            if st.button("📧 Contact", key="footer_contact_btn", use_container_width=True):
                track_user_action("footer_contact_clicked")
                st.session_state.show_contact = not st.session_state.get("show_contact", False)
                st.rerun()
        
        with col_btn3:
            if st.button("❔ How it works", key="footer_howto_btn", use_container_width=True):
                track_user_action("footer_howto_clicked")
                st.session_state.show_howto = True
                st.rerun()
        
        with col_btn4:
            if st.button("🛰️ Satellite Database", key="footer_db_btn", use_container_width=True):
                track_user_action("footer_db_clicked")
                st.switch_page("pages/2_Satellite_Database.py")

def render_acknowledgments():
    """Renders the API acknowledgments footer"""
    st.markdown("---")
    st.markdown("""
    <div style="text-align: center; padding: 20px 0 10px 0; color: #666; font-size: 0.85rem;">
        <p style="margin-bottom: 10px;"><strong>🙏 Acknowledgments</strong></p>
        <p style="margin-bottom: 5px;">
            <a href="https://rhodesmill.org/skyfield/" target="_blank" style="color: #666; text-decoration: none;">Skyfield</a> - Astrometry library &nbsp;|&nbsp;
            <a href="https://python-visualization.github.io/folium/" target="_blank" style="color: #666; text-decoration: none;">Folium</a> - Interactive maps &nbsp;|&nbsp;
            <a href="https://streamlit.io/" target="_blank" style="color: #666; text-decoration: none;">Streamlit</a> - Web framework
        </p>
        <p style="margin-bottom: 5px;">
            <a href="https://www.space-track.org/" target="_blank" style="color: #666; text-decoration: none;">Space-Track.org</a> - TLE data &nbsp;|&nbsp;
            <a href="https://openweathermap.org/" target="_blank" style="color: #666; text-decoration: none;">OpenWeatherMap</a> - Cloud cover data
        </p>
    </div>
    """, unsafe_allow_html=True)
