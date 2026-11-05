# Rutile3

Rutile3 runs locally in your browser and calculates binary equilibrium phase diagrams using pycalphad. You supply a thermodynamic database, choose two elements and a temperature range, then inspect the phases, molar phase fractions, and compositions across the calculated map.

The current app supports database inspection and import, binary phase maps at fixed pressure, background calculation with cancellation, JSON export, and optional Materials Project reference lookups. Solidification, precipitation, calibrated property prediction, and alloy optimization are not yet available in the app.

## Install and start

Use Python 3.12. Run these commands from the repository root.

### Windows (PowerShell)

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -c requirements-win-py312.txt -e .
.\.venv\Scripts\python.exe scripts/run_app.py
```

### Linux or macOS

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -e .
.venv/bin/python scripts/run_app.py
```

The constraints file is specifically for Windows and Python 3.12; do not use it for the Linux/macOS installation. The frontend needs no Node.js installation or build step.

On your local machine, open http://127.0.0.1:8000 in a browser. Keep the server terminal open while using the app. Stop it with **Ctrl+C**. On subsequent launches, run only the last command for your platform. Add `--open` to open a browser automatically, or `--port 8001` if port 8000 is in use.

The server listens on loopback only. If it runs on a remote machine, that machine's loopback address is not your computer's; use an appropriate supported remote-access workflow.

## 1. Load a thermodynamic database

A fresh checkout does not include an assessed alloy database. You need a pycalphad-compatible `.tdb` or `.tbd` text file with Gibbs-energy parameters for the system you want to study. A Materials Project key is not needed for phase-diagram calculations.

In **Define your system**:

1. Select a file from **Thermodynamic database**, using the search box to filter filenames and source labels.
2. If the library is empty, click **＋ Import a TDB file** and choose your file. Imports are limited to 10 MB and are copied into the local workspace; the original file is left alone.
3. Check the element count, phase count, and filename below the selector. If parsing fails or the file has no Gibbs-energy parameters, choose another thermodynamic database.

For an existing collection, set `RUTILE_DATABASE_ROOT` before starting the server:

```powershell
$env:RUTILE_DATABASE_ROOT = 'C:\path\to\databases'
.\.venv\Scripts\python.exe scripts/run_app.py
```

```bash
RUTILE_DATABASE_ROOT=/path/to/databases .venv/bin/python scripts/run_app.py
```

The default source location is `Y:/ThermodynamicDatabases`. If `Useful` or `SinglePhase` subdirectories exist under the source root, the app scans those subdirectories; otherwise it scans the root recursively. Imported files are also included. Restart the server after changing the source directory or adding external files, then reload the page.

## 2. Generate a phase diagram

1. Choose **Element A** and **Element B**. They must be different. The calculation includes these two elements and vacancies where required by the database; other chemical elements are excluded.
2. Set the **Temperature range** in kelvin. The default is 300–1200 K; the maximum must exceed the minimum.
3. Choose **Map resolution**. Start with **Quick look · 31 × 25**, then refine if needed. **Standard · 51 × 41** is the default; larger grids require more calculations.
4. Open **Calculation details** to change the pressure in pascals. The default is 101325 Pa. All compatible phases with Gibbs-energy data are considered; there is no manual phase-selection control.
5. Click **Generate diagram**. The status and progress bar report temperature-row progress. Only one calculation can run at a time. Use **Cancel calculation** to stop it and change the inputs.

The horizontal axis is atomic percent of **Element B**, not mass percent. The vertical axis is temperature in kelvin. The result is a sampled equilibrium map: finer grids can reveal smaller regions but do not automatically verify the database's accuracy or validity range.

## 3. Inspect and save results

- **Hover over a cell** to see its temperature, composition, and phase assemblage. The **At this point** panel shows each phase's molar amount and composition in atomic percent.
- **Click or tap a cell** to pin it. Click **Unpin ×** to follow the pointer again.
- **Use the keyboard:** focus the plot with Tab, use the arrow keys to move between cells, Enter to toggle pinning, and Escape to unpin.
- **Read split phases separately.** In a miscibility gap, labels such as `FCC_A1 #1` and `FCC_A1 #2` identify the same phase at distinct compositions. Numbering follows increasing element B content at that point.
- **Check warnings and unresolved cells.** Unresolved cells use a hatched fill. Open **Source & calculation provenance** to inspect the recorded source and solver information.
- Click **↓ Export JSON** to download the sampled equilibria, settings, warnings, and provenance, including the database checksum. The app currently has no image-export control.

Imported databases and calculation files persist on disk, but the browser does not provide a saved-run library or a JSON reimport control. Export results you want to keep handy before refreshing or closing the page. A server restart interrupts running calculations; they must be submitted again.

## Optional: Materials Project references

The **Materials Project ↗** tab looks up computed crystal references for the selected binary system and its pure elements. These records are supplementary candidates, not verified matches to the calculated CALPHAD phases, and do not replace the TDB.

1. Open **Connect Materials Project** in that tab.
2. Enter your Materials Project API key and click **Use for this session**. The app keeps this key in server memory, not in project files or browser storage. Submitting a blank field clears the session key.
3. Click **Load reference materials**, or use **Explore reference materials ↗** from the point inspector.

Alternatively, supply `MP_API_KEY` in the server environment before startup. Clearing the session key does not remove an environment-provided key. The server needs network access to `api.materialsproject.org`. The lookup shows up to 60 records, with available symmetry, density, energy above hull, and elastic-data availability; links open the corresponding Materials Project entries.

## Local files and troubleshooting

The default storage directory is `workspace/` under the repository. Set `RUTILE_WORKSPACE` before startup to use another location.

| Location | Contents |
| --- | --- |
| `workspace/imports/` | Imported database copies, grouped by content checksum |
| `workspace/runs/<job-id>/` | Source snapshot, request settings, job status, worker log, and completed result JSON |

These generated files and `.venv/` are ignored by Git. External source databases are read without modification.

- **No local databases found:** import a compatible file or set `RUTILE_DATABASE_ROOT` to a directory accessible on the machine running the server.
- **Generate diagram is disabled:** select a parsable database with Gibbs-energy parameters and two different elements.
- **No compatible phases / calculation failure:** check that the selected database describes the chosen binary system. For a failed worker, inspect `worker.log` in its run directory.
- **Materials Project fails:** check the key, network access, and reported service error. Phase-diagram calculations do not require this service.

A database listing two elements does not establish that their interactions are assessed. The app does not automatically check assessment validity ranges or select the best source. Validate scientific results against suitable references. The tests include a synthetic regular-solution miscibility-gap regression; published alloy benchmark validation remains a roadmap item.

## Development

Backend code and tests live in `backend/src/rutile3/` and `backend/tests/`; the browser interface lives in `frontend/`.

Install test dependencies and run the suite from the repository root:

```powershell
.\.venv\Scripts\python.exe -m pip install -c requirements-win-py312.txt -e ".[dev]"
.\.venv\Scripts\python.exe -m pytest
```

```bash
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/python -m pytest
```

The `research` extra declares ESPEI and matminer for research workflows. Installing extras does not add new application screens or calculation modes.

See the [documentation index](docs/README.md), [roadmap](docs/roadmap.md), and [project instructions for coding agents](AGENTS.md).
