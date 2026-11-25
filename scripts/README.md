# Developer utilities

Place reproducible environment, import, benchmark, and maintenance utilities here. Utilities should use backend modules rather than duplicate scientific logic and must not alter external source collections by default.

Run utilities from the repository root with the project Python environment.
Install the `dev` extra for pytest and Playwright, and use
`requirements-win-py312.txt` as a constraint file on Windows.
`scripts/check_environment.py` also imports the `research` extra, including
ESPEI and matminer. It checks installation and an analytical ideal solution.

With Rutile running, run `scripts/check_browser.py` using the project’s Python environment. It uses Playwright with Microsoft Edge and the bundled Al–Cu TDB. It covers the animated shell, appearance settings, diagram workflow, and narrow layouts, and saves preview images in `workspace/`.

`scripts/check_settings_ui.py` checks desktop and mobile Materials Project key
save and removal, MCP setup, failed-save feedback, keyboard access, and
bundled Al/Fe/Ni mobility indicators. Run against an isolated local test server
with a disposable `.env` and no saved key. It saves a test credential and
screenshots under `workspace/settings-ui-check/`. `RUTILE_TEST_URL` selects the server.

`scripts/check_optimizer_ui.py` checks the Alloy studio submenu, five-step optimization
setup, and four-step exact-composition creation setup in Edge
on desktop and mobile, including the shared zoom, reduced motion, composition
bounds, exact amounts and base balance, property limits, review/edit revalidation,
selection preservation, and step changes that keep the top Back button visible.
It also checks vertical menu rotation, the empty optimizer background before
selection, family switching, BCC Fe coordination, progressive FCC Al illumination, sharp settled rendering, synchronized
step navigation, the 30% composition camera zoom, arc-melting temperatures,
footer placement, and the black diagram background.
It confirms that the setup preview makes no diagram calculation requests;
optimization itself is not implemented. It retains
screenshots under `workspace/optimizer-ui-check/`. This is a UI check, not
scientific validation. It also accepts `RUTILE_TEST_URL`.

`scripts/check_processing_workflow.py` uploads the bundled Al-Cu assessment,
completes a real processing subprocess job, retrieves balanced results, cancels
a second worker, and checks real desktop/mobile UI simulation, upload, export,
keyboard operation, and stale-result notices in both Optimize alloy and Create
alloy, including exported exact-composition settings. Reference API lookups are
disabled for these local checks. `--matcalc` additionally exercises
the bundled Al–Cu, Fe–Cr, Ni–Cr, Mg–Al, Ti–Al, and Mo–Ti family companions with real Kawin diffusion
calculations. It is an integration check, not experimental validation. Artifacts
stay under `workspace/processing-ui-check/`; `RUTILE_TEST_URL` is supported.

For a supplied local assessment, `check_phase_workflow.py` runs a Detailed-quality
upload/calculation/inspection workflow while repeatedly reading status and previews
to exercise Windows sharing-lock handling. It also checks full-width setup, the
loading bar position, black liquid, keyboard access, and mobile overflow. Source
files remain unchanged; calculations, managed imports, and screenshots stay in
ignored workspace storage. For example:

```powershell
.venv/Scripts/python.exe scripts/check_phase_workflow.py --database examples/ReW-00Liu-LB.tdb --components RE W --maximum 4000
```

Set `RUTILE_TEST_URL` to use a separate loopback test server. This browser check
is optional and is not required by the ordinary test suite.

Replace `--maximum 4000` with `--auto` to exercise the automatic melting-range
preflight and verify that the completed diagram uses its resolved limits.

`benchmark_diagram.py` runs a real subprocess job without starting a web server.
It retains the source snapshot, settings, progress, logs, result, and a
`benchmark.json` summary under `workspace/runs/` (or `RUTILE_WORKSPACE`). It reports
stage times, check classifications, warnings, and the source checksum; a completed
job can still contain unresolved map regions or disagreements. For example:

```powershell
.venv/Scripts/python.exe scripts/benchmark_diagram.py --database examples/ReW-00Liu-LB.tdb --components RE W --auto --workers 8
```

Use `--workers 1` for a serial comparison, `--quality quick` for a smaller run,
or `--minimum 300 --maximum 4000` instead of `--auto` for fixed limits. The default
timeout is 600 seconds; timeout or Ctrl+C cancels the worker and its children.

`scripts/check_plot_ui.py` uses explicitly synthetic display fixtures against a
running server to check zoom-to-black, liquid callout placement, pointer/keyboard
label movement and reset, current-phase legends, contrast, sample controls, and
mobile layout. Screenshots are retained in `workspace/plot-ui-check/`. It does not
validate thermodynamics; `check_browser.py` exercises a real assessed calculation.

`scripts/capture_readme_images.py --rew-job UUID` refreshes the
README's WebP screenshots using the current interface and genuine completed runs.
It requires a running server, Edge, and Pillow in the project environment. It
verifies bundled source checksums and matching calculation settings before
replaying completed job responses in its authoring browser; numerical results
are unchanged. This documentation utility does not add caching or a saved-run
browser to the app. It also captures the title and alloy setup preview.

`scripts/check_reference_screening_ui.py` exercises the 75 wt% Ni / 25 wt% Mn
example with a configured Materials Project key. It checks source-specific
element choices and property export on desktop and mobile. Its assertions
expect the historical pure-host modulus proxy. Current processing tries offline
elemental modulus interpolation before the host proxy, so the script can fail
on a valid interpolation result. Artifacts stay in
`workspace/reference-screening-ui-check/`. [Current screening methods](../docs/processing.md#solid-solution-screening-fallback)

`scripts/benchmark_density.py` runs six explicit nominal alloy compositions
(6061, 7075, 304L, 316L, INCONEL 600 and 625) through the processing worker,
with Materials Project disabled. It saves full coverage/failure results and
separate constrained-FCC diagnostics. See `docs/density-benchmarks.md` for
reference sources, omissions and interpretation; these are not experimental
validation results.
