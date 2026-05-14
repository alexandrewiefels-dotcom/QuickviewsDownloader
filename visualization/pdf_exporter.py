"""
PDF Report Generation for Tasking Results (3.22).

Enhanced PDF exporter with:
- Cover page with mission summary
- Per-satellite pass tables
- Coverage statistics and charts
- AOI map with tasked footprints
- Export to file or bytes

Usage:
    from visualization.pdf_exporter import generate_tasking_report
    pdf_bytes = generate_tasking_report(passes, aoi, results)
    
    # Or use the class-based API:
    from visualization.pdf_exporter import PDFExporter
    PDFExporter.set_map_size(width_inch=10.0, height_inch=7.0)
    pdf_buffer = PDFExporter.create_full_report(passes=passes, tasking_results=results, aoi=aoi, filters=filters)
"""

import io
import math
import logging
from datetime import datetime
from typing import List, Optional

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import Patch
from shapely.geometry import box

from geometry.utils import split_polygon_at_antimeridian, split_line_at_antimeridian
from geometry.footprint import clip_geometry_to_latitude_band

logger = logging.getLogger(__name__)

try:
    import cartopy.crs as ccrs
    import cartopy.feature as cfeature
    from cartopy.mpl.gridliner import LONGITUDE_FORMATTER, LATITUDE_FORMATTER
    import matplotlib.ticker as mticker
    CARTOPY_AVAILABLE = True
except ImportError:
    CARTOPY_AVAILABLE = False

try:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image as RLImage, PageBreak
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False


def _create_static_map(passes, aoi, title="Tasking Results Map", dpi=150):
    """Create a static map image using Cartopy."""
    if not CARTOPY_AVAILABLE:
        return None

    fig = plt.figure(figsize=(10, 8), dpi=dpi)
    ax = fig.add_subplot(1, 1, 1, projection=ccrs.PlateCarree())

    # Set extent based on AOI
    if aoi and not aoi.is_empty:
        bounds = aoi.bounds
        lon_min, lat_min, lon_max, lat_max = bounds
        margin = max((lon_max - lon_min) * 0.3, 5)
        ax.set_extent([lon_min - margin, lon_max + margin,
                       max(lat_min - margin, -90), min(lat_max + margin, 90)],
                      crs=ccrs.PlateCarree())
    else:
        ax.set_global()

    # Add map features
    ax.add_feature(cfeature.LAND, facecolor='lightgray', alpha=0.5)
    ax.add_feature(cfeature.OCEAN, facecolor='lightblue', alpha=0.3)
    ax.add_feature(cfeature.COASTLINE, linewidth=0.5)
    ax.add_feature(cfeature.BORDERS, linewidth=0.3, alpha=0.5)
    ax.gridlines(draw_labels=True, linewidth=0.3, alpha=0.5, color='gray')

    # Draw AOI
    if aoi and not aoi.is_empty:
        from shapely.geometry import mapping
        import cartopy.io.shapereader as shpreader
        ax.add_geometries([aoi], crs=ccrs.PlateCarree(),
                          facecolor='cyan', edgecolor='blue',
                          linewidth=2, alpha=0.3, label='AOI')

    # Draw passes
    for p in passes[:50]:  # Limit to 50 passes for readability
        fp = getattr(p, 'display_footprint', None) or p.footprint
        if fp and not fp.is_empty:
            try:
                parts = split_polygon_at_antimeridian(fp)
                for part in parts:
                    if not part.is_empty:
                        ax.add_geometries([part], crs=ccrs.PlateCarree(),
                                          facecolor=p.color, edgecolor='black',
                                          linewidth=0.5, alpha=0.3)
            except Exception:
                pass

    plt.title(title, fontsize=14, fontweight='bold')
    plt.tight_layout()

    # Save to bytes
    buf = io.BytesIO()
    plt.savefig(buf, format='png', dpi=dpi, bbox_inches='tight')
    plt.close(fig)
    buf.seek(0)
    return buf


def generate_tasking_report(passes, aoi, results, title="OrbitShow Tasking Report",
                            filename=None) -> Optional[bytes]:
    """
    Generate a comprehensive PDF report for tasking results.
    
    Args:
        passes: List of pass objects
        aoi: AOI geometry
        results: Tasking results dict
        title: Report title
        filename: Optional filename to save to
    
    Returns:
        PDF bytes if successful, None otherwise
    """
    if not REPORTLAB_AVAILABLE:
        logger.warning("ReportLab not installed. Install with: pip install reportlab")
        return None

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, title=title,
                            author="OrbitShow",
                            subject="Satellite Tasking Report")

    styles = getSampleStyleSheet()
    story = []
    title_style = ParagraphStyle('CustomTitle', parent=styles['Title'],
                                  fontSize=22, spaceAfter=20)
    heading_style = ParagraphStyle('CustomHeading', parent=styles['Heading2'],
                                    fontSize=14, spaceAfter=10)
    normal_style = ParagraphStyle('CustomNormal', parent=styles['Normal'],
                                   fontSize=10, spaceAfter=6)

    # ── Cover Page ────────────────────────────────────────────────────────
    story.append(Spacer(1, 2 * inch))
    story.append(Paragraph("🛰️ OrbitShow", title_style))
    story.append(Paragraph(title, heading_style))
    story.append(Spacer(1, 0.5 * inch))
    story.append(Paragraph(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')} UTC", normal_style))
    story.append(Paragraph(f"Passes analyzed: {len(passes)}", normal_style))
    if results:
        tasked = results.get('tasked_passes', [])
        story.append(Paragraph(f"Passes tasked: {len(tasked)}", normal_style))
        coverage = results.get('total_coverage_km2', 0)
        story.append(Paragraph(f"Total coverage: {coverage:,.0f} km²", normal_style))
    story.append(PageBreak())

    # ── Static Map ────────────────────────────────────────────────────────
    story.append(Paragraph("Coverage Map", heading_style))
    map_img = _create_static_map(passes, aoi, title)
    if map_img:
        img = RLImage(map_img, width=6.5 * inch, height=5 * inch)
        story.append(img)
    else:
        story.append(Paragraph("(Map requires cartopy library)", normal_style))
    story.append(PageBreak())

    # ── Pass Summary Table ────────────────────────────────────────────────
    story.append(Paragraph("Pass Summary", heading_style))

    # Group passes by satellite
    from collections import defaultdict
    by_satellite = defaultdict(list)
    for p in passes:
        by_satellite[p.satellite_name].append(p)

    for sat_name, sat_passes in sorted(by_satellite.items()):
        story.append(Paragraph(f"<b>{sat_name}</b> ({len(sat_passes)} passes)", normal_style))

        table_data = [["#", "Date", "Time (UTC)", "ONA (°)", "Direction", "Duration"]]
        for i, p in enumerate(sat_passes[:20], 1):  # Max 20 per satellite
            table_data.append([
                str(i),
                getattr(p, 'date_utc8', ''),
                getattr(p, 'time_utc8', ''),
                f"{getattr(p, 'min_ona', 0):.1f}",
                getattr(p, 'orbit_direction', ''),
                f"{getattr(p, 'duration_min', 0):.1f} min",
            ])

        if len(sat_passes) > 20:
            table_data.append(["...", f"({len(sat_passes) - 20} more)", "", "", "", ""])

        table = Table(table_data, colWidths=[0.3*inch, 1*inch, 1*inch, 0.7*inch, 0.8*inch, 0.8*inch])
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2ecc71')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTSIZE', (0, 0), (-1, -1), 8),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f0f0f0')]),
        ]))
        story.append(table)
        story.append(Spacer(1, 0.2 * inch))

    # ── Coverage Statistics ───────────────────────────────────────────────
    if results:
        story.append(PageBreak())
        story.append(Paragraph("Coverage Statistics", heading_style))

        tasked_passes = results.get('tasked_passes', [])
        total_coverage = results.get('total_coverage_km2', 0)
        coverage_pct = results.get('coverage_percent', 0)

        stats_data = [
            ["Metric", "Value"],
            ["Total Passes", str(len(passes))],
            ["Passes Tasked", str(len(tasked_passes))],
            ["Total Coverage", f"{total_coverage:,.0f} km²"],
            ["Coverage %", f"{coverage_pct:.1f}%"],
            ["Overlap %", f"{results.get('overlap_percent', 10):.0f}%"],
        ]

        stats_table = Table(stats_data, colWidths=[2*inch, 2*inch])
        stats_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#3498db')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ]))
        story.append(stats_table)

    # Build PDF
    doc.build(story)
    pdf_bytes = buf.getvalue()

    if filename:
        with open(filename, 'wb') as f:
            f.write(pdf_bytes)
        logger.info(f"PDF report saved to {filename}")

    return pdf_bytes


def generate_simple_report(passes, aoi, filename="tasking_report.pdf") -> bool:
    """
    Generate a simple PDF report without tasking results.
    Returns True if successful.
    """
    result = generate_tasking_report(passes, aoi, {}, filename=filename)
    return result is not None


# ============================================================================
# PDFExporter class — Backward-compatible API for existing callers
# ============================================================================

class PDFExporter:
    """
    PDF export utility class providing a class-based API.
    
    This class wraps the standalone functions for backward compatibility
    with existing callers that use PDFExporter.create_full_report(), etc.
    
    Usage:
        PDFExporter.set_map_size(width_inch=10.0, height_inch=7.0)
        pdf_buffer = PDFExporter.create_full_report(passes=passes, ...)
    """
    
    _map_width = 10.0
    _map_height = 7.0
    _map_padding = 0.3
    
    @classmethod
    def set_map_size(cls, width_inch=10.0, height_inch=7.0):
        """Set the default map size for PDF exports."""
        cls._map_width = width_inch
        cls._map_height = height_inch
    
    @classmethod
    def set_map_padding(cls, padding=0.3):
        """Set the default map padding for PDF exports."""
        cls._map_padding = padding
    
    @classmethod
    def create_full_report(cls, passes=None, tasking_results=None, aoi=None, filters=None) -> bytes:
        """
        Create a full PDF report with passes, tasking results, and map.
        
        Args:
            passes: List of pass objects
            tasking_results: Tasking results dict or None
            aoi: AOI geometry or None
            filters: Dict of filter info for the report header
        
        Returns:
            PDF bytes
        """
        passes = passes or []
        tasking_results = tasking_results or {}
        
        # Build a results dict compatible with generate_tasking_report
        results = {}
        if isinstance(tasking_results, dict):
            results = {
                'tasked_passes': tasking_results.get('tasked_passes', tasking_results.get('assignments', [])),
                'total_coverage_km2': tasking_results.get('total_coverage_km2', 0),
                'coverage_percent': tasking_results.get('coverage_percent', tasking_results.get('total_coverage_pct', 0)),
                'overlap_percent': tasking_results.get('overlap_percent', 10),
            }
        elif isinstance(tasking_results, list):
            results = {
                'tasked_passes': tasking_results,
                'total_coverage_km2': 0,
                'coverage_percent': 0,
                'overlap_percent': 10,
            }
        
        title = "OrbitShow Pass Report"
        if filters:
            filter_str = " | ".join(f"{k}: {v}" for k, v in filters.items() if v)
            if filter_str:
                title += f" ({filter_str})"
        
        pdf_bytes = generate_tasking_report(passes, aoi, results, title=title)
        if pdf_bytes is None:
            # Fallback: return empty bytes if reportlab not available
            return b""
        return pdf_bytes
    
    @classmethod
    def create_simple_report(cls, passes_list, tasking_results=None, aoi=None, 
                              filters=None, map_image=None, center=None, zoom=None) -> bytes:
        """
        Create a simple PDF report (alias for create_full_report without map capture).
        
        Args:
            passes_list: List of pass objects
            tasking_results: Tasking results dict or None
            aoi: AOI geometry or None
            filters: Dict of filter info
            map_image: Optional pre-captured map image bytes
            center: Optional map center [lat, lon]
            zoom: Optional map zoom level
        
        Returns:
            PDF bytes
        """
        return cls.create_full_report(
            passes=passes_list,
            tasking_results=tasking_results,
            aoi=aoi,
            filters=filters
        )
    
    @classmethod
    def capture_map_as_image(cls, map_renderer, center, zoom, aoi_geom,
                              passes_list, opportunities=None,
                              highlighted_pass_id=None, filters=None) -> Optional[bytes]:
        """
        Capture a map as an image for embedding in PDF.
        
        Args:
            map_renderer: MapRenderer instance
            center: Map center [lat, lon]
            zoom: Zoom level
            aoi_geom: AOI geometry
            passes_list: List of pass objects
            opportunities: Optional list of opportunities
            highlighted_pass_id: Optional pass ID to highlight
            filters: Optional filter info
        
        Returns:
            PNG image bytes or None if cartopy not available
        """
        if not CARTOPY_AVAILABLE:
            return None
        
        try:
            # Use the static map generator
            buf = _create_static_map(passes_list, aoi_geom, 
                                      title="OrbitShow Coverage Map",
                                      dpi=150)
            if buf:
                return buf.getvalue()
            return None
        except Exception as e:
            logger.warning(f"Failed to capture map image: {e}")
            return None
