"""Check Settings credentials and bundled mobility in Edge without external API calls."""
import os
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
BASE = os.environ.get("RUTILE_TEST_URL", "http://127.0.0.1:8000")


def main():
    output = ROOT / "workspace" / "settings-ui-check"
    output.mkdir(parents=True, exist_ok=True)
    fake_key = "settings-test-only-never-a-real-key"
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="msedge", headless=True)
        for label, width, height in [("desktop", 1500, 1040), ("mobile", 390, 844)]:
            context = browser.new_context(viewport={"width": width, "height": height},
                                          device_scale_factor=2, reduced_motion="reduce")
            page = context.new_page()
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(BASE)
            initial = page.request.get(f"{BASE}/api/materials/status").json()
            assert initial["source"] in (None, "environment"), "Use a test server without a session key."
            page.locator("#start-button").click()
            page.locator("#menu-settings").focus()
            page.keyboard.press("Enter")
            expect(page.locator("#settings-heading")).to_be_focused()
            status = page.locator("#materials-key-status")
            expect(status).not_to_have_text("Checking key status…")
            expect(page.locator("#materials-key-clear")).to_be_disabled()
            expect(page.locator("#materials-key")).to_have_attribute("type", "password")
            page.locator("#materials-key").fill("short")
            assert not page.locator("#materials-key").evaluate("input => input.checkValidity()")
            page.locator("#materials-key").fill(fake_key)
            page.keyboard.press("Enter")
            expect(status).to_have_text("Key set for this server session.")
            expect(page.locator("#materials-key")).to_have_value("")
            expect(page.locator("#materials-key-clear")).to_be_enabled()
            assert not page.evaluate("key => [...Object.values(localStorage), ...Object.values(sessionStorage)].some(value => value.includes(key))", fake_key)
            response = page.request.get(f"{BASE}/api/materials/status")
            assert response.json() == {"configured": True, "source": "session"}
            assert fake_key not in response.text()
            page.reload()
            page.locator("#start-button").click()
            page.locator("#menu-settings").click()
            expect(status).to_have_text("Key set for this server session.")
            expect(page.locator("#materials-key")).to_have_value("")
            page.locator("#materials-key-clear").click()
            expected = "Key configured by the server environment." if initial["configured"] else "No API key configured. Phase calculations work without one."
            expect(status).to_have_text(expected)
            expect(page.locator("#materials-key-clear")).to_be_disabled()
            # A failed save clears the field without claiming the key was saved.
            page.route("**/api/materials/key", lambda route: route.fulfill(status=503, json={"detail": "test failure"}))
            page.locator("#materials-key").fill(fake_key)
            page.locator("#materials-key-save").click()
            expect(status).to_contain_text("Could not update the key")
            expect(page.locator("#materials-key")).to_have_value("")
            page.unroute("**/api/materials/key")
            page.locator("#shell-back").click()
            page.locator("#menu-settings").click()
            expect(status).to_have_text(expected)
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            page.evaluate("window.scrollTo(0, 0)")
            assert page.locator("#shell-back").bounding_box()["y"] >= 0
            page.screenshot(path=str(output / f"{label}-settings.png"), full_page=True)
            page.locator("#shell-back").click()
            expect(page.locator("#menu-settings")).to_be_focused()
            page.locator("#menu-optimize").click()
            page.locator("#studio-create").click()
            sources = page.request.get(f"{BASE}/api/processing/sources").json()["sources"]
            assert len(sources) == 3 and all(record["available"] and record["mobility_available"] for record in sources)
            for family, mobility in [("al", "mc_al_v2008.ddb"), ("fe", "mc_fe_v2016.ddb"), ("ni", "mc_ni_v2012.ddb")]:
                page.locator(f"#family-{family}").click()
                page.locator("#opt-next").click()
                page.locator('[name="opt-element"][value="Cu"]').check()
                page.locator("#opt-Cu-amount").fill("2")
                page.locator("#create-use-balance").click()
                page.locator("#opt-next").click()
                expect(page.locator("#process-source-status")).to_contain_text(f"Mobility attached: {mobility}")
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
                page.locator('[data-opt-step="0"]').click()
            assert not errors, errors
            print(f"PASS {label}: key save/clear, reload, privacy, failure feedback, keyboard/layout and bundled Al/Fe/Ni mobility", flush=True)
            context.close()
        browser.close()


if __name__ == "__main__":
    main()
