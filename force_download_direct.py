"""Direct download with hardcoded credentials (temporary)"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

# HARDCODE CREDENTIALS TEMPORARILY (remove after testing)
SPACE_TRACK_USER = "alexandrewiefels@gmail.com"
SPACE_TRACK_PASSWORD = "SpaceTrackPassword34"

from config.satellites import SATELLITES
from data.tle_fetcher import TLEFetcher

# Create fetcher with hardcoded credentials
fetcher = TLEFetcher(
    space_track_user=SPACE_TRACK_USER,
    space_track_pass=SPACE_TRACK_PASSWORD
)

print(f"Space-Track available: {fetcher.space_track_available}")

if fetcher.space_track_available:
    # Force bulk download
    from force_download_tles import bulk_download_from_space_track
    session = fetcher.space_track_session
    bulk_tles = bulk_download_from_space_track(session)
    
    if bulk_tles:
        # Get all NORADs
        norads = set()
        for category in SATELLITES.values():
            for sat_info in category.values():
                if sat_info.get("norad"):
                    norads.add(sat_info["norad"])
        
        matched = 0
        for norad in norads:
            if norad in bulk_tles:
                fetcher.tles[norad] = bulk_tles[norad]
                matched += 1
        
        fetcher._save_to_csv()
        print(f"Saved {matched}/{len(norads)} TLEs")
