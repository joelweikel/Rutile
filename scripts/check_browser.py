"""Exercise the running local app in headless Edge; saves previews in workspace/."""
import json
from pathlib import Path
import re

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        page = browser.new_page(viewport={"width": 1500, "height": 1040}, device_scale_factor=1)
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto("http://127.0.0.1:8000", wait_until="networkidle")
        page.wait_for_function("!document.querySelector('#calculate').disabled")
        assert page.locator("#database-info").inner_text().endswith("alzn_mey.tdb")
        assert page.evaluate("document.fonts.check('16px Spectral')")
        with page.expect_response(re.compile(r"/api/jobs/[^/]+/result$"), timeout=180000) as response:
            page.locator("#calculate").click()
        result = response.value.json()
        page.wait_for_function("!document.querySelector('#export').disabled")
        assert len(result["cells"]) == 51 * 41
        assert any(c["miscibility_gap"] for c in result["cells"])
        gap = next(c for c in result["cells"] if c["miscibility_gap"])
        point = page.evaluate("""([xi,ti,nx,nt]) => {
            const svg=document.querySelector('#plot'),p=svg.createSVGPoint();
            p.x=76+(xi+.5)/nx*670;p.y=25+465-(ti+.5)/nt*465;
            const q=p.matrixTransform(svg.getScreenCTM());return {x:q.x,y:q.y};
        }""", [gap["xi"], gap["ti"], 51, 41])
        page.mouse.move(point["x"], point["y"])
        assert page.locator("#tooltip").is_visible()
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
        page.locator("#plot").focus()
        page.keyboard.press("Escape")
        assert not page.locator("#unpin").is_visible()
        page.keyboard.press("ArrowRight")
        page.keyboard.press("Enter")
        assert page.locator("#unpin").is_visible()
        # A second job must be cancellable without freezing the interface.
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
        print("PASS: real Al-Zn map, split-phase hover, pinning, keyboard navigation, JSON export, cancellation, mobile layout; no JavaScript errors.")
        browser.close()


if __name__ == "__main__":
    main()
