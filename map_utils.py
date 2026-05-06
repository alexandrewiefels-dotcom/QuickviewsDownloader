# File: map_utils.py
import folium
from streamlit_folium import st_folium
import streamlit as st

def show_aoi_map(geojson):
    """Display a Leaflet map with the AOI polygon."""
    if not geojson:
        return
    try:
        # Extract geometry
        if geojson.get("type") == "FeatureCollection":
            geom = geojson["features"][0]["geometry"]
        elif geojson.get("type") == "Feature":
            geom = geojson["geometry"]
        else:
            geom = geojson
        # Compute bounds
        coords = geom["coordinates"][0]
        lats = [c[1] for c in coords]
        lons = [c[0] for c in coords]
        center = [(min(lats)+max(lats))/2, (min(lons)+max(lons))/2]
        m = folium.Map(location=[center[0], center[1]], zoom_start=6)
        folium.GeoJson(geom, style_function=lambda x: {"color": "blue", "weight": 3, "fillOpacity": 0.2}).add_to(m)
        st_folium(m, width=600, height=400)
    except Exception as e:
        st.warning(f"Could not display AOI on map: {e}")

def show_footprints_map(features):
    """Display a Leaflet map with footprint polygons and popups."""
    if not features:
        return
    # Determine center from first feature
    first_geom = features[0]["geometry"]
    coords = first_geom["coordinates"][0]
    lons = [c[0] for c in coords]
    lats = [c[1] for c in coords]
    center_lat = sum(lats) / len(lats)
    center_lon = sum(lons) / len(lons)
    m = folium.Map(location=[center_lat, center_lon], zoom_start=8)
    for feat in features:
        popup_html = f"""
        <b>{feat['properties']['satellite']} {feat['properties']['sensor']}</b><br>
        Date: {feat['properties']['date']}<br>
        Cloud: {feat['properties']['cloud']}%<br>
        <img src="{feat['properties']['quickview']}" width="200"><br>
        <a href="{feat['properties']['quickview']}" target="_blank">Open full image</a>
        """
        folium.GeoJson(
            feat["geometry"],
            popup=folium.Popup(popup_html, max_width=300),
            style_function=lambda x: {"color": "red", "weight": 2, "fillOpacity": 0.1}
        ).add_to(m)
    st_folium(m, width=800, height=500)