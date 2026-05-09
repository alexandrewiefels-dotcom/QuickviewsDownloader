#!/usr/bin/env python3
"""
Visual test for L.ImageWarpLayer.
Fetches a real quickview image, builds a standalone Leaflet HTML,
opens it headlessly with Playwright, and saves a screenshot.

Run: python test_quickview_visual.py
Output: logs/test_quickview.html  (open in browser for live inspection)
        logs/test_quickview.png   (Playwright screenshot for automated check)
"""
import asyncio
import base64
import json
import sys
from pathlib import Path

import requests

# ── Target scene (GF5B Alsace, confirmed fetched successfully in session log) ──
URL = (
    "https://quickview.obs.cn-north-10.myhuaweicloud.com"
    "/GF5B/24407/232/82/GF5B_AHSI_E8.4_N48.5_20260409_024407_L10001337615.jpg"
)
CORNERS = [
    [48.869562, 8.118382],   # NW
    [48.726257, 8.916978],   # NE
    [48.184861, 8.694130],   # SE
    [48.327154, 7.903745],   # SW
]
CENTER = [48.53, 8.41]
ZOOM   = 9

HEADERS = {
    "Referer":    "https://www.sasclouds.com/",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
}

OUT_DIR     = Path(__file__).parent / "logs"
HTML_FILE   = OUT_DIR / "test_quickview.html"
SCREENSHOT  = OUT_DIR / "test_quickview.png"

# ── Warp layer JS — exact copy of _WARP_LAYER_JS from map_utils.py ─────────────
# (minus the outer <script> tags; those are added in the HTML template)
WARP_LAYER_JS = """
(function(){
  if (window._ImageWarpLayerDefined) return;
  window._ImageWarpLayerDefined = true;
  L.ImageWarpLayer = L.Layer.extend({
    initialize: function(src, corners, options) {
      this._corners = corners;
      this._opacity = (options && options.opacity != null) ? options.opacity : 1.0;
      this._img = new Image();
      this._ready = false;
      var self = this;
      this._img.onload = function() {
        self._ready = true;
        qvLog('Image decoded | ' + self._img.naturalWidth + 'x' + self._img.naturalHeight + 'px');
        if (self._map) self._draw();
      };
      this._img.onerror = function() {
        qvLog('ERROR: image decode FAILED');
        document.getElementById('status').textContent = 'IMG ERROR';
      };
      this._img.src = src;
    },
    onAdd: function(map) {
      this._map = map;
      qvLog('onAdd fired | map ID=' + map.getContainer().id);
      if (!this._canvas) {
        this._canvas = document.createElement('canvas');
        this._canvas.style.cssText = 'position:absolute;pointer-events:none;';
        this._canvas.id = 'qv-canvas';
      }
      map.getPanes().overlayPane.appendChild(this._canvas);
      map.on('moveend zoomend viewreset', this._draw, this);
      this._draw();
    },
    onRemove: function(map) {
      if (this._canvas && this._canvas.parentNode)
        this._canvas.parentNode.removeChild(this._canvas);
      map.off('moveend zoomend viewreset', this._draw, this);
      this._map = null;
    },
    _draw: function() {
      var map = this._map;
      if (!map || !this._ready) return;
      var size = map.getSize();
      var c = this._canvas;
      c.width = size.x; c.height = size.y;
      var tl = map.containerPointToLayerPoint([0, 0]);
      L.DomUtil.setPosition(c, tl);
      var ctx = c.getContext('2d');
      ctx.clearRect(0, 0, size.x, size.y);
      ctx.globalAlpha = this._opacity;
      var pts = this._corners.map(function(ll) {
        var p = map.latLngToLayerPoint(L.latLng(ll[0], ll[1]));
        return [p.x - tl.x, p.y - tl.y];
      });
      var iw = this._img.naturalWidth, ih = this._img.naturalHeight;
      if (!iw || !ih) { qvLog('ERROR: naturalWidth/Height=0'); return; }
      ctx.save();
      ctx.transform(
        (pts[1][0]-pts[0][0])/iw, (pts[1][1]-pts[0][1])/iw,
        (pts[3][0]-pts[0][0])/ih, (pts[3][1]-pts[0][1])/ih,
        pts[0][0], pts[0][1]
      );
      ctx.drawImage(this._img, 0, 0);
      ctx.restore();
      // Stamp a visible label so the screenshot proves _draw was reached
      ctx.resetTransform ? ctx.resetTransform() : ctx.setTransform(1,0,0,1,0,0);
      ctx.font = 'bold 20px monospace';
      ctx.lineWidth = 4;
      ctx.strokeStyle = '#000';
      ctx.fillStyle  = '#00ff44';
      ctx.strokeText('QV RENDERED', 12, 36);
      ctx.fillText  ('QV RENDERED', 12, 36);
      qvLog('_draw OK | canvas=' + c.width + 'x' + c.height
            + ' pts[0]=(' + pts[0][0].toFixed(0) + ',' + pts[0][1].toFixed(0) + ')');
      document.getElementById('status').textContent = 'RENDERED';
      document.getElementById('status').style.background = '#007700';
      document.getElementById('status').dataset.rendered = '1';
    }
  });
})();
"""

HTML_TEMPLATE = """\
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>Quickview warp-layer test</title>
  <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
  <style>
    body {{ margin:0; font-family:monospace; background:#1a1a1a; color:#eee; }}
    #map {{ width:100vw; height:75vh; }}
    #logbox {{ padding:8px; height:25vh; overflow-y:auto;
               background:#111; color:#0f0; font-size:12px; line-height:1.5; }}
    #status {{
      position:fixed; top:10px; right:10px; z-index:9999;
      padding:8px 18px; border-radius:6px; font-weight:bold; font-size:16px;
      background:#880000; color:#fff; transition:background 0.3s;
    }}
  </style>
</head>
<body>
  <div id="status">LOADING…</div>
  <div id="map"></div>
  <div id="logbox"></div>

  <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
  <!-- image data must be declared BEFORE the map setup script uses it -->
  <script>var IMG_SRC = {img_src_js};</script>
  <script>
    // -- Debug log panel ------------------------------------------------------
    var _lines = [];
    function qvLog(msg) {{
      var ts = new Date().toISOString().slice(11,23);
      _lines.push(ts + ' | ' + msg);
      var box = document.getElementById('logbox');
      box.innerHTML = _lines.map(function(l){{return '<div>'+l+'</div>';}}).join('');
      box.scrollTop = box.scrollHeight;
      console.log('[QV] ' + msg);
    }}

    // -- L.ImageWarpLayer class -----------------------------------------------
    {warp_js}

    // -- Map setup ------------------------------------------------------------
    qvLog('Leaflet loaded - creating map');
    var map = L.map('map').setView([{lat}, {lon}], {zoom});
    L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
      attribution: 'OSM'
    }}).addTo(map);

    var corners = {corners_js};
    qvLog('IMG_SRC defined: ' + (typeof IMG_SRC !== 'undefined' ? IMG_SRC.substring(0,40)+'...' : 'UNDEFINED'));
    qvLog('Instantiating L.ImageWarpLayer | ' + corners.length + ' corners');
    new L.ImageWarpLayer(IMG_SRC, corners, {{opacity: 0.85}}).addTo(map);
    qvLog('addTo() called - waiting for image onload...');
  </script>
</body>
</html>
"""


def build_html(img_src: str) -> str:
    return HTML_TEMPLATE.format(
        warp_js     = WARP_LAYER_JS,
        lat         = CENTER[0],
        lon         = CENTER[1],
        zoom        = ZOOM,
        corners_js  = json.dumps(CORNERS),
        img_src_js  = json.dumps(img_src),   # properly escaped JS string literal
    )


async def screenshot(html_path: Path, out_path: Path) -> bool:
    """
    Open html_path in headless Chrome via CDP.
    Serves the file over localhost HTTP so CDN requests (Leaflet) are not blocked.
    Routes incoming CDP messages by ID (responses) vs. method (events).
    Waits up to 12 s for the quickview canvas to render, then screenshots.
    """
    import asyncio
    import base64 as _b64
    import json as _json
    import subprocess
    import threading
    import time
    import urllib.request
    import http.server
    import websockets

    CHROME     = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
    DEBUG_PORT = 9222
    HTTP_PORT  = 18765

    # Serve the HTML directory (logs/) over HTTP so CDN URLs are not blocked by Chrome
    import functools
    handler = functools.partial(
        http.server.SimpleHTTPRequestHandler,
        directory=str(html_path.parent),
    )
    httpd = http.server.HTTPServer(("127.0.0.1", HTTP_PORT), handler)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()

    # URL relative to the logs/ directory (which is the HTML parent)
    url = f"http://127.0.0.1:{HTTP_PORT}/{html_path.name}"

    proc = subprocess.Popen([
        CHROME, "--headless=new", "--disable-gpu", "--no-sandbox",
        f"--remote-debugging-port={DEBUG_PORT}",
        "--window-size=1280,900", url,
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
       cwd=str(html_path.parent))

    ws_url = None
    for _ in range(20):
        try:
            raw  = urllib.request.urlopen(f"http://localhost:{DEBUG_PORT}/json", timeout=2).read()
            tabs = _json.loads(raw)
            print(f"  [CDP] targets: {[t.get('type','?') + ' ' + t.get('url','?')[:60] for t in tabs]}")
            # Pick the page tab pointing at our URL, not an extension or devtools page
            page_tabs = [t for t in tabs if t.get("type") == "page"]
            if page_tabs:
                ws_url = page_tabs[0]["webSocketDebuggerUrl"]
                break
        except Exception as ex:
            print(f"  [CDP] waiting for devtools… ({ex})")
            time.sleep(0.5)

    if not ws_url:
        proc.kill()
        print("ERROR: Chrome devtools did not start")
        return False
    print(f"  [CDP] connected to: {ws_url[:80]}")

    console_msgs = []
    rendered     = False

    try:
        async with websockets.connect(ws_url, max_size=50 * 1024 * 1024) as ws:
            # ── message router ────────────────────────────────────────────────
            pending   = {}          # id → asyncio.Future
            events    = asyncio.Queue()
            _msg_id   = 0

            async def _pump():
                async for raw in ws:
                    msg = _json.loads(raw)
                    if "id" in msg and msg["id"] in pending:
                        pending.pop(msg["id"]).set_result(msg)
                    elif "method" in msg:
                        await events.put(msg)

            pump_task = asyncio.ensure_future(_pump())

            async def cdp(method, params=None):
                nonlocal _msg_id
                _msg_id += 1
                fut = asyncio.get_event_loop().create_future()
                pending[_msg_id] = fut
                await ws.send(_json.dumps({"id": _msg_id, "method": method,
                                           "params": params or {}}))
                return await asyncio.wait_for(fut, timeout=10)

            # Enable domains
            await cdp("Page.enable")
            await cdp("Runtime.enable")

            # The page is already loading (URL passed on Chrome's command line).
            # Drain any queued events (loadEventFired may already be in the buffer).
            # Then poll the DOM directly — no reliance on event timing.
            await asyncio.sleep(2)          # give tiles + image decode time to start
            while not events.empty():
                evt = events.get_nowait()
                if evt.get("method") == "Runtime.consoleAPICalled":
                    args = evt.get("params", {}).get("args", [])
                    text = " ".join(str(a.get("value", "")) for a in args)
                    console_msgs.append(text)
                    print(f"  [console] {text}")

            # Poll up to 12 s for the canvas _draw() to complete
            deadline = asyncio.get_event_loop().time() + 12
            while asyncio.get_event_loop().time() < deadline:
                # Drain console events accumulated while sleeping
                while not events.empty():
                    evt = events.get_nowait()
                    if evt.get("method") == "Runtime.consoleAPICalled":
                        args = evt.get("params", {}).get("args", [])
                        text = " ".join(str(a.get("value", "")) for a in args)
                        console_msgs.append(text)
                        print(f"  [console] {text}")

                resp = await cdp("Runtime.evaluate", {
                    "expression": (
                        "JSON.stringify({"
                        "  readyState: document.readyState,"
                        "  title: document.title,"
                        "  statusEl: document.getElementById('status') ? "
                        "    document.getElementById('status').textContent : 'MISSING',"
                        "  rendered: document.getElementById('status') ? "
                        "    (document.getElementById('status').dataset.rendered || 'no') : 'MISSING'"
                        "})"
                    ),
                    "returnByValue": True,
                })
                r_obj   = resp.get("result", {}).get("result", {})
                val_str = r_obj.get("value")
                exc     = resp.get("result", {}).get("exceptionDetails")
                if exc:
                    print(f"  [poll] JS ERROR: {exc.get('text','?')} – {exc.get('exception',{}).get('description','')[:120]}")
                    info = {}
                else:
                    info = _json.loads(val_str) if val_str else {}
                    print(f"  [poll] {info}")
                if info.get("rendered") == "1" or info.get("rendered") == 1:
                    rendered = True
                    print("  [CDP] Canvas rendered — taking screenshot")
                    break
                await asyncio.sleep(1)

            if not rendered:
                print("  [CDP] Timeout — screenshotting current state")

            resp = await cdp("Page.captureScreenshot",
                             {"format": "png", "captureBeyondViewport": False})
            out_path.write_bytes(_b64.b64decode(resp["result"]["data"]))

    finally:
        try:
            pump_task.cancel()
        except Exception:
            pass
        proc.kill()
        httpd.shutdown()

    print("\n-- Browser console ------------------------------------------")
    for m in console_msgs:
        print(" ", m)
    print("-------------------------------------------------------------\n")
    return rendered


def main():
    OUT_DIR.mkdir(exist_ok=True)

    # 1. Fetch image
    print(f"Fetching: {URL}")
    resp = requests.get(URL, timeout=30, headers=HEADERS)
    if resp.status_code != 200:
        print(f"FAIL: HTTP {resp.status_code}")
        sys.exit(1)
    ct = resp.headers.get("Content-Type", "image/jpeg").split(";")[0].strip()
    b64 = base64.b64encode(resp.content).decode()
    img_src = f"data:{ct};base64,{b64}"
    print(f"OK: {len(resp.content)//1024} KB, MIME={ct}")

    # 2. Write HTML
    html = build_html(img_src)
    HTML_FILE.write_text(html, encoding="utf-8")
    print(f"HTML written: {HTML_FILE} ({len(html)//1024} KB)")

    # 3. Playwright screenshot
    print("Launching headless Chromium…")
    rendered = asyncio.run(screenshot(HTML_FILE, SCREENSHOT))

    # 4. Result
    if rendered:
        print(f"PASS — quickview rendered. Screenshot: {SCREENSHOT}")
    else:
        print(f"FAIL — status never reached RENDERED. Screenshot saved for inspection: {SCREENSHOT}")
        print(f"       Open {HTML_FILE} in a browser to debug interactively.")
        sys.exit(1)


if __name__ == "__main__":
    main()
