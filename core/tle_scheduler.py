# ============================================================================
# FILE: core/tle_scheduler.py – Daily TLE update scheduler
# Uses Celestrak (no API key, no rate limits)
# FIX: Replaced all print() with logging
# ============================================================================
import streamlit as st
import threading
from pathlib import Path
from datetime import datetime, timedelta
import json
import logging

from update_tles import update_all_satellites, get_cache_status
from core.exceptions import TLEError, TLEFetchError

logger = logging.getLogger(__name__)


class TLEScheduler:
    """Manages automatic TLE updates using Celestrak"""
    
    def __init__(self):
        self.last_update_time = None
        self.update_in_progress = False
        self.update_interval_hours = 24
        self.status_file = Path("data/tle_cache/scheduler_status.json")
        self._load_state()
    
    def _load_state(self):
        """Load persisted scheduler state"""
        if self.status_file.exists():
            try:
                with open(self.status_file, 'r') as f:
                    data = json.load(f)
                    if 'last_update_time' in data and data['last_update_time']:
                        self.last_update_time = datetime.fromisoformat(data['last_update_time'])
            except (json.JSONDecodeError, IOError, ValueError):
                pass
    
    def _save_state(self):
        """Persist scheduler state"""
        try:
            self.status_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.status_file, 'w') as f:
                json.dump({
                    'last_update_time': self.last_update_time.isoformat() if self.last_update_time else None
                }, f)
        except (IOError, OSError):
            pass
    
    def is_update_needed(self):
        """Check if TLEs need to be updated"""
        if self.last_update_time is None:
            return True
        
        hours_since = (datetime.now() - self.last_update_time).total_seconds() / 3600
        return hours_since >= self.update_interval_hours
    
    def run_update(self):
        """Run a TLE update"""
        if self.update_in_progress:
            return {"status": "already_running"}
        
        self.update_in_progress = True
        try:
            logger.info("Starting update at %s", datetime.now())
            success_count, failed = update_all_satellites(force=False)
            self.last_update_time = datetime.now()
            self._save_state()
            
            return {
                "status": "success",
                "success_count": success_count,
                "failed_count": len(failed)
            }
        except Exception as e:
            return {"status": "failed", "error": str(e)}
        finally:
            self.update_in_progress = False
    
    def run_update_async(self):
        """Run update in background thread"""
        if self.update_in_progress:
            return {"status": "already_running"}
        
        if not self.is_update_needed():
            return {"status": "not_needed"}
        
        thread = threading.Thread(target=self.run_update, daemon=True)
        thread.start()
        return {"status": "started"}
    
    def get_status(self):
        """Get current cache status"""
        status = get_cache_status()
        status["last_update"] = self.last_update_time.isoformat() if self.last_update_time else None
        status["update_in_progress"] = self.update_in_progress
        status["update_interval_hours"] = self.update_interval_hours
        return status


_scheduler = None


def get_scheduler():
    global _scheduler
    if _scheduler is None:
        _scheduler = TLEScheduler()
    return _scheduler


def check_and_run_auto_update():
    """Check and run auto-update if needed"""
    scheduler = get_scheduler()
    if scheduler.is_update_needed() and not scheduler.update_in_progress:
        return scheduler.run_update_async()
    return None


def render_tle_scheduler_ui():
    """Render TLE status in sidebar (admin only)"""
    from admin_auth import is_admin
    
    if not is_admin():
        return
    
    scheduler = get_scheduler()
    status = scheduler.get_status()
    
    st.sidebar.markdown("---")
    st.sidebar.markdown("### 🛰️ TLE Status")
    
    if status['total'] > 0:
        valid_pct = (status['valid'] / status['total'] * 100) if status['total'] > 0 else 0
        st.sidebar.progress(valid_pct / 100, text=f"Cache: {valid_pct:.0f}%")
    
    if status['last_update']:
        last_update = datetime.fromisoformat(status['last_update'])
        hours_ago = (datetime.now() - last_update).total_seconds() / 3600
        st.sidebar.caption(f"Last update: {hours_ago:.1f}h ago")
    
    if st.sidebar.button("🔄 Update TLEs", key="tle_update_btn"):
        with st.spinner("Updating TLEs..."):
            result = scheduler.run_update()
            if result['status'] == 'success':
                st.sidebar.success(f"✅ Updated {result['success_count']} satellites")
            else:
                st.sidebar.error("Update failed")
            st.rerun()


def get_tle_cache_summary():
    """Get human-readable cache summary"""
    scheduler = get_scheduler()
    status = scheduler.get_status()
    
    if status['total'] == 0:
        return "⚠️ No TLE data cached"
    
    valid_pct = (status['valid'] / status['total'] * 100) if status['total'] > 0 else 0
    
    if valid_pct >= 80:
        return f"✅ {status['valid']}/{status['total']} TLEs valid"
    elif valid_pct >= 50:
        return f"⚠️ {status['valid']}/{status['total']} TLEs valid"
    else:
        return f"🔴 {status['valid']}/{status['total']} TLEs valid"
