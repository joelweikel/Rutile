"""Check a supplied local assessment in Edge; no database redistribution.

Example: --database PATH/ReW-00Liu-LB.tdb --components RE W --maximum 4000
The app must already be running at RUTILE_TEST_URL (loopback only).
"""
import argparse
import json
import os
from pathlib import Path
import re
from threading import Event, Thread
from urllib.error import HTTPError
from urllib.request import urlopen

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
BASE = os.environ.get("RUTILE_TEST_URL", "http://127.0.0.1:8000")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--components", nargs=2, required=True)
    parser.add_argument("--minimum", type=float, default=300)
    parser.add_argument("--maximum", type=float)
    parser.add_argument("--auto", action="store_true", help="Estimate the range from liquidus probes")
    args = parser.parse_args()
    if not args.auto and args.maximum is None:
        parser.error("Provide --maximum or choose --auto")
    prefix = "-".join(args.components).lower()
    done, reads, failures = Event(), [], []
    def stress(job):
        while not done.is_set():
            for suffix in ("", "/preview"):
                try:
                    with urlopen(f"{BASE}/api/jobs/{job}{suffix}", timeout=10) as response:
                        json.load(response)
                    reads.append(suffix)
                except HTTPError as exc:
                    if exc.code != 409:
                        failures.append(str(exc))
                except Exception as exc:
                    failures.append(str(exc))
            done.wait(.02)
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        page = browser.new_page(viewport={"width": 1500, "height": 1040})
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.add_init_script("localStorage.setItem('rutile.appearance', JSON.stringify({reduce:true,specimen:'lab'}))")
        page.goto(BASE)
        page.locator("#start-button").click()
        page.locator("#menu-diagrams").click()
        assert page.locator(".live-dot").count() == 0
        box = page.locator("#workspace").bounding_box()
        setup = page.locator(".setup").bounding_box()
        assert abs(box["width"]-setup["width"]) < 2
        page.locator("#upload").set_input_files(args.database.resolve())
        page.wait_for_function("!document.querySelector('#calculate').disabled")
        for name, value in zip(("component-a", "component-b"), args.components):
            page.locator(f"#{name}").select_option(value)
        page.locator("#calculation-settings > summary").click()
        if args.auto:
            assert page.locator("#temperature-mode").input_value() == "auto"
            assert page.locator("#tmax").is_disabled()
        else:
            page.locator("#temperature-mode").select_option("manual")
            page.locator("#tmin").fill(str(args.minimum))
            page.locator("#tmax").fill(str(args.maximum))
        assert page.locator("#resolution").input_value() == "81,61"
        with page.expect_response(re.compile(r"/api/diagrams$")) as submitted:
            page.locator("#calculate").click()
        response = submitted.value
        assert response.ok, response.text()
        job = response.json()["id"]
        thread = Thread(target=stress, args=(job,), daemon=True)
        thread.start()
        try:
            assert page.locator("#live-stage").evaluate("e => e.nextElementSibling.id") == "progress"
            assert page.locator("#progress").is_visible()
            page.locator("#boundaries path").first.wait_for(timeout=180000)
            page.screenshot(path=str(ROOT / "workspace" / f"{prefix}-loading.png"), full_page=True)
            page.wait_for_function("['complete','interrupted'].includes(document.querySelector('#workspace').dataset.stage)", timeout=300000)
            assert page.locator("#workspace").get_attribute("data-stage") == "complete", page.locator("#status").inner_text()
            result = page.request.get(f"{BASE}/api/jobs/{job}/result").json()
            assert len(result["cells"]) == 4941
            assert not any(c["check"] == "unresolved" for c in result["cells"])
            if "LIQUID" in {p["phase"] for c in result["cells"] for p in c["phases"]}:
                swatch = page.locator(".legend-item").filter(has_text=re.compile(r"^LIQUID$"))
                assert swatch.evaluate("e => getComputedStyle(e).backgroundColor") == "rgb(0, 0, 0)"
            assert sum(result["validation"]["counts"].values()) == 4941
            if args.auto:
                estimate = result["provenance"]["temperature_range_estimate"]
                assert estimate["sample_count"] == 10
                assert result["settings"]["temperature_max"] >= estimate["maximum_liquidus_upper_bound_k"]+30
                assert "Auto range:" in page.locator("#temperature-summary").inner_text()
            if args.components == ["TA", "ZR"]:
                assert any(b["temperature_min"] <= 2095 <= b["temperature_max"] and b["phase"] == "BCC_A2"
                           for b in result["boundaries"]["single_phase_bands"])
            near = next((c for c in result["cells"] if c["check"] == "near_boundary"), None)
            if near:
                point = page.evaluate("""([xi, ti]) => {
                    const svg = document.querySelector('#plot'), p = svg.createSVGPoint();
                    p.x = 76 + (xi+.5)/81*670; p.y = 25+465-(ti+.5)/61*465;
                    const q = p.matrixTransform(svg.getScreenCTM()); return {x:q.x,y:q.y};
                }""", [near["xi"], near["ti"]])
                page.mouse.move(point["x"], point["y"])
                page.locator("#tooltip").wait_for(state="visible")
                assert "near boundary (ignored)" in page.locator("#point-audit").inner_text()
                assert "Boundary prediction at sample" in page.locator("#point-audit").inner_text()
            page.locator("#plot").focus()
            page.keyboard.press("ArrowRight")
            page.keyboard.press("Enter")
            assert page.locator("#unpin").is_visible()
            page.screenshot(path=str(ROOT / "workspace" / f"{prefix}-diagram.png"), full_page=True)
            page.set_viewport_size({"width": 390, "height": 844})
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            page.screenshot(path=str(ROOT / "workspace" / f"{prefix}-mobile.png"), full_page=True)
            print(json.dumps({"job": job, "database": args.database.name,
                              "checks": result["validation"]["counts"],
                              "single_phase_bands": len(result["boundaries"].get("single_phase_bands", []))}), flush=True)
        finally:
            done.set()
            thread.join(timeout=12)
            browser.close()
        assert reads and not failures, failures
        assert not errors, errors
        print(f"PASS: {len(reads)} concurrent status/preview reads; completed calculation, panel sizing, progress placement, liquid color, keyboard, and mobile checks.", flush=True)


if __name__ == "__main__":
    main()
