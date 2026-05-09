# ============================================================================
# FILE: visualization/csv_exporter.py
# CSV export for passes and tasking results
# Aligned with UI tables: passes and tasking have same columns as displayed.
# ============================================================================
import pandas as pd
import io
from datetime import datetime, timedelta
from typing import List, Optional
from models.satellite_pass import SatellitePass
from detection.daylight_filter import get_local_time_political


def safe_get_pass_time(p):
    """Safely get pass time from pass object"""
    if hasattr(p, 'pass_time'):
        return p.pass_time
    if hasattr(p, 'start_time'):
        return p.start_time
    return None


class CSVExporter:
    """Export passes and tasking results to CSV format"""
    
    @staticmethod
    def export_passes_to_csv(passes: List[SatellitePass], aoi=None) -> str:
        """
        Export passes to CSV string with columns matching the UI table.
        Columns: #, Satellite, Camera, Date (UTC), Time (UTC), Local Date, Local Time, ONA (°), Direction, Clouds
        """
        if not passes:
            return ""
        
        data = []
        for idx, p in enumerate(passes, start=1):
            pass_time = safe_get_pass_time(p)
            if pass_time is None:
                continue
            
            # UTC date and time
            date_utc = pass_time.strftime("%Y-%m-%d")
            time_utc = pass_time.strftime("%H:%M:%S")
            
            # Local political time
            local_time_str = get_local_time_political(pass_time, aoi)
            if " " in local_time_str:
                local_date, local_time = local_time_str.split(" ", 1)
            else:
                local_date = local_time_str
                local_time = ""
            
            cloud_str = f"{p.mean_cloud_cover:.0f}%" if hasattr(p, 'mean_cloud_cover') and p.mean_cloud_cover is not None else "N/A"
            
            row = {
                "#": idx,
                "Satellite": p.satellite_name,
                "Camera": p.camera_name,
                "Date (UTC)": date_utc,
                "Time (UTC)": time_utc,
                "Local Date": local_date,
                "Local Time": local_time,
                "ONA (°)": round(p.min_ona, 1),
                "Direction": p.orbit_direction,
                "Clouds": cloud_str,
            }
            data.append(row)
        
        df = pd.DataFrame(data)
        return df.to_csv(index=False)
    
    @staticmethod
    def export_tasking_to_csv(tasking_results: List[dict], aoi=None) -> str:
        """
        Export tasking results to CSV string with columns matching the UI table.
        Columns: #, Satellite, Camera, Date/Time UTC, Date/Time local, ONA used, Offset, Swath (km), GSD (m), Weather, Coverage
        """
        if not tasking_results:
            return ""
        
        data = []
        for idx, r in enumerate(tasking_results, start=1):
            pass_time = r.get('pass_time')
            if pass_time is None and 'pass' in r and hasattr(r['pass'], 'pass_time'):
                pass_time = r['pass'].pass_time
            
            if pass_time:
                date_time_utc = pass_time.strftime("%Y-%m-%d %H:%M:%S")
                local_time_str = get_local_time_political(pass_time, aoi)
            else:
                date_time_utc = "N/A"
                local_time_str = "N/A"
            
            shift = abs(r.get('shift_km', r.get('offset_km', 0)))
            shift_dir = "→" if r.get('shift_km', 0) > 0 else "←" if r.get('shift_km', 0) < 0 else ""
            offset_str = f"{shift_dir} {shift:.1f}" if shift_dir else f"{shift:.1f}"
            
            cloud = r.get('cloud_cover')
            cloud_str = f"{cloud:.0f}%" if cloud is not None else "N/A"
            coverage = r.get('coverage_pct', 0)
            
            row = {
                "#": idx,
                "Satellite": r.get('satellite', 'N/A'),
                "Camera": r.get('camera', 'N/A'),
                "Date/Time UTC": date_time_utc,
                "Date/Time local": local_time_str,
                "ONA used (°)": round(r.get('required_ona', 0), 1),
                "Offset (km)": offset_str,
                "Swath (km)": r.get('swath_km', 0),
                "GSD (m)": r.get('resolution_m', 0),
                "Weather": cloud_str,
                "Coverage (%)": round(coverage, 1),
            }
            data.append(row)
        
        df = pd.DataFrame(data)
        return df.to_csv(index=False)
