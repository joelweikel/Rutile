"""Exercise the running local app in headless Edge; saves previews in workspace/."""
import json
import os
from pathlib import Path
import re

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
BASE_URL = os.environ.get("RUTILE_TEST_URL", "http://127.0.0.1:8000")


def open_diagrams(page):
    page.locator("#start-button").click()
    page.locator("#menu-diagrams").click()
    page.locator("#diagrams-heading").wait_for()


def main():
    example = ROOT / "examples" / "AlCu-21Kro.tdb"
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        page = browser.new_page(viewport={"width": 1500, "height": 1040}, device_scale_factor=1)
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.add_init_script("""const drawImage = CanvasRenderingContext2D.prototype.drawImage;
          CanvasRenderingContext2D.prototype.drawImage = function(image, ...args) {
            if(this.canvas.id === 'rutile-scene' && args.length === 4) {
              window.latticePixelScales = [...(window.latticePixelScales || []).slice(-2), image.width / args[2]];
            }
            return drawImage.call(this, image, ...args);
          };""")
        page.goto(BASE_URL, wait_until="domcontentloaded")
        assert page.get_by_role("button", name="Skip intro").count() == 0
        page.locator("#screen-loading").wait_for(state="visible")
        page.locator("#title-heading").wait_for(state="visible")
        assert page.locator("body").get_attribute("data-specimen") == "lab"
        assert page.locator(".wordmark").inner_text() == "JoelTech"
        assert page.locator("#shell-bar use[href='#icon-jt']").count() == 0
        page.keyboard.press("Enter")
        page.locator("#menu-heading").wait_for()
        assert page.locator(".menu-tile:disabled").count() == 2
        page.locator("#menu-settings").click()
        assert page.locator("body").get_attribute("data-dive") is not None
        page.locator("#screen-settings").evaluate("element => Promise.all(element.getAnimations().map(a => a.finished))")
        page.evaluate("new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))")
        lattice = page.locator("#rutile-scene")
        settled = lattice.evaluate("element => element.toDataURL()")
        page.wait_for_timeout(300)
        assert lattice.evaluate("element => element.toDataURL()") == settled
        assert page.evaluate("window.latticePixelScales.length === 3 && Math.min(...window.latticePixelScales) >= .98")
        page.locator("input[name=specimen][value=natural]").check()
        page.locator("#reduce-motion").check()
        page.locator("#shell-back").click()
        assert page.locator("#menu-settings").evaluate("element => element === document.activeElement")

        app_script = "**/src/js/app.js*"
        page.route(app_script, lambda route: route.abort())
        page.goto(BASE_URL)
        assert page.locator("body").get_attribute("data-specimen") == "natural"
        assert page.locator("body").get_attribute("data-motion") == "reduced"
        assert page.locator("#screen-loading").is_hidden()
        canvas = page.locator("#rutile-scene")
        page.evaluate("document.fonts.ready.then(() => new Promise(requestAnimationFrame))")
        original = canvas.screenshot()
        page.mouse.move(1070, 500)
        page.mouse.down()
        page.mouse.move(1180, 580, steps=4)
        page.mouse.up()
        page.evaluate("new Promise(requestAnimationFrame)")
        assert canvas.screenshot() != original
        assert page.locator("#title-heading").is_visible()
        open_diagrams(page)
        assert page.locator("#upload").is_disabled()
        assert "launcher" in page.locator("#upload-status").inner_text()
        page.unroute(app_script)
        response = page.goto(BASE_URL, wait_until="networkidle")
        assert response.headers["cache-control"] == "no-cache"
        assert page.get_by_role("heading", name="Rutile", exact=True).is_visible()
        open_diagrams(page)
        calculate = page.locator("#calculate")
        upload = page.locator("#upload")
        assert page.locator("#workspace").get_attribute("data-stage") == "setup"
        assert page.locator("#diagram-panel").is_hidden()
        assert page.locator("#inspector").is_hidden()
        assert page.locator("#resolution").input_value() == "81,61"
        page.screenshot(path=str(ROOT / "workspace" / "phase-setup-preview.png"), full_page=True)
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
        assert page.locator("#plot").evaluate("element => getComputedStyle(element).fontFamily").startswith("Estedad")
        for font in ['Estedad', '"Momo Trust Display"']:
            assert page.evaluate("font => document.fonts.load('16px ' + font).then(faces => faces.length > 0)", font)
        page.locator("#calculation-settings > summary").click()
        page.locator("#temperature-mode").select_option("manual")
        page.locator("#resolution").select_option("31,25")
        with page.expect_response(re.compile(r"/api/jobs/[^/]+/result$"), timeout=300000) as response:
            page.locator("#calculate").click()
            assert page.locator("#workspace").get_attribute("data-stage") == "running"
            assert page.locator("#calculation-live").is_visible()
            assert page.locator("#inspector").is_hidden()
            page.locator("#boundaries path").first.wait_for(timeout=180000)
            page.screenshot(path=str(ROOT / "workspace" / "phase-loading-preview.png"), full_page=True)
        result = response.value.json()
        page.wait_for_function("!document.querySelector('#export').disabled")
        nx, nt = len(result["x"]), len(result["temperatures"])
        assert (nx, nt) == (31, 25)
        assert len(result["cells"]) == nx * nt
        assert result["boundaries"]["ribbons"]
        assert sum(result["validation"]["counts"].values()) == nx * nt
        assert page.locator("#inspector").is_visible()
        assert page.locator("#workspace").get_attribute("data-stage") == "complete"
        assert page.locator("#region-labels text").count() > 0
        page.locator("#show-samples").check()
        assert page.locator("#checks circle").count() > 0
        page.locator("#show-samples").uncheck()
        labels = page.locator("#region-labels").text_content()
        stable_phases = {p["phase"] for cell in result["cells"] for p in cell["phases"]}
        assert all(phase in labels for phase in stable_phases)
        assert page.locator("#plot").get_attribute("viewBox") == "0 0 940 580"
        assert any(c["valid"] and {p["phase"] for p in c["phases"]} == {"LIQUID"} for c in result["cells"])
        xi = min(range(nx), key=lambda i: abs(result["x"][i] - 0.1))
        ti = min(range(nt), key=lambda i: abs(result["temperatures"][i] - 750))
        cell = result["cells"][ti * nx + xi]
        assert cell["valid"] and {p["phase"] for p in cell["phases"]} == {"FCC_A1", "AL2CU_C16"}
        page.locator("#plot").scroll_into_view_if_needed()
        point = page.evaluate("""([xi,ti,nx,nt]) => {
            const svg=document.querySelector('#plot'),p=svg.createSVGPoint();
            p.x=76+(xi+.5)/nx*670;p.y=25+465-(ti+.5)/nt*465;
            const q=p.matrixTransform(svg.getScreenCTM());return {x:q.x,y:q.y};
        }""", [xi, ti, nx, nt])
        page.mouse.move(point["x"], point["y"])
        page.locator("#tooltip").wait_for(state="visible")
        assert "FCC_A1" in page.locator("#tooltip").inner_text()
        assert "AL2CU_C16" in page.locator("#phase-cards").inner_text()
        assert "Independent check: agreement" not in page.locator("#point-audit").inner_text()
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
        page.locator("#shell-back").click()
        page.locator("#menu-diagrams").click()
        assert page.locator("#export").is_enabled()
        assert page.locator("#unpin").is_visible()
        page.set_viewport_size({"width": 390, "height": 844})
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        page.screenshot(path=str(ROOT / "workspace" / "phase-complete-mobile.png"), full_page=True)
        page.set_viewport_size({"width": 1500, "height": 1040})
        # A second job must be cancellable without freezing the interface.
        page.locator("#resolution").select_option("101,101")
        page.locator("#calculate").click()
        assert not page.locator("#quality-summary").inner_text()
        assert not page.locator("#plot-note").inner_text()
        page.wait_for_function("document.querySelector('#cancel').hidden === false")
        page.locator("#cancel").click()
        page.wait_for_function("document.querySelector('#status').textContent.includes('cancelled')")
        assert page.locator("#calculate").is_enabled()
        page.set_viewport_size({"width": 390, "height": 844})
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        page.screenshot(path=str(ROOT / "workspace" / "phase-diagram-mobile.png"), full_page=True)
        page.locator("#shell-back").click()
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        page.locator("#menu-settings").click()
        assert page.locator("input[name=specimen][value=natural]").is_checked()
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        assert not errors, errors
        print("PASS: intro, crystal rotation, menus, persisted appearance, assessed Al-Cu map, keyboard inspection, export, cancellation, and mobile layout.")
        browser.close()


if __name__ == "__main__":
    main()
