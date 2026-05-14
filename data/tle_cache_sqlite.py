"""
SQLite backend for TLE cache (3.13).

Provides an alternative to the CSV-based cache with:
- ACID transactions (safe concurrent writes)
- Indexed lookups by NORAD
- Automatic vacuuming
- Migration from CSV to SQLite

Usage:
    from data.tle_cache_sqlite import SQLiteTLECache
    cache = SQLiteTLECache("data/tle_cache.db")
    cache.store(40118, ("line1...", "line2..."))
    tle = cache.fetch(40118)
"""

import sqlite3
import json
import threading
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple, Dict, List

logger = logging.getLogger(__name__)

# Default database path
DEFAULT_DB_PATH = Path("data/tle_cache.db")

# Schema version for migration tracking
SCHEMA_VERSION = 1


class SQLiteTLECache:
    """
    SQLite-backed TLE cache with thread-safe operations.
    
    Features:
    - Thread-safe via connection-per-thread pattern
    - Automatic table creation and migration
    - Indexed lookups by NORAD ID
    - Metadata tracking (source, epoch, last_updated)
    """

    def __init__(self, db_path: str | Path = None):
        self.db_path = Path(db_path or DEFAULT_DB_PATH)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._local = threading.local()
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        """Get a thread-local database connection."""
        if not hasattr(self._local, 'conn') or self._local.conn is None:
            self._local.conn = sqlite3.connect(str(self.db_path))
            self._local.conn.execute("PRAGMA journal_mode=WAL")
            self._local.conn.execute("PRAGMA synchronous=NORMAL")
        return self._local.conn

    def _init_db(self):
        """Create tables and indexes if they don't exist."""
        conn = self._get_conn()
        conn.execute("""
            CREATE TABLE IF NOT EXISTS tle_cache (
                norad INTEGER PRIMARY KEY,
                line1 TEXT NOT NULL,
                line2 TEXT NOT NULL,
                source TEXT DEFAULT 'unknown',
                epoch TEXT DEFAULT '',
                last_updated TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS metadata (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)
        # Set schema version
        conn.execute("""
            INSERT OR REPLACE INTO metadata (key, value)
            VALUES ('schema_version', ?)
        """, (str(SCHEMA_VERSION),))
        conn.commit()

    def store(self, norad: int, tle: Tuple[str, str], source: str = "unknown",
              epoch: str = "") -> bool:
        """Store a TLE entry. Returns True on success."""
        try:
            line1, line2 = tle
            conn = self._get_conn()
            conn.execute("""
                INSERT OR REPLACE INTO tle_cache (norad, line1, line2, source, epoch, last_updated)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (norad, line1, line2, source, epoch, datetime.now().isoformat()))
            conn.commit()
            return True
        except Exception as e:
            logger.error(f"SQLite store failed for NORAD {norad}: {e}")
            return False

    def store_batch(self, tles: Dict[int, Tuple[str, str]], source: str = "unknown") -> int:
        """Store multiple TLEs in a single transaction. Returns count stored."""
        if not tles:
            return 0
        try:
            conn = self._get_conn()
            now = datetime.now().isoformat()
            data = [
                (norad, line1, line2, source, "", now)
                for norad, (line1, line2) in tles.items()
            ]
            conn.executemany("""
                INSERT OR REPLACE INTO tle_cache (norad, line1, line2, source, epoch, last_updated)
                VALUES (?, ?, ?, ?, ?, ?)
            """, data)
            conn.commit()
            return len(data)
        except Exception as e:
            logger.error(f"SQLite batch store failed: {e}")
            return 0

    def fetch(self, norad: int) -> Optional[Tuple[str, str]]:
        """Fetch a TLE by NORAD. Returns None if not found."""
        try:
            conn = self._get_conn()
            cursor = conn.execute(
                "SELECT line1, line2 FROM tle_cache WHERE norad = ?", (norad,)
            )
            row = cursor.fetchone()
            if row:
                return (row[0], row[1])
            return None
        except Exception as e:
            logger.error(f"SQLite fetch failed for NORAD {norad}: {e}")
            return None

    def fetch_all(self) -> Dict[int, Tuple[str, str]]:
        """Fetch all TLEs from the cache."""
        try:
            conn = self._get_conn()
            cursor = conn.execute("SELECT norad, line1, line2 FROM tle_cache")
            return {row[0]: (row[1], row[2]) for row in cursor.fetchall()}
        except Exception as e:
            logger.error(f"SQLite fetch_all failed: {e}")
            return {}

    def delete(self, norad: int) -> bool:
        """Delete a TLE entry. Returns True if deleted."""
        try:
            conn = self._get_conn()
            cursor = conn.execute("DELETE FROM tle_cache WHERE norad = ?", (norad,))
            conn.commit()
            return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"SQLite delete failed for NORAD {norad}: {e}")
            return False

    def clear(self) -> bool:
        """Clear all TLE entries. Returns True on success."""
        try:
            conn = self._get_conn()
            conn.execute("DELETE FROM tle_cache")
            conn.commit()
            return True
        except Exception as e:
            logger.error(f"SQLite clear failed: {e}")
            return False

    def count(self) -> int:
        """Return the number of cached TLEs."""
        try:
            conn = self._get_conn()
            cursor = conn.execute("SELECT COUNT(*) FROM tle_cache")
            return cursor.fetchone()[0]
        except Exception as e:
            logger.error(f"SQLite count failed: {e}")
            return 0

    def vacuum(self):
        """Reclaim unused space. Call periodically (e.g., after large deletes)."""
        try:
            conn = self._get_conn()
            conn.execute("VACUUM")
            logger.info("SQLite cache vacuumed")
        except Exception as e:
            logger.error(f"SQLite vacuum failed: {e}")

    def get_stats(self) -> dict:
        """Get cache statistics."""
        try:
            conn = self._get_conn()
            total = self.count()
            cursor = conn.execute("SELECT MIN(last_updated), MAX(last_updated) FROM tle_cache")
            min_date, max_date = cursor.fetchone()
            db_size = self.db_path.stat().st_size if self.db_path.exists() else 0
            return {
                "total_entries": total,
                "oldest_entry": min_date,
                "newest_entry": max_date,
                "db_size_bytes": db_size,
                "db_size_mb": round(db_size / (1024 * 1024), 2),
                "schema_version": SCHEMA_VERSION,
            }
        except Exception as e:
            logger.error(f"SQLite stats failed: {e}")
            return {"error": str(e)}

    def migrate_from_csv(self, csv_path: str | Path) -> int:
        """
        Migrate TLEs from a CSV cache file into SQLite.
        Returns the number of entries migrated.
        """
        import pandas as pd
        csv_path = Path(csv_path)
        if not csv_path.exists():
            logger.warning(f"CSV file not found: {csv_path}")
            return 0
        try:
            df = pd.read_csv(csv_path)
            if df.empty or 'norad' not in df.columns:
                return 0
            tles = {}
            for _, row in df.iterrows():
                try:
                    norad = int(row['norad'])
                    line1 = row['line1']
                    line2 = row['line2']
                    if line1 and line2 and len(line1) >= 69 and len(line2) >= 69:
                        tles[norad] = (line1, line2)
                except (ValueError, KeyError):
                    continue
            count = self.store_batch(tles, source="csv_migration")
            logger.info(f"Migrated {count} TLEs from {csv_path} to SQLite")
            return count
        except Exception as e:
            logger.error(f"CSV migration failed: {e}")
            return 0
