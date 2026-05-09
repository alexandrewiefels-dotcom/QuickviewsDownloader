"""
Run this script ONCE to copy OrbitShow into this directory and set up the
combined SASClouds + OrbitShow app.

    python setup_integration.py

It is safe to run multiple times (overwrites stale files).
"""

import shutil
import os
from pathlib import Path

SRC = Path(r"c:\Alexandre\OMEOSpace\Python\Modular OrbitShow")
DST = Path(__file__).parent

SKIP_DIRS  = {".venv", ".git", "__pycache__", "admin_data", ".devcontainer",
               ".qodo", ".zencoder", ".zenflow", "scripts", "logs"}
SKIP_FILES = {"all_scripts.txt", "test.py", "test_full_workflow.py",
               "test_full_workflow2.py", "test_tle.py", "setup_integration.py"}

def copy_tree():
    for src_path in SRC.rglob("*"):
        # Skip excluded dirs
        if any(part in SKIP_DIRS for part in src_path.parts):
            continue
        # Skip pyc and excluded filenames
        if src_path.suffix == ".pyc" or src_path.name in SKIP_FILES:
            continue
        if not src_path.is_file():
            continue

        rel = src_path.relative_to(SRC)
        dst_path = DST / rel

        # Don't overwrite SASCloud-specific files with OrbitShow versions
        PRESERVE = {"sasclouds_api_scraper.py", "sasclouds_sidebar.py",
                    "sasclouds_map_utils.py", "sasclouds_search_logic.py"}
        if dst_path.name in PRESERVE:
            print(f"  KEEP   {rel}")
            continue

        dst_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src_path, dst_path)
        print(f"  COPY   {rel}")

def rename_sasclouds_files():
    renames = {
        DST / "sidebar.py":     DST / "sasclouds_sidebar.py",
        DST / "map_utils.py":   DST / "sasclouds_map_utils.py",
        DST / "search_logic.py": DST / "sasclouds_search_logic.py",
    }
    for src, dst in renames.items():
        if src.exists() and not dst.exists():
            shutil.copy2(src, dst)
            print(f"  RENAME {src.name} -> {dst.name}")

if __name__ == "__main__":
    print("Copying OrbitShow source tree ...")
    copy_tree()
    print("\nRenaming SASCloud-specific files ...")
    rename_sasclouds_files()
    print("\nDone. Run:  streamlit run main.py")
