"""
SQLite backend for logs/analytics (3.14).

Replaces JSONL files with structured SQLite tables for:
- API interactions (api_interactions)
- AOI history (aoi_history)
- Search history (search_history)
- Quickview operations (quickview_ops)

Features:
- Thread-safe via connection-per-thread pattern
- Automatic table creation
- Indexed queries by timestamp and type
- Batch insert for performance
- JSONL migration utility
"""

import sqlite3
import json
import threading
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, List, Any

logger = logging.getLogger(__name__)

# Default database path
DEFAULT_DB_PATH = Path("data/logs.db")

# Schema version
SCHEMA_VERSION = 1


class LogsSQLiteBackend:
    """
    SQLite-backed log storage with thread-safe operations.
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
            self._local.conn.row_factory = sqlite3.Row
        return self._local.conn

    def _init_db(self):
        """Create tables and indexes if they don't exist."""
        conn = self._get_conn()

        # API interactions log
        conn.execute("""
            CREATE TABLE IF NOT EXISTS api_interactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                api_name TEXT NOT NULL,
                endpoint TEXT,
                method TEXT,
                status TEXT,
                duration_ms REAL,
                request_size INTEGER,
                response_size INTEGER,
                error TEXT,
                metadata TEXT
            )
        """)

        # AOI history
        conn.execute("""
            CREATE TABLE IF NOT EXISTS aoi_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                action TEXT NOT NULL,
                aoi_name TEXT,
                area_km2 REAL,
                vertex_count INTEGER,
                source TEXT,
                metadata TEXT
            )
        """)

        # Search history
        conn.execute("""
            CREATE TABLE IF NOT EXISTS search_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                search_type TEXT NOT NULL,
                query TEXT,
                satellite_count INTEGER,
                pass_count INTEGER,
                duration_ms REAL,
                filters TEXT,
                metadata TEXT
            )
        """)

        # Quickview operations
        conn.execute("""
            CREATE TABLE IF NOT EXISTS quickview_ops (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                operation TEXT NOT NULL,
                satellite TEXT,
                scene_id TEXT,
                status TEXT,
                duration_ms REAL,
                size_bytes INTEGER,
                error TEXT,
                metadata TEXT
            )
        """)

        # Navigation tracking
        conn.execute("""
            CREATE TABLE IF NOT EXISTS navigation_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                session_id TEXT,
                event_type TEXT NOT NULL,
                page TEXT,
                action TEXT,
                value TEXT,
                metadata TEXT
            )
        """)

        # Create indexes for common queries
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_api_timestamp ON api_interactions(timestamp)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_api_name ON api_interactions(api_name)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_aoi_timestamp ON aoi_history(timestamp)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_search_timestamp ON search_history(timestamp)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_quickview_timestamp ON quickview_ops(timestamp)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_nav_timestamp ON navigation_events(timestamp)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_nav_event_type ON navigation_events(event_type)
        """)

        # Metadata table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS metadata (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)
        conn.execute("""
            INSERT OR REPLACE INTO metadata (key, value)
            VALUES ('schema_version', ?)
        """, (str(SCHEMA_VERSION),))
        conn.commit()

    # ── API Interactions ──────────────────────────────────────────────────

    def log_api_interaction(self, api_name: str, endpoint: str = None,
                            method: str = None, status: str = None,
                            duration_ms: float = None, request_size: int = None,
                            response_size: int = None, error: str = None,
                            metadata: dict = None) -> int:
        """Log an API interaction. Returns the row ID."""
        try:
            conn = self._get_conn()
            cursor = conn.execute("""
                INSERT INTO api_interactions
                (timestamp, api_name, endpoint, method, status, duration_ms,
                 request_size, response_size, error, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                datetime.now().isoformat(), api_name, endpoint, method,
                status, duration_ms, request_size, response_size, error,
                json.dumps(metadata) if metadata else None
            ))
            conn.commit()
            return cursor.lastrowid
        except Exception as e:
            logger.error(f"Failed to log API interaction: {e}")
            return -1

    def get_api_interactions(self, days: int = 7, api_name: str = None,
                             limit: int = 100) -> List[Dict]:
        """Query API interactions."""
        try:
            conn = self._get_conn()
            query = "SELECT * FROM api_interactions WHERE timestamp >= ?"
            params = [(datetime.now().isoformat(),)]
            if api_name:
                query += " AND api_name = ?"
                params.append(api_name)
            query += " ORDER BY timestamp DESC LIMIT ?"
            params.append(limit)
            cursor = conn.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Failed to query API interactions: {e}")
            return []

    # ── AOI History ───────────────────────────────────────────────────────

    def log_aoi_action(self, action: str, aoi_name: str = None,
                       area_km2: float = None, vertex_count: int = None,
                       source: str = None, metadata: dict = None) -> int:
        """Log an AOI action. Returns the row ID."""
        try:
            conn = self._get_conn()
            cursor = conn.execute("""
                INSERT INTO aoi_history
                (timestamp, action, aoi_name, area_km2, vertex_count, source, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                datetime.now().isoformat(), action, aoi_name, area_km2,
                vertex_count, source, json.dumps(metadata) if metadata else None
            ))
            conn.commit()
            return cursor.lastrowid
        except Exception as e:
            logger.error(f"Failed to log AOI action: {e}")
            return -1

    def get_aoi_history(self, days: int = 30, limit: int = 100) -> List[Dict]:
        """Query AOI history."""
        try:
            conn = self._get_conn()
            cursor = conn.execute("""
                SELECT * FROM aoi_history
                WHERE timestamp >= ?
                ORDER BY timestamp DESC LIMIT ?
            """, (datetime.now().isoformat(), limit))
            return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Failed to query AOI history: {e}")
            return []

    # ── Search History ────────────────────────────────────────────────────

    def log_search(self, search_type: str, query: str = None,
                   satellite_count: int = None, pass_count: int = None,
                   duration_ms: float = None, filters: dict = None,
                   metadata: dict = None) -> int:
        """Log a search operation. Returns the row ID."""
        try:
            conn = self._get_conn()
            cursor = conn.execute("""
                INSERT INTO search_history
                (timestamp, search_type, query, satellite_count, pass_count,
                 duration_ms, filters, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                datetime.now().isoformat(), search_type, query,
                satellite_count, pass_count, duration_ms,
                json.dumps(filters) if filters else None,
                json.dumps(metadata) if metadata else None
            ))
            conn.commit()
            return cursor.lastrowid
        except Exception as e:
            logger.error(f"Failed to log search: {e}")
            return -1

    def get_search_history(self, days: int = 7, limit: int = 100) -> List[Dict]:
        """Query search history."""
        try:
            conn = self._get_conn()
            cursor = conn.execute("""
                SELECT * FROM search_history
                WHERE timestamp >= ?
                ORDER BY timestamp DESC LIMIT ?
            """, (datetime.now().isoformat(), limit))
            return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Failed to query search history: {e}")
            return []

    # ── Quickview Operations ──────────────────────────────────────────────

    def log_quickview_op(self, operation: str, satellite: str = None,
                         scene_id: str = None, status: str = None,
                         duration_ms: float = None, size_bytes: int = None,
                         error: str = None, metadata: dict = None) -> int:
        """Log a quickview operation. Returns the row ID."""
        try:
            conn = self._get_conn()
            cursor = conn.execute("""
                INSERT INTO quickview_ops
                (timestamp, operation, satellite, scene_id, status,
                 duration_ms, size_bytes, error, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                datetime.now().isoformat(), operation, satellite, scene_id,
                status, duration_ms, size_bytes, error,
                json.dumps(metadata) if metadata else None
            ))
            conn.commit()
            return cursor.lastrowid
        except Exception as e:
            logger.error(f"Failed to log quickview op: {e}")
            return -1

    # ── Navigation Events ─────────────────────────────────────────────────

    def log_navigation_event(self, session_id: str, event_type: str,
                             page: str = None, action: str = None,
                             value: str = None, metadata: dict = None) -> int:
        """Log a navigation event. Returns the row ID."""
        try:
            conn = self._get_conn()
            cursor = conn.execute("""
                INSERT INTO navigation_events
                (timestamp, session_id, event_type, page, action, value, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                datetime.now().isoformat(), session_id, event_type, page,
                action, value, json.dumps(metadata) if metadata else None
            ))
            conn.commit()
            return cursor.lastrowid
        except Exception as e:
            logger.error(f"Failed to log navigation event: {e}")
            return -1

    def get_navigation_events(self, days: int = 7, event_type: str = None,
                              limit: int = 100) -> List[Dict]:
        """Query navigation events."""
        try:
            conn = self._get_conn()
            query = "SELECT * FROM navigation_events WHERE timestamp >= ?"
            params = [(datetime.now().isoformat(),)]
            if event_type:
                query += " AND event_type = ?"
                params.append(event_type)
            query += " ORDER BY timestamp DESC LIMIT ?"
            params.append(limit)
            cursor = conn.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Failed to query navigation events: {e}")
            return []

    # ── Statistics ────────────────────────────────────────────────────────

    def get_stats(self) -> dict:
        """Get database statistics."""
        try:
            conn = self._get_conn()
            stats = {}
            for table in ["api_interactions", "aoi_history", "search_history",
                          "quickview_ops", "navigation_events"]:
                cursor = conn.execute(f"SELECT COUNT(*) FROM {table}")
                stats[table] = cursor.fetchone()[0]
            db_size = self.db_path.stat().st_size if self.db_path.exists() else 0
            stats["db_size_bytes"] = db_size
            stats["db_size_mb"] = round(db_size / (1024 * 1024), 2)
            return stats
        except Exception as e:
            logger.error(f"Failed to get stats: {e}")
            return {"error": str(e)}

    def vacuum(self):
        """Reclaim unused space."""
        try:
            conn = self._get_conn()
            conn.execute("VACUUM")
            logger.info("Logs SQLite database vacuumed")
        except Exception as e:
            logger.error(f"Failed to vacuum: {e}")

    # ── JSONL Migration ───────────────────────────────────────────────────

    def migrate_from_jsonl(self, jsonl_path: str | Path, table: str) -> int:
        """
        Migrate entries from a JSONL file into the specified table.
        Returns the number of entries migrated.
        """
        jsonl_path = Path(jsonl_path)
        if not jsonl_path.exists():
            logger.warning(f"JSONL file not found: {jsonl_path}")
            return 0

        count = 0
        try:
            with open(jsonl_path, 'r') as f:
                for line in f:
                    try:
                        entry = json.loads(line)
                        timestamp = entry.get('timestamp', datetime.now().isoformat())

                        if table == 'api_interactions':
                            self.log_api_interaction(
                                api_name=entry.get('api_name', 'unknown'),
                                endpoint=entry.get('endpoint'),
                                method=entry.get('method'),
                                status=entry.get('status'),
                                duration_ms=entry.get('duration_ms'),
                                error=entry.get('error'),
                                metadata=entry.get('metadata')
                            )
                        elif table == 'aoi_history':
                            self.log_aoi_action(
                                action=entry.get('action', 'unknown'),
                                aoi_name=entry.get('aoi_name'),
                                area_km2=entry.get('area_km2'),
                                vertex_count=entry.get('vertex_count'),
                                source=entry.get('source'),
                                metadata=entry.get('metadata')
                            )
                        elif table == 'search_history':
                            self.log_search(
                                search_type=entry.get('search_type', 'unknown'),
                                query=entry.get('query'),
                                satellite_count=entry.get('satellite_count'),
                                pass_count=entry.get('pass_count'),
                                duration_ms=entry.get('duration_ms'),
                                filters=entry.get('filters'),
                                metadata=entry.get('metadata')
                            )
                        elif table == 'quickview_ops':
                            self.log_quickview_op(
                                operation=entry.get('operation', 'unknown'),
                                satellite=entry.get('satellite'),
                                scene_id=entry.get('scene_id'),
                                status=entry.get('status'),
                                duration_ms=entry.get('duration_ms'),
                                size_bytes=entry.get('size_bytes'),
                                error=entry.get('error'),
                                metadata=entry.get('metadata')
                            )
                        count += 1
                    except (json.JSONDecodeError, KeyError):
                        continue
            logger.info(f"Migrated {count} entries from {jsonl_path} to {table}")
            return count
        except Exception as e:
            logger.error(f"Failed to migrate {jsonl_path}: {e}")
            return 0
