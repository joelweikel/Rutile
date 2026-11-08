# Developer utilities

Place reproducible environment, import, benchmark, and maintenance utilities here. Utilities should use backend modules rather than duplicate scientific logic and must not alter external source collections by default.

With Rutile running, run `scripts/check_browser.py` using the project’s Python environment. It uses Playwright with Microsoft Edge and the bundled Al–Cu TDB. It covers the animated shell, appearance settings, diagram workflow, and narrow layouts, and saves preview images in `workspace/`.

`scripts/check_optimizer_ui.py` checks the five-step alloy setup preview in Edge
on desktop and mobile, including the shared zoom, reduced motion, composition
bounds, property limits, review/edit revalidation, and selection preservation.
It also checks vertical menu rotation, the empty optimizer background before
selection, progressive FCC Al illumination, sharp settled rendering, synchronized
step navigation, the editable processing graph, treatment reordering/removal,
cold-work reduction, footer placement, and the black diagram background.
It confirms that the preview makes no diagram calculation requests and retains
screenshots under `workspace/optimizer-ui-check/`. This is a UI check, not
scientific validation. It also accepts `RUTILE_TEST_URL`.

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

`scripts/capture_readme_images.py --rew-job UUID --alcu-job UUID` refreshes the
README's WebP screenshots using the current interface and genuine completed runs.
It requires a running server, Edge, and Pillow in the project environment. It
verifies bundled source checksums and matching calculation settings before
replaying completed job responses in its authoring browser; numerical results
are unchanged. This documentation utility does not add caching or a saved-run
browser to the app. It also captures the title, Settings, and alloy setup preview.
