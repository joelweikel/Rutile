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


def check_studio(page):
    canvas = page.locator(".studio-viewport")
    page.locator("#studio-heading").wait_for()
    assert page.locator("#studio-heading").evaluate("element => element === document.activeElement")
    page.wait_for_function("document.querySelectorAll('.studio-wire').length === 8")
    page.wait_for_function("getComputedStyle(document.querySelector('.studio-world')).opacity === '1'")
    assert page.locator("#screen-studio").evaluate("""element => {
        const box = element.getBoundingClientRect();
        const grid = getComputedStyle(element.querySelector('.studio-viewport'), '::before');
        return box.x === 0 && box.y === 0 && box.width === innerWidth && box.height === innerHeight &&
            grid.backgroundColor === 'rgb(0, 0, 0)' && grid.backgroundImage.match(/radial-gradient/g).length === 2;
    }""")
    assert canvas.evaluate("""element => {
        const card = id => element.querySelector('[data-node=' + id + ']').getBoundingClientRect();
        return card('composition').bottom < card('sources').top &&
            card('sources').bottom < card('schedule').top;
    }""")

    def wire_point():
        return page.locator('.studio-wire-hit[data-wire="3"][data-segment="0"]').evaluate("""path => {
            for (const fraction of [.5, .4, .6, .3, .7]) {
                const point = path.getPointAtLength(path.getTotalLength() * fraction).matrixTransform(path.getScreenCTM());
                if (document.elementFromPoint(point.x, point.y) === path) return {x: point.x, y: point.y};
            }
            throw new Error('No accessible section of the phase viewer wire');
        }""")

    point = wire_point()
    page.mouse.dblclick(point["x"], point["y"])
    dot = page.locator(".studio-reroute")
    dot.wait_for()
    box = dot.bounding_box()
    x, y = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
    page.mouse.move(x, y)
    page.mouse.down()
    page.mouse.move(x + 24, y + 38, steps=5)
    page.mouse.up()
    assert abs(dot.bounding_box()["y"] - box["y"] - 38) < 2
    saved_route = page.evaluate("JSON.parse(localStorage.getItem('rutile.alloy-studio.v1')).graph.edges[3][4]")
    assert len(saved_route) == 1
    dot.click(button="right")
    assert dot.count() == 0
    point = wire_point()
    page.mouse.click(point["x"], point["y"], button="right")
    page.wait_for_function("document.querySelectorAll('.studio-wire').length === 7")
    page.locator("[data-node=equilibrium] [data-pin=phase]").press("Enter")
    page.locator("[data-node=viewer] [data-pin=phase]").press("Enter")
    page.wait_for_function("document.querySelectorAll('.studio-wire').length === 8")

    canvas.click(button="right", position={"x": 130, "y": 15})
    search = page.get_by_role("searchbox", name="Search nodes")
    search.fill("vision")
    assert page.get_by_text("No matching nodes").is_visible()
    search.fill("phase viewer")
    search.press("Enter")
    assert page.locator(".studio-node.detached").count() == 1
    source = page.locator("[data-node=equilibrium] [data-pin=phase] i").bounding_box()
    drop = canvas.evaluate("""element => {
        const canvas = element.getBoundingClientRect();
        const viewer = element.querySelector('[data-node=viewer]');
        const size = viewer.getBoundingClientRect();
        const pin = viewer.querySelector('[data-pin=phase] i').getBoundingClientRect();
        const offset = {x: pin.left + pin.width / 2 - size.left, y: pin.top + pin.height / 2 - size.top};
        const cards = [...element.querySelectorAll('.studio-node')].map(node => node.getBoundingClientRect());
        for (let y = canvas.top + 30; y + size.height < canvas.bottom - 20; y += 20) {
            for (let x = canvas.left + 30; x + size.width < canvas.right - 20; x += 20) {
                if (!cards.some(card => x < card.right + 24 && x + size.width + 24 > card.left &&
                    y < card.bottom + 24 && y + size.height + 24 > card.top)) {
                    return {x: x + offset.x, y: y + offset.y};
                }
            }
        }
        throw new Error('No room to drop a new phase viewer');
    }""")
    page.mouse.move(source["x"] + source["width"] / 2, source["y"] + source["height"] / 2)
    page.mouse.down()
    page.mouse.move(drop["x"], drop["y"], steps=8)
    page.mouse.up()
    assert page.locator(".studio-library [data-add]").count() == 3
    search.fill("phase viewer")
    search.press("Enter")
    page.wait_for_function("document.querySelectorAll('.studio-wire').length === 9")
    new_input = page.locator(".studio-node.selected [data-direction=input] i").bounding_box()
    assert abs(new_input["x"] + new_input["width"] / 2 - drop["x"]) < 12
    assert abs(new_input["y"] + new_input["height"] / 2 - drop["y"]) < 12
    page.locator("[data-node=density] [data-title]").click()
    page.get_by_label("Use compatible reference volumes").uncheck()
    page.locator("[data-action=run]").click()
    page.wait_for_function("document.querySelector('[data-action=run]').disabled === false", timeout=180000)
    assert "phases" in page.locator("[data-node=equilibrium] .studio-node-note").inner_text()
    assert "Coverage" in page.locator(".studio-inspector").inner_text()
    assert "K" in page.locator("[data-node=tracer] .studio-node-note").inner_text()
    equilibrium_id = page.evaluate("""JSON.parse(localStorage.getItem('rutile.alloy-studio.v1')).runs
        .find(([name]) => name === 'equilibrium')[1].job""")
    with page.expect_request(re.compile(r"/api/workflow/branch$")) as rerun:
        page.get_by_role("button", name="Run Density", exact=True).click()
    assert rerun.value.post_data_json["operation"] == "density"
    assert rerun.value.post_data_json["equilibrium_job"] == equilibrium_id
    page.wait_for_function("document.querySelector('[data-action=run]').disabled === false", timeout=90000)
    page.locator("#screen-studio").screenshot(path=str(ROOT / "workspace" / "alloy-studio-preview.png"))
    composition = page.locator("[data-node=composition]")
    inspector = page.locator(".studio-inspector")
    composition.locator("[data-title]").click()
    amount = composition.get_by_label("Addition (%)")
    amount.fill("5")
    amount.press("Enter")
    assert inspector.get_by_label("Addition (%)").input_value() == "5"
    assert composition.locator("[data-balance]").inner_text() == "Balance · AL 95 wt%"
    inspector.get_by_label("Addition (%)").fill("6")
    inspector.get_by_label("Addition (%)").press("Tab")
    assert amount.input_value() == "6"
    assert "Stale" in page.locator("[data-node=equilibrium] .studio-node-note").inner_text()
    schedule = page.locator("[data-node=schedule]")
    points = schedule.get_by_label("Cooling points")
    points.fill("13")
    points.press("Enter")
    schedule.locator("[data-title]").click()
    assert inspector.get_by_label("Cooling points").input_value() == "13"
    points.fill("3.5")
    points.press("Enter")
    assert points.input_value() == "13"
    page.set_viewport_size({"width": 390, "height": 844})
    page.locator("[data-action=fit]").click()
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    page.set_viewport_size({"width": 1500, "height": 1040})


def main():
    example = ROOT / "examples" / "AlCu-21Kro.tdb"
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        page = browser.new_page(viewport={"width": 1500, "height": 1040}, device_scale_factor=1)
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.add_init_script("""if (!localStorage.getItem('rutile.appearance')) {
            localStorage.setItem('rutile.appearance', JSON.stringify({specimen:'lab',reduce:false}));
          }
          const drawImage = CanvasRenderingContext2D.prototype.drawImage;
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
        assert page.get_by_role("button", name="Start", exact=True).is_visible()
        assert page.get_by_text("Drag or use arrow keys to rotate").count() == 0
        assert page.locator("body").get_attribute("data-specimen") == "lab"
        assert page.locator(".wordmark").count() == 0
        assert page.locator("#screen-loading use[href='#icon-jt']").count() == 1
        assert page.locator("#shell-bar use[href='#icon-jt']").count() == 0
        page.keyboard.press("Enter")
        page.locator("#menu-heading").wait_for()
        assert page.locator(".menu-tile").first.get_attribute("id") == "menu-optimize"
        page.locator("#menu-optimize").focus()
        page.keyboard.press("Enter")
        assert page.locator("body").get_attribute("data-dive") is not None
        assert page.locator(".studio-bar").evaluate("element => getComputedStyle(element).animationName") == "studio-slide-down"
        assert page.locator(".studio-inspector").evaluate("element => getComputedStyle(element).animationName") == "studio-slide-left"
        check_studio(page)
        page.locator("#shell-back").click()
        assert page.locator("#menu-optimize").evaluate("element => element === document.activeElement")
        page.keyboard.press("Enter")
        page.keyboard.press("Escape")
        assert page.locator("#screen-menu").is_visible()
        assert page.locator("#menu-optimize").evaluate("element => element === document.activeElement")
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
        page.wait_for_function("!document.querySelector('#calculate').disabled")
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
        assert not page.locator("#legend").is_visible()
        page.locator("#sample-summary > summary").click()
        page.locator("#show-samples").check()
        assert page.locator("#checks circle").count() > 0
        page.locator("#show-samples").uncheck()
        page.locator("#sample-summary > summary").click()
        labels = page.locator("#region-labels").text_content()
        stable_phases = {p["phase"] for cell in result["cells"] for p in cell["phases"]}
        assert all(phase in labels for phase in stable_phases)
        assert page.locator('[data-label-placement="liquid"]').count() == 0
        label = page.locator('[data-region-label="LIQUID"]')
        original_x = label.get_attribute("data-label-x")
        label.focus()
        page.keyboard.press("Shift+ArrowRight")
        assert label.get_attribute("data-label-x") != original_x
        assert label.get_attribute("data-label-placement") == "manual"
        page.locator("#reset-labels").click()
        assert label.get_attribute("data-label-x") == original_x
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
        page.locator("#point-details").wait_for(state="visible")
        assert "FCC" in page.locator("#point-structure").inner_text()
        assert "C16" in page.locator("#point-structure").inner_text()
        assert page.locator("#tooltip").is_hidden()
        assert "AL2CU_C16" in page.locator("#phase-cards").inner_text()
        assert "Independent check: agreement" not in page.locator("#point-audit").inner_text()
        page.mouse.click(point["x"], point["y"])
        assert page.locator("#unpin").is_visible()
        before = page.locator("#point-temperature").inner_text()
        label.locator("rect").scroll_into_view_if_needed()
        rect = label.locator("rect").bounding_box()
        page.mouse.move(rect["x"] + rect["width"] / 2, rect["y"] + rect["height"] / 2)
        page.mouse.down()
        page.mouse.move(rect["x"] + rect["width"] / 2 + 25, rect["y"] + rect["height"] / 2 + 14, steps=4)
        page.wait_for_function("getComputedStyle(document.querySelector('#unpin')).opacity === '0'")
        assert page.locator("#unpin").evaluate("el => el.inert")
        page.mouse.up()
        page.wait_for_function("getComputedStyle(document.querySelector('#unpin')).opacity === '1'")
        assert page.locator("#point-temperature").inner_text() == before
        assert not page.locator("#unpin").evaluate("el => el.inert")
        page.get_by_role("button", name="Unpin", exact=True).click()
        assert page.locator("#unpin").is_hidden()
        page.keyboard.press("Enter")
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
