"""Capture current UI with genuine completed runs for documentation.

Run against a local server with a --rew-job UUID. The authoring
browser redirects matching diagram submissions to those completed jobs to avoid
recalculating unchanged science. This is not an app cache or saved-run browser.
Numerical results are never synthesized or edited. Sources must match examples/.
"""
import argparse
from hashlib import sha256
from io import BytesIO
import json
import os
from pathlib import Path

from PIL import Image
from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
BASE = os.environ.get("RUTILE_TEST_URL", "http://127.0.0.1:8000")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--rew-job', required=True)
    args = parser.parse_args()
    output = ROOT / 'docs' / 'images'

    def capture(page, filename):
        page.mouse.move(5, 5)
        page.evaluate('document.fonts.ready')
        page.wait_for_timeout(150)
        screenshot = page.screenshot(full_page=True)
        with Image.open(BytesIO(screenshot)) as im:
            im.convert('RGB').save(output / filename, 'WEBP', quality=88, method=6)
        print(f'Captured {filename}', flush=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(channel='msedge', headless=True)
        context = browser.new_context(viewport={'width': 1500, 'height': 1040}, device_scale_factor=1)
        page = context.new_page()
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.goto(BASE)
        page.locator('#title-heading').wait_for(state='visible')
        page.wait_for_timeout(1500)
        capture(page, 'title-screen.webp')
        page.locator('#title-settings').click()
        page.locator('#screen-settings').evaluate('el => Promise.all(el.getAnimations().map(a => a.finished))')
        page.wait_for_timeout(300)
        page.locator('#reduce-motion').check()
        page.locator('#shell-back').click()
        page.locator('#start-button').click()
        page.locator('#menu-optimize').click()
        page.locator('#studio-optimize').click()
        page.locator('#family-al').click()
        capture(page, 'alloy-family.webp')
        page.locator('#opt-next').click()
        for symbol, low, high in [('Mg', '.5', '1.5'), ('Si', '.4', '1')]:
            page.locator(f'[name="opt-element"][value="{symbol}"]').check()
            page.locator(f'#opt-{symbol}-min').fill(low)
            page.locator(f'#opt-{symbol}-max').fill(high)
        page.locator('#opt-next').click()
        page.locator('#opt-route').select_option('arc_melting')
        page.locator('#process-melt-temperature').fill('800')
        capture(page, 'alloy-processing.webp')
        page.locator('[data-opt-step="0"]').click()
        page.locator('#shell-back').click()  # Alloy Studio
        page.locator('#shell-back').click()  # Main menu
        page.locator('#menu-diagrams').click()
        for job, source, filename, x, temperature in [
            (args.rew_job, 'ReW-00Liu-LB.tdb', 're-w-phase-diagram.webp', .5, 2200),
        ]:
            response = page.request.get(f'{BASE}/api/jobs/{job}/result')
            assert response.ok, response.text()
            result = response.json()
            source_hash = sha256((ROOT / 'examples' / source).read_bytes()).hexdigest()
            assert result['provenance']['sha256'] == source_hash
            settings = result['settings']
            page.locator('#upload').set_input_files(ROOT / 'examples' / source)
            page.wait_for_function("!document.querySelector('#calculate').disabled")
            page.locator('#calculation-settings').evaluate('el => el.open = true')
            mode = settings.get('temperature_mode', 'manual')
            page.locator('#temperature-mode').select_option(mode)
            if mode == 'manual':
                page.locator('#tmin').fill(str(settings['temperature_min']))
                page.locator('#tmax').fill(str(settings['temperature_max']))
            page.locator('#resolution').select_option(f"{settings['composition_points']},{settings['temperature_points']}")

            def replay(route):
                request = route.request.post_data_json
                assert request['database_id'] == source_hash
                keys = ['components', 'pressure', 'composition_points', 'temperature_points',
                        'boundary_steps', 'boundary_tolerance']
                if mode == 'manual':
                    keys += ['temperature_min', 'temperature_max']
                assert request['temperature_mode'] == mode
                for key in keys:
                    assert request[key] == settings[key], (key, request[key], settings[key])
                route.fulfill(status=202, json={'id': job})

            page.route('**/api/diagrams', replay)
            page.locator('#calculate').click()
            page.wait_for_function("document.querySelector('#workspace').dataset.stage === 'complete'")
            page.unroute('**/api/diagrams', replay)
            page.locator('#calculation-settings').evaluate('el => el.open = false')
            page.locator('#plot').scroll_into_view_if_needed()
            point = page.evaluate("""([x,t,low,high]) => {
                const plot=document.querySelector('#plot'), p=plot.createSVGPoint();
                p.x=76+x*670; p.y=25+465-(t-low)/(high-low)*465;
                const q=p.matrixTransform(plot.getScreenCTM());return {x:q.x,y:q.y};
            }""", [x, temperature, settings['temperature_min'], settings['temperature_max']])
            page.mouse.click(point['x'], point['y'])
            expect(page.locator('#unpin')).to_be_visible()
            page.evaluate('scrollTo(0,0)')
            capture(page, filename)
            print(json.dumps({'source': source, 'checks': result['validation']['counts'],
                              'composition_points': settings['composition_points'],
                              'temperature_points': settings['temperature_points']}), flush=True)
        assert not errors, errors
        browser.close()


if __name__ == '__main__':
    main()
