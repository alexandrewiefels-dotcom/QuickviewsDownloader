"""
Application health check endpoint (3.24).

Provides a simple health check for monitoring/uptime checks.
Can be called via CLI or imported as a module.

Usage:
    python health.py          # Run health check and print results
    from health import check_health
    status = check_health()
"""

import os
import sys
import json
import logging
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


def check_health() -> dict:
    """
    Run a comprehensive health check of the application.
    Returns a dictionary with status information.
    """
    health = {
        "status": "ok",
        "timestamp": datetime.now().isoformat(),
        "checks": {},
    }

    # 1. Python environment
    health["checks"]["python"] = {
        "status": "ok",
        "version": sys.version,
        "executable": sys.executable,
    }

    # 2. Critical directories
    required_dirs = ["config", "data", "logs", "ui", "core", "detection", "geometry", "visualization"]
    missing_dirs = []
    for d in required_dirs:
        if not Path(d).exists():
            missing_dirs.append(d)
    if missing_dirs:
        health["checks"]["directories"] = {
            "status": "error",
            "missing": missing_dirs,
        }
        health["status"] = "degraded"
    else:
        health["checks"]["directories"] = {"status": "ok"}

    # 3. TLE cache
    tle_cache_csv = Path("data/tle_cache.csv")
    tle_cache_db = Path("data/tle_cache.db")
    if tle_cache_db.exists():
        health["checks"]["tle_cache"] = {
            "status": "ok",
            "type": "sqlite",
            "size_kb": round(tle_cache_db.stat().st_size / 1024, 1),
        }
    elif tle_cache_csv.exists():
        health["checks"]["tle_cache"] = {
            "status": "ok",
            "type": "csv",
            "size_kb": round(tle_cache_csv.stat().st_size / 1024, 1),
        }
    else:
        health["checks"]["tle_cache"] = {
            "status": "warning",
            "message": "No TLE cache found (will be created on first run)",
        }

    # 4. Logs directory
    log_files = list(Path("logs").glob("*.jsonl"))
    health["checks"]["logs"] = {
        "status": "ok" if log_files else "warning",
        "count": len(log_files),
        "message": f"{len(log_files)} log files found" if log_files else "No log files yet",
    }

    # 5. Configuration
    config_files = list(Path("config").glob("*.py"))
    health["checks"]["config"] = {
        "status": "ok",
        "files": len(config_files),
    }

    # 6. Environment variables
    env_vars = {
        "ORBITSHOW_ADMIN_USERNAME": bool(os.environ.get("ORBITSHOW_ADMIN_USERNAME")),
        "ORBITSHOW_ADMIN_PASSWORD": bool(os.environ.get("ORBITSHOW_ADMIN_PASSWORD")),
        "SPACETRACK_USERNAME": bool(os.environ.get("SPACETRACK_USERNAME")),
        "SPACETRACK_PASSWORD": bool(os.environ.get("SPACETRACK_PASSWORD")),
        "N2YO_API_KEY": bool(os.environ.get("N2YO_API_KEY")),
        "OWM_API_KEY": bool(os.environ.get("OWM_API_KEY")),
    }
    configured = sum(1 for v in env_vars.values() if v)
    health["checks"]["environment"] = {
        "status": "ok",
        "configured_vars": configured,
        "total_vars": len(env_vars),
        "vars": env_vars,
    }

    # 7. Disk space
    try:
        import shutil
        total, used, free = shutil.disk_usage(".")
        free_gb = free / (1024 ** 3)
        health["checks"]["disk"] = {
            "status": "ok" if free_gb > 0.5 else "warning",
            "free_gb": round(free_gb, 2),
            "message": f"{free_gb:.1f} GB free" if free_gb > 0.5 else "Low disk space",
        }
    except Exception:
        health["checks"]["disk"] = {"status": "unknown"}

    # Overall status
    all_ok = all(
        check.get("status") == "ok" or check.get("status") == "warning"
        for check in health["checks"].values()
    )
    if not all_ok:
        health["status"] = "degraded"

    return health


def print_health():
    """Print health check results in a readable format."""
    health = check_health()
    print(f"\n{'='*50}")
    print(f"  OrbitShow Health Check")
    print(f"  Status: {health['status'].upper()}")
    print(f"  Time: {health['timestamp']}")
    print(f"{'='*50}")
    for name, check in health["checks"].items():
        status_icon = "✅" if check.get("status") == "ok" else "⚠️" if check.get("status") == "warning" else "❌"
        print(f"\n  {status_icon} {name.upper()}: {check.get('status', 'unknown')}")
        for key, value in check.items():
            if key != "status":
                print(f"     {key}: {value}")


if __name__ == "__main__":
    print_health()
