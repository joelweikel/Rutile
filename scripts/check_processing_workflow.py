"""Real upload/worker/result/browser checks; local sources, no external network.

RUTILE_TEST_URL selects the running server. --matcalc also checks the three
bundled family companions. Outputs stay in ignored workspace/.
"""
import argparse
import base64
import json
import os
from pathlib import Path
from time import monotonic, sleep

import requests
from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
BASE = os.environ.get("RUTILE_TEST_URL", "http://127.0.0.1:8000")


def submit(payload):
    # A completed result can be published just before its worker exits. Wait for
    # that worker to retire before submitting the next calculation on this test server.
    for _ in range(50):
        response = requests.post(f"{BASE}/api/processing", json=payload, timeout=30)
        if response.status_code == 422 and response.json().get("detail") == "A calculation is already running. Wait or cancel it first.":
            sleep(.1)
            continue
        break
    assert response.status_code == 202, response.text
    response.raise_for_status()
    job = response.json()["id"]
    deadline = monotonic() + 240
    while monotonic() < deadline:
        status = requests.get(f"{BASE}/api/jobs/{job}", timeout=30).json()
        if status["state"] == "failed":
            raise AssertionError(status)
        if status["state"] == "completed":
            response = requests.get(f"{BASE}/api/jobs/{job}/result", timeout=30)
            response.raise_for_status()
            result = response.json()
            for state in result["states"]:
                assert abs(sum(p["fraction"] for p in state["phases"]) - 1) < 1e-5
                assert max(abs(error) for error in state["balance_errors"].values()) < 1e-5
            return job, result
        sleep(.4)
    requests.delete(f"{BASE}/api/jobs/{job}", timeout=30).raise_for_status()
    raise AssertionError("Processing worker exceeded workflow check timeout.")


def main(matcalc):
    output = ROOT / "workspace" / "processing-ui-check"
    output.mkdir(parents=True, exist_ok=True)
    source = ROOT / "examples" / "AlCu-21Kro.tdb"
    response = requests.post(f"{BASE}/api/databases", json={"filename": source.name,
        "content": base64.b64encode(source.read_bytes()).decode(), "encoding": "base64"}, timeout=30)
    response.raise_for_status()
    key = response.json()["id"]
    payload = {"family": "AL", "database_id": key, "additions": [{"element": "CU", "maximum": 4}],
               "melt_temperature_k": 1073.15, "cooling_points": 5,
               "include_reference_properties": False}
    job, result = submit(payload)
    assert result["composition"]["nominal_percent"] == {"AL": 98, "CU": 2}
    assert result["kawin"]["state"] == "unavailable"  # No arbitrary companion pairing.
    (output / "uploaded-result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"PASS upload, completed subprocess job and result retrieval: {job}", flush=True)
    # Start a real worker and cancel its process tree before its first solve.
    response = requests.post(f"{BASE}/api/processing", json={**payload, "cooling_points": 61}, timeout=30)
    response.raise_for_status()
    cancel_id = response.json()["id"]
    cancelled = requests.delete(f"{BASE}/api/jobs/{cancel_id}", timeout=30)
    cancelled.raise_for_status()
    assert cancelled.json()["state"] == "cancelled"
    assert requests.get(f"{BASE}/api/jobs/{cancel_id}/result", timeout=30).status_code == 409
    print("PASS real worker cancellation and incomplete-result protection", flush=True)
    if matcalc:
        manifest = json.loads((ROOT / 'data' / 'matcalc' / 'manifest.json').read_text(encoding='utf-8'))
        for family, element, temperature in [("AL", "CU", 1073.15), ("FE", "CR", 1973.15), ("NI", "CR", 1873.15)]:
            job, result = submit({"family": family, "additions": [{"element": element, "maximum": 4}],
                                  "melt_temperature_k": temperature, "cooling_points": 5,
                                  "include_reference_properties": False})
            (output / f"matcalc-{family}.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
            print(f"PASS {family}: phases {[p['label'] for p in result['final']['phases']]}; Kawin {result['kawin']['state']}; job {job}", flush=True)
            assert result["kawin"]["state"] == "completed", result["kawin"]
            hashes = {item['role']: item['sha256'] for item in manifest['files'] if item['family'] == family}
            assert result["provenance"]["source_sha256"] == hashes['thermodynamic']
            assert result["provenance"]["mobility_source_sha256"] == hashes['mobility']
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="msedge", headless=True)
        for label, width, height, mode in [("desktop", 1500, 1040, "optimize"), ("mobile", 390, 844, "optimize"),
                                           ("create-desktop", 1500, 1040, "create"), ("create-mobile", 390, 844, "create")]:
            context = browser.new_context(viewport={"width": width, "height": height}, device_scale_factor=2,
                                          reduced_motion="reduce", accept_downloads=True)
            page = context.new_page()
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(BASE)
            page.locator('#start-button').click()
            page.locator('#menu-optimize').click()
            page.locator(f'#studio-{mode}').click()
            page.locator('#family-al').focus()
            page.keyboard.press('Enter')
            page.locator('#opt-next').click()
            page.locator('[name="opt-element"][value="Cu"]').check()
            if mode == 'create':
                page.locator('#opt-Cu-amount').fill('2')
                expect(page.locator('#alloy-balance')).to_have_text('98 wt%')
            else:
                page.locator('#opt-Cu-max').fill('4')
            page.locator('#opt-next').click()
            expect(page.locator('#opt-route option')).to_have_count(1)
            page.locator('#process-import').set_input_files(source)
            expect(page.locator('#process-source-status')).to_contain_text('Manual source', timeout=30000)
            page.locator('#process-reference-properties').uncheck()
            page.locator('#opt-next').click()
            if mode == 'optimize':
                page.locator('#opt-next').click()
                expect(page.locator('#opt-review')).to_contain_text('Cu 2 wt%')
            else:
                expect(page.locator('#opt-review')).to_contain_text('Simulation uses these exact amounts.')
            page.locator('#phase-run').focus()
            page.keyboard.press('Enter')
            expect(page.locator('#phase-result')).to_be_visible(timeout=120000)
            expect(page.locator('#phase-status')).to_contain_text('complete')
            expect(page.locator('#phase-result')).to_contain_text('mol%')
            expect(page.locator('#density-estimate')).to_be_visible()
            expect(page.locator('#modulus-estimate')).to_be_visible()
            page.locator('#phase-result summary', has_text='Assumptions').click()
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            page.screenshot(path=str(output / f'{label}-result.png'), full_page=True)
            with page.expect_download() as download:
                page.locator('#phase-export').click()
            saved = output / f'{label}-export.json'
            download.value.save_as(saved)
            exported = json.loads(saved.read_text(encoding='utf-8'))
            assert exported['composition']['nominal_percent'] == {'AL': 98, 'CU': 2}
            assert exported['settings']['composition_mode'] == ('fixed' if mode == 'create' else 'bounds')
            assert ('Exact entered' in exported['composition']['rule']) == (mode == 'create')
            page.locator('[data-review-edit="1"]').click()
            page.locator('#opt-Cu-amount' if mode == 'create' else '#opt-Cu-max').fill('6')
            expect(page.locator('#phase-status')).to_contain_text('Setup changed')
            assert not errors, errors
            print(f'PASS {label}: real phase simulation, manual upload, JSON export, stale-result labeling, keyboard and layout', flush=True)
            context.close()
        browser.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--matcalc', action='store_true')
    main(parser.parse_args().matcalc)
