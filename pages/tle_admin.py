# ============================================================================
# FILE: pages/tle_admin.py – TLE Management for Admin
# All TLE-related UI moved from sidebar to this dedicated admin page
# ============================================================================
import streamlit as st
import pandas as pd
from datetime import datetime
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).parent.parent))

from update_tles import update_all_satellites, export_tles_to_config, get_cache_status, DEFAULT_NORADS
from core.tle_scheduler import get_scheduler
from admin_auth import authenticate_admin


def render_tle_status_card():
    """Render TLE status card with all metrics"""
    scheduler = get_scheduler()
    status = scheduler.get_status()
    
    st.subheader("📡 TLE Data Status")
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Cache Validity", f"{status['cache_validity_hours']}h")
    with col2:
        st.metric("Update Interval", f"{status['update_interval_hours']}h")
    with col3:
        if status['last_update']:
            last_update = datetime.fromisoformat(status['last_update'])
            hours_ago = (datetime.now() - last_update).total_seconds() / 3600
            st.metric("Last Update", f"{hours_ago:.1f}h ago")
        else:
            st.metric("Last Update", "Never")
    with col4:
        next_update = status.get('next_update_in_hours', 0)
        st.metric("Next Update", f"{next_update:.1f}h")
    
    st.markdown("---")
    
    # Cache health
    st.subheader("📊 Cache Health")
    
    if status['total'] > 0:
        valid_pct = (status['valid'] / status['total'] * 100) if status['total'] > 0 else 0
        st.progress(valid_pct / 100, text=f"Cache health: {valid_pct:.1f}%")
        
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Total Satellites", status['total'])
        with col2:
            st.metric("Valid (Fresh)", status['valid'], delta=f"{status['valid'] - status['expired']}")
        with col3:
            st.metric("Expired", status['expired'])
        
        if status['missing'] > 0:
            st.warning(f"⚠️ {status['missing']} satellites have no TLE data")
    else:
        st.warning("⚠️ No TLE data found. Run an update to fetch satellite orbital data.")
    
    return status


def render_update_controls():
    """Render manual update controls"""
    st.subheader("🔄 Manual TLE Update")
    
    col1, col2 = st.columns(2)
    with col1:
        force_update = st.checkbox("Force update (ignore cache)", value=False)
    with col2:
        export_after = st.checkbox("Export after update", value=True)
    
    if st.button("🔄 Update All TLEs Now", type="primary", use_container_width=True):
        with st.spinner("Updating TLEs... This may take a few minutes..."):
            success_count, failed_norads = update_all_satellites(
                norads=DEFAULT_NORADS,
                force=force_update
            )
            
            if export_after:
                export_tles_to_config()
            
            if success_count > 0:
                st.success(f"✅ Successfully updated {success_count} satellites")
                if failed_norads:
                    st.warning(f"⚠️ Failed to update {len(failed_norads)} satellites")
                    with st.expander("View failed NORADs"):
                        st.write(failed_norads)
            else:
                st.error("❌ Update failed")
            
            # Update scheduler state
            scheduler = get_scheduler()
            scheduler.last_update_time = datetime.now()
            scheduler._save_state()
            time.sleep(1)
            st.rerun()
    
    # Single satellite update
    st.subheader("🎯 Update Specific Satellite")
    norad_input = st.text_input("NORAD ID", placeholder="Enter NORAD ID (e.g., 40961)")
    
    if st.button("Update Single Satellite", use_container_width=True):
        if norad_input and norad_input.isdigit():
            norad = int(norad_input)
            with st.spinner(f"Updating NORAD {norad}..."):
                from update_tles import update_single_satellite
                line1, line2 = update_single_satellite(norad, force=force_update)
                if line1 and line2:
                    st.success(f"✅ Updated NORAD {norad}")
                    st.code(f"{line1}\n{line2}")
                    export_tles_to_config()
                else:
                    st.error(f"❌ Failed to update NORAD {norad}")
        else:
            st.error("Please enter a valid NORAD ID")


def render_satellite_details():
    """Render detailed satellite TLE information"""
    st.subheader("📋 Satellite TLE Details")
    
    status = get_cache_status()
    
    if status['satellites']:
        df = pd.DataFrame(status['satellites'])
        df = df.sort_values('age_hours', ascending=False)
        
        # Add status icons
        def get_status_icon(age, valid):
            if not valid:
                return '🔴'
            elif age <= 24:
                return '🟢'
            elif age <= 48:
                return '🟡'
            else:
                return '🟠'
        
        df['Status'] = df.apply(lambda x: get_status_icon(x['age_hours'], x['valid']), axis=1)
        df['age_hours'] = df['age_hours'].apply(lambda x: f"{x:.1f}h")
        
        # Select columns to display
        display_df = df[['Status', 'norad', 'age_hours', 'valid', 'source', 'epoch']]
        display_df.columns = ['Status', 'NORAD ID', 'Cache Age', 'Valid', 'Source', 'Epoch']
        
        st.dataframe(display_df, use_container_width=True)
        
        # Export option
        csv = df.to_csv(index=False)
        st.download_button(
            label="📥 Export Satellite Status (CSV)",
            data=csv,
            file_name=f"tle_status_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            mime="text/csv"
        )
    else:
        st.info("No satellite TLE data available. Run an update to fetch data.")


def render_auto_update_settings():
    """Render auto-update settings"""
    st.subheader("⚙️ Auto-Update Settings")
    
    scheduler = get_scheduler()
    
    col1, col2 = st.columns(2)
    with col1:
        new_interval = st.number_input(
            "Update interval (hours)",
            min_value=6,
            max_value=168,
            value=scheduler.update_interval_hours,
            step=6,
            help="How often to automatically check for TLE updates"
        )
        if new_interval != scheduler.update_interval_hours:
            scheduler.update_interval_hours = new_interval
            scheduler._save_state()
            st.success(f"Update interval set to {new_interval} hours")
    
    with col2:
        st.info(f"""
        **How auto-update works:**
        - TLEs are valid for {scheduler.cache_validity_hours} hours
        - Updates run automatically every {scheduler.update_interval_hours} hours
        - Updates happen in background when someone visits the app
        - Manual updates can be triggered anytime
        """)
    
    st.caption("Note: TLEs are fetched from Celestrak (free) and cached locally for 72 hours.")


def main():
    # Check authentication
    if not authenticate_admin():
        st.stop()
    
    st.title("🛰️ TLE Management Console")
    st.markdown("Manage Two-Line Element (TLE) data for all satellites")
    st.markdown("---")
    
    # Create tabs
    tab1, tab2, tab3, tab4 = st.tabs([
        "📊 Status", "🔄 Update", "📋 Satellite Details", "⚙️ Settings"
    ])
    
    with tab1:
        render_tle_status_card()
    
    with tab2:
        render_update_controls()
    
    with tab3:
        render_satellite_details()
    
    with tab4:
        render_auto_update_settings()
    
    st.markdown("---")
    st.caption("""
    **About TLE Data:**
    - TLEs (Two-Line Elements) are orbital parameters that predict satellite positions
    - Data is fetched from Celestrak (free public API)
    - Cache validity: 72 hours (TLEs typically expire after 24-48 hours)
    - Updates run automatically every 24 hours when the app is accessed
    """)

if __name__ == "__main__":
    main()
