# ============================================================================
# FILE: backup_manager.py – Versioned backup system for any project
# ============================================================================

import hashlib
import json
import re
import shutil
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional


class BackupManager:
    """
    Manages versioned folder and ZIP backups stored in a sibling directory.

    - Folder backups  : ../ProjectName_backups/ProjectName_backup_vN_TIMESTAMP/
    - ZIP backups     : ../ProjectName_backups/ProjectName_backup_vN_TIMESTAMP.zip
      (no intermediate folder copy — ZIPs write directly from source files)
    - SHA-256 checksums stored and verified at restore time
    - Relative paths in metadata so the backup folder is portable
    """

    EXCLUDED_DIRS: set = {
        "venv", "env", "ENV", ".venv",
        "__pycache__",
        ".git", ".hg", ".svn",
        ".idea", ".vscode",
        ".pytest_cache", ".mypy_cache",
        "node_modules", "dist", "build",
        "logs", "tmp", "temp",
    }

    EXCLUDED_EXTENSIONS: set = {
        ".pyc", ".pyo", ".pyd",
        ".so", ".dll", ".dylib",
        ".exe", ".msi",
        ".log", ".tmp", ".cache",
        ".db-journal", ".wal", ".shm",
        ".lock", ".pid",
    }

    EXCLUDED_FILES: set = {
        ".DS_Store", "Thumbs.db", "desktop.ini",
        ".gitignore", ".gitattributes",
        ".env", "secrets.toml",
    }

    def __init__(self, project_root: str = None, project_name: str = None):
        """
        Args:
            project_root:  Path to project root. Auto-detected from this script's
                           location if omitted.
            project_name:  Name used in backup folder/file names. Defaults to the
                           project root directory's name.
        """
        if project_root is None:
            current = Path(__file__).resolve()
            markers = {"main.py", "app.py", "requirements.txt", "setup.py", "pyproject.toml"}
            for parent in current.parents:
                if any((parent / m).exists() for m in markers):
                    self.project_root = parent
                    break
            else:
                self.project_root = current.parent
        else:
            self.project_root = Path(project_root).resolve()

        self.project_name = project_name or self.project_root.name

        self.backup_base = self.project_root.parent / f"{self.project_name}_backups"
        self.backup_base.mkdir(exist_ok=True)

        self.metadata_file = self.backup_base / "backup_metadata.json"
        self._load_metadata()

        print(f"📁 Project : {self.project_root}")
        print(f"📁 Backups : {self.backup_base}")

    # ── Exclusion ─────────────────────────────────────────────────────────────

    def _should_exclude(self, path: Path) -> bool:
        try:
            rel = path.relative_to(self.project_root)
        except ValueError:
            return False

        for part in rel.parts:
            if part.startswith("."):
                return True
            if part in self.EXCLUDED_DIRS:
                return True

        if path.is_file():
            if path.suffix.lower() in self.EXCLUDED_EXTENSIONS:
                return True
            if path.name in self.EXCLUDED_FILES:
                return True

        return False

    def _project_files(self) -> List[Path]:
        files = []
        for item in self.project_root.rglob("*"):
            if not item.is_file():
                continue
            if self._should_exclude(item):
                continue
            try:
                if self.backup_base in item.parents:
                    continue
            except Exception:
                continue
            files.append(item)
        return sorted(files)

    # ── Checksums ─────────────────────────────────────────────────────────────

    @staticmethod
    def _sha256(path: Path) -> str:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()

    def _build_checksums(self, files: List[Path]) -> Dict[str, str]:
        return {
            str(f.relative_to(self.project_root)): self._sha256(f)
            for f in files
        }

    def _verify_checksums(self, backup_path: Path, checksums: Dict[str, str]) -> List[str]:
        """Return list of failure descriptions (empty = all OK)."""
        failures = []
        for rel_str, expected in checksums.items():
            dst = backup_path / rel_str
            if not dst.exists():
                failures.append(f"MISSING  {rel_str}")
            elif self._sha256(dst) != expected:
                failures.append(f"CORRUPT  {rel_str}")
        return failures

    # ── Metadata ──────────────────────────────────────────────────────────────

    def _load_metadata(self):
        if self.metadata_file.exists():
            try:
                with open(self.metadata_file, encoding="utf-8") as f:
                    self.metadata = json.load(f)
                self._migrate_metadata()
                return
            except (json.JSONDecodeError, IOError):
                pass
        self.metadata = {"backups": [], "last_backup": None}

    def _migrate_metadata(self):
        """Upgrade entries written by the old format to the new schema."""
        for b in self.metadata.get("backups", []):
            # Old format stored absolute "path"; new format stores "rel_path"
            if "path" in b and "rel_path" not in b:
                b["rel_path"] = Path(b["path"]).name
            # Old format used "1.0.X" version strings; new format uses int
            if isinstance(b.get("version"), str) and "." in str(b["version"]):
                try:
                    b["version"] = int(b["version"].split(".")[-1])
                except (ValueError, IndexError):
                    pass

    def _save_metadata(self):
        with open(self.metadata_file, "w", encoding="utf-8") as f:
            json.dump(self.metadata, f, indent=2, default=str)

    def _next_version(self) -> int:
        if not self.metadata["backups"]:
            return 1
        nums = []
        for b in self.metadata["backups"]:
            try:
                nums.append(int(b["version"]))
            except (ValueError, KeyError, TypeError):
                nums.append(0)
        return max(nums) + 1

    def _resolve_version(self, version_arg: str) -> Optional[int]:
        """Parse a version argument; handle both "5" and legacy "1.0.5"."""
        s = str(version_arg)
        if "." in s:
            try:
                return int(s.split(".")[-1])
            except ValueError:
                pass
        try:
            return int(s)
        except ValueError:
            return None

    # ── Name helpers ──────────────────────────────────────────────────────────

    @staticmethod
    def _sanitize(text: str, maxlen: int = 40) -> str:
        s = re.sub(r"[^a-zA-Z0-9_\-]", "_", text)
        s = re.sub(r"_+", "_", s).strip("_")
        return s[:maxlen]

    def _unique_path(self, path: Path) -> Path:
        if not path.exists():
            return path
        stem, suffix, parent = path.stem, path.suffix, path.parent
        for i in range(1, 9999):
            candidate = parent / f"{stem}_{i}{suffix}"
            if not candidate.exists():
                return candidate
        raise RuntimeError(f"Cannot find unique path for {path}")

    def _make_name(self, version: int, description: str, ext: str = "") -> str:
        parts = [self.project_name, "backup", f"v{version}"]
        desc_sfx = self._sanitize(description) if description else ""
        if desc_sfx:
            parts.append(desc_sfx)
        parts.append(datetime.now().strftime("%Y%m%d_%H%M%S"))
        return "_".join(parts) + ext

    # ── Public API ────────────────────────────────────────────────────────────

    def create_backup(self, description: str = "") -> Dict:
        """
        Create a versioned folder backup. Returns the backup info dict.
        Checksums are computed and verified after copying.
        """
        version     = self._next_version()
        ts          = datetime.now()
        backup_path = self._unique_path(self.backup_base / self._make_name(version, description))
        backup_path.mkdir(parents=True)

        print(f"\n📦 Creating folder backup v{version}: {backup_path.name}")

        src_files, checksums, file_count, copy_errors = self._project_files(), {}, 0, []

        for src in src_files:
            rel = src.relative_to(self.project_root)
            dst = backup_path / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            try:
                shutil.copy2(src, dst)
                checksums[str(rel)] = self._sha256(dst)
                file_count += 1
                if file_count % 25 == 0:
                    print(f"   … {file_count}/{len(src_files)} files")
            except OSError as exc:
                copy_errors.append(f"{rel}: {exc}")

        failures = self._verify_checksums(backup_path, checksums)

        if copy_errors:
            print(f"   ⚠ {len(copy_errors)} copy error(s):")
            for e in copy_errors:
                print(f"     {e}")
        if failures:
            print(f"   ⚠ {len(failures)} integrity failure(s):")
            for f in failures[:5]:
                print(f"     {f}")

        info = {
            "version":      version,
            "timestamp":    ts.isoformat(),
            "description":  description,
            "rel_path":     backup_path.name,
            "file_count":   file_count,
            "copy_errors":  len(copy_errors),
            "integrity_ok": len(failures) == 0,
            "project_name": self.project_name,
            "checksums":    checksums,
        }

        with open(backup_path / "backup_info.json", "w", encoding="utf-8") as f:
            json.dump(info, f, indent=2)

        # Metadata omits checksums (kept only inside the backup folder)
        meta_entry = {k: v for k, v in info.items() if k != "checksums"}
        self.metadata["backups"].append(meta_entry)
        self.metadata["last_backup"] = ts.isoformat()
        self._save_metadata()

        print(f"✅ Backup v{version} — {file_count} files, integrity {'OK' if not failures else 'WARN'}")
        return info

    def create_zip_backup(self, description: str = "") -> Path:
        """
        Create a compressed ZIP backup written directly to backup_base.
        No intermediate folder copy — avoids double disk usage.
        Checksums of source files are stored inside the ZIP.
        Returns path to the ZIP file.
        """
        version  = self._next_version()
        ts       = datetime.now()
        zip_path = self._unique_path(self.backup_base / self._make_name(version, description, ".zip"))

        print(f"\n📦 Creating ZIP backup v{version}: {zip_path.name}")

        src_files, checksums, file_count, copy_errors = self._project_files(), {}, 0, []

        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
            for src in src_files:
                rel = src.relative_to(self.project_root)
                try:
                    zf.write(src, arcname=rel)
                    checksums[str(rel)] = self._sha256(src)
                    file_count += 1
                    if file_count % 25 == 0:
                        print(f"   … {file_count}/{len(src_files)} files")
                except OSError as exc:
                    copy_errors.append(f"{rel}: {exc}")

            info = {
                "version":      version,
                "timestamp":    ts.isoformat(),
                "description":  description,
                "file_count":   file_count,
                "copy_errors":  len(copy_errors),
                "project_name": self.project_name,
                "checksums":    checksums,
            }
            zf.writestr("backup_info.json", json.dumps(info, indent=2))

        size_mb = zip_path.stat().st_size / (1024 * 1024)

        if copy_errors:
            print(f"   ⚠ {len(copy_errors)} file(s) skipped:")
            for e in copy_errors:
                print(f"     {e}")

        self.metadata["backups"].append({
            "version":      version,
            "timestamp":    ts.isoformat(),
            "description":  description,
            "rel_path":     zip_path.name,
            "file_count":   file_count,
            "copy_errors":  len(copy_errors),
            "zip":          True,
        })
        self.metadata["last_backup"] = ts.isoformat()
        self._save_metadata()

        print(f"✅ ZIP backup v{version} — {file_count} files, {size_mb:.2f} MB")
        return zip_path

    def list_backups(self) -> List[Dict]:
        return self.metadata["backups"]

    def restore_backup(
        self,
        version,
        target_dir: Path = None,
        dry_run: bool = False,
    ) -> bool:
        """
        Restore a folder backup file-by-file.

        Steps:
          1. Verify stored checksums against the backup copy.
          2. Report stale files (in project now, absent from backup).
          3. In dry_run mode: print what would change, return True.
          4. Create a safety backup of the current state.
          5. Copy every file from backup to project.

        ZIP backups cannot be restored directly — unzip them first.
        """
        resolved = self._resolve_version(str(version))
        backup_info = next(
            (b for b in self.metadata["backups"] if b["version"] == resolved),
            None,
        )
        if not backup_info:
            available = [b["version"] for b in self.metadata["backups"]]
            print(f"❌ Version {version!r} not found. Available: {available}")
            return False

        if backup_info.get("zip"):
            print("❌ Cannot restore from a ZIP backup directly — unzip it first.")
            return False

        backup_path = self.backup_base / backup_info["rel_path"]
        if not backup_path.exists():
            print(f"❌ Backup directory missing: {backup_path}")
            return False

        target_dir = Path(target_dir).resolve() if target_dir else self.project_root

        # Load checksums from the backup's info file
        checksums: Dict[str, str] = {}
        info_file = backup_path / "backup_info.json"
        if info_file.exists():
            try:
                with open(info_file, encoding="utf-8") as f:
                    stored = json.load(f)
                checksums = stored.get("checksums", {})
            except Exception:
                pass

        backup_files = sorted(
            f for f in backup_path.rglob("*")
            if f.is_file() and f.name != "backup_info.json"
        )

        print(f"\n🔄 Restore v{resolved}")
        print(f"   From : {backup_path.name}")
        print(f"   To   : {target_dir}")
        print(f"   Files: {len(backup_files)}")

        # Integrity check
        if checksums:
            failures = self._verify_checksums(backup_path, checksums)
            if failures:
                print(f"\n❌ Integrity check failed ({len(failures)} file(s)) — restore aborted:")
                for line in failures[:10]:
                    print(f"     {line}")
                return False
            print(f"   ✓ Integrity OK ({len(checksums)} files verified)")

        # Stale file report
        if checksums:
            stale = [
                str(pf.relative_to(self.project_root))
                for pf in self._project_files()
                if str(pf.relative_to(self.project_root)) not in checksums
            ]
            if stale:
                print(f"\n   ⚠ {len(stale)} project file(s) not in this backup (will be left as-is):")
                for s in stale[:15]:
                    print(f"     + {s}")
                if len(stale) > 15:
                    print(f"     … and {len(stale) - 15} more")

        if dry_run:
            print("\n📋 Dry-run — files that would be restored:")
            for bf in backup_files:
                rel    = bf.relative_to(backup_path)
                dst    = target_dir / rel
                status = "UPDATE" if dst.exists() else "NEW   "
                print(f"   {status}  {rel}")
            return True

        # Safety backup first
        safety = self.create_backup(f"pre-restore_before_v{resolved}")
        print(f"📦 Safety backup created: v{safety['version']}")

        # File-by-file restore
        ok = fail = 0
        for bf in backup_files:
            rel = bf.relative_to(backup_path)
            dst = target_dir / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            try:
                shutil.copy2(bf, dst)
                ok += 1
            except OSError as exc:
                print(f"   ✗ {rel}: {exc}")
                fail += 1

        print(f"✅ Restored v{resolved}: {ok} files OK, {fail} failed")
        return fail == 0

    def cleanup_old_backups(self, keep_count: int = 10) -> int:
        """Delete old backups, keeping the most recent keep_count."""
        total = len(self.metadata["backups"])
        if total <= keep_count:
            print(f"ℹ️  {total} backup(s) — nothing to delete (keep={keep_count})")
            return 0

        to_delete = self.metadata["backups"][:-keep_count]
        deleted = 0
        for b in to_delete:
            p = self.backup_base / b["rel_path"]
            try:
                if p.is_dir():
                    shutil.rmtree(p)
                elif p.is_file():
                    p.unlink()
                deleted += 1
                print(f"🗑️  Deleted v{b['version']} ({b['timestamp'][:19]})")
            except OSError as exc:
                print(f"   ✗ Could not delete v{b['version']}: {exc}")

        self.metadata["backups"] = self.metadata["backups"][-keep_count:]
        self._save_metadata()
        print(f"✅ Cleanup done: kept {keep_count}, deleted {deleted}")
        return deleted

    def get_backup_size(self, version=None) -> float:
        """Return size in MB for one version or all backups combined."""
        def _size(rel: str) -> float:
            p = self.backup_base / rel
            if not p.exists():
                return 0.0
            if p.is_file():
                return p.stat().st_size / (1024 * 1024)
            return sum(f.stat().st_size for f in p.rglob("*") if f.is_file()) / (1024 * 1024)

        if version is not None:
            resolved = self._resolve_version(str(version))
            b = next((x for x in self.metadata["backups"] if x["version"] == resolved), None)
            return _size(b["rel_path"]) if b else 0.0

        return sum(_size(b["rel_path"]) for b in self.metadata["backups"])

    def export_manifest(self, version=None) -> Dict:
        """Return a detailed manifest dict (pass to json.dump if needed)."""
        target_backups = (
            [b for b in self.metadata["backups"]
             if b["version"] == self._resolve_version(str(version))]
            if version else self.metadata["backups"]
        )
        result: Dict = {
            "exported_at":  datetime.now().isoformat(),
            "project_name": self.project_name,
            "backups":      [],
        }
        for b in target_backups:
            p = self.backup_base / b["rel_path"]
            if not p.exists():
                continue
            candidates = p.rglob("*") if p.is_dir() else []
            files = []
            for fp in candidates:
                if fp.is_file() and fp.name != "backup_info.json":
                    rel = fp.relative_to(p)
                    files.append({
                        "path":       str(rel),
                        "size_bytes": fp.stat().st_size,
                        "modified":   datetime.fromtimestamp(fp.stat().st_mtime).isoformat(),
                    })
            result["backups"].append({
                "version":       b["version"],
                "timestamp":     b["timestamp"],
                "description":   b.get("description", ""),
                "zip":           b.get("zip", False),
                "file_count":    len(files),
                "total_size_mb": sum(f["size_bytes"] for f in files) / (1024 * 1024),
                "files":         files,
            })
        return result


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Versioned project backup manager",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python backup_manager.py --create
  python backup_manager.py --create --description "Before major update"
  python backup_manager.py --create-zip --description "Release v2.0"
  python backup_manager.py --list
  python backup_manager.py --restore 5
  python backup_manager.py --restore 5 --dry-run
  python backup_manager.py --cleanup --keep 5
  python backup_manager.py --size
  python backup_manager.py --manifest backup_manifest.json
        """,
    )

    parser.add_argument("--create",      "-c", action="store_true", help="Create a folder backup")
    parser.add_argument("--create-zip",  "-z", action="store_true", help="Create a ZIP backup")
    parser.add_argument("--list",        "-l", action="store_true", help="List all backups")
    parser.add_argument("--restore",     "-r", type=str,            help="Restore version N")
    parser.add_argument("--dry-run",           action="store_true", help="Preview restore, no changes")
    parser.add_argument("--cleanup",           action="store_true", help="Delete old backups")
    parser.add_argument("--keep",              type=int, default=10, help="Backups to keep (default: 10)")
    parser.add_argument("--description", "-d", type=str, default="", help="Backup description")
    parser.add_argument("--size",        "-s", action="store_true", help="Show total backup size")
    parser.add_argument("--manifest",    "-m", type=str,            help="Export manifest to JSON file")
    parser.add_argument("--name",              type=str, default=None,
                        help="Override project name (default: auto-detected)")

    args = parser.parse_args()
    manager = BackupManager(project_name=args.name)

    if args.create:
        manager.create_backup(args.description)

    elif args.create_zip:
        manager.create_zip_backup(args.description)

    elif args.list:
        backups = manager.list_backups()
        if not backups:
            print("\n📦 No backups found.")
        else:
            print(f"\n{'Ver':<5} {'Timestamp':<20} {'Description':<32} {'Files':>6} {'Size MB':>8}  Type")
            print("-" * 82)
            for b in backups:
                size = manager.get_backup_size(b["version"])
                kind = "ZIP" if b.get("zip") else "dir"
                desc = (b.get("description") or "")[:31]
                print(
                    f"  {b['version']:<3}  {b['timestamp'][:19]}  {desc:<32} "
                    f"{b['file_count']:>6}  {size:>7.2f}   {kind}"
                )

    elif args.restore:
        manager.restore_backup(args.restore, dry_run=args.dry_run)

    elif args.cleanup:
        manager.cleanup_old_backups(args.keep)

    elif args.size:
        total = manager.get_backup_size()
        backups = manager.list_backups()
        print(f"\n📊 Backup statistics — {manager.project_name}")
        print(f"   Backups       : {len(backups)}")
        print(f"   Total size    : {total:.2f} MB")
        print(f"   Backup folder : {manager.backup_base}")

    elif args.manifest:
        manifest = manager.export_manifest()
        with open(args.manifest, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2, default=str)
        print(f"✅ Manifest exported to: {args.manifest}")

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
