"""
Batch tasking for multiple AOIs (3.20).

Processes multiple regions in one run, allowing users to:
- Upload multiple AOI files at once
- Select multiple countries
- Run tasking optimization for each AOI sequentially
- Compare results across AOIs

Usage:
    from core.batch_tasking import BatchTaskingRunner
    runner = BatchTaskingRunner()
    results = runner.run_batch(aois, passes, satellites)
"""

import logging
from datetime import datetime
from typing import List, Dict, Optional, Any
from pathlib import Path

import streamlit as st

logger = logging.getLogger(__name__)


class BatchTaskingRunner:
    """
    Runs tasking optimization for multiple AOIs in batch mode.
    """

    def __init__(self):
        self.results = {}

    def run_batch(self, aois: List[Dict], passes: List, satellites: List,
                  overlap_percent: float = 10.0, max_ona: float = 30.0,
                  progress_callback=None) -> Dict[str, Any]:
        """
        Run tasking for multiple AOIs.
        
        Args:
            aois: List of dicts with 'name', 'geometry', 'area_km2' keys
            passes: List of pass objects
            satellites: List of satellite configs
            overlap_percent: Overlap percentage for tasking
            max_ona: Maximum ONA angle
            progress_callback: Optional callback(aoi_name, progress_0to1)
        
        Returns:
            Dict mapping AOI name to tasking results
        """
        from core.tasking_runner import run_tasking_session

        total = len(aois)
        results = {}

        for i, aoi_info in enumerate(aois):
            aoi_name = aoi_info.get("name", f"AOI {i+1}")
            aoi_geom = aoi_info.get("geometry")

            if aoi_geom is None:
                logger.warning(f"Skipping AOI '{aoi_name}': no geometry")
                continue

            if progress_callback:
                progress_callback(aoi_name, i / total)

            try:
                # Run tasking for this AOI
                tasking_result = run_tasking_session(
                    aoi=aoi_geom,
                    passes=passes,
                    satellites=satellites,
                    overlap_percent=overlap_percent,
                    max_ona=max_ona,
                )

                results[aoi_name] = {
                    "success": True,
                    "area_km2": aoi_info.get("area_km2", 0),
                    "pass_count": len(passes),
                    "tasked_count": len(tasking_result.get("tasked_passes", [])),
                    "central_pass": tasking_result.get("central_pass"),
                    "total_coverage_km2": tasking_result.get("total_coverage_km2", 0),
                    "coverage_percent": tasking_result.get("coverage_percent", 0),
                    "duration_ms": tasking_result.get("duration_ms", 0),
                    "details": tasking_result,
                }

                logger.info(f"Batch tasking for '{aoi_name}': "
                           f"{results[aoi_name]['tasked_count']} passes tasked")

            except Exception as e:
                logger.error(f"Batch tasking failed for '{aoi_name}': {e}")
                results[aoi_name] = {
                    "success": False,
                    "area_km2": aoi_info.get("area_km2", 0),
                    "error": str(e),
                }

            if progress_callback:
                progress_callback(aoi_name, (i + 1) / total)

        self.results = results
        return results

    def get_summary(self) -> Dict:
        """Get a summary of batch tasking results."""
        total_aois = len(self.results)
        successful = sum(1 for r in self.results.values() if r.get("success"))
        failed = total_aois - successful

        total_tasked = sum(
            r.get("tasked_count", 0) for r in self.results.values() if r.get("success")
        )
        total_area = sum(
            r.get("area_km2", 0) for r in self.results.values()
        )

        return {
            "total_aois": total_aois,
            "successful": successful,
            "failed": failed,
            "total_tasked_passes": total_tasked,
            "total_area_km2": total_area,
            "timestamp": datetime.now().isoformat(),
        }

    def get_comparison_table(self) -> List[Dict]:
        """Get a comparison table of all AOI results."""
        rows = []
        for aoi_name, result in self.results.items():
            rows.append({
                "AOI": aoi_name,
                "Area (km²)": result.get("area_km2", 0),
                "Status": "✅" if result.get("success") else "❌",
                "Passes Tasked": result.get("tasked_count", 0),
                "Coverage (km²)": result.get("total_coverage_km2", 0),
                "Coverage %": f"{result.get('coverage_percent', 0):.1f}%",
                "Duration (ms)": result.get("duration_ms", 0),
                "Error": result.get("error", ""),
            })
        return rows


def render_batch_tasking_ui():
    """Render the batch tasking UI in Streamlit."""
    st.markdown("### 📦 Batch Tasking")
    st.markdown("Run tasking optimization for multiple AOIs simultaneously.")

    # File upload for multiple AOIs
    uploaded_files = st.file_uploader(
        "Upload AOI files (GeoJSON, KML, or ZIP)",
        type=["geojson", "json", "kml", "kmz", "zip"],
        accept_multiple_files=True,
        help="Upload multiple AOI files to process in batch"
    )

    # Or select from saved AOIs
    st.markdown("— or —")
    use_saved = st.checkbox("Use saved AOIs from history")

    # Configuration
    col1, col2 = st.columns(2)
    with col1:
        overlap = st.slider("Overlap %", 0, 50, 10, help="Overlap between adjacent passes")
    with col2:
        max_ona = st.slider("Max ONA (°)", 5, 60, 30, help="Maximum off-nadir angle")

    if st.button("🚀 Run Batch Tasking", type="primary", use_container_width=True):
        if not uploaded_files and not use_saved:
            st.warning("Please upload AOI files or select saved AOIs.")
            return

        st.info("Batch tasking started...")
        # Placeholder for actual batch execution
        st.success("Batch tasking complete! (Integration pending)")
