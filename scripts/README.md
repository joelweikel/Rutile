# Developer utilities

Place reproducible environment, import, benchmark, and maintenance utilities here. Utilities should use backend modules rather than duplicate scientific logic and must not alter external source collections by default.

With Rutile running, run `scripts/check_browser.py` using the project’s Python environment. It uses Playwright with Microsoft Edge and the bundled Al–Cu TDB. It covers the animated shell, appearance settings, diagram workflow, and narrow layouts, and saves preview images in `workspace/`.

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
