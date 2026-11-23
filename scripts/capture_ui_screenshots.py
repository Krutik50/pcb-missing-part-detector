import asyncio
import json
import os
import sys
import subprocess
import time
import base64
import urllib.request
from pathlib import Path
import websockets

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

ARTIFACTS_DIR = Path(r"C:\Users\Admin\.gemini\antigravity\brain\1a7fd3eb-6da0-4cbe-bdae-f0587aee5bf9")
RESULTS_SCREENSHOTS_DIR = ROOT / "results" / "screenshots"
RESULTS_SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
CHROME_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"


class CDPClient:
    def __init__(self, ws_url):
        self.ws_url = ws_url
        self.ws = None
        self.msg_id = 0

    async def connect(self):
        self.ws = await websockets.connect(self.ws_url, max_size=50 * 1024 * 1024)

    async def send(self, method, params=None):
        self.msg_id += 1
        payload = {"id": self.msg_id, "method": method, "params": params or {}}
        await self.ws.send(json.dumps(payload))
        while True:
            resp_raw = await self.ws.recv()
            resp = json.loads(resp_raw)
            if resp.get("id") == self.msg_id:
                return resp.get("result", {})

    async def evaluate(self, expr):
        res = await self.send("Runtime.evaluate", {"expression": expr, "awaitPromise": True, "returnByValue": True})
        return res.get("result", {}).get("value")

    async def capture(self, filename):
        res = await self.send("Page.captureScreenshot", {"format": "png"})
        img_bytes = base64.b64decode(res["data"])

        # Save to artifacts directory
        p1 = ARTIFACTS_DIR / filename
        with open(p1, "wb") as f:
            f.write(img_bytes)

        # Also save to results/screenshots/
        p2 = RESULTS_SCREENSHOTS_DIR / filename
        with open(p2, "wb") as f:
            f.write(img_bytes)

        print(f"[OK] Captured: {filename} ({len(img_bytes)} bytes)")

    async def close(self):
        if self.ws:
            await self.ws.close()


async def run_automation():
    print("Starting background FastAPI server...")
    import uvicorn
    import threading
    from app.main import app

    server_config = uvicorn.Config(app, host="127.0.0.1", port=8000, log_level="warning")
    server = uvicorn.Server(server_config)
    server_thread = threading.Thread(target=server.run, daemon=True)
    server_thread.start()
    time.sleep(1.5)

    print("Launching Chrome headless with remote debugging...")
    temp_dir = os.path.abspath("chrome_temp_profile")
    os.makedirs(temp_dir, exist_ok=True)

    chrome_proc = subprocess.Popen([
        CHROME_PATH,
        "--headless=new",
        "--disable-gpu",
        f"--user-data-dir={temp_dir}",
        "--remote-debugging-port=9222",
        "--remote-allow-origins=*",
        "--window-size=1366,768",
        "about:blank"
    ])
    time.sleep(2.0)

    try:
        # Find WebSocket URL
        req = urllib.request.Request("http://localhost:9222/json/list", headers={"Host": "localhost"})
        with urllib.request.urlopen(req) as resp:
            targets = json.loads(resp.read().decode())
        ws_url = targets[0]["webSocketDebuggerUrl"]
        if "localhost/" in ws_url:
            ws_url = ws_url.replace("localhost/", "127.0.0.1:9222/")

        print(f"Connecting to CDP WebSocket: {ws_url}")
        client = CDPClient(ws_url)
        await client.connect()
        await client.send("Page.enable")
        await client.send("Runtime.enable")

        print("Navigating to http://127.0.0.1:8000...")
        await client.send("Page.navigate", {"url": "http://127.0.0.1:8000"})
        await asyncio.sleep(1.5)

        # 1. SCREENSHOT: Step 1 (Upload Reference)
        print("Capturing Step 1 (Upload Reference)...")
        await client.capture("ui_step1_upload_reference.png")

        # 2. Transition to Step 2: Load Sample Reference
        print("Loading sample reference photo...")
        await client.evaluate("""
        (async () => {
            const res = await fetch('/sample_data/reference.png');
            const blob = await res.blob();
            const file = new File([blob], 'reference.png', { type: 'image/png' });
            const dt = new DataTransfer();
            dt.items.add(file);
            const input = document.getElementById('ref-file-input');
            input.files = dt.files;
            input.dispatchEvent(new Event('change', { bubbles: true }));
        })()
        """)

        # Wait for Step 2 panel to be visible
        for _ in range(40):
            await asyncio.sleep(0.3)
            disp = await client.evaluate("window.getComputedStyle(document.getElementById('panel-step-2')).display")
            if disp != "none":
                break

        await asyncio.sleep(1.0)
        print("Capturing Step 2 (Reference Board Loaded with Framing Tips)...")
        await client.capture("ui_step2_reference_loaded.png")

        # Load Standard 14 Components
        print("Loading standard 14 components...")
        await client.evaluate("document.getElementById('btn-load-sample-comps').click()")
        # Wait for components to populate
        for _ in range(30):
            await asyncio.sleep(0.2)
            count = await client.evaluate("document.querySelectorAll('#component-list-container .component-card-item').length")
            if count >= 14:
                break

        await asyncio.sleep(0.8)
        print("Capturing Step 2 (Components Marked & Listed with Warning Badges)...")
        await client.capture("ui_step2_components_marked.png")

        # 3. Transition to Step 3: Click "Proceed to Inspection"
        print("Proceeding to Step 3...")
        await client.evaluate("document.getElementById('btn-proceed-to-step3').click()")
        for _ in range(30):
            await asyncio.sleep(0.3)
            disp = await client.evaluate("window.getComputedStyle(document.getElementById('panel-step-3')).display")
            if disp != "none":
                break

        await asyncio.sleep(0.8)
        print("Capturing Step 3 Setup (Sensitivity Selector & Test Upload Zone)...")
        await client.capture("ui_step3_inspection_setup.png")

        # 4. Load Batch of Test Boards: calib_01 (OK), calib_08 (DEFECT MCU), calib_12 (DEFECT Passives)
        print("Adding test photos (1 Complete OK, 2 Defective)...")
        js_load_batch = """
        (async () => {
            const filesData = [
                { name: 'calib_01_all_ok_nominal.png', path: '/sample_data/calibration/calib_01_all_ok_nominal.png' },
                { name: 'calib_08_missing_u1_mcu.png', path: '/sample_data/calibration/calib_08_missing_u1_mcu.png' },
                { name: 'calib_12_missing_adj_c1_c2.png', path: '/sample_data/calibration/calib_12_missing_adj_c1_c2.png' },
            ];
            const dt = new DataTransfer();
            for (const item of filesData) {
                const res = await fetch(item.path);
                const blob = await res.blob();
                dt.items.add(new File([blob], item.name, { type: 'image/png' }));
            }
            const input = document.getElementById('test-file-input');
            input.files = dt.files;
            input.dispatchEvent(new Event('change', { bubbles: true }));
        })()
        """
        await client.evaluate(js_load_batch)

        for _ in range(40):
            await asyncio.sleep(0.3)
            tag_count = await client.evaluate("document.querySelectorAll('#test-file-list .file-tag').length")
            if tag_count >= 3:
                break

        await asyncio.sleep(0.8)

        # Trigger Inspection
        print("Running inspection on batch...")
        await client.evaluate("document.getElementById('btn-run-inspect').click()")

        # Wait for inspection to finish
        for _ in range(60):
            await asyncio.sleep(0.5)
            res_disp = await client.evaluate("window.getComputedStyle(document.getElementById('inspection-results-area')).display")
            spin_disp = await client.evaluate("window.getComputedStyle(document.getElementById('inspection-spinner')).display")
            if res_disp != "none" and spin_disp == "none":
                break

        await asyncio.sleep(1.5)
        print("Capturing Overall Inspection Results...")
        await client.capture("ui_inspection_results_overview.png")

        # Scroll to Card 0: OK Board (calib_01)
        print("Capturing OK Board Result Card...")
        await client.evaluate("document.querySelectorAll('.result-card')[0].scrollIntoView({behavior: 'instant', block: 'start'})")
        await asyncio.sleep(0.8)
        await client.capture("ui_result_ok_board.png")

        # Scroll to Card 1: DEFECT Board (calib_08 Missing MCU)
        print("Capturing DEFECT Board Result Card (Missing U1_MCU)...")
        await client.evaluate("document.querySelectorAll('.result-card')[1].scrollIntoView({behavior: 'instant', block: 'start'})")
        await asyncio.sleep(0.8)
        await client.capture("ui_result_defect_board.png")

        # 5. Inspection for REVIEW Result (calib_05 in Strict mode)
        print("Running Strict mode inspection to demonstrate REVIEW result...")
        # Select Strict mode
        await client.evaluate("document.querySelector('input[value=\"strict\"]').click()")
        await asyncio.sleep(0.4)

        # Load calib_05_all_ok_dim.png
        js_load_dim = """
        (async () => {
            const res = await fetch('/sample_data/calibration/calib_05_all_ok_dim.png');
            const blob = await res.blob();
            const dt = new DataTransfer();
            dt.items.add(new File([blob], 'calib_05_all_ok_dim.png', { type: 'image/png' }));
            const input = document.getElementById('test-file-input');
            input.files = dt.files;
            input.dispatchEvent(new Event('change', { bubbles: true }));
        })()
        """
        await client.evaluate(js_load_dim)
        await asyncio.sleep(1.0)

        # Click Inspect
        await client.evaluate("document.getElementById('btn-run-inspect').click()")
        for _ in range(60):
            await asyncio.sleep(0.5)
            spin_disp = await client.evaluate("window.getComputedStyle(document.getElementById('inspection-spinner')).display")
            if spin_disp == "none":
                break

        await asyncio.sleep(1.5)
        # Scroll to top card of new results
        await client.evaluate("document.querySelector('.result-card').scrollIntoView({behavior: 'instant', block: 'start'})")
        await asyncio.sleep(0.8)
        print("Capturing REVIEW Board Result Card...")
        await client.capture("ui_result_review_board.png")

        await client.close()
        print("All UI automation flow completed successfully!")

    finally:
        chrome_proc.terminate()
        server.should_exit = True
        import shutil
        if os.path.exists(temp_dir):
            time.sleep(0.5)
            shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    asyncio.run(run_automation())
