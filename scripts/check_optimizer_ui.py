"""Exercise the UI-only alloy setup against a running server in headless Edge.

RUTILE_TEST_URL overrides http://127.0.0.1:8000. Artifacts stay in workspace/.
This checks setup behavior, not scientific model validity.
"""
import os
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
BASE = os.environ.get("RUTILE_TEST_URL", "http://127.0.0.1:8000")


def main():
    folder = ROOT / "workspace" / "optimizer-ui-check"
    folder.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        for label, width, height, reduced in [
            ("desktop", 1500, 1040, False),
            ("mobile", 390, 844, True),
        ]:
            context = browser.new_context(
                viewport={"width": width, "height": height}, device_scale_factor=2,
                reduced_motion="reduce" if reduced else "no-preference")
            page = context.new_page()
            errors, calculations = [], []
            page.add_init_script("""const originalTurn = WebGL2RenderingContext.prototype.uniformMatrix3fv;
                WebGL2RenderingContext.prototype.uniformMatrix3fv = function(location, transpose, values) {
                    window.crystalTurn = [...values];
                    return originalTurn.call(this, location, transpose, values);
                };
                const originalText = CanvasRenderingContext2D.prototype.fillText;
                CanvasRenderingContext2D.prototype.fillText = function(text, ...args) {
                    this.canvas.drawnSymbols ??= new Set(); this.canvas.drawnSymbols.add(text);
                    if (this.canvas.id === 'rutile-scene' && text === 'Al') {
                        window.revealSamples ??= []; window.revealSamples.push(`${args[0]},${args[1]}`);
                    }
                    return originalText.call(this, text, ...args);
                };
                const originalImage = CanvasRenderingContext2D.prototype.drawImage;
                CanvasRenderingContext2D.prototype.drawImage = function(image, ...args) {
                    if (this.canvas.id === 'rutile-scene' && args.length === 4) {
                        window.lastLatticeWidth = args[2];
                        window.renderedSymbols ??= [];
                        window.renderedSymbols.push(...(image.drawnSymbols || []));
                        window.latticeScales = [...(window.latticeScales || []).slice(-2), image.width / args[2]];
                    }
                    return originalImage.call(this, image, ...args);
                };""")
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.on("request", lambda req: calculations.append(req.url)
                    if "/api/diagrams" in req.url else None)
            page.goto(BASE)
            page.locator("#start-button").click()
            if reduced:
                canvas = page.locator('.scene')
                page.evaluate('new Promise(requestAnimationFrame)')
                initial = canvas.screenshot()
                initial_turn = page.evaluate('window.crystalTurn')
                page.keyboard.press('ArrowUp')
                page.evaluate('new Promise(requestAnimationFrame)')
                assert canvas.screenshot() != initial
                up_turn = page.evaluate('window.crystalTurn')
                assert up_turn[5] > initial_turn[5]
                page.keyboard.press('ArrowDown')
                page.evaluate('new Promise(requestAnimationFrame)')
                down_turn = page.evaluate('window.crystalTurn')
                assert all(abs(a - b) < 1e-8 for a, b in zip(down_turn, initial_turn))
                page.mouse.move(width * .4, height - 100)
                page.mouse.down()
                page.mouse.move(width * .4, height - 125, steps=3)
                page.mouse.up()
                page.evaluate('new Promise(requestAnimationFrame)')
                assert page.evaluate('window.crystalTurn[5]') > down_turn[5]
            page.evaluate('window.renderedSymbols = []')
            page.locator("#menu-optimize").focus()
            page.keyboard.press("Enter")
            expect(page.locator("#studio-heading")).to_be_focused()
            page.locator("#studio-optimize").focus()
            page.keyboard.press("Enter")
            expect(page.locator("#optimize-heading")).to_be_focused()
            assert page.locator("body").evaluate("el => el.hasAttribute('data-dive')") == (not reduced)
            page.locator("#screen-optimize").evaluate(
                "el => Promise.all(el.getAnimations().map(a => a.finished))")
            expect(page.locator('#rutile-scene')).to_have_attribute('data-structure', 'none')
            assert page.evaluate('window.renderedSymbols.length === 0')
            expect(page.locator('.optimizer-intro, .optimizer-progress')).to_have_count(0)
            expect(page.locator('#opt-family-heading')).to_have_text('Choose alloy family')
            expect(page.locator('.opt-eyebrow, .family-grid-key, .alloy-backdrop-note, .family-status')).to_have_count(0)
            expect(page.locator('.family-detail')).to_have_text('Select an alloy familyMatCalc thermodynamic sources')
            expect(page.locator(".family-tile")).to_have_count(15)
            expect(page.locator(".family-tile:not(:disabled)")).to_have_count(3)
            expect(page.locator(".family-available")).to_have_count(3)
            assert page.locator('.family-tile').evaluate_all("tiles => tiles.map(tile => tile.dataset.family)") == [
                'Mg', 'Al', 'Ti', 'Fe', 'Ni', 'Co', 'Cu', 'Zn', 'Zr', 'Ag', 'W', 'Pt', 'Au', 'Pb', 'other']
            expect(page.locator('.family-tile').last.locator('.family-symbol')).to_have_text('+')
            assert page.locator("#family-al").evaluate("el => el.clientWidth >= 80 && el.clientHeight >= 90")
            assert page.locator('#family-al .family-symbol').evaluate('el => parseFloat(getComputedStyle(el).borderRadius) < el.clientWidth / 3')
            expect(page.locator('[data-opt-step="4"]')).to_be_disabled()
            expect(page.locator("#opt-next")).to_be_disabled()
            expect(page.locator('[data-opt-step="1"]')).to_be_disabled()
            for symbol, structure in [('Fe', 'bcc-fe'), ('Ni', 'fcc-ni')]:
                page.locator(f'#family-{symbol.lower()}').focus()
                page.keyboard.press('Enter')
                expect(page.locator('#rutile-scene')).to_have_attribute('data-structure', structure)
                expect(page.locator('.family-detail')).to_contain_text('MatCalc')
                expect(page.locator('.family-detail')).not_to_contain_text('coverage unverified')
                expect(page.locator('#balance-label')).to_contain_text(symbol)
                expect(page.locator(f'[name="opt-element"][value="{symbol}"]')).to_be_disabled()
                page.wait_for_timeout(2300 if not reduced else 100)
                assert page.evaluate('window.latticeScales.length === 3 && Math.min(...window.latticeScales) >= .98')
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
                page.screenshot(path=str(folder / f'{label}-{symbol}.png'), full_page=True)
            assert page.evaluate("""async () => {
                const {makeBccLattice} = await import('/src/js/rutile-scene.js');
                const interior = makeBccLattice().filter(a => Math.hypot(...a.position) < .65);
                return interior.length > 0 && interior.every(a => a.element === 'Fe' && a.neighbours.length === 8);
            }""")
            page.evaluate('window.renderedSymbols = []')
            page.locator("#family-al").click()
            if not reduced:
                page.wait_for_timeout(200)
                first_atoms = page.evaluate('new Set(window.revealSamples || []).size')
                page.wait_for_timeout(600)
                assert page.evaluate('new Set(window.revealSamples || []).size') > first_atoms
                page.wait_for_timeout(1700)
            else:
                page.wait_for_timeout(100)
            expect(page.locator('#rutile-scene')).to_have_attribute('data-structure', 'fcc-al')
            assert page.evaluate('window.renderedSymbols.length > 0 && window.renderedSymbols.every(symbol => symbol === "Al")')
            assert page.evaluate('window.latticeScales.length === 3 && Math.min(...window.latticeScales) >= .98')
            settled = page.locator('#rutile-scene').evaluate('el => el.toDataURL()')
            page.wait_for_timeout(300)
            assert page.locator('#rutile-scene').evaluate('el => el.toDataURL()') == settled
            assert page.evaluate("""async () => {
                const {makeFccLattice} = await import('/src/js/rutile-scene.js');
                const atoms = makeFccLattice();
                // Stay one nearest-neighbor shell inside the clipped display slab.
                const interior = atoms.filter(a => Math.hypot(...a.position) < .65);
                return interior.length > 0 && interior.every(a => a.element === 'Al' && a.neighbours.length === 12);
            }""")
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            page.screenshot(path=str(folder / f"{label}-family.png"), full_page=True)
            expect(page.locator('[data-opt-step="1"]')).to_be_enabled()
            family_lattice_width = page.evaluate('window.lastLatticeWidth')
            page.locator("#opt-next").click()
            assert page.evaluate("scrollY === 0")
            expect(page.locator("#opt-composition-heading")).to_have_text("Select composition")
            assert page.locator("#shell-back").bounding_box()["y"] >= 0
            page.wait_for_function("expected => Math.abs(window.lastLatticeWidth / expected - 1.3) < .003", arg=family_lattice_width)
            assert page.evaluate('Math.min(...window.latticeScales) >= .98')
            expect(page.locator("#opt-next")).to_be_disabled()
            expect(page.locator('[data-opt-step="2"]')).to_be_disabled()
            page.wait_for_function("Number(getComputedStyle(document.querySelector('#rutile-scene')).opacity) < .2")
            page.locator('[name="opt-element"][value="Mg"]').check()
            page.locator('[name="opt-element"][value="Si"]').check()
            page.locator("#opt-Mg-min").fill("3")
            page.locator("#opt-Mg-max").fill("2")
            expect(page.locator("#opt-next")).to_be_disabled()
            expect(page.locator("#opt-error")).to_contain_text("minimum must not exceed")
            page.locator("#opt-Mg-min").fill("0.5")
            page.locator("#opt-Mg-max").fill("99")
            expect(page.locator("#opt-next")).to_be_disabled()
            expect(page.locator("#opt-error")).to_contain_text("below 100%")
            page.locator("#opt-Mg-max").fill("1.5")
            page.locator("#opt-Si-min").fill("0.4")
            page.locator("#opt-Si-max").fill("1")
            expect(page.locator("#alloy-balance")).to_have_text("97.5–99.1 wt%")
            page.locator('[name="opt-basis"][value="atomic"]').check()
            expect(page.locator("#alloy-balance")).to_have_text("97.5–99.1 at%")
            expect(page.locator("#opt-Mg-max")).to_have_value("1.5")
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            page.locator('[name="opt-basis"][value="mass"]').check()
            page.locator("#opt-next").click()
            expect(page.locator("#opt-route")).to_have_value('arc_melting')
            expect(page.locator('#opt-route option')).to_have_count(1)
            expect(page.locator('#opt-next')).to_be_enabled()
            page.locator('#process-melt-temperature').fill('20')
            expect(page.locator('#opt-next')).to_be_disabled()
            expect(page.locator('#opt-error')).to_contain_text('melt temperature')
            page.locator('#process-melt-temperature').fill('800')
            expect(page.locator('#opt-next')).to_be_enabled()
            expect(page.locator('#thermal-plot polyline')).to_have_count(1)
            page.locator('summary', has_text='Notes').click()
            page.locator("#opt-condition-notes").fill("<b>Class example</b>")
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            page.screenshot(path=str(folder / f"{label}-processing.png"), full_page=True)
            page.locator("#opt-next").click()
            page.locator("#add-opt-goal").click()
            expect(page.locator("#opt-goals .opt-rule")).to_have_count(2)
            page.locator("#add-opt-limit").click()
            limit = page.locator("#opt-limits .opt-rule").first
            limit.locator(".rule-value").fill("2.8")
            page.locator("#add-opt-limit").click()
            second = page.locator("#opt-limits .opt-rule").nth(1)
            second.locator(".rule-direction").select_option("min")
            second.locator(".rule-value").fill("3")
            expect(page.locator("#opt-next")).to_be_disabled()
            expect(page.locator("#opt-error")).to_contain_text("lower limit exceeds")
            second.locator(".rule-property").select_option("toughness")
            second.locator(".rule-value").fill("25")
            expect(page.locator("#opt-error")).to_be_hidden()
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            page.screenshot(path=str(folder / f"{label}-goals.png"), full_page=True)
            page.locator("#opt-next").click()
            expect(page.locator("#opt-review")).to_contain_text("97.5–99.1 wt%")
            expect(page.locator("#opt-review")).to_contain_text("800 °C")
            expect(page.locator("#opt-review")).to_contain_text("Arc melting")
            expect(page.locator("#opt-review")).to_contain_text("<b>Class example</b>")
            expect(page.locator("#opt-review b")).to_have_count(0)
            expect(page.locator("#phase-run")).to_be_enabled()
            page.screenshot(path=str(folder / f"{label}-review.png"), full_page=True)
            page.locator('[data-review-edit="1"]').click()
            expect(page.locator("#opt-Mg-max")).to_have_value("1.5")
            page.locator("#opt-Mg-max").fill("99")
            expect(page.locator('[data-opt-step="4"]')).to_be_disabled()
            expect(page.locator('[data-opt-step="2"]')).to_be_disabled()
            expect(page.locator("#opt-next")).to_be_disabled()
            expect(page.locator("#opt-error")).to_contain_text("below 100%")
            page.locator("#opt-Mg-max").fill("1.5")
            page.locator('[name="opt-element"][value="Mg"]').uncheck()
            page.locator('[name="opt-element"][value="Si"]').uncheck()
            expect(page.locator('[data-opt-step="2"]')).to_be_disabled()
            expect(page.locator("#opt-next")).to_be_disabled()
            page.locator('[name="opt-element"][value="Mg"]').check()
            expect(page.locator('[data-opt-step="2"]')).to_be_enabled()
            page.locator('[data-opt-step="4"]').click()
            expect(page.locator('[data-opt-panel="4"]')).to_be_visible()
            page.locator("#shell-back").click()
            expect(page.locator('[data-opt-panel="3"]')).to_be_visible()
            page.locator('[data-opt-step="0"]').click()
            page.evaluate('window.renderedSymbols = []')
            page.locator("#shell-back").click()
            expect(page.locator("#studio-optimize")).to_be_focused()
            page.wait_for_timeout(250)
            assert page.evaluate('window.renderedSymbols.every(symbol => symbol === "Al")')
            page.keyboard.press("Enter")
            expect(page.locator("#family-al")).to_have_attribute("aria-pressed", "true")
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            page.locator('#shell-back').click()
            page.locator('#studio-create').focus()
            page.keyboard.press('Enter')
            expect(page.locator('#optimize-heading')).to_have_text('Create alloy')
            expect(page.locator('.optimizer-steps button:visible')).to_have_count(4)
            expect(page.locator('[data-opt-step="3"]')).to_be_hidden()
            expect(page.locator('.family-available')).to_have_count(3)
            page.locator('#family-al').click()
            page.locator('#opt-next').click()
            expect(page.locator('#composition-title')).to_have_text('Composition amounts')
            expect(page.locator('#opt-Mg-min')).to_be_hidden()
            expect(page.locator('#opt-Mg-max')).to_be_hidden()
            page.locator('#opt-Mg-amount').fill('2.5')
            expect(page.locator('#alloy-balance')).to_have_text('97.5 wt%')
            expect(page.locator('#opt-next')).to_be_enabled()
            page.locator('[name="opt-element"][value="Cu"]').check()
            page.locator('#opt-Cu-amount').fill('97.5')
            expect(page.locator('#opt-next')).to_be_disabled()
            expect(page.locator('#opt-error')).to_contain_text('positive Al balance')
            expect(page.locator('#alloy-proportions')).to_be_hidden()
            page.locator('[name="opt-element"][value="Cu"]').uncheck()
            page.locator('[name="opt-basis"][value="atomic"]').check()
            expect(page.locator('#alloy-balance')).to_have_text('97.5 at%')
            expect(page.locator('#opt-Mg-amount')).to_have_value('2.5')
            page.locator('[name="opt-basis"][value="mass"]').check()
            page.locator('#opt-Mg-amount').fill('3')
            expect(page.locator('#alloy-balance')).to_have_text('97 wt%')
            expect(page.locator('#alloy-proportions')).to_have_attribute('aria-label', 'Al 97 wt%, Mg 3 wt%')
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            page.screenshot(path=str(folder / f'{label}-create-composition.png'), full_page=True)
            page.locator('#opt-next').click()
            assert page.evaluate('scrollY === 0')
            page.locator('#opt-next').click()
            expect(page.locator('[data-opt-panel="4"]')).to_be_visible()
            expect(page.locator('#opt-review .review-card')).to_have_count(3)
            expect(page.locator('#opt-review')).to_contain_text('Simulation uses these exact amounts.')
            expect(page.locator('#opt-review')).not_to_contain_text('Goals & limits')
            expect(page.locator('#simulation-composition-help')).not_to_contain_text('half')
            assert page.evaluate('scrollY === 0')
            page.locator('#shell-back').click()
            expect(page.locator('[data-opt-panel="2"]')).to_be_visible()
            assert page.evaluate('scrollY === 0')
            page.locator('[data-opt-step="0"]').click()
            page.locator('#shell-back').click()
            expect(page.locator('#studio-create')).to_be_focused()
            page.locator('#studio-optimize').click()
            page.locator('[data-opt-step="1"]').click()
            expect(page.locator('#opt-Mg-max')).to_have_value('5')
            expect(page.locator('#opt-Mg-amount')).to_be_hidden()
            page.locator('[data-opt-step="0"]').click()
            page.locator('#shell-back').click()
            page.locator('#shell-back').click()
            page.locator('#menu-diagrams').click()
            expect(page.locator('#rutile-scene')).to_have_attribute('data-structure', 'none')
            assert page.locator('.scene').evaluate('el => getComputedStyle(el).backgroundColor') == 'rgb(0, 0, 0)'
            assert page.locator('.wordmark').evaluate('el => el.getBoundingClientRect().bottom <= innerHeight')
            page.locator('#shell-back').click()
            page.locator('#menu-settings').click()
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            expect(page.locator('#materials-key')).to_be_visible()
            assert page.locator('#shell-back').bounding_box()['y'] >= 0
            assert not errors, errors
            assert not calculations, calculations
            print(f"PASS {label}: full setup, bounds/limits validation, edit revalidation, navigation, no calculation requests", flush=True)
            context.close()
        browser.close()


if __name__ == "__main__":
    main()
