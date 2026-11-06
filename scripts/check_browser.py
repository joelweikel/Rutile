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
        page.goto(BASE_URL, wait_until="networkidle")
        if page.locator("#library").get_attribute("open") is None:
            page.locator("#library > summary").click()
        page.locator("#upload").set_input_files(example)
        page.wait_for_function("document.querySelector('#scan-status').textContent.startsWith('Imported')")
        page.locator("#component-a").fill("Al")
        page.locator("#component-b").fill("Cu")
        page.locator("#tmax").fill("1900")
        page.locator("#review-sources").click()
        candidate = page.locator("#database option").filter(has_text="synthetic-regular-solution.tdb")
        page.locator("#database").select_option(candidate.get_attribute("value"))
        page.locator("#uncertainty-note").fill("Synthetic regular-solution test, not alloy data.")
        page.wait_for_function("!document.querySelector('#calculate').disabled")
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
        assert downloaded["provenance"]["selection"]["request"]["uncertainty_note"].startswith("Synthetic")
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
        print("PASS: TDB import, source review, synthetic equilibrium map, keyboard navigation, provenance export, cancellation, and mobile layout.")
        browser.close()


if __name__ == "__main__":
    main()
