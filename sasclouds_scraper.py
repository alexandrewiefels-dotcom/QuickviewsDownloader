"""
Fully automated SASClouds scraper – no manual interaction.
Accepts AOI bounding box, date range, cloud max via command line arguments.
"""

import re
import json
import time
import sys
from pathlib import Path
from datetime import datetime
import requests
from PIL import Image
from playwright.sync_api import sync_playwright

# Selectors (same as your original)
ROW_SELECTOR = "tr.ant-table-row-level-0"
THUMBNAIL_SELECTOR = ".query-standard-result__quick"
MODAL_CONTAINER = ".ant-modal"
MODAL_IMG = ".quickImg"
MODAL_CLOSE = ".ant-modal-close, .ant-modal-close-x"
NEXT_PAGE_BUTTON = ".ant-pagination-next:not(.ant-pagination-disabled)"

# ----------------------------------------------------------------------
# Helper functions (unchanged – copy from your original script)
# ----------------------------------------------------------------------
def create_output_folder() -> Path:
    base_dir = Path("./sasclouds_scrapes")
    base_dir.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = base_dir / timestamp
    output_dir.mkdir(parents=True, exist_ok=True)
    print(f"📁 Output folder: {output_dir}")
    return output_dir

def extract_image_name_from_thumb(url: str) -> str:
    filename = url.split('/')[-1]
    if '_64.jpg' in filename:
        return filename.replace('_64.jpg', '')
    elif '_64.jpeg' in filename:
        return filename.replace('_64.jpeg', '')
    else:
        return filename.rsplit('.', 1)[0]

def download_image(url: str, path: Path) -> bool:
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        resp = requests.get(url, timeout=20, headers=headers)
        if resp.status_code == 200:
            path.write_bytes(resp.content)
            return True
    except Exception:
        return False

def create_rotated_world_file(img_path: Path, coords: dict):
    try:
        img = Image.open(img_path)
        width, height = img.size
        img.close()
    except Exception:
        return
    tl = coords.get("Top left")
    tr = coords.get("Top right")
    bl = coords.get("Bottom left")
    if not (tl and tr and bl):
        print("      Missing corners for world file")
        return
    x_tl, y_tl = tl
    x_tr, y_tr = tr
    x_bl, y_bl = bl
    A = (x_tr - x_tl) / width
    B = (x_bl - x_tl) / height
    D = (y_tr - y_tl) / width
    E = (y_bl - y_tl) / height
    C = x_tl
    F = y_tl
    world_lines = [f"{A:.10f}", f"{D:.10f}", f"{B:.10f}", f"{E:.10f}", f"{C:.10f}", f"{F:.10f}"]
    world_path = img_path.with_suffix(".jgw")
    world_path.write_text("\n".join(world_lines))
    prj_path = img_path.with_suffix(".prj")
    prj_content = 'GEOGCS["WGS 84",DATUM["WGS_1984",SPHEROID["WGS 84",6378137,298.257223563,AUTHORITY["EPSG","7030"]],AUTHORITY["EPSG","6326"]],PRIMEM["Greenwich",0,AUTHORITY["EPSG","8901"]],UNIT["degree",0.0174532925199433,AUTHORITY["EPSG","9122"]],AUTHORITY["EPSG","4326"]]'
    prj_path.write_text(prj_content)

def extract_coords_from_text(text: str) -> dict:
    coords = {}
    patterns = {
        "Top left": r"Top left lon/lat\s+([-+]?\d*\.\d+),([-+]?\d*\.\d+)",
        "Top right": r"Top right lon/lat\s+([-+]?\d*\.\d+),([-+]?\d*\.\d+)",
        "Bottom right": r"Bottom right lon/lat\s+([-+]?\d*\.\d+),([-+]?\d*\.\d+)",
        "Bottom left": r"Bottom left lon/lat\s+([-+]?\d*\.\d+),([-+]?\d*\.\d+)",
    }
    for key, pattern in patterns.items():
        match = re.search(pattern, text)
        if match:
            coords[key] = (float(match.group(1)), float(match.group(2)))
    return coords

def polygon_from_coords(coords: dict) -> list | None:
    order = ["Top left", "Top right", "Bottom right", "Bottom left"]
    points = [list(coords[k]) for k in order if k in coords]
    if len(points) != 4:
        return None
    points.append(points[0])
    return points

def parse_metadata(text: str) -> dict:
    metadata = {}
    lines = text.splitlines()
    for i, line in enumerate(lines):
        line = line.strip()
        if "Satellite" in line and i+1 < len(lines):
            metadata["satellite"] = lines[i+1].strip()
        elif "Sensor" in line and i+1 < len(lines):
            metadata["sensor"] = lines[i+1].strip()
        elif "Acquire time" in line and i+1 < len(lines):
            metadata["date"] = lines[i+1].strip()
        elif "Cloudage" in line and i+1 < len(lines):
            metadata["cloud_cover"] = lines[i+1].strip().replace("%", "")
        elif "Resolution" in line and i+1 < len(lines):
            metadata["resolution"] = lines[i+1].strip()
        elif "Orbit number" in line and i+1 < len(lines):
            metadata["orbit"] = lines[i+1].strip()
        elif "Product ID" in line and i+1 < len(lines):
            metadata["product_id"] = lines[i+1].strip()
    return metadata

def close_modal_safe(page):
    try:
        close_btn = page.query_selector(MODAL_CLOSE)
        if close_btn and close_btn.is_visible():
            close_btn.click()
            page.wait_for_timeout(500)
            page.wait_for_selector(MODAL_CONTAINER, state="hidden", timeout=2000)
    except Exception:
        pass

def scrape_page(page, page_num, all_features, output_dir):
    rows = page.query_selector_all(ROW_SELECTOR)
    print(f"\n📄 Page {page_num}: {len(rows)} rows", flush=True)
    for idx, row in enumerate(rows):
        print(f"   Processing row {idx+1}/{len(rows)}", flush=True)
        row.scroll_into_view_if_needed()
        time.sleep(0.3)
        close_modal_safe(page)
        time.sleep(0.3)
        thumb = row.query_selector(THUMBNAIL_SELECTOR)
        if not thumb:
            print("      ❌ No thumbnail, skipping", flush=True)
            continue
        thumb_url = thumb.get_attribute("src")
        try:
            thumb.evaluate("el => el.click()")
        except Exception:
            thumb.click(force=True, timeout=3000)
        try:
            page.wait_for_selector(MODAL_CONTAINER, timeout=8000)
            page.wait_for_selector(MODAL_IMG, timeout=8000)
        except Exception as e:
            print(f"      ❌ Modal did not open: {e}", flush=True)
            continue
        modal = page.query_selector(MODAL_CONTAINER)
        if not modal:
            continue
        modal_text = modal.inner_text()
        img = modal.query_selector(MODAL_IMG)
        full_img_url = img.get_attribute("src") if img else None
        coords = extract_coords_from_text(modal_text)
        polygon = polygon_from_coords(coords)
        if not polygon:
            print("      ❌ No polygon coordinates, skipping", flush=True)
            close_modal_safe(page)
            continue
        metadata = parse_metadata(modal_text)
        base_name = extract_image_name_from_thumb(thumb_url) if thumb_url else f"scene_{len(all_features)+1:04d}"
        img_path = output_dir / f"{base_name}.jpg"
        if full_img_url and download_image(full_img_url, img_path):
            print(f"      ✅ Downloaded: {img_path.name}", flush=True)
            create_rotated_world_file(img_path, coords)
            print(f"      ✅ World file created", flush=True)
        properties = {
            "index": len(all_features) + 1,
            "satellite": metadata.get("satellite"),
            "sensor": metadata.get("sensor"),
            "date": metadata.get("date"),
            "cloud_cover": metadata.get("cloud_cover"),
            "resolution": metadata.get("resolution"),
            "orbit": metadata.get("orbit"),
            "product_id": metadata.get("product_id"),
            "image_name": base_name
        }
        properties = {k: v for k, v in properties.items() if v is not None}
        feature = {"type": "Feature", "geometry": {"type": "Polygon", "coordinates": [polygon]}, "properties": properties}
        all_features.append(feature)
        print(f"      ✅ Extracted {metadata.get('satellite', 'unknown')} - {metadata.get('date', 'unknown')}", flush=True)
        close_modal_safe(page)
        time.sleep(0.5)
    return len(rows)

# ----------------------------------------------------------------------
# Automation functions for AOI, date, cloud, search
# ----------------------------------------------------------------------
def set_aoi_rectangle(page, bbox):
    """
    Draw a rectangle on the Leaflet map using JavaScript.
    bbox = [west, south, east, north] (decimal degrees)
    """
    js = f"""
    (function() {{
        // Try to find the Leaflet map object (it may be stored globally)
        let map = null;
        if (window.map) map = window.map;
        else if (window.leafletMap) map = window.leafletMap;
        else {{
            // Try to get the map from the DOM
            const mapDiv = document.querySelector('.leaflet-container');
            if (mapDiv && mapDiv._leaflet_id) {{
                map = mapDiv.__map;
            }}
        }}
        if (!map) return false;
        // Remove existing rectangle if any
        if (window._aoiRectangle) {{
            map.removeLayer(window._aoiRectangle);
        }}
        const bounds = [[{bbox[1]}, {bbox[0]}], [{bbox[3]}, {bbox[2]}]];
        window._aoiRectangle = L.rectangle(bounds, {{color: "#ff0000", weight: 2, fillOpacity: 0.2}}).addTo(map);
        map.fitBounds(bounds);
        return true;
    }})();
    """
    try:
        # Wait a moment for the map to be fully initialised
        time.sleep(2)
        result = page.evaluate(js)
        print(f"   AOI set: {'✅' if result else '⚠️ (map not found)'}", flush=True)
    except Exception as e:
        print(f"   Error setting AOI: {e}", flush=True)

def set_date_range(page, start_date, end_date):
    """Automatically fill the Ant Design RangePicker."""
    try:
        # Click the range picker to open
        picker = page.query_selector(".ant-picker")
        if picker:
            picker.click()
            time.sleep(0.5)
            # Find start and end inputs in the dropdown
            start_input = page.query_selector(".ant-picker-panel input:first-child")
            if start_input:
                start_input.fill(start_date)
            end_input = page.query_selector(".ant-picker-panel input:last-child")
            if end_input:
                end_input.fill(end_date)
            # Confirm by pressing Enter or clicking OK
            page.keyboard.press("Enter")
            time.sleep(0.5)
        else:
            # Fallback to separate date inputs
            start_el = page.query_selector("input[name='startDate']")
            if start_el:
                start_el.fill(start_date)
            end_el = page.query_selector("input[name='endDate']")
            if end_el:
                end_el.fill(end_date)
        print(f"   Date range set: {start_date} to {end_date}", flush=True)
    except Exception as e:
        print(f"   Error setting date range: {e}", flush=True)

def set_cloud_cover(page, max_cloud):
    """Set the cloud slider value."""
    try:
        slider = page.query_selector(".ant-slider")
        if slider:
            # Ant Design slider: we can set the value via JavaScript
            js = f"""
            const slider = document.querySelector('.ant-slider');
            if (slider) {{
                const track = slider.querySelector('.ant-slider-track');
                const handle = slider.querySelector('.ant-slider-handle');
                if (handle) {{
                    handle.setAttribute('aria-valuenow', {max_cloud});
                    const percent = {max_cloud} / 100;
                    if (track) {{
                        track.style.left = '0%';
                        track.style.width = (percent * 100) + '%';
                    }}
                    if (handle) {{
                        handle.style.left = (percent * 100) + '%';
                    }}
                    // Trigger input event to update any bound data
                    const inputEvent = new Event('input', {{ bubbles: true }});
                    handle.dispatchEvent(inputEvent);
                }}
            }}
            """
            page.evaluate(js)
            print(f"   Cloud cover set to: {max_cloud}%", flush=True)
        else:
            # Try numeric input if slider not found
            cloud_input = page.query_selector("input[placeholder*='cloud']")
            if cloud_input:
                cloud_input.fill(str(max_cloud))
    except Exception as e:
        print(f"   Error setting cloud cover: {e}", flush=True)

def click_search(page):
    """Click the Search button."""
    try:
        search_btn = page.query_selector("button.ant-btn-primary")
        if search_btn:
            search_btn.click()
            print("   Search button clicked", flush=True)
            return True
        else:
            print("   Search button not found", flush=True)
            return False
    except Exception as e:
        print(f"   Error clicking search: {e}", flush=True)
        return False

# ----------------------------------------------------------------------
# Main (automated)
# ----------------------------------------------------------------------
def main():
    import sys
    # Parse command line arguments
    output_dir = None
    bbox = None
    start_date = None
    end_date = None
    max_cloud = 20

    i = 1
    while i < len(sys.argv):
        if sys.argv[i] == "--output" and i+1 < len(sys.argv):
            output_dir = Path(sys.argv[i+1])
            i += 2
        elif sys.argv[i] == "--bbox" and i+4 < len(sys.argv):
            bbox = [float(sys.argv[i+1]), float(sys.argv[i+2]), float(sys.argv[i+3]), float(sys.argv[i+4])]
            i += 5
        elif sys.argv[i] == "--start" and i+1 < len(sys.argv):
            start_date = sys.argv[i+1]
            i += 2
        elif sys.argv[i] == "--end" and i+1 < len(sys.argv):
            end_date = sys.argv[i+1]
            i += 2
        elif sys.argv[i] == "--cloud" and i+1 < len(sys.argv):
            max_cloud = int(sys.argv[i+1])
            i += 2
        else:
            i += 1

    if output_dir is None:
        output_dir = create_output_folder()
    else:
        output_dir.mkdir(parents=True, exist_ok=True)
        print(f"📁 Output folder: {output_dir}", flush=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=['--no-sandbox', '--disable-dev-shm-usage'])
        context = browser.new_context(viewport={"width": 1280, "height": 800})
        page = context.new_page()

        print("🌐 Navigating to SASClouds catalog...", flush=True)
        page.goto("https://www.sasclouds.com/english/normal/", wait_until="networkidle")
        print("✅ Page loaded", flush=True)

        # Apply filters
        if bbox:
            set_aoi_rectangle(page, bbox)
        if start_date and end_date:
            set_date_range(page, start_date, end_date)
        set_cloud_cover(page, max_cloud)

        # Click Search
        if not click_search(page):
            browser.close()
            return

        # Wait for results
        print("⏳ Waiting for results to load...", flush=True)
        try:
            page.wait_for_selector(ROW_SELECTOR, timeout=60000)
            print("✅ Results loaded", flush=True)
        except:
            print("❌ No results found after 60 seconds", flush=True)
            browser.close()
            return

        # Scrape
        all_features = []
        page_num = 1
        while True:
            rows = scrape_page(page, page_num, all_features, output_dir)
            if rows == 0:
                break
            next_btn = page.query_selector(NEXT_PAGE_BUTTON)
            if not next_btn:
                break
            next_btn.click()
            page.wait_for_timeout(3000)
            try:
                page.wait_for_selector(ROW_SELECTOR, timeout=10000)
            except:
                break
            page_num += 1

        geojson_path = output_dir / "footprints.geojson"
        with open(geojson_path, "w", encoding="utf-8") as f:
            json.dump({"type": "FeatureCollection", "features": all_features}, f, indent=2)
        print(f"\n✅ Scraping finished. Total features: {len(all_features)}", flush=True)
        browser.close()

if __name__ == "__main__":
    main()