"""Layout/interaction checks using explicitly synthetic display fixtures.

Requires a running server and Edge. Does not validate thermodynamics or execute
calculations. Real solver/inspection coverage remains in check_browser.py.
"""
import copy
import os
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
BASE = os.environ.get("RUTILE_TEST_URL", "http://127.0.0.1:8000")


def fixture(phase=None):
    settings = dict(components=["AL", "CU"], temperature_min=300,
                    temperature_max=1200, composition_points=31, temperature_points=25)
    cells = []
    for ti in range(25):
        for xi in range(31):
            name = phase or ("FCC_A1" if xi < 15 else "LIQUID")
            cells.append(dict(xi=xi, ti=ti, valid=True, check="agreement", phases=[
                dict(phase=name, label=name, fraction=1, composition={"AL": .5, "CU": .5})]))
    ribbons = [] if phase else [
        dict(ties=[dict(temperature=t, left=left, right=right, phases=names)
                   for t in (450, 600, 750, 900)])
        for left, right, names in [(.498, .5, ["FCC_A1", "NARROW"]),
                                   (.5, .502, ["NARROW", "LIQUID"])]]
    return dict(settings=settings, cells=cells, validation={"counts": {"agreement": 775}},
                boundaries=dict(ribbons=ribbons, single_phase_bands=[
                    dict(phase=phase or "LIQUID", temperature_min=300 if phase else 1000,
                         temperature_max=1200)], invariants=[]))


def main():
    folder = ROOT / "workspace" / "plot-ui-check"
    folder.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        for name, width, height, reduce in [("desktop", 1500, 1040, False), ("mobile", 390, 844, True)]:
            context = browser.new_context(viewport={"width": width, "height": height},
                                          reduced_motion="reduce" if reduce else "no-preference")
            page = context.new_page()
            page.route("**/src/js/app.js*", lambda route: route.abort())
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(BASE)
            page.locator("#start-button").click()
            page.locator("#menu-diagrams").click()
            expect(page.locator("#rutile-scene")).to_have_attribute("data-structure", "none")
            if not reduce:
                assert page.locator('body').evaluate("el => el.hasAttribute('data-dive')")
                page.wait_for_timeout(400)
                assert page.locator('#rutile-scene').evaluate("el => el.getContext('2d').getImageData(0,0,el.width,el.height).data.some((v,i) => i%4===3 && v>0)")
                page.wait_for_timeout(1600)
            assert page.locator('#rutile-scene').evaluate("el => !el.getContext('2d').getImageData(0,0,el.width,el.height).data.some((v,i) => i%4===3 && v>0)")
            page.evaluate("""async data => {
                const {createPhasePlot} = await import('/src/js/phase-plot.js');
                window.plotHarness = createPhasePlot(); window.plotHarness.render(data);
                document.querySelector('#diagram-panel').hidden = false;
                document.querySelector('#workspace').dataset.stage = 'complete';
                document.querySelector('#system-title').textContent = 'Synthetic display fixture · UI check only';
            }""", fixture())
            label = page.locator('[data-region-label="NARROW"]')
            expect(label).to_have_attribute('data-label-placement', 'liquid')
            original_x = float(label.get_attribute('data-label-x'))
            label.locator('rect').scroll_into_view_if_needed()
            box = label.locator('rect').bounding_box()
            page.mouse.move(box['x'] + box['width'] / 2, box['y'] + box['height'] / 2)
            page.mouse.down()
            page.mouse.move(box['x'] + box['width'] / 2 + 24, box['y'] + box['height'] / 2 + 12, steps=4)
            page.mouse.up()
            expect(label).to_have_attribute('data-label-placement', 'manual')
            assert float(label.get_attribute('data-label-x')) > original_x
            expect(page.locator('#unpin')).to_be_hidden()
            moved_x = float(label.get_attribute('data-label-x'))
            label.focus()
            page.keyboard.press('Shift+ArrowRight')
            assert float(label.get_attribute('data-label-x')) == moved_x + 12
            page.locator('#reset-labels').click()
            expect(label).to_have_attribute('data-label-placement', 'liquid')
            expect(page.locator('#legend .legend-item')).to_have_count(3)
            liquid = page.locator('#legend .legend-item').filter(has_text='LIQUID')
            assert liquid.evaluate('el => getComputedStyle(el).backgroundColor') == 'rgb(0, 0, 0)'
            assert liquid.evaluate('el => getComputedStyle(el).color') == 'rgb(255, 255, 255)'
            expect(page.locator('#sample-count')).to_have_text('775 samples')
            expect(page.locator('#disagreement-key')).to_be_hidden()
            page.locator('#show-samples').check()
            expect(page.locator('#checks circle')).to_have_count(775)
            divergent = copy.deepcopy(fixture())
            divergent['cells'][0]['check'] = 'disagreement'
            divergent['validation']['counts'] = dict(agreement=774, disagreement=1)
            page.evaluate('data => window.plotHarness.render(data)', divergent)
            expect(page.locator('#disagreement-key')).to_be_visible()
            assert int(page.locator('#legend .legend-item').first.evaluate('el => parseFloat(getComputedStyle(el).fontSize)')) >= 14
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            page.screenshot(path=str(folder / f'{name}.png'), full_page=True)
            page.evaluate('data => window.plotHarness.render(data)', fixture('BETA'))
            expect(page.locator('#legend')).to_have_text('BETA')
            expect(page.locator('#disagreement-key')).to_be_hidden()
            page.evaluate('window.plotHarness.reset()')
            expect(page.locator('#legend .legend-item')).to_have_count(0)
            expect(page.locator('#diagram-details')).to_be_hidden()
            assert not errors, errors
            print(f'PASS {name}: zoom to black, liquid callouts, pointer/keyboard label movement, legend replacement, sample controls', flush=True)
            context.close()
        browser.close()


if __name__ == '__main__':
    main()
