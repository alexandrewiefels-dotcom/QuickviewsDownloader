# ============================================================================
# FILE: visualization/static_map_exporter.py
# Static map generation using matplotlib and cartopy (no browser required)
# ============================================================================
import io
import math
from datetime import datetime
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import Polygon as MPLPolygon
from matplotlib.lines import Line2D
import numpy as np

# Try to import cartopy
try:
    import cartopy.crs as ccrs
    import cartopy.feature as cfeature
    CARTOPY_AVAILABLE = True
except ImportError:
    CARTOPY_AVAILABLE = False
    print("Warning: cartopy not installed. Install with: pip install cartopy")


class StaticMapExporter:
    """Generate static maps using matplotlib and cartopy"""
    
    @staticmethod
    def create_map_image(aoi, passes, tasking_results=None, center=None, zoom=None,
                         width=800, height=600, dpi=150, title=None, show_legend=True):
        """
        Create a static map image with AOI and footprints.
        
        Args:
            aoi: Area of Interest polygon (Shapely Polygon)
            passes: List of SatellitePass objects
            tasking_results: List of tasking results (optional, for tasked footprints)
            center: Map center [lat, lon] (optional, auto-calculated from AOI)
            zoom: Zoom level (optional, auto-calculated from AOI)
            width: Image width in pixels
            height: Image height in pixels
            dpi: Image DPI
            title: Optional title for the map
            show_legend: Whether to show the legend
        
        Returns:
            BytesIO object containing PNG image data
        """
        if not CARTOPY_AVAILABLE:
            print("Cartopy not available. Install with: pip install cartopy")
            return None
        
        # Create figure
        fig, ax = plt.subplots(figsize=(width/dpi, height/dpi), 
                               dpi=dpi,
                               subplot_kw={'projection': ccrs.PlateCarree()})
        
        # Determine map extent
        if aoi and not aoi.is_empty:
            bounds = aoi.bounds
            min_lon, min_lat, max_lon, max_lat = bounds
            
            # Add padding based on zoom
            lon_range = max_lon - min_lon
            lat_range = max_lat - min_lat
            lon_pad = max(lon_range * 0.2, 0.5)
            lat_pad = max(lat_range * 0.2, 0.5)
            
            ax.set_extent([min_lon - lon_pad, max_lon + lon_pad, 
                          min_lat - lat_pad, max_lat + lat_pad], 
                         crs=ccrs.PlateCarree())
        else:
            # Default to world view
            ax.set_global()
        
        # Add map features
        ax.add_feature(cfeature.LAND, facecolor='#f0f0f0', alpha=0.8)
        ax.add_feature(cfeature.OCEAN, facecolor='#e0f0ff', alpha=0.8)
        ax.add_feature(cfeature.COASTLINE, linewidth=0.8, edgecolor='#666666')
        ax.add_feature(cfeature.BORDERS, linewidth=0.5, edgecolor='#888888', linestyle=':')
        ax.add_feature(cfeature.LAKES, facecolor='#c8e8ff', alpha=0.5, edgecolor='none')
        ax.add_feature(cfeature.RIVERS, linewidth=0.5, edgecolor='#66aaff', alpha=0.5)
        
        # Add gridlines
        gl = ax.gridlines(draw_labels=True, linestyle='--', alpha=0.4, linewidth=0.5)
        gl.top_labels = False
        gl.right_labels = False
        gl.xlabel_style = {'size': 8, 'color': '#333333'}
        gl.ylabel_style = {'size': 8, 'color': '#333333'}
        
        # Add AOI (red outline with transparent fill)
        if aoi and not aoi.is_empty:
            StaticMapExporter._add_polygon_to_ax(ax, aoi, 
                                                  facecolor='#ff0000', 
                                                  edgecolor='#cc0000',
                                                  alpha=0.25, 
                                                  linewidth=2,
                                                  label='Area of Interest')
        
        # Determine which footprints to show
        if tasking_results:
            footprints_to_show = tasking_results
            is_tasking = True
        else:
            footprints_to_show = passes
            is_tasking = False
        
        # Add footprints with different colors
        colors = ['#2ecc71', '#3498db', '#e74c3c', '#f39c12', '#9b59b6', 
                  '#1abc9c', '#e67e22', '#2c3e50', '#16a085', '#c0392b']
        
        for i, item in enumerate(footprints_to_show):
            # Get footprint and color
            if isinstance(item, dict):
                footprint = item.get('footprint')
                # Get color from item or use default
                color = item.get('color', colors[i % len(colors)])
                satellite = item.get('satellite', f'Pass {i+1}')
                ona = item.get('required_ona', 0)
                is_central = item.get('is_central', False)
            else:
                footprint = getattr(item, 'tasked_footprint', None) or item.footprint
                color = getattr(item, 'color', colors[i % len(colors)])
                satellite = item.satellite_name
                ona = getattr(item, 'tasked_ona', item.min_ona)
                is_central = getattr(item, 'is_central', False)
            
            if footprint and not footprint.is_empty:
                # Different style for tasked vs original
                if is_tasking:
                    # Tasked footprints: dashed border, semi-transparent fill
                    StaticMapExporter._add_polygon_to_ax(
                        ax, footprint, 
                        facecolor=color, 
                        edgecolor='#000000',
                        alpha=0.35, 
                        linewidth=1.5,
                        linestyle='--',
                        label=f'{satellite} (ONA: {ona:.1f}°)' if i < 10 else None
                    )
                else:
                    # Original footprints: solid border, light fill
                    StaticMapExporter._add_polygon_to_ax(
                        ax, footprint, 
                        facecolor=color, 
                        edgecolor='#333333',
                        alpha=0.25, 
                        linewidth=1,
                        label=satellite if i < 10 else None
                    )
        
        # Add title
        if title:
            ax.set_title(title, fontsize=14, fontweight='bold', pad=20)
        else:
            date_str = datetime.now().strftime('%Y-%m-%d')
            if is_tasking:
                ax.set_title(f'OrbitShow - Tasking Results ({date_str})', 
                            fontsize=14, fontweight='bold', pad=20)
            else:
                ax.set_title(f'OrbitShow - Satellite Coverage Map ({date_str})', 
                            fontsize=14, fontweight='bold', pad=20)
        
        # Add legend
        if show_legend:
            StaticMapExporter._add_legend(ax, is_tasking)
        
        # Adjust layout
        plt.tight_layout()
        
        # Save to buffer
        buffer = io.BytesIO()
        plt.savefig(buffer, format='PNG', dpi=dpi, bbox_inches='tight', facecolor='white')
        plt.close(fig)
        buffer.seek(0)
        
        return buffer
    
    @staticmethod
    def _add_polygon_to_ax(ax, geometry, facecolor, edgecolor, alpha, linewidth=1, 
                           linestyle='-', label=None):
        """Add a shapely polygon to matplotlib axis."""
        from shapely.geometry import Polygon, MultiPolygon
        
        if geometry.geom_type == 'Polygon':
            x, y = geometry.exterior.xy
            ax.fill(x, y, facecolor=facecolor, edgecolor=edgecolor, 
                   alpha=alpha, linewidth=linewidth, linestyle=linestyle,
                   transform=ccrs.PlateCarree(), label=label)
            
            # Add holes if any
            for interior in geometry.interiors:
                x, y = zip(*interior.coords)
                ax.fill(x, y, facecolor='white', edgecolor=edgecolor,
                       alpha=0.8, linewidth=0.5, transform=ccrs.PlateCarree())
                       
        elif geometry.geom_type == 'MultiPolygon':
            for poly in geometry.geoms:
                x, y = poly.exterior.xy
                ax.fill(x, y, facecolor=facecolor, edgecolor=edgecolor,
                       alpha=alpha, linewidth=linewidth, linestyle=linestyle,
                       transform=ccrs.PlateCarree(), label=label if poly == geometry.geoms[0] else None)
    
    @staticmethod
    def _add_legend(ax, is_tasking=False):
        """Add legend to the map."""
        legend_elements = []
        
        # AOI
        legend_elements.append(
            mpatches.Patch(facecolor='#ff0000', edgecolor='#cc0000', 
                          alpha=0.25, label='Area of Interest (AOI)')
        )
        
        if is_tasking:
            # Tasked footprints
            legend_elements.append(
                mpatches.Patch(facecolor='#2ecc71', edgecolor='#000000', 
                              alpha=0.35, linestyle='--', label='Tasked Footprint')
            )
            legend_elements.append(
                Line2D([0], [0], color='#2ecc71', linewidth=2, 
                       linestyle='--', label='Tasked Ground Track')
            )
        else:
            # Original footprints
            legend_elements.append(
                mpatches.Patch(facecolor='#2ecc71', edgecolor='#333333', 
                              alpha=0.25, label='Satellite Footprint')
            )
        
        # Map features
        legend_elements.append(
            mpatches.Patch(facecolor='#f0f0f0', edgecolor='none', label='Land')
        )
        legend_elements.append(
            mpatches.Patch(facecolor='#e0f0ff', edgecolor='none', label='Water')
        )
        
        ax.legend(handles=legend_elements, loc='lower right', 
                 fontsize=8, framealpha=0.9, edgecolor='#cccccc')
    
    @staticmethod
    def create_simple_map(aoi, footprints, output_path=None, width=800, height=600):
        """
        Create a simple map with AOI and footprints (simplified interface).
        
        Args:
            aoi: Area of Interest polygon
            footprints: List of footprints (Polygon objects)
            output_path: Optional file path to save the image
            width: Image width in pixels
            height: Image height in pixels
        
        Returns:
            BytesIO object or None
        """
        if not CARTOPY_AVAILABLE:
            return None
        
        dpi = 150
        fig, ax = plt.subplots(figsize=(width/dpi, height/dpi), 
                               dpi=dpi,
                               subplot_kw={'projection': ccrs.PlateCarree()})
        
        # Set extent based on AOI
        if aoi and not aoi.is_empty:
            bounds = aoi.bounds
            lon_pad = (bounds[2] - bounds[0]) * 0.2
            lat_pad = (bounds[3] - bounds[1]) * 0.2
            ax.set_extent([bounds[0] - lon_pad, bounds[2] + lon_pad,
                          bounds[1] - lat_pad, bounds[3] + lat_pad],
                         crs=ccrs.PlateCarree())
        else:
            ax.set_global()
        
        # Add base map
        ax.add_feature(cfeature.LAND, facecolor='#f0f0f0')
        ax.add_feature(cfeature.OCEAN, facecolor='#e0f0ff')
        ax.add_feature(cfeature.COASTLINE, linewidth=0.5)
        
        # Add AOI
        if aoi and not aoi.is_empty:
            if aoi.geom_type == 'Polygon':
                x, y = aoi.exterior.xy
                ax.fill(x, y, facecolor='red', edgecolor='darkred', 
                       alpha=0.3, linewidth=2, transform=ccrs.PlateCarree())
        
        # Add footprints
        colors = ['#2ecc71', '#3498db', '#e74c3c', '#f39c12', '#9b59b6']
        for i, fp in enumerate(footprints[:20]):
            if fp and not fp.is_empty:
                if fp.geom_type == 'Polygon':
                    x, y = fp.exterior.xy
                    ax.fill(x, y, facecolor=colors[i % len(colors)], 
                           edgecolor='black', alpha=0.3, linewidth=1,
                           transform=ccrs.PlateCarree())
        
        ax.set_title('Satellite Coverage Map', fontsize=14, fontweight='bold')
        
        # Save or return
        buffer = io.BytesIO()
        plt.savefig(buffer, format='PNG', dpi=dpi, bbox_inches='tight')
        plt.close(fig)
        buffer.seek(0)
        
        if output_path:
            with open(output_path, 'wb') as f:
                f.write(buffer.getvalue())
        
        return buffer


def create_coverage_map(aoi, passes, tasking_results=None):
    """
    Quick function to create a coverage map.
    
    Args:
        aoi: Area of Interest polygon
        passes: List of passes
        tasking_results: Optional tasking results
    
    Returns:
        BytesIO object with PNG image
    """
    return StaticMapExporter.create_map_image(
        aoi=aoi,
        passes=passes,
        tasking_results=tasking_results,
        width=800,
        height=600,
        dpi=150,
        show_legend=True
    )
