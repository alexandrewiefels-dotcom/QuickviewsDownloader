"""
Log rotation utility for JSONL log files (3.16).

Automatically rotates and archives log files based on:
- Maximum file size (default: 10 MB)
- Maximum age (default: 7 days)
- Maximum number of archived files (default: 5)

Usage:
    from data.log_rotation import rotate_logs, rotate_logs_if_needed
    rotate_logs_if_needed()  # Call periodically (e.g., at app startup)
"""

import os
import gzip
import shutil
import logging
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)

# Default configuration
DEFAULT_MAX_SIZE_MB = 10
DEFAULT_MAX_AGE_DAYS = 7
DEFAULT_MAX_ARCHIVES = 5

# Log files to monitor (relative to project root)
LOG_FILES = [
    "logs/api_interactions.jsonl",
    "logs/aoi_history.jsonl",
    "logs/search_history.jsonl",
    "logs/quickview_ops.jsonl",
]

# Archive directory
ARCHIVE_DIR = Path("logs/archive")


def get_file_size_mb(path: Path) -> float:
    """Get file size in megabytes."""
    if not path.exists():
        return 0.0
    return path.stat().st_size / (1024 * 1024)


def get_file_age_days(path: Path) -> float:
    """Get file age in days since last modification."""
    if not path.exists():
        return 0.0
    mtime = datetime.fromtimestamp(path.stat().st_mtime)
    return (datetime.now() - mtime).total_seconds() / (24 * 3600)


def compress_file(src: Path, dst: Path) -> bool:
    """Compress a file using gzip. Returns True on success."""
    try:
        with open(src, 'rb') as f_in:
            with gzip.open(str(dst) + '.gz', 'wb') as f_out:
                shutil.copyfileobj(f_in, f_out)
        return True
    except Exception as e:
        logger.error(f"Failed to compress {src}: {e}")
        return False


def rotate_single_file(filepath: Path, max_size_mb: float = DEFAULT_MAX_SIZE_MB,
                       max_age_days: float = DEFAULT_MAX_AGE_DAYS,
                       max_archives: int = DEFAULT_MAX_ARCHIVES) -> bool:
    """
    Rotate a single log file if it exceeds size or age limits.
    
    Returns True if rotation was performed.
    """
    if not filepath.exists():
        return False

    size_mb = get_file_size_mb(filepath)
    age_days = get_file_age_days(filepath)

    # Check if rotation is needed
    if size_mb < max_size_mb and age_days < max_age_days:
        return False

    # Create archive directory
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)

    # Generate archive filename with timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    archive_name = f"{filepath.stem}_{timestamp}.jsonl"
    archive_path = ARCHIVE_DIR / archive_name

    # Compress and archive
    if compress_file(filepath, archive_path):
        # Truncate original file (keep it, but empty)
        with open(filepath, 'w') as f:
            pass
        logger.info(f"Rotated {filepath.name} ({size_mb:.1f} MB, {age_days:.1f} days) -> {archive_name}.gz")

        # Clean up old archives
        _cleanup_old_archives(filepath.stem, max_archives)
        return True

    return False


def _cleanup_old_archives(base_name: str, max_archives: int):
    """Remove oldest archives beyond the retention limit."""
    if not ARCHIVE_DIR.exists():
        return

    archives = sorted(
        [f for f in ARCHIVE_DIR.glob(f"{base_name}_*.jsonl.gz")],
        key=lambda f: f.stat().st_mtime,
    )

    while len(archives) > max_archives:
        oldest = archives.pop(0)
        try:
            oldest.unlink()
            logger.info(f"Removed old archive: {oldest.name}")
        except Exception as e:
            logger.error(f"Failed to remove {oldest}: {e}")


def rotate_logs(max_size_mb: float = DEFAULT_MAX_SIZE_MB,
                max_age_days: float = DEFAULT_MAX_AGE_DAYS,
                max_archives: int = DEFAULT_MAX_ARCHIVES) -> List[str]:
    """
    Rotate all monitored log files.
    
    Returns a list of rotated file names.
    """
    rotated = []
    for log_file in LOG_FILES:
        path = Path(log_file)
        if rotate_single_file(path, max_size_mb, max_age_days, max_archives):
            rotated.append(log_file)
    return rotated


def rotate_logs_if_needed(max_size_mb: float = DEFAULT_MAX_SIZE_MB,
                          max_age_days: float = DEFAULT_MAX_AGE_DAYS,
                          max_archives: int = DEFAULT_MAX_ARCHIVES) -> List[str]:
    """
    Convenience function: rotate logs only if any exceed size/age limits.
    Call this at application startup.
    """
    rotated = []
    for log_file in LOG_FILES:
        path = Path(log_file)
        if not path.exists():
            continue
        size_mb = get_file_size_mb(path)
        age_days = get_file_age_days(path)
        if size_mb >= max_size_mb or age_days >= max_age_days:
            if rotate_single_file(path, max_size_mb, max_age_days, max_archives):
                rotated.append(log_file)
    if rotated:
        logger.info(f"Log rotation completed: {rotated}")
    return rotated


def get_log_stats() -> dict:
    """Get statistics about all monitored log files."""
    stats = {}
    for log_file in LOG_FILES:
        path = Path(log_file)
        archive_dir = ARCHIVE_DIR
        base = path.stem

        # Current file stats
        current_size = get_file_size_mb(path)
        current_age = get_file_age_days(path)

        # Archive stats
        archives = sorted(
            [f for f in archive_dir.glob(f"{base}_*.jsonl.gz")] if archive_dir.exists() else [],
            key=lambda f: f.stat().st_mtime,
        )
        archive_count = len(archives)
        archive_total_size = sum(
            f.stat().st_size for f in archives
        ) / (1024 * 1024) if archives else 0.0

        stats[log_file] = {
            "current_size_mb": round(current_size, 2),
            "current_age_days": round(current_age, 1),
            "archive_count": archive_count,
            "archive_total_size_mb": round(archive_total_size, 2),
            "needs_rotation": current_size >= DEFAULT_MAX_SIZE_MB or current_age >= DEFAULT_MAX_AGE_DAYS,
        }
    return stats
