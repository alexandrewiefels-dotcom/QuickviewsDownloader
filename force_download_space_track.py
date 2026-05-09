#!/usr/bin/env python3
"""Force download TLEs using Space-Track.org ONLY (no Celestrak)"""

import sys
import time
import json
import requests
from pathlib import Path
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from config.satellites import SATELLITES
from data.tle_fetcher import TLEFetcher, CACHE_FILE

# Space-Track API URLs
SPACE_TRACK_AUTH_URL = "https://www.space-track.org/ajaxauth/login"
SPACE_TRACK_BULK_URL = "https://www.space-track.org/basicspacedata/query/class/tle_latest/ORDINAL/1/orderby/NORAD_CAT_ID/format/3le"


def get_all_norads():
    """Extract all NORAD IDs from config"""
    norads = set()
    for category in SATELLITES.values():
        for sat_info in category.values():
            norad = sat_info.get("norad")
            if norad:
                norads.add(norad)
    return sorted(list(norads))


def login_space_track(username, password):
    """Login to Space-Track and return session"""
    try:
        session = requests.Session()
        auth_data = {"identity": username, "password": password}
        print(f"Logging in as {username}...")
        response = session.post(SPACE_TRACK_AUTH_URL, data=auth_data, timeout=30)
        
        if response.status_code == 200:
            print("✅ Space-Track login successful")
            return session
        else:
            print(f"❌ Login failed: HTTP {response.status_code}")
            return None
    except Exception as e:
        print(f"❌ Login error: {e}")
        return None


def download_bulk_tles(session):
    """Download ALL TLEs in one request"""
    try:
        print("\nDownloading bulk TLEs from Space-Track...")
        print("This may take 30-60 seconds...")
        
        response = session.get(SPACE_TRACK_BULK_URL, timeout=120)
        
        if response.status_code == 200:
            content = response.text
            lines = content.strip().split('\n')
            print(f"Downloaded {len(lines)} lines")
            
            tles = {}
            for i in range(0, len(lines), 3):
                if i + 2 < len(lines):
                    line1 = lines[i+1].strip()
                    line2 = lines[i+2].strip()
                    
                    if len(line2) >= 7:
                        norad_str = line2[2:7].strip()
                        if norad_str.isdigit():
                            norad = int(norad_str)
                            tles[norad] = (line1, line2)
            
            print(f"Parsed {len(tles)} TLEs")
            return tles
        else:
            print(f"❌ Bulk download failed: HTTP {response.status_code}")
            return {}
    except Exception as e:
        print(f"❌ Bulk download error: {e}")
        return {}


def main():
    print("=" * 60)
    print("SPACE-TRACK FORCE DOWNLOAD")
    print("=" * 60)
    
    # Load credentials
    try:
        import streamlit as st
        username = st.secrets.get("SPACE_TRACK_USER")
        password = st.secrets.get("SPACE_TRACK_PASSWORD")
        
        if not username or not password:
            print("❌ Credentials not found in secrets.toml")
            print("Make sure you have:")
            print("  SPACE_TRACK_USER = 'your_email'")
            print("  SPACE_TRACK_PASSWORD = 'your_password'")
            return
    except Exception as e:
        print(f"❌ Error loading secrets: {e}")
        print("Make sure you're running with: streamlit run this_script.py")
        return
    
    # Get all NORADs
    norads = get_all_norads()
    print(f"\n📡 Total satellites: {len(norads)}")
    
    # Login and download
    session = login_space_track(username, password)
    if not session:
        return
    
    bulk_tles = download_bulk_tles(session)
    if not bulk_tles:
        print("❌ No TLEs downloaded")
        return
    
    # Update cache
    fetcher = TLEFetcher()
    matched = 0
    for norad in norads:
        if norad in bulk_tles:
            fetcher.tles[norad] = bulk_tles[norad]
            matched += 1
    
    # Save to CSV
    fetcher._save_to_csv()
    
    print(f"\n✅ Saved {matched}/{len(norads)} TLEs to cache")
    
    # Show missing
    missing = [n for n in norads if n not in fetcher.tles]
    if missing:
        print(f"\n⚠️ Still missing {len(missing)} NORADs:")
        for n in missing[:20]:
            print(f"  - {n}")
        if len(missing) > 20:
            print(f"  ... and {len(missing)-20} more")


if __name__ == "__main__":
    main()
