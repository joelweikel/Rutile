# Rutile3

Rutile3 is a local materials modeling application. The current version focuses on inspecting thermodynamic databases and calculating binary equilibrium phase diagrams. It uses a FastAPI backend, pycalphad for equilibrium calculations, and a browser interface built with HTML, CSS, and native JavaScript.

## Run locally

From the repository root in PowerShell with Python 3.12 installed, create the project environment and start the app.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -c requirements-win-py312.txt -e .
.\.venv\Scripts\python.exe scripts/run_app.py
```

Open http://127.0.0.1:8000 in your browser. Pass `--open` to launch the browser automatically or `--port 8001` to use a different port. The server listens only on loopback.

On other platforms, create the environment with `python3.12 -m venv .venv` and use `.venv/bin/python` to install the project with `-m pip install -e .` and run the same launcher. The constraints file targets Windows and Python 3.12.

## Calculate a binary phase diagram

1. Select a database from the catalog or import a pycalphad-compatible TDB file.
2. Choose two elements and set the temperature range, pressure in pascals, and grid resolution. The plot displays composition in atomic percent and temperature in kelvin.
3. Run the calculation and follow its progress in the browser. You can cancel a running job.
4. Inspect individual grid cells for molar phase fractions and phase compositions, and export the sampled equilibria, settings, warnings, and provenance as JSON.

Each cell represents equilibrium at a sampled composition and temperature. Grid resolution limits how precisely the plot locates phase boundaries. Database suitability depends on the assessment and its interaction coverage. The repository includes a synthetic miscibility-gap regression test. Published alloy benchmark validation remains a roadmap item.

The optional Materials Project lookup shows computed reference records for the selected chemical system. It requires an API key, which you can enter for the running server session or supply through `MP_API_KEY`. Equilibrium calculations use the selected TDB.

## Data and development

- Set `RUTILE_DATABASE_ROOT` before startup to scan an external source directory. The default on Windows is `Y:\ThermodynamicDatabases`. The app reads the source collection and stores imported copies and calculation runs under `workspace/` by default. Set `RUTILE_WORKSPACE` to use a different workspace.
- Backend code and tests live in `backend/src/rutile3/` and `backend/tests/`. The browser UI lives in `frontend/` and requires no build step.
- The `research` extra installs ESPEI and matminer. The `dev` extra installs test dependencies.

```powershell
.\.venv\Scripts\python.exe -m pip install -c requirements-win-py312.txt -e ".[dev]"
.\.venv\Scripts\python.exe -m pytest
```

Solidification, precipitation, calibrated property prediction, and alloy optimization are planned. See the [documentation index](docs/README.md) and [roadmap](docs/roadmap.md) for the scope and acceptance criteria.
