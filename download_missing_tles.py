# download_missing_tles.py
"""Script pour télécharger les TLEs des NORADs manquants"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from data.tle_fetcher import TLEFetcher, get_pending_missing_norads, clear_missing_norads
from config.satellites import SATELLITES


def get_all_satellite_norads():
    """Get all NORADs from config"""
    norads = set()
    for category in SATELLITES.values():
        for sat_name, sat_info in category.items():
            norad = sat_info.get("norad")
            if norad:
                norads.add(norad)
    return list(norads)


def download_missing_tles():
    """Download TLEs for all missing NORADs"""
    print("=" * 60)
    print("  TÉLÉCHARGEMENT DES TLES MANQUANTS")
    print("=" * 60)
    
    fetcher = TLEFetcher()
    all_norads = get_all_satellite_norads()
    
    # Find which NORADs are missing
    missing = [n for n in all_norads if n not in fetcher.tles]
    
    print(f"\n📊 Statut actuel:")
    print(f"   Total satellites: {len(all_norads)}")
    print(f"   En cache: {len(fetcher.tles)}")
    print(f"   Manquants: {len(missing)}")
    
    if not missing:
        print("\n✅ Aucun TLE manquant!")
        return
    
    print(f"\n📡 NORADs manquants: {missing[:20]}{'...' if len(missing) > 20 else ''}")
    
    # Download missing TLEs
    print("\n🔄 Téléchargement des TLEs manquants...")
    
    success_count = 0
    for idx, norad in enumerate(missing, 1):
        print(f"[{idx:3d}/{len(missing)}] NORAD {norad}...", end=" ", flush=True)
        
        # Force refresh to try downloading
        tle = fetcher.fetch(norad, force_refresh=True)
        
        if tle:
            print("✅")
            success_count += 1
        else:
            print("❌")
        
        # Small delay to be polite
        time.sleep(0.5)
    
    print(f"\n📊 Résultat:")
    print(f"   Téléchargés: {success_count}/{len(missing)}")
    print(f"   Toujours manquants: {len(missing) - success_count}")
    
    # Clear pending list
    clear_missing_norads()
    
    print("\n✅ Terminé!")


if __name__ == "__main__":
    download_missing_tles()
