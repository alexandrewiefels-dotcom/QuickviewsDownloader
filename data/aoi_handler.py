# ============================================================================
# FILE: data/aoi_handler.py – gestion des AOI (KML, GeoJSON, ZIP/Shapefile)
# + nettoyage automatique des KML (suppression des trous)
# + extraction manuelle des coordonnées KML en dernier recours
# + logs détaillés pour le débogage
# ============================================================================
import os
import tempfile
import zipfile
import math
from typing import Optional, Tuple
import geopandas as gpd
from shapely.geometry import Polygon, MultiPolygon, box
from shapely.ops import unary_union
import streamlit as st
import pyproj
from pathlib import Path
import logging
import xml.etree.ElementTree as ET

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class AOIHandler:
    @staticmethod
    def load_from_filepath(filepath: str) -> Optional[Polygon]:
        """
        Charge un fichier AOI (KML, GeoJSON, ou ZIP contenant un Shapefile).
        Retourne un polygone (ou None en cas d'erreur).
        """
        logger.info(f"[AOIHandler] load_from_filepath: {filepath}")
        try:
            if filepath.lower().endswith('.kml'):
                logger.info("Fichier KML détecté")
                gdf = None
                
                # Stratégie 1 : lecture directe avec geopandas
                try:
                    gdf = gpd.read_file(filepath, driver='KML')
                    if gdf is not None and not gdf.empty:
                        logger.info(f"Lecture directe KML réussie: {len(gdf)} entités")
                    else:
                        logger.warning("Lecture directe KML vide")
                        gdf = None
                except Exception as e:
                    logger.warning(f"Lecture directe KML échouée: {e}")
                    gdf = None

                # Stratégie 2 : nettoyage avec fastkml puis lecture
                if gdf is None or gdf.empty:
                    cleaned_path = AOIHandler._clean_kml(filepath)
                    if cleaned_path:
                        try:
                            gdf = gpd.read_file(cleaned_path, driver='KML')
                            os.unlink(cleaned_path)
                            if gdf is not None and not gdf.empty:
                                logger.info(f"Lecture KML après nettoyage réussie: {len(gdf)} entités")
                            else:
                                logger.warning("KML après nettoyage toujours vide")
                                gdf = None
                        except Exception as e:
                            logger.error(f"Erreur lecture KML nettoyé: {e}")
                            if os.path.exists(cleaned_path):
                                os.unlink(cleaned_path)
                            gdf = None

                # Stratégie 3 : extraction manuelle des coordonnées
                if gdf is None or gdf.empty:
                    logger.info("Tentative d'extraction manuelle des coordonnées KML")
                    geom = AOIHandler._extract_polygon_from_kml(filepath)
                    if geom and isinstance(geom, Polygon):
                        logger.info("Extraction manuelle réussie")
                        return geom
                    else:
                        logger.error("Impossible d'extraire un polygone du KML")
                        st.error("The KML file does not contain a valid polygon.")
                        return None

            elif filepath.lower().endswith('.geojson'):
                logger.info("Fichier GeoJSON détecté")
                gdf = gpd.read_file(filepath)
                logger.info(f"GeoDataFrame lu: {len(gdf)} entités")
            elif filepath.lower().endswith('.zip'):
                logger.info("Fichier ZIP détecté, recherche d'un Shapefile...")
                with tempfile.TemporaryDirectory() as tmpdir:
                    with zipfile.ZipFile(filepath, 'r') as zip_ref:
                        zip_ref.extractall(tmpdir)
                    shp_files = []
                    for root, dirs, files in os.walk(tmpdir):
                        for file in files:
                            if file.endswith('.shp'):
                                shp_files.append(os.path.join(root, file))
                    if not shp_files:
                        logger.error("Aucun fichier .shp trouvé dans l'archive ZIP")
                        st.error("No .shp file found in the ZIP archive.")
                        return None
                    gdf = gpd.read_file(shp_files[0])
                    logger.info(f"Shapefile chargé: {len(gdf)} entités")
            else:
                logger.error(f"Format de fichier non supporté: {filepath}")
                st.error("Unsupported file format. Please use KML, GeoJSON, or ZIP (Shapefile).")
                return None

            # Si on a un GeoDataFrame (GeoJSON, Shapefile, ou KML réussi)
            if gdf is not None and not gdf.empty:
                gdf = gdf.to_crs('EPSG:4326')
                geom = unary_union(gdf.geometry)
                logger.info(f"Géométrie unifiée: type={geom.geom_type}, valide={geom.is_valid}")

                if not geom.is_valid:
                    logger.warning("Géométrie invalide, tentative de réparation")
                    from shapely.validation import make_valid
                    geom = make_valid(geom)

                if geom.geom_type == 'MultiPolygon':
                    logger.info("MultiPolygon détecté, sélection du polygone le plus grand")
                    geom = max(geom.geoms, key=lambda g: g.area)

                if geom.geom_type != 'Polygon':
                    logger.error(f"La géométrie finale n'est pas un Polygon: {geom.geom_type}")
                    st.error(f"Final geometry is not a polygon: {geom.geom_type}")
                    return None

                logger.info(f"Polygone final: {geom.bounds}")
                return geom
            else:
                logger.error("GeoDataFrame vide après toutes les tentatives")
                return None

        except Exception as e:
            logger.exception(f"Erreur lors du chargement: {e}")
            st.error(f"Error loading AOI: {str(e)}")
            return None

    @staticmethod
    def _extract_polygon_from_kml(kml_path: str) -> Optional[Polygon]:
        """
        Extrait manuellement les coordonnées d'un polygone depuis un fichier KML
        en utilisant xml.etree.ElementTree.
        """
        try:
            tree = ET.parse(kml_path)
            root = tree.getroot()
            ns = {'kml': 'http://www.opengis.net/kml/2.2'}
            coords_elements = root.findall('.//kml:coordinates', ns)
            if not coords_elements:
                coords_elements = root.findall('.//coordinates')
            for elem in coords_elements:
                if elem.text:
                    coord_text = elem.text.strip()
                    points = []
                    for triplet in coord_text.split():
                        parts = triplet.split(',')
                        if len(parts) >= 2:
                            try:
                                lon = float(parts[0])
                                lat = float(parts[1])
                                points.append((lon, lat))
                            except ValueError:
                                continue
                    if len(points) >= 3:
                        poly = Polygon(points)
                        if poly.is_valid and not poly.is_empty:
                            logger.info(f"Polygone extrait avec {len(points)} points")
                            return poly
            logger.warning("Aucune coordonnée valide trouvée dans le KML")
            return None
        except Exception as e:
            logger.error(f"Extraction manuelle échouée: {e}")
            return None

    @staticmethod
    def _clean_kml(input_kml_path: str) -> Optional[str]:
        """
        Nettoie un fichier KML : supprime les trous et ne garde que l'anneau extérieur.
        Retourne le chemin d'un fichier temporaire nettoyé, ou None si échec.
        """
        logger.info(f"[AOIHandler] Nettoyage KML: {input_kml_path}")
        try:
            from fastkml import kml as fkml
            from shapely.geometry import shape
            from lxml import etree

            with open(input_kml_path, 'rb') as f:
                content = f.read()
            k = fkml.KML()
            k.from_string(content)

            features_list = k.features
            if not features_list:
                logger.warning("Aucune feature trouvée dans le KML avec fastkml")
                return None

            def get_exterior_rings(geom):
                rings = []
                if isinstance(geom, Polygon):
                    rings.append(list(geom.exterior.coords))
                elif isinstance(geom, MultiPolygon):
                    for part in geom.geoms:
                        rings.append(list(part.exterior.coords))
                return rings

            # Construction d'un nouveau KML
            ns = {None: "http://www.opengis.net/kml/2.2"}
            root = etree.Element("kml", nsmap=ns)
            document = etree.SubElement(root, "Document", id="root_doc")
            etree.SubElement(document, "visibility").text = "1"
            folder_name = Path(input_kml_path).stem
            folder = etree.SubElement(document, "Folder")
            etree.SubElement(folder, "name").text = folder_name
            etree.SubElement(folder, "visibility").text = "1"

            def process_features(features):
                for feature in features:
                    if isinstance(feature, fkml.Placemark) and feature.geometry is not None:
                        geom = shape(feature.geometry)
                        rings = get_exterior_rings(geom)
                        if not rings:
                            continue
                        placemark = etree.SubElement(folder, "Placemark", id=f"{folder_name}.1")
                        etree.SubElement(placemark, "name").text = feature.name or folder_name
                        etree.SubElement(placemark, "visibility").text = "1"
                        style = etree.SubElement(placemark, "Style")
                        l_style = etree.SubElement(style, "LineStyle")
                        etree.SubElement(l_style, "color").text = "ff0000ff"
                        etree.SubElement(l_style, "width").text = "1"
                        p_style = etree.SubElement(style, "PolyStyle")
                        etree.SubElement(p_style, "fill").text = "0"
                        etree.SubElement(p_style, "outline").text = "1"
                        mg = etree.SubElement(placemark, "MultiGeometry")
                        for ring_coords in rings:
                            poly_node = etree.SubElement(mg, "Polygon")
                            out_bound = etree.SubElement(poly_node, "outerBoundaryIs")
                            lin_ring = etree.SubElement(out_bound, "LinearRing")
                            coords_str = " ".join([f"{c[0]},{c[1]}" for c in ring_coords])
                            etree.SubElement(lin_ring, "coordinates").text = coords_str
                    elif hasattr(feature, 'features'):
                        process_features(feature.features)

            process_features(features_list)

            schema = etree.SubElement(document, "Schema", id=folder_name, name=folder_name)
            etree.SubElement(schema, "SimpleField", type="int", name="id")
            etree.SubElement(schema, "SimpleField", type="string", name="area_code")

            fd, temp_path = tempfile.mkstemp(suffix='.kml')
            os.close(fd)
            tree = etree.ElementTree(root)
            tree.write(temp_path, pretty_print=True, xml_declaration=True, encoding="UTF-8")
            logger.info(f"KML nettoyé sauvegardé: {temp_path}")
            return temp_path
        except Exception as e:
            logger.error(f"Erreur lors du nettoyage KML: {e}")
            return None

    @staticmethod
    def calculate_area(geom) -> Tuple[float, str]:
        if geom is None:
            return 0, "km²"
        if geom.geom_type == 'Polygon':
            coords = list(geom.exterior.coords)
        elif geom.geom_type == 'MultiPolygon':
            coords = list(geom.geoms[0].exterior.coords)
        else:
            return 0, "km²"
        lons = [c[0] for c in coords]
        lats = [c[1] for c in coords]
        geod = pyproj.Geod(ellps='WGS84')
        area_m2, _ = geod.polygon_area_perimeter(lons, lats)
        area_km2 = abs(area_m2) / 1_000_000
        if area_km2 < 0.01:
            return area_km2 * 1_000_000, "m²"
        elif area_km2 < 1:
            return area_km2 * 100, "ha"
        else:
            return area_km2, "km²"

    @staticmethod
    def create_test_square(lat: float, lon: float, area_km2: float = 100) -> Polygon:
        side_km = math.sqrt(area_km2)
        side_deg = side_km / 111.32 / max(math.cos(math.radians(lat)), 0.01)
        half = side_deg / 2
        return box(lon - half, lat - half, lon + half, lat + half)
