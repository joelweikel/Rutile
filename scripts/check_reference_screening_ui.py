"""Live local MatCalc/MP regression for the reported Ni–Mn FCC example.

Requires the named external family sources and a configured server credential.
Screenshots and exports stay under ignored workspace/.
"""
import json
import os
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
BASE = os.environ.get('RUTILE_TEST_URL', 'http://127.0.0.1:8000')


def main():
    output = ROOT / 'workspace' / 'reference-screening-ui-check'
    output.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(channel='msedge', headless=True)
        for name, width, height in [('desktop', 1500, 1040), ('mobile', 390, 844)]:
            context = browser.new_context(viewport={'width': width, 'height': height},
                                          reduced_motion='reduce', device_scale_factor=2, accept_downloads=True)
            page = context.new_page()
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.goto(BASE)
            page.locator('#start-button').click()
            page.locator('#menu-optimize').click()
            page.locator('#studio-optimize').click()
            records = {item['family']: item for item in page.request.get(f'{BASE}/api/processing/sources').json()['sources']}
            for family in ['Al', 'Fe', 'Ni']:
                page.locator(f'#family-{family.lower()}').click()
                page.locator('#opt-next').click()
                expect(page.locator('#composition-source-help')).to_contain_text('Elements declared')
                visible = page.locator('[name="opt-element"]').evaluate_all(
                    'inputs => inputs.filter(i => !i.disabled).map(i => i.value.toUpperCase()).sort()')
                assert visible == sorted(set(records[family.upper()]['elements']) - {family.upper()})
                if family == 'Al':
                    expect(page.locator('[name="opt-element"][value="Ta"]')).not_to_be_visible()
                if family == 'Fe':
                    page.locator('[name="opt-element"][value="Ta"]').check()
                if family != 'Ni':
                    page.locator('[data-opt-step="0"]').click()
            expect(page.locator('[name="opt-element"][value="Ta"]')).not_to_be_checked()
            expect(page.locator('#opt-Ta-max')).to_have_count(0)
            page.locator('[name="opt-element"][value="Mn"]').check()
            page.locator('#opt-Mn-max').fill('50')
            page.locator('#opt-next').click()
            expect(page.locator('#process-screening-properties')).to_be_checked()
            page.locator('#opt-next').click()
            page.locator('#opt-next').click()
            page.locator('#phase-run').focus()
            page.keyboard.press('Enter')
            expect(page.locator('#phase-result')).to_be_visible(timeout=180000)
            expect(page.locator('#density-estimate')).to_contain_text('g/cm³')
            expect(page.locator('#modulus-estimate')).to_contain_text('GPa')
            expect(page.locator('.property-estimates')).to_contain_text('MatCalc DP')
            expect(page.locator('.property-estimates')).to_contain_text('not an alloy modulus')
            page.locator('summary', has_text='Property coverage').click()
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            page.locator('.property-estimates').screenshot(path=str(output / f'{name}-properties.png'))
            with page.expect_download() as download:
                page.locator('#phase-export').click()
            path = output / f'{name}-result.json'
            download.value.save_as(path)
            result = json.loads(path.read_text(encoding='utf-8'))
            assert result['composition']['nominal_percent'] == {'NI': 75, 'MN': 25}
            assert result['properties']['density']['state'] == 'estimated'
            assert result['properties']['density']['source'] == 'MatCalc DP'
            assert result['properties']['screening']['modulus']['host_element'] == 'NI'
            assert not errors, errors
            print(f'PASS {name}: source element filtering, unsupported selection cleanup, real Ni–Mn calculation, labeled screening cards and export', flush=True)
            context.close()
        browser.close()


if __name__ == '__main__':
    main()
