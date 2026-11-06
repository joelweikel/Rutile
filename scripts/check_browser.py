"""Exercise the running local app in headless Edge; saves previews in workspace/."""
import json
import os
from pathlib import Path
import re

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
BASE_URL = os.environ.get("RUTILE_TEST_URL", "http://127.0.0.1:8000")


def main():
    example = ROOT / "examples" / "synthetic-regular-solution.tdb"
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        page = browser.new_page(viewport={"width": 1500, "height": 1040}, device_scale_factor=1)
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        app_script = "**/src/js/app.js*"
        page.route(app_script, lambda route: route.abort())
        page.goto(BASE_URL)
        assert page.locator("#upload").is_disabled()
        assert "launcher" in page.locator("#upload-status").inner_text()
        page.unroute(app_script)
        response = page.goto(BASE_URL, wait_until="networkidle")
        assert response.headers["cache-control"] == "no-cache"
        calculate = page.locator("#calculate")
        upload = page.locator("#upload")
        assert page.get_by_role("heading", name="Rutile", exact=True).is_visible()
        assert calculate.is_disabled()
        upload.set_input_files({"name": "invalid.tbd", "mimeType": "text/plain", "buffer": b"invalid data"})
        page.locator("#upload-status.error").wait_for()
        assert calculate.is_disabled()
        stalled = {"name": "stalled.tdb", "mimeType": "text/plain", "buffer": example.read_bytes()}

        page.evaluate("""() => {
            const fetch = window.fetch.bind(window);
            window.stalledUploads = 0;
            window.fetch = (url, options) => {
                if (url !== '/api/databases' || JSON.parse(options.body).filename !== 'stalled.tdb') {
                    return fetch(url, options);
                }
                window.stalledUploads++;
                return new Promise((resolve, reject) => {
                    options.signal.addEventListener('abort', () => reject(options.signal.reason), {once: true});
                });
            };
        }""")
        page.clock.install()
        upload.set_input_files(stalled)
        page.wait_for_function("window.stalledUploads === 1")
        assert upload.is_enabled()
        page.clock.fast_forward(61_000)
        page.get_by_text("Loading timed out.", exact=False).wait_for()
        assert upload.is_enabled()
        upload.set_input_files(stalled)
        page.wait_for_function("window.stalledUploads === 2")
        # A file with more than two elements must offer a choice from that file.
        ternary = example.read_bytes() + b"\nELEMENT ZN FCC_A1 65.38 0 0 !\n"
        upload.set_input_files({"name": "ternary.tbd", "mimeType": "text/plain", "buffer": ternary})
        page.get_by_text("Choose two of its 3 elements.", exact=False).wait_for()
        assert calculate.is_disabled()
        page.locator("#component-a").select_option("AL")
        page.locator("#component-b").select_option("ZN")
        assert calculate.is_enabled()
        with page.expect_response(re.compile(r"/api/databases$")) as imported:
            upload.set_input_files(example)
        database_id = imported.value.json()["id"]
        page.get_by_text("Both elements are selected.", exact=False).wait_for()
        assert page.locator("#component-a").input_value() == "AL"
        assert page.locator("#component-b").input_value() == "CU"
        assert page.locator("#component-b option[value=ZN]").count() == 0
        assert calculate.is_enabled()
        page.locator("#component-b").select_option("AL")
        assert calculate.is_disabled()
        assert "two different elements" in page.locator("#status").inner_text()
        page.locator("#component-b").select_option("CU")
        assert calculate.is_enabled()
        assert page.locator("body").evaluate("element => getComputedStyle(element).fontFamily").startswith('"Times New Roman"')
        assert page.locator("#plot text").first.evaluate("element => getComputedStyle(element).fontFamily").startswith("Spectral")
        with page.expect_response(re.compile(r"/api/jobs/[^/]+/result$"), timeout=180000) as response:
            page.locator("#calculate").click()
        result = response.value.json()
        page.wait_for_function("!document.querySelector('#export').disabled")
        assert len(result["cells"]) == 51 * 41
        assert any(c["miscibility_gap"] for c in result["cells"])
        gap = next(c for c in result["cells"] if c["miscibility_gap"])
        page.locator("#plot").scroll_into_view_if_needed()
        point = page.evaluate("""([xi,ti,nx,nt]) => {
            const svg=document.querySelector('#plot'),p=svg.createSVGPoint();
            p.x=76+(xi+.5)/nx*670;p.y=25+465-(ti+.5)/nt*465;
            const q=p.matrixTransform(svg.getScreenCTM());return {x:q.x,y:q.y};
        }""", [gap["xi"], gap["ti"], 51, 41])
        page.mouse.move(point["x"], point["y"])
        page.locator("#tooltip").wait_for(state="visible")
        assert "FCC_A1 #1" in page.locator("#tooltip").inner_text()
        assert page.locator("#gap-banner").is_visible()
        assert "FCC_A1 #2" in page.locator("#phase-cards").inner_text()
        page.mouse.click(point["x"], point["y"])
        assert page.locator("#unpin").is_visible()
        page.mouse.move(10, 10)
        page.screenshot(path=str(ROOT / "workspace" / "phase-diagram-preview.png"), full_page=True)
        with page.expect_download() as download:
            page.locator("#export").click()
        downloaded = json.loads(Path(download.value.path()).read_text(encoding="utf-8"))
        assert downloaded["provenance"]["sha256"] == result["provenance"]["sha256"]
        selection = downloaded["provenance"]["selection"]
        assert selection["selected_id"] == database_id
        assert "Assessment coverage may be unverified" in selection["request"]["uncertainty_note"]
        page.locator("#plot").focus()
        page.keyboard.press("Escape")
        assert not page.locator("#unpin").is_visible()
        page.keyboard.press("ArrowRight")
        page.keyboard.press("Enter")
        assert page.locator("#unpin").is_visible()
        # A second job must be cancellable without freezing the interface.
        page.locator("#calculation-settings > summary").click()
        page.locator("#resolution").select_option("101,101")
        page.locator("#calculate").click()
        page.wait_for_function("document.querySelector('#status').textContent.includes('row')")
        page.locator("#cancel").click()
        page.wait_for_function("document.querySelector('#status').textContent.includes('cancelled')")
        assert page.locator("#calculate").is_enabled()
        page.set_viewport_size({"width": 390, "height": 844})
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        page.screenshot(path=str(ROOT / "workspace" / "phase-diagram-mobile.png"), full_page=True)
        assert not errors, errors
        print("PASS: single-file import, element selection, synthetic equilibrium map, keyboard navigation, provenance export, cancellation, and mobile layout.")
        browser.close()


if __name__ == "__main__":
    main()
