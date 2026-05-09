# ============================================================================
# FILE: backup_manager.py – Versioned backup system for any project
# UPDATED: Added collision protection, excludes dot-folders, editable project name
# ============================================================================

import os
import re
import shutil
import json
import time
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional
import zipfile


class BackupManager:
    """
    Manages versioned backups of project files, stored outside the project root.
    Excludes all folders starting with a dot (.) and other common exclusions.
    
    PROJECT_NAME: Change this variable to match your project name.
    """
    
    # ================================================================
    # EDIT THIS VARIABLE TO MATCH YOUR PROJECT
    # ================================================================
    PROJECT_NAME = "OrbitShow"  # ← Change this to your project name
    # ================================================================
    
    # Excluded directories (case insensitive for some)
    EXCLUDED_DIRS = [
        # Dot folders (any folder starting with .)
        # Handled dynamically in _should_exclude method
        "venv", "env", "ENV", ".venv",
        "__pycache__",
        "backups",
        ".git",
        ".idea", ".vscode",
        "logs", "tmp", "temp", "node_modules",
        "dist", "build", "egg-info",
        ".pytest_cache", ".mypy_cache", ".coverage",
        ".streamlit/cache",  # Streamlit cache
    ]
    
    EXCLUDED_EXTENSIONS = [
        ".pyc", ".pyo", ".pyd",
        ".so", ".dll", ".dylib",
        ".exe", ".msi", ".bat", ".cmd",
        ".log", ".tmp", ".cache",
        ".db-journal", ".wal", ".shm",  # SQLite temp files
        ".lock", ".pid",
        ".pycache",
    ]
    
    EXCLUDED_FILES = [
        ".DS_Store",
        "Thumbs.db",
        "desktop.ini",
        ".gitignore",
        ".gitattributes",
        ".env",  # Environment variables (sensitive)
        ".secrets.toml",  # Secrets file
    ]
    
    def __init__(self, project_root: str = None):
        """
        Initialize backup manager.
        
        Args:
            project_root: Path to project root. If None, auto-detects from current file.
        """
        if project_root is None:
            # Auto-detect project root (directory containing this script)
            current_file = Path(__file__).resolve()
            
            # Try to find project root by looking for common markers
            markers = ["app.py", "main.py", "requirements.txt", "setup.py"]
            for parent in current_file.parents:
                if any((parent / marker).exists() for marker in markers):
                    self.project_root = parent
                    break
            else:
                self.project_root = current_file.parent
        
        else:
            self.project_root = Path(project_root)
        
        # Backup base directory (parent of project root)
        self.backup_base = self.project_root.parent / f"{self.PROJECT_NAME}_backups"
        self.backup_base.mkdir(exist_ok=True)
        
        # Metadata file
        self.metadata_file = self.backup_base / "backup_metadata.json"
        self._load_metadata()
        
        print(f"📁 Project root: {self.project_root}")
        print(f"📁 Backup base: {self.backup_base}")
    
    def _is_dot_folder(self, path: Path) -> bool:
        """Check if any part of the path starts with a dot (.)"""
        for part in path.parts:
            if part.startswith('.') and len(part) > 1:  # Exclude current dir "."
                return True
        return False
    
    def _get_unique_path(self, base_path: Path) -> Path:
        """
        If base_path exists, appends an incrementing counter until a unique path is found.
        Works for both directories and files.
        """
        if not base_path.exists():
            return base_path
        
        counter = 1
        suffix = base_path.suffix  # .zip or empty for folders
        stem = base_path.stem      # filename without extension
        parent = base_path.parent

        while True:
            new_path = parent / f"{stem}_{counter}{suffix}"
            if not new_path.exists():
                return new_path
            counter += 1
    
    def _sanitize_description(self, description: str) -> str:
        """Sanitize description for use in filenames"""
        if not description:
            return ""
        sanitized = re.sub(r'[^a-zA-Z0-9_\-]', '_', description)
        sanitized = re.sub(r'_+', '_', sanitized)
        return sanitized[:50]
    
    def _should_exclude(self, path: Path) -> bool:
        """
        Determine if a path should be excluded from backup.
        Excludes dot-folders, common excluded directories, and file extensions.
        """
        # Exclude dot folders (any folder starting with .)
        if self._is_dot_folder(path):
            return True
        
        # Check excluded directories
        for excluded in self.EXCLUDED_DIRS:
            if excluded in path.parts:
                return True
        
        # Check excluded file extensions
        if path.is_file():
            for ext in self.EXCLUDED_EXTENSIONS:
                if path.suffix.lower() == ext:
                    return True
            
            # Check excluded filenames
            if path.name in self.EXCLUDED_FILES:
                return True
        
        return False
    
    def _get_all_project_files(self) -> List[Path]:
        """Recursively get all project files, excluding unwanted ones."""
        files = []
        
        for item in self.project_root.rglob("*"):
            # Skip if should be excluded
            if self._should_exclude(item):
                continue
            
            # Skip if item is inside backup directory
            if self.backup_base in item.parents or item == self.backup_base:
                continue
            
            if item.is_file():
                files.append(item)
        
        return files
    
    def _load_metadata(self):
        """Load backup metadata from JSON file."""
        if self.metadata_file.exists():
            try:
                with open(self.metadata_file, 'r', encoding='utf-8') as f:
                    self.metadata = json.load(f)
            except (json.JSONDecodeError, IOError):
                self.metadata = {"backups": [], "current_version": "1.0.0", "last_backup": None}
        else:
            self.metadata = {"backups": [], "current_version": "1.0.0", "last_backup": None}
    
    def _save_metadata(self):
        """Save backup metadata to JSON file."""
        with open(self.metadata_file, 'w', encoding='utf-8') as f:
            json.dump(self.metadata, f, indent=2, default=str)
    
    def _get_next_version(self) -> str:
        """Generate next version number."""
        if not self.metadata["backups"]:
            return "1.0.0"
        
        # Find highest version number
        versions = []
        for backup in self.metadata["backups"]:
            try:
                parts = backup["version"].split('.')
                versions.append(int(parts[-1]))
            except (ValueError, KeyError, IndexError):
                versions.append(0)
        
        if versions:
            next_num = max(versions) + 1
        else:
            next_num = 1
        
        return f"1.0.{next_num}"
    
    def create_backup(self, description: str = "", include_data: bool = True) -> Dict:
        """
        Create a full backup of the project.
        
        Args:
            description: Optional description of the backup
            include_data: Whether to include data files (default True)
        
        Returns:
            Dict with backup information
        """
        version = self._get_next_version()
        timestamp = datetime.now()
        timestamp_str = timestamp.strftime("%Y%m%d_%H%M%S")
        
        desc_suffix = self._sanitize_description(description)
        if desc_suffix:
            backup_name = f"{self.PROJECT_NAME}_backup_v{version}_{desc_suffix}_{timestamp_str}"
        else:
            backup_name = f"{self.PROJECT_NAME}_backup_v{version}_{timestamp_str}"
        
        # Ensure unique backup path
        backup_path = self._get_unique_path(self.backup_base / backup_name)
        backup_path.mkdir(parents=True, exist_ok=True)
        
        print(f"\n📦 Creating backup: {backup_path.name}")
        
        # Copy all project files
        file_count = 0
        for src_file in self._get_all_project_files():
            # Calculate relative path from project root
            rel_path = src_file.relative_to(self.project_root)
            dst_file = backup_path / rel_path
            
            # Create parent directories
            dst_file.parent.mkdir(parents=True, exist_ok=True)
            
            # Copy file
            shutil.copy2(src_file, dst_file)
            file_count += 1
        
        # Create backup info file
        backup_info = {
            "version": version,
            "timestamp": timestamp.isoformat(),
            "description": description,
            "path": str(backup_path),
            "include_data": include_data,
            "file_count": file_count,
            "project_name": self.PROJECT_NAME,
            "project_root": str(self.project_root)
        }
        
        with open(backup_path / "backup_info.json", 'w', encoding='utf-8') as f:
            json.dump(backup_info, f, indent=2, default=str)
        
        # Update metadata
        self.metadata["backups"].append(backup_info)
        self.metadata["last_backup"] = timestamp.isoformat()
        self._save_metadata()
        
        print(f"✅ Backup created: {backup_path.name}")
        print(f"   Version: v{version}")
        print(f"   Files backed up: {file_count}")
        
        return backup_info
    
    def create_zip_backup(self, description: str = "", include_data: bool = True) -> Path:
        """
        Create a compressed zip backup.
        
        Args:
            description: Optional description
            include_data: Whether to include data files
        
        Returns:
            Path to created zip file
        """
        # First create the folder backup
        backup_info = self.create_backup(description, include_data)
        backup_dir = Path(backup_info["path"])
        
        version = backup_info["version"]
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        desc_suffix = self._sanitize_description(description)
        if desc_suffix:
            zip_name = f"{self.PROJECT_NAME}_backup_v{version}_{desc_suffix}_{timestamp}.zip"
        else:
            zip_name = f"{self.PROJECT_NAME}_backup_v{version}_{timestamp}.zip"
        
        # Ensure unique zip filename
        zip_path = self._get_unique_path(backup_dir / zip_name)
        
        print(f"\n📦 Creating zip archive: {zip_path.name}")
        
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for file_path in backup_dir.rglob("*"):
                if file_path.is_file() and file_path != zip_path:
                    arcname = file_path.relative_to(backup_dir)
                    zipf.write(file_path, arcname)
        
        print(f"✅ Zip backup created: {zip_path.name}")
        print(f"   Size: {zip_path.stat().st_size / (1024*1024):.2f} MB")
        
        return zip_path
    
    def list_backups(self) -> List[Dict]:
        """List all available backups."""
        return self.metadata["backups"]
    
    def restore_backup(self, version: str, target_dir: Path = None, dry_run: bool = False) -> bool:
        """
        Restore a backup version.
        
        Args:
            version: Version to restore (e.g., "1.0.5")
            target_dir: Target directory (default: project root)
            dry_run: If True, only show what would be restored
        
        Returns:
            True if successful
        """
        # Find backup info
        backup_info = None
        for b in self.metadata["backups"]:
            if b["version"] == version:
                backup_info = b
                break
        
        if not backup_info:
            print(f"❌ Backup version {version} not found")
            print(f"   Available versions: {[b['version'] for b in self.metadata['backups']]}")
            return False
        
        backup_path = Path(backup_info["path"])
        if not backup_path.exists():
            print(f"❌ Backup directory not found: {backup_path}")
            return False
        
        if target_dir is None:
            target_dir = self.project_root
        
        print(f"\n🔄 Restoring backup v{version}")
        print(f"   From: {backup_path}")
        print(f"   To: {target_dir}")
        
        if dry_run:
            print("\n📋 Files that would be restored:")
            for item in backup_path.rglob("*"):
                if item.is_file() and item.name != "backup_info.json":
                    rel = item.relative_to(backup_path)
                    print(f"   - {rel}")
            print(f"\n   Total: {backup_info['file_count']} files")
            return True
        
        # Create a pre-restore backup for safety
        pre_restore_backup = self.create_backup(f"Pre-restore before restoring v{version}")
        print(f"📦 Created safety backup: v{pre_restore_backup['version']}")
        
        # Restore files
        restored_count = 0
        for item in backup_path.iterdir():
            if item.name == "backup_info.json":
                continue
            
            dst = target_dir / item.name
            if item.is_dir():
                if dst.exists():
                    shutil.rmtree(dst)
                shutil.copytree(item, dst, ignore_dangling_symlinks=True)
            else:
                shutil.copy2(item, dst)
            restored_count += 1
        
        print(f"✅ Restored version {version} ({restored_count} items)")
        return True
    
    def cleanup_old_backups(self, keep_count: int = 10) -> int:
        """
        Delete old backups, keeping only the most recent N.
        
        Args:
            keep_count: Number of backups to keep
        
        Returns:
            Number of backups deleted
        """
        if len(self.metadata["backups"]) <= keep_count:
            print(f"ℹ️ Only {len(self.metadata['backups'])} backups, nothing to clean (keep={keep_count})")
            return 0
        
        to_delete = self.metadata["backups"][:-keep_count]
        deleted_count = 0
        
        for backup in to_delete:
            backup_path = Path(backup["path"])
            if backup_path.exists():
                shutil.rmtree(backup_path)
                deleted_count += 1
                print(f"🗑️ Deleted old backup: v{backup['version']} ({backup['timestamp'][:19]})")
        
        # Keep only the most recent backups
        self.metadata["backups"] = self.metadata["backups"][-keep_count:]
        self._save_metadata()
        
        print(f"✅ Cleanup complete. Kept {keep_count} backups, deleted {deleted_count}")
        return deleted_count
    
    def get_backup_size(self, version: str = None) -> float:
        """Get size of backup(s) in MB."""
        if version:
            for backup in self.metadata["backups"]:
                if backup["version"] == version:
                    backup_path = Path(backup["path"])
                    if backup_path.exists():
                        total_size = sum(f.stat().st_size for f in backup_path.rglob("*") if f.is_file())
                        return total_size / (1024 * 1024)
                    return 0
            return 0
        else:
            total_size = 0
            for backup in self.metadata["backups"]:
                backup_path = Path(backup["path"])
                if backup_path.exists():
                    total_size += sum(f.stat().st_size for f in backup_path.rglob("*") if f.is_file())
            return total_size / (1024 * 1024)
    
    def export_manifest(self, version: str = None) -> Dict:
        """Export detailed manifest of backed up files."""
        if version:
            backups = [b for b in self.metadata["backups"] if b["version"] == version]
        else:
            backups = self.metadata["backups"]
        
        manifest = {
            "exported_at": datetime.now().isoformat(),
            "project_name": self.PROJECT_NAME,
            "backups": []
        }
        
        for backup in backups:
            backup_path = Path(backup["path"])
            if not backup_path.exists():
                continue
            
            files = []
            for file_path in backup_path.rglob("*"):
                if file_path.is_file() and file_path.name != "backup_info.json":
                    rel = file_path.relative_to(backup_path)
                    files.append({
                        "path": str(rel),
                        "size_bytes": file_path.stat().st_size,
                        "modified": datetime.fromtimestamp(file_path.stat().st_mtime).isoformat()
                    })
            
            manifest["backups"].append({
                "version": backup["version"],
                "timestamp": backup["timestamp"],
                "description": backup["description"],
                "file_count": len(files),
                "total_size_mb": sum(f["size_bytes"] for f in files) / (1024 * 1024),
                "files": files
            })
        
        return manifest


def main():
    """CLI interface for backup management."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description=f"{BackupManager.PROJECT_NAME} - Backup Manager",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python backup_manager.py --create
  python backup_manager.py --create --description "Before major update"
  python backup_manager.py --create-zip --description "Release v2.0"
  python backup_manager.py --list
  python backup_manager.py --restore 1.0.5
  python backup_manager.py --restore 1.0.5 --dry-run
  python backup_manager.py --cleanup --keep 5
  python backup_manager.py --size
        """
    )
    
    parser.add_argument("--create", "-c", action="store_true", help="Create a new backup folder")
    parser.add_argument("--create-zip", "-z", action="store_true", help="Create a zip backup inside the backup folder")
    parser.add_argument("--list", "-l", action="store_true", help="List all backups")
    parser.add_argument("--restore", "-r", type=str, help="Restore a specific version")
    parser.add_argument("--dry-run", action="store_true", help="Preview restore without copying files")
    parser.add_argument("--cleanup", action="store_true", help="Clean old backups")
    parser.add_argument("--keep", type=int, default=10, help="Number of backups to keep (default: 10)")
    parser.add_argument("--description", "-d", type=str, default="", help="Backup description")
    parser.add_argument("--no-data", action="store_true", help="Exclude data files from backup")
    parser.add_argument("--size", "-s", action="store_true", help="Show backup sizes")
    parser.add_argument("--manifest", "-m", type=str, help="Export manifest to JSON file")
    
    args = parser.parse_args()
    
    manager = BackupManager()
    
    if args.create:
        manager.create_backup(args.description, not args.no_data)
    
    elif args.create_zip:
        manager.create_zip_backup(args.description, not args.no_data)
    
    elif args.list:
        backups = manager.list_backups()
        if not backups:
            print("\n📦 No backups found.")
        else:
            print("\n📦 Available Backups:")
            print("-" * 90)
            for b in backups:
                size = manager.get_backup_size(b["version"])
                print(f"  v{b['version']:<8} | {b['timestamp'][:19]} | {b['description'] or 'No description':<30} | {b['file_count']:>6} files | {size:.2f} MB")
    
    elif args.restore:
        manager.restore_backup(args.restore, dry_run=args.dry_run)
    
    elif args.cleanup:
        manager.cleanup_old_backups(args.keep)
    
    elif args.size:
        total_size = manager.get_backup_size()
        print(f"\n📊 Backup Statistics for {BackupManager.PROJECT_NAME}:")
        print(f"   Total backups: {len(manager.list_backups())}")
        print(f"   Total size: {total_size:.2f} MB")
        print(f"   Backup location: {manager.backup_base}")
    
    elif args.manifest:
        manifest = manager.export_manifest()
        with open(args.manifest, 'w', encoding='utf-8') as f:
            json.dump(manifest, f, indent=2, default=str)
        print(f"✅ Manifest exported to: {args.manifest}")
    
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
