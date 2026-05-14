"""
Performance metrics tracking (3.26).

Tracks and displays performance metrics for:
- Search time (pass detection duration)
- Render time (map rendering duration)
- TLE fetch time
- API call durations
- Memory usage

Usage:
    from core.performance_metrics import MetricsTracker
    tracker = MetricsTracker()
    with tracker.track("search"):
        # do search
    tracker.display_dashboard()
"""

import time
import logging
from datetime import datetime, timedelta
from collections import defaultdict, deque
from typing import Dict, List, Optional
from statistics import mean, median

import streamlit as st

logger = logging.getLogger(__name__)


class MetricsTracker:
    """
    Tracks performance metrics for application operations.
    Stores metrics in-memory with a configurable retention window.
    """

    def __init__(self, max_entries: int = 1000):
        self.max_entries = max_entries
        self._metrics: Dict[str, deque] = defaultdict(
            lambda: deque(maxlen=max_entries)
        )
        self._active_timers: Dict[str, float] = {}

    def start_timer(self, operation: str):
        """Start a timer for an operation."""
        self._active_timers[operation] = time.time()

    def stop_timer(self, operation: str, metadata: dict = None) -> Optional[float]:
        """
        Stop a timer and record the duration.
        Returns duration in seconds.
        """
        if operation not in self._active_timers:
            logger.warning(f"No active timer for '{operation}'")
            return None

        duration = time.time() - self._active_timers[operation]
        del self._active_timers[operation]

        self.record(operation, duration, metadata)
        return duration

    def record(self, operation: str, duration_s: float, metadata: dict = None):
        """Record a metric entry."""
        entry = {
            "timestamp": datetime.now(),
            "operation": operation,
            "duration_s": round(duration_s, 3),
            "metadata": metadata or {},
        }
        self._metrics[operation].append(entry)

    def get_stats(self, operation: str = None, minutes: int = None) -> Dict:
        """
        Get statistics for one or all operations.
        
        Args:
            operation: Specific operation to query, or None for all
            minutes: Only include entries from last N minutes
        
        Returns:
            Dict with stats per operation
        """
        cutoff = datetime.now() - timedelta(minutes=minutes) if minutes else None

        if operation:
            ops = [operation]
        else:
            ops = list(self._metrics.keys())

        stats = {}
        for op in ops:
            entries = list(self._metrics[op])
            if cutoff:
                entries = [e for e in entries if e["timestamp"] >= cutoff]

            if not entries:
                stats[op] = {"count": 0}
                continue

            durations = [e["duration_s"] for e in entries]
            stats[op] = {
                "count": len(entries),
                "min_s": round(min(durations), 3),
                "max_s": round(max(durations), 3),
                "mean_s": round(mean(durations), 3),
                "median_s": round(median(durations), 3),
                "total_s": round(sum(durations), 3),
                "last_s": round(durations[-1], 3),
            }

        return stats

    def get_recent(self, operation: str = None, limit: int = 10) -> List[Dict]:
        """Get recent metric entries."""
        if operation:
            entries = list(self._metrics[operation])
        else:
            entries = []
            for op_entries in self._metrics.values():
                entries.extend(op_entries)
            entries.sort(key=lambda e: e["timestamp"], reverse=True)

        return entries[:limit]

    def clear(self, operation: str = None):
        """Clear metrics for an operation, or all if None."""
        if operation:
            self._metrics[operation].clear()
        else:
            self._metrics.clear()

    def display_dashboard(self, minutes: int = 60):
        """Display a performance metrics dashboard in Streamlit."""
        st.markdown("### 📊 Performance Metrics")
        st.caption(f"Showing data from the last {minutes} minutes")

        stats = self.get_stats(minutes=minutes)

        if not stats:
            st.info("No metrics recorded yet.")
            return

        # Summary cards
        cols = st.columns(4)
        total_ops = sum(s["count"] for s in stats.values())
        total_time = sum(s["total_s"] for s in stats.values())

        with cols[0]:
            st.metric("Total Operations", total_ops)
        with cols[1]:
            st.metric("Total Time", f"{total_time:.1f}s")
        with cols[2]:
            st.metric("Avg Duration", f"{total_time / max(total_ops, 1):.2f}s")
        with cols[3]:
            st.metric("Operations/min", f"{total_ops / max(minutes, 1):.1f}")

        # Per-operation table
        st.markdown("#### Per-Operation Statistics")
        table_data = []
        for op, s in sorted(stats.items()):
            table_data.append({
                "Operation": op,
                "Count": s["count"],
                "Avg (s)": s["mean_s"],
                "Min (s)": s["min_s"],
                "Max (s)": s["max_s"],
                "Median (s)": s["median_s"],
                "Total (s)": s["total_s"],
            })

        if table_data:
            st.dataframe(table_data, use_container_width=True, hide_index=True)

        # Recent entries
        st.markdown("#### Recent Operations")
        recent = self.get_recent(limit=20)
        if recent:
            recent_data = [{
                "Time": e["timestamp"].strftime("%H:%M:%S"),
                "Operation": e["operation"],
                "Duration (s)": e["duration_s"],
            } for e in recent]
            st.dataframe(recent_data, use_container_width=True, hide_index=True)


# Global tracker instance
_tracker = None


def get_metrics_tracker() -> MetricsTracker:
    """Get or create the global MetricsTracker instance."""
    global _tracker
    if _tracker is None:
        _tracker = MetricsTracker()
    return _tracker


class TimerContext:
    """Context manager for timing operations."""

    def __init__(self, operation: str, tracker: MetricsTracker = None,
                 metadata: dict = None):
        self.operation = operation
        self.tracker = tracker or get_metrics_tracker()
        self.metadata = metadata

    def __enter__(self):
        self.tracker.start_timer(self.operation)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type:
            self.metadata = self.metadata or {}
            self.metadata["error"] = str(exc_val)
        self.tracker.stop_timer(self.operation, self.metadata)
