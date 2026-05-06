"""
SASClouds Scraper – extract footprints, full images, world files
"""
import re
import json
import time
from pathlib import Path
from datetime import datetime
import requests
from PIL import Image
from playwright.sync_api import sync_playwright

# -------------------------------
# Configuration
CATALOG_URL = "https://www.sasclouds.com/english/normal/"
ROW_SELECTOR = "tr.ant-table-row-level-0"
THUMBNAIL_SELECTOR = ".query-standard-result__quick"
MODAL_CONTAINER = ".ant-modal"
MODAL_IMG = ".quickImg"
MODAL_CLOSE = ".ant-modal-close, .ant-modal-close-x"
NEXT_PAGE_BUTTON = ".ant-pagination-next:not(.ant-pagination-disabled)"

# -------------------------------
# Helper functions
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
        pass
    return False

def create_rotated_world_file(img_path: Path, coords: dict):
    try:
        img = Image.open(img_path)
        width, height = img.size
        img.close()
    except Exception as e:
        print(f"      Cannot read image size: {e}")
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
    points.append(points[0])  # close ring
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
    print(f"\n📄 Page {page_num}: {len(rows)} rows")
    for idx, row in enumerate(rows):
        print(f"   Processing row {idx+1}/{len(rows)}")
        row.scroll_into_view_if_needed()
        time.sleep(0.3)
        close_modal_safe(page)
        time.sleep(0.3)
        thumb = row.query_selector(THUMBNAIL_SELECTOR)
        if not thumb:
            print("      ❌ No thumbnail, skipping")
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
            print(f"      ❌ Modal did not open: {e}")
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
            print("      ❌ No polygon coordinates, skipping")
            close_modal_safe(page)
            continue
        metadata = parse_metadata(modal_text)
        base_name = extract_image_name_from_thumb(thumb_url) if thumb_url else f"scene_{len(all_features)+1:04d}"
        img_path = output_dir / f"{base_name}.jpg"
        if full_img_url and download_image(full_img_url, img_path):
            print(f"      ✅ Downloaded: {img_path.name}")
            create_rotated_world_file(img_path, coords)
            print(f"      ✅ World file created")
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
        print(f"      ✅ Extracted {metadata.get('satellite', 'unknown')} - {metadata.get('date', 'unknown')}")
        close_modal_safe(page)
        time.sleep(0.5)
    return len(rows)

def main():
    output_dir = create_output_folder()
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(viewport={"width": 1280, "height": 800})
        page = context.new_page()
        print(f"\n🌐 Loading catalog page: {CATALOG_URL}")
        page.goto(CATALOG_URL, wait_until="networkidle")
        print("✅ Page loaded. Please log in, apply filters, and click Search. Waiting 10 seconds...")
        time.sleep(10)
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
        print(f"\n✅ Scraping finished. Total features: {len(all_features)}")
        browser.close()

if __name__ == "__main__":
    main()