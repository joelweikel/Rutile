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
.venv/Scripts/python.exe scripts/check_phase_workflow.py --database Y:/ThermodynamicDatabases/Useful/Binary/ReW/ReW-00Liu-LB.tdb --components RE W --maximum 4000
```

Set `RUTILE_TEST_URL` to use a separate loopback test server. The external example
is optional and is not required by the ordinary test suite.

Replace `--maximum 4000` with `--auto` to exercise the automatic melting-range
preflight and verify that the completed diagram uses its resolved limits.
