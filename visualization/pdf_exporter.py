# ============================================================================
# FILE: visualization/pdf_exporter.py – Modern OSM‑style static maps
# MODIFIED: force_aoi_extent, use_original_footprints, fixed line splitting
# ============================================================================
import io
import math
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import Patch
from datetime import datetime
from shapely.geometry import box
from geometry.utils import split_polygon_at_antimeridian, split_line_at_antimeridian
from geometry.footprint import clip_geometry_to_latitude_band

try:
    import cartopy.crs as ccrs
    import cartopy.feature as cfeature
    from cartopy.mpl.gridliner import LONGITUDE_FORMATTER, LATITUDE_FORMATTER
    import matplotlib.ticker as mticker
    CARTOPY_AVAILABLE = True
except ImportError:
    CARTOPY_AVAILABLE = False
    print("Warning: cartopy not installed. Install with: pip install cartopy")

try:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image as RLImage, PageBreak
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.lib.enums import TA_CENTER, TA_LEFT
    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False
    print("Warning: reportlab not installed. PDF export will be disabled.")

try:
    from detection.daylight_filter import get_local_time_political
except ImportError:
    def get_local_time_political(pass_time, aoi):
        return pass_time.strftime("%Y-%m-%d %H:%M:%S")


class PDFExporter:
    MAP_WIDTH_INCH = 7.0
    MAP_HEIGHT_INCH = 4.5
    MAP_PADDING = 0.2
    MAP_DPI = 150
    MAP_FIGURE_WIDTH = 800
    MAP_FIGURE_HEIGHT = 600

    COLORS = {
        'land': '#f2efe9',
        'ocean': '#cde3f0',
        'coastline': '#9ca3af',
        'border': '#cbd5e1',
        'lake': '#b9d9f0',
        'river': '#a0c4e8',
        'aoi_face': '#ef4444',
        'aoi_edge': '#b91c1c',
        'aoi_alpha': 0.25,
        'footprint_alpha': 0.35,
        'footprint_edge': '#4b5563',
        'tasked_edge': '#374151',
        'gridline': '#e5e7eb',
        'text': '#1f2937',
    }

    @staticmethod
    def set_map_size(width_inch, height_inch):
        PDFExporter.MAP_WIDTH_INCH = width_inch
        PDFExporter.MAP_HEIGHT_INCH = height_inch

    @staticmethod
    def set_map_padding(padding):
        PDFExporter.MAP_PADDING = padding

    @staticmethod
    def _add_scale_bar(ax, length_km=None):
        xlim = ax.get_xlim()
        ylim = ax.get_ylim()
        map_width_deg = xlim[1] - xlim[0]
        if length_km is None:
            mean_lat = (ylim[0] + ylim[1]) / 2
            km_per_deg = 111.0 * math.cos(math.radians(mean_lat))
            map_width_km = map_width_deg * km_per_deg
            candidates = [10, 20, 50, 100, 200, 500, 1000, 2000, 5000]
            length_km = min(candidates, key=lambda x: abs(x - map_width_km * 0.2))
        length_km = max(length_km, 10)
        km_per_deg = 111.0 * math.cos(math.radians((ylim[0]+ylim[1])/2))
        length_deg = length_km / km_per_deg
        x_start_data, y_base_data = ax.transData.inverted().transform((0.05, 0.05))
        x_end_data = x_start_data + length_deg
        ax.plot([x_start_data, x_end_data], [y_base_data, y_base_data],
                color='black', linewidth=2, transform=ax.transData, clip_on=False)
        ax.plot([x_start_data, x_start_data], [y_base_data - 0.2*length_deg, y_base_data + 0.2*length_deg],
                color='black', linewidth=1.5, transform=ax.transData, clip_on=False)
        ax.plot([x_end_data, x_end_data], [y_base_data - 0.2*length_deg, y_base_data + 0.2*length_deg],
                color='black', linewidth=1.5, transform=ax.transData, clip_on=False)
        ax.text(x_start_data + length_deg/2, y_base_data - 0.3*length_deg,
                f'{length_km} km', ha='center', va='top', fontsize=8,
                transform=ax.transData)

    @staticmethod
    def _add_north_arrow(ax):
        from matplotlib.patches import Polygon
        arrow_size = 0.05
        x_center = 0.95
        y_base = 0.95
        tip = (x_center, y_base + arrow_size)
        left = (x_center - arrow_size/2, y_base)
        right = (x_center + arrow_size/2, y_base)
        arrow = Polygon([tip, left, right], facecolor='black', edgecolor='black',
                        transform=ax.transAxes, clip_on=False)
        ax.add_patch(arrow)
        ax.text(x_center, y_base + arrow_size + 0.01, 'N',
                ha='center', va='bottom', fontsize=10, fontweight='bold',
                transform=ax.transAxes)

    @staticmethod
    def create_static_map_image(aoi, passes, title="Satellite Coverage Map",
                                tasking_results=None, width=None, height=None, dpi=None,
                                force_aoi_extent=False, use_original_footprints=False):
        if not CARTOPY_AVAILABLE:
            return None

        width = width or PDFExporter.MAP_FIGURE_WIDTH
        height = height or PDFExporter.MAP_FIGURE_HEIGHT
        dpi = dpi or PDFExporter.MAP_DPI

        try:
            fig, ax = plt.subplots(figsize=(width/dpi, height/dpi), dpi=dpi,
                                   subplot_kw={'projection': ccrs.PlateCarree()},
                                   facecolor='white')

            # Determine map extent
            if force_aoi_extent and aoi and not aoi.is_empty:
                min_lon, min_lat, max_lon, max_lat = aoi.bounds
                lon_range = max_lon - min_lon
                lat_range = max_lat - min_lat
                lon_pad = max(lon_range * PDFExporter.MAP_PADDING, 0.5)
                lat_pad = max(lat_range * PDFExporter.MAP_PADDING, 0.5)
                ax.set_extent([min_lon - lon_pad, max_lon + lon_pad,
                              min_lat - lat_pad, max_lat + lat_pad],
                              crs=ccrs.PlateCarree())
            else:
                # Auto-extent from AOI and all footprints
                min_lon, max_lon, min_lat, max_lat = None, None, None, None
                if aoi and not aoi.is_empty:
                    min_lon, min_lat, max_lon, max_lat = aoi.bounds

                items = tasking_results if tasking_results else passes
                for item in items:
                    if isinstance(item, dict):
                        fp = item.get('display_footprint') or item.get('footprint')
                    else:
                        if use_original_footprints:
                            fp = getattr(item, 'footprint', None)
                        else:
                            fp = getattr(item, 'display_footprint', None) or getattr(item, 'footprint', None)
                    if fp and not fp.is_empty:
                        b = fp.bounds
                        if min_lon is None:
                            min_lon, min_lat, max_lon, max_lat = b
                        else:
                            min_lon = min(min_lon, b[0])
                            min_lat = min(min_lat, b[1])
                            max_lon = max(max_lon, b[2])
                            max_lat = max(max_lat, b[3])

                if min_lon is not None:
                    lon_range = max_lon - min_lon
                    lat_range = max_lat - min_lat
                    lon_pad = max(lon_range * PDFExporter.MAP_PADDING, 0.5)
                    lat_pad = max(lat_range * PDFExporter.MAP_PADDING, 0.5)
                    ax.set_extent([min_lon - lon_pad, max_lon + lon_pad,
                                  min_lat - lat_pad, max_lat + lat_pad],
                                  crs=ccrs.PlateCarree())
                else:
                    ax.set_global()

            # Base map
            ax.add_feature(cfeature.LAND, facecolor='#f2efe9', alpha=0.95)
            ax.add_feature(cfeature.OCEAN, facecolor='#cde3f0', alpha=0.95)
            ax.add_feature(cfeature.COASTLINE, linewidth=0.5, edgecolor='#9ca3af')
            ax.add_feature(cfeature.BORDERS, linewidth=0.3, edgecolor='black', linestyle='-')
            ax.add_feature(cfeature.LAKES, facecolor='#b9d9f0', alpha=0.8, edgecolor='none')
            ax.add_feature(cfeature.RIVERS, linewidth=0.3, edgecolor='#a0c4e8', alpha=0.6)

            # Gridlines
            gl = ax.gridlines(draw_labels=True, linestyle='--', alpha=0.4,
                              linewidth=0.3, color='#e5e7eb')
            gl.top_labels = False
            gl.right_labels = False
            gl.xlabel_style = {'size': 7, 'color': '#1f2937'}
            gl.ylabel_style = {'size': 7, 'color': '#1f2937'}
            gl.xformatter = LONGITUDE_FORMATTER
            gl.yformatter = LATITUDE_FORMATTER
            gl.xlocator = mticker.MultipleLocator(5)
            gl.ylocator = mticker.MultipleLocator(5)

            # AOI
            if aoi and not aoi.is_empty:
                if aoi.geom_type == 'Polygon':
                    x, y = aoi.exterior.xy
                    ax.fill(x, y, facecolor='#ef4444', edgecolor='#b91c1c',
                           alpha=0.25, linewidth=1.5, transform=ccrs.PlateCarree())
                elif aoi.geom_type == 'MultiPolygon':
                    for poly in aoi.geoms:
                        x, y = poly.exterior.xy
                        ax.fill(x, y, facecolor='#ef4444', edgecolor='#b91c1c',
                               alpha=0.25, linewidth=1.5, transform=ccrs.PlateCarree())

            # Footprints
            is_tasking = tasking_results is not None
            items_to_draw = tasking_results if is_tasking else passes
            footprint_colors = ['#2ECC71', '#3498DB', '#E74C3C', '#F39C12', '#9B59B6',
                                '#1ABC9C', '#E67E22', '#2C3E50', '#16A085', '#C0392B']
            edge_color = '#222222' if is_tasking else '#4b5563'
            line_style = '--' if is_tasking else '-'
            line_width = 0.8 if is_tasking else 0.5
            alpha_fill = 0.3 if is_tasking else 0.35

            for i, item in enumerate(items_to_draw[:30]):
                if isinstance(item, dict):
                    fp = item.get('display_footprint') or item.get('footprint')
                    color = item.get('color', footprint_colors[i % len(footprint_colors)])
                else:
                    if use_original_footprints:
                        fp = getattr(item, 'footprint', None)
                    else:
                        fp = getattr(item, 'display_footprint', None) or getattr(item, 'footprint', None)
                    color = getattr(item, 'color', footprint_colors[i % len(footprint_colors)])

                if fp and not fp.is_empty:
                    parts = split_polygon_at_antimeridian(fp)
                    for part in parts:
                        if part.is_empty:
                            continue
                        if part.geom_type == 'Polygon':
                            x, y = part.exterior.xy
                            ax.fill(x, y, facecolor=color, edgecolor=edge_color,
                                   alpha=alpha_fill, linewidth=line_width, linestyle=line_style,
                                   transform=ccrs.PlateCarree())
                        elif part.geom_type == 'MultiPolygon':
                            for poly in part.geoms:
                                x, y = poly.exterior.xy
                                ax.fill(x, y, facecolor=color, edgecolor=edge_color,
                                       alpha=alpha_fill, linewidth=line_width, linestyle=line_style,
                                       transform=ccrs.PlateCarree())

            # Ground tracks
            for item in items_to_draw[:30]:
                if isinstance(item, dict):
                    track = item.get('display_ground_track') or item.get('ground_track')
                else:
                    if use_original_footprints:
                        track = getattr(item, 'ground_track', None)
                    else:
                        track = getattr(item, 'display_ground_track', None) or getattr(item, 'ground_track', None)

                if track and not track.is_empty:
                    if track.geom_type == 'LineString':
                        parts = split_line_at_antimeridian(track)
                    elif track.geom_type == 'MultiLineString':
                        parts = list(track.geoms)
                    else:
                        parts = [track]
                    for part in parts:
                        if part.geom_type == 'LineString':
                            coords = part.coords
                            coords_2d = [(c[0], c[1]) for c in coords]
                            ax.plot([c[0] for c in coords_2d], [c[1] for c in coords_2d],
                                    color='#666666', linewidth=1.2, linestyle='-',
                                    transform=ccrs.PlateCarree())
                        elif part.geom_type == 'MultiLineString':
                            for seg in part.geoms:
                                coords = seg.coords
                                coords_2d = [(c[0], c[1]) for c in coords]
                                ax.plot([c[0] for c in coords_2d], [c[1] for c in coords_2d],
                                        color='#666666', linewidth=1.2, linestyle='-',
                                        transform=ccrs.PlateCarree())

            PDFExporter._add_scale_bar(ax)
            PDFExporter._add_north_arrow(ax)
            ax.set_title(title, fontsize=12, fontweight='bold', pad=15, color='#1f2937')

            legend_elements = [
                Patch(facecolor='#ef4444', edgecolor='#b91c1c', alpha=0.25, label='Area of Interest (AOI)')
            ]
            if is_tasking:
                legend_elements.append(
                    Patch(facecolor='#2ECC71', edgecolor='#222222', alpha=0.3,
                          linestyle='--', label='Tasked Footprint')
                )
            else:
                legend_elements.append(
                    Patch(facecolor='#2ECC71', edgecolor='#4b5563', alpha=0.35,
                          label='Satellite Footprint')
                )
            legend_elements.extend([
                Patch(facecolor='#f2efe9', edgecolor='none', label='Land'),
                Patch(facecolor='#cde3f0', edgecolor='none', label='Water')
            ])
            ax.legend(handles=legend_elements, loc='lower right',
                     fontsize=7, framealpha=0.95, edgecolor='#cccccc',
                     fancybox=True, shadow=True)

            plt.tight_layout()
            buffer = io.BytesIO()
            plt.savefig(buffer, format='PNG', dpi=dpi, bbox_inches='tight',
                       facecolor='white', edgecolor='none')
            plt.close(fig)
            buffer.seek(0)
            return buffer

        except Exception as e:
            print(f"Error creating static map: {e}")
            import traceback
            traceback.print_exc()
            return None

    @staticmethod
    def create_full_report(passes, tasking_results, aoi, filters=None):
        if not REPORTLAB_AVAILABLE:
            return PDFExporter._create_text_report(passes, tasking_results, aoi, filters)

        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=landscape(A4),
                                rightMargin=36, leftMargin=36,
                                topMargin=36, bottomMargin=36)

        styles = getSampleStyleSheet()
        story = []

        # Styles
        title_style = ParagraphStyle('CustomTitle', parent=styles['Heading1'],
                                      fontSize=24, textColor=colors.HexColor('#2ecc71'),
                                      alignment=TA_CENTER, spaceAfter=20)
        subtitle_style = ParagraphStyle('Subtitle', parent=styles['Normal'],
                                         alignment=TA_CENTER, fontSize=10,
                                         textColor=colors.grey, spaceAfter=30)
        section_style = ParagraphStyle('Section', parent=styles['Heading1'],
                                        fontSize=18, textColor=colors.HexColor('#3498db'),
                                        alignment=TA_LEFT, spaceAfter=15, spaceBefore=20)
        subsection_style = ParagraphStyle('Subsection', parent=styles['Heading2'],
                                           fontSize=14, textColor=colors.HexColor('#27ae60'),
                                           spaceAfter=10, spaceBefore=15)
        heading_style = ParagraphStyle('Heading', parent=styles['Heading2'],
                                        fontSize=16, textColor=colors.HexColor('#27ae60'),
                                        spaceAfter=10, spaceBefore=20)

        # Header
        story.append(Paragraph("OrbitShow Satellite Mission Report", title_style))
        story.append(Paragraph(f"Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", subtitle_style))
        story.append(Spacer(1, 10))

        # Executive Summary
        story.append(Paragraph("Executive Summary", heading_style))
        stats_data = [["Metric", "Value"]]
        if aoi and not aoi.is_empty:
            try:
                from data.aoi_handler import AOIHandler
                area_val, area_unit = AOIHandler.calculate_area(aoi)
                stats_data.append(["AOI Area", f"{area_val:.2f} {area_unit}"])
            except Exception:
                stats_data.append(["AOI Area", f"{aoi.area:.2f} deg²"])
        stats_data.append(["Total Passes Found", str(len(passes))])
        if tasking_results:
            stats_data.append(["Tasked Passes", str(len(tasking_results))])
            coverage_pct = 0
            if aoi and aoi.area > 0:
                try:
                    from shapely.ops import unary_union
                    valid_footprints = []
                    for r in tasking_results:
                        if 'footprint' in r and r['footprint'] and not r['footprint'].is_empty:
                            intersection = r['footprint'].intersection(aoi)
                            if not intersection.is_empty and intersection.area > 0:
                                valid_footprints.append(r['footprint'])
                    if valid_footprints:
                        total_coverage = unary_union(valid_footprints)
                        coverage_area = total_coverage.intersection(aoi).area
                        coverage_pct = (coverage_area / aoi.area) * 100
                        stats_data.append(["AOI Coverage", f"{coverage_pct:.1f}%"])
                except Exception as e:
                    print(f"Coverage calculation error: {e}")
        if filters:
            if 'Dates' in filters:
                stats_data.append(["Date Range", filters['Dates']])
            if 'Max ONA (Filter)' in filters:
                stats_data.append(["Max ONA (Filter)", filters['Max ONA (Filter)']])
            if 'Orbit direction' in filters:
                stats_data.append(["Orbit Direction", filters['Orbit direction']])
            if 'Satellites' in filters:
                stats_data.append(["Satellites", filters['Satellites']])
        stats_table = Table(stats_data, colWidths=[2.5*inch, 4*inch])
        stats_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (1, 0), colors.HexColor('#2ecc71')),
            ('TEXTCOLOR', (0, 0), (1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 12),
            ('FONTSIZE', (0, 1), (-1, -1), 10),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ]))
        story.append(stats_table)
        story.append(Spacer(1, 20))

        # SECTION 1: Search Passes
        story.append(PageBreak())
        story.append(Paragraph("SECTION 1: Search Passes Results", section_style))
        story.append(Spacer(1, 10))

        print("[PDF] Generating map for Search Passes section (force_aoi_extent=True, use_original_footprints=True)...")
        map_image_search = PDFExporter.create_static_map_image(
            aoi=aoi,
            passes=passes,
            tasking_results=None,
            title="Search Passes - Satellite Footprints",
            force_aoi_extent=True,
            use_original_footprints=True
        )

        if map_image_search:
            story.append(Paragraph("Coverage Map - Search Passes", subsection_style))
            try:
                map_image_search.seek(0)
                img = RLImage(map_image_search,
                             width=PDFExporter.MAP_WIDTH_INCH*inch,
                             height=PDFExporter.MAP_HEIGHT_INCH*inch)
                img.hAlign = 'CENTER'
                story.append(img)
                story.append(Spacer(1, 10))
                caption_style = ParagraphStyle('Caption', parent=styles['Normal'],
                                                fontSize=8, textColor=colors.grey,
                                                alignment=TA_CENTER)
                story.append(Paragraph("Figure 1: Original satellite footprints over Area of Interest", caption_style))
                story.append(Spacer(1, 20))
            except Exception as e:
                print(f"Error adding search map to PDF: {e}")
                story.append(Paragraph("Map could not be rendered.", subtitle_style))
                story.append(Spacer(1, 20))

        # Passes table
        story.append(Paragraph("Detected Passes", subsection_style))
        pass_data = [["#", "Satellite", "Camera", "Date (UTC)", "Time (UTC)", "Local Date", "Local Time", "ONA (°)", "Direction", "Clouds"]]
        for idx, p in enumerate(passes[:50], start=1):
            local_time_str = get_local_time_political(p.pass_time, aoi)
            local_parts = local_time_str.split()
            local_date = local_parts[0] if len(local_parts) > 0 else ""
            local_time = local_parts[1] if len(local_parts) > 1 else ""
            cloud_str = f"{p.mean_cloud_cover:.0f}%" if hasattr(p, 'mean_cloud_cover') and p.mean_cloud_cover is not None else "N/A"
            pass_data.append([
                str(idx), p.satellite_name[:20], p.camera_name[:15],
                p.date_utc, p.time_utc.replace(" UTC", ""),
                local_date, local_time,
                f"{p.min_ona:.1f}", p.orbit_direction[:3], cloud_str
            ])
        if len(passes) > 50:
            pass_data.append(["", f"... and {len(passes) - 50} more passes", "", "", "", "", "", "", "", ""])
        pass_table = Table(pass_data, repeatRows=1,
                          colWidths=[0.4*inch, 1.6*inch, 1.2*inch, 0.9*inch, 0.8*inch, 0.9*inch, 0.8*inch, 0.6*inch, 0.6*inch, 0.8*inch])
        pass_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#3498db')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 8),
            ('FONTSIZE', (0, 1), (-1, -1), 7),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ]))
        story.append(pass_table)

        # SECTION 2: Tasking
        if tasking_results:
            story.append(PageBreak())
            story.append(Paragraph("SECTION 2: Simulate Tasking Results", section_style))
            story.append(Spacer(1, 10))

            print("[PDF] Generating map for Simulate Tasking section (force_aoi_extent=True)...")
            map_image_tasking = PDFExporter.create_static_map_image(
                aoi=aoi,
                passes=passes,
                tasking_results=tasking_results,
                title="Simulate Tasking - Tasked Footprints",
                force_aoi_extent=True,
                use_original_footprints=False
            )

            if map_image_tasking:
                story.append(Paragraph("Coverage Map - Tasking Results", subsection_style))
                try:
                    map_image_tasking.seek(0)
                    img = RLImage(map_image_tasking,
                                 width=PDFExporter.MAP_WIDTH_INCH*inch,
                                 height=PDFExporter.MAP_HEIGHT_INCH*inch)
                    img.hAlign = 'CENTER'
                    story.append(img)
                    story.append(Spacer(1, 10))
                    caption_style = ParagraphStyle('Caption', parent=styles['Normal'],
                                                    fontSize=8, textColor=colors.grey,
                                                    alignment=TA_CENTER)
                    story.append(Paragraph("Figure 2: Tasked satellite footprints after optimization (dashed borders)", caption_style))
                    story.append(Spacer(1, 20))
                except Exception as e:
                    print(f"Error adding tasking map to PDF: {e}")
                    story.append(Paragraph("Map could not be rendered.", subtitle_style))
                    story.append(Spacer(1, 20))

            # Coverage analysis
            story.append(Paragraph("Coverage Analysis", subsection_style))
            total_coverage_pct = 0
            if aoi and aoi.area > 0:
                try:
                    from shapely.ops import unary_union
                    valid_footprints = []
                    for r in tasking_results:
                        if 'footprint' in r and r['footprint'] and not r['footprint'].is_empty:
                            intersection = r['footprint'].intersection(aoi)
                            if not intersection.is_empty and intersection.area > 0:
                                valid_footprints.append(r['footprint'])
                    if valid_footprints:
                        total_coverage = unary_union(valid_footprints)
                        coverage_area = total_coverage.intersection(aoi).area
                        total_coverage_pct = (coverage_area / aoi.area) * 100
                except Exception as e:
                    print(f"Coverage calculation error: {e}")

            coverage_data = [
                ["Metric", "Value"],
                ["Total Tasked Passes", str(len(tasking_results))],
                ["AOI Coverage", f"{total_coverage_pct:.1f}%"],
                ["Average ONA Used", f"{sum(r.get('required_ona', 0) for r in tasking_results) / len(tasking_results):.1f}°"],
                ["Best Coverage Pass", max(tasking_results, key=lambda x: x.get('coverage_pct', 0)).get('satellite', 'N/A')[:25]]
            ]
            coverage_table = Table(coverage_data, colWidths=[2.5*inch, 4*inch])
            coverage_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (1, 0), colors.HexColor('#e67e22')),
                ('TEXTCOLOR', (0, 0), (1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 11),
                ('FONTSIZE', (0, 1), (-1, -1), 9),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ]))
            story.append(coverage_table)
            story.append(Spacer(1, 20))

            # Tasking results table
            story.append(Paragraph("Tasking Results Details", subsection_style))
            tasking_data = [["#", "Satellite", "Date (UTC)", "Time (UTC)", "Local Date", "Local Time", "ONA Used", "Shift", "Swath", "Coverage", "Clouds"]]
            for idx, r in enumerate(tasking_results[:50], start=1):
                pass_time = r.get('pass_time')
                if pass_time:
                    local_time_str = get_local_time_political(pass_time, aoi)
                    local_parts = local_time_str.split()
                    local_date = local_parts[0] if len(local_parts) > 0 else ""
                    local_time_display = local_parts[1] if len(local_parts) > 1 else ""
                    date_utc = pass_time.strftime("%Y-%m-%d")
                    time_utc = pass_time.strftime("%H:%M:%S")
                else:
                    date_utc = "N/A"
                    time_utc = "N/A"
                    local_date = "N/A"
                    local_time_display = "N/A"

                shift = abs(r.get('shift_km', r.get('offset_km', 0)))
                shift_dir = "→" if r.get('shift_km', 0) > 0 else "←" if r.get('shift_km', 0) < 0 else ""
                shift_str = f"{shift_dir} {shift:.1f}" if shift_dir else f"{shift:.1f}"
                cloud = r.get('cloud_cover')
                cloud_str = f"{cloud:.0f}%" if cloud is not None else "N/A"
                coverage = r.get('coverage_pct', 0)
                tasking_data.append([
                    str(idx), r.get('satellite', 'N/A')[:20], date_utc, time_utc,
                    local_date, local_time_display,
                    f"{r.get('required_ona', 0):.1f}°", shift_str,
                    f"{r.get('swath_km', 0):.0f}", f"{coverage:.1f}%", cloud_str
                ])
            if len(tasking_results) > 50:
                tasking_data.append(["", f"... and {len(tasking_results) - 50} more tasked passes", "", "", "", "", "", "", "", "", ""])
            tasking_table = Table(tasking_data, repeatRows=1,
                                 colWidths=[0.4*inch, 1.8*inch, 0.9*inch, 0.7*inch, 0.9*inch, 0.7*inch, 0.8*inch, 0.8*inch, 0.8*inch, 0.8*inch, 0.7*inch])
            tasking_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#e67e22')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 8),
                ('FONTSIZE', (0, 1), (-1, -1), 7),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ]))
            story.append(tasking_table)

        # Footer
        story.append(Spacer(1, 30))
        footer_style = ParagraphStyle('Footer', parent=styles['Normal'],
                                       fontSize=8, textColor=colors.grey,
                                       alignment=TA_CENTER)
        story.append(Paragraph("Report generated by OrbitShow - Satellite Pass Prediction Platform", footer_style))
        story.append(Paragraph(f"OrbitShow v1.0 - {datetime.now().strftime('%Y-%m-%d')}", footer_style))

        doc.build(story)
        buffer.seek(0)
        return buffer

    @staticmethod
    def capture_map_as_image(map_renderer, center, zoom, aoi, passes, opportunities=None,
                             highlighted_pass_id=None, filters=None, width=800, height=600):
        try:
            import streamlit as st
            tasking_results = st.session_state.get('tasking_results', None)
            map_image = PDFExporter.create_static_map_image(
                aoi=aoi,
                passes=passes,
                tasking_results=tasking_results,
                width=width,
                height=height,
                dpi=150,
                force_aoi_extent=True,
                use_original_footprints=False
            )
            return map_image
        except Exception as e:
            print(f"Error capturing map: {e}")
            return None

    @staticmethod
    def create_simple_report(passes, tasking_results=None, aoi=None, filters=None,
                            map_image=None, center=None, zoom=None):
        return PDFExporter.create_full_report(passes, tasking_results, aoi, filters)

    @staticmethod
    def _create_text_report(passes, tasking_results=None, aoi=None, filters=None):
        buffer = io.BytesIO()
        lines = []
        lines.append("=" * 70)
        lines.append("ORBITSHOW SATELLITE MISSION REPORT")
        lines.append("=" * 70)
        lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append("")
        lines.append("NOTE: For full PDF with maps and images, install required packages:")
        lines.append("  pip install reportlab matplotlib cartopy")
        lines.append("")
        lines.append("EXECUTIVE SUMMARY")
        lines.append("-" * 50)
        lines.append(f"Total Passes Found: {len(passes)}")
        if tasking_results:
            lines.append(f"Tasked Passes: {len(tasking_results)}")
        if aoi and hasattr(aoi, 'area'):
            try:
                from data.aoi_handler import AOIHandler
                area_val, area_unit = AOIHandler.calculate_area(aoi)
                lines.append(f"AOI Area: {area_val:.2f} {area_unit}")
            except Exception:
                lines.append(f"AOI Area: {aoi.area:.2f} deg²")
        if filters:
            if 'Dates' in filters:
                lines.append(f"Date Range: {filters['Dates']}")
            if 'Max ONA (Filter)' in filters:
                lines.append(f"Max ONA: {filters['Max ONA (Filter)']}")
        lines.append("")
        lines.append("=" * 70)
        lines.append("SECTION 1: SEARCH PASSES RESULTS")
        lines.append("=" * 70)
        lines.append("")
        lines.append("DETECTED PASSES")
        lines.append("-" * 80)
        lines.append(f"{'#':<4} {'Satellite':<25} {'Date (UTC)':<12} {'Time (UTC)':<10} {'ONA':<6} {'Direction':<10}")
        lines.append("-" * 80)
        for idx, p in enumerate(passes[:100], start=1):
            lines.append(f"{idx:<4} {p.satellite_name[:24]:<25} {p.date_utc:<12} {p.time_utc:<10} {p.min_ona:<6.1f} {p.orbit_direction[:10]:<10}")
        if len(passes) > 100:
            lines.append(f"... and {len(passes) - 100} more passes")
        if tasking_results:
            lines.append("")
            lines.append("=" * 70)
            lines.append("SECTION 2: SIMULATE TASKING RESULTS")
            lines.append("=" * 70)
            lines.append("")
            lines.append("TASKING RESULTS")
            lines.append("-" * 80)
            lines.append(f"{'#':<4} {'Satellite':<25} {'ONA Used':<10} {'Shift (km)':<12} {'Coverage':<10}")
            lines.append("-" * 80)
            for idx, r in enumerate(tasking_results[:50], start=1):
                shift = abs(r.get('shift_km', r.get('offset_km', 0)))
                coverage = r.get('coverage_pct', 0)
                lines.append(f"{idx:<4} {r.get('satellite', 'N/A')[:24]:<25} {r.get('required_ona', 0):<10.1f} {shift:<12.1f} {coverage:<10.1f}%")
        lines.append("")
        lines.append("=" * 70)
        lines.append("End of Report - Generated by OrbitShow")
        content = "\n".join(lines)
        buffer.write(content.encode('utf-8'))
        buffer.seek(0)
        return buffer