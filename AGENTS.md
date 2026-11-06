# Rutile3 development instructions

## Purpose and priorities

Develop the existing local materials modeling application with a FastAPI/Python backend, pycalphad equilibrium solver, and HTML/CSS/native JavaScript UI. Current features include thermodynamic database inspection and import, binary equilibrium phase maps at fixed pressure, background jobs with progress and cancellation, point inspection, JSON export, and optional Materials Project reference lookups.

Solidification, precipitation, calibrated property prediction, and alloy optimization remain planned. Published alloy benchmark validation is also outstanding; the existing scientific regression uses a synthetic regular solution. See `README.md` for current usage and `docs/roadmap.md` before expanding scope. Some older documentation still describes the initial scaffold; check the implementation before relying on those descriptions.

## Environment and layout

- Use Python 3.12 in the project virtual environment. Run `.venv/Scripts/python.exe` on Windows and `.venv/bin/python` on other platforms, from the repository root.
- Install with `python -m pip install -e '.[dev]'` using that environment's interpreter. On Windows, also pass `-c requirements-win-py312.txt`; these constraints are specific to Windows/Python 3.12.
- Start with the environment's Python and `scripts/run_app.py` (optional `--open` or `--port 8001`). It serves the API and frontend on loopback, port 8000 by default. The frontend has no Node.js dependency or build step.
- Backend source belongs in `backend/src/rutile3`; frontend source belongs in `frontend/src`.
- Declare dependencies in the root `pyproject.toml`; install into the project environment, not the system interpreter.
- Keep documentation under `docs/` and update it when behavior or architectural decisions change.
- Preserve the native JavaScript modules. Do not introduce a frontend framework or build system without a concrete feature need.
- Use the existing checkout in an isolated cloud task; do not create a Git worktree unless explicitly requested. Keep machine-specific setup and credentials out of these shared instructions.

## Architecture

- Keep HTTP transport in `api/`, orchestration in `services/`, and scientific library adapters in `engines/`.
- Keep domain types and property calculations independent of HTTP and UI code.
- Put catalog/import/storage code in the backend `data/` package. Keep local datasets in ignored storage, such as the root `data/` directory, and preserve the existing `workspace/imports/` and `workspace/runs/` layout for imported files and jobs.
- Scientific calculations must have explicit inputs and structured results. Preserve the existing subprocess job layer in `jobs/`, including progress, cancellation, source snapshots, settings, status, result JSON, and worker logs.
- Avoid blocking HTTP request handlers with long CPU-bound calculations.
- Preserve the distinction between thermodynamic equilibrium, solidification history, microstructure evolution, and engineering property prediction.

## Scientific and data integrity

- Always make units, composition basis (mass/mole/atomic fraction), temperature scale, pressure, and phase-fraction basis explicit.
- Track source identifiers, checksums, solver versions, model parameters, processing history, and assumptions with each saved run.
- Never substitute zero for missing property data or present dummy volume parameters as measurements.
- Database element lists alone do not establish assessed interaction coverage or applicability.
- Do not concatenate TDB assessments automatically or choose them solely by age, number of phases, or existing quality labels.
- Check compatibility of phase models, reference states, and mobility/thermodynamic descriptions.
- Materials Project currently provides supplementary reference candidates, not verified CALPHAD phase matches. Any future matching must consider structure as well as composition; record missing property coverage.
- Separate measured values, computed reference values, estimates, and calibrated predictions in results.
- Strength and hardness require material-condition information and validation; do not imply that a TDB alone provides them.

## Source files and secrets

- Treat `Y:\ThermodynamicDatabases` as an external source collection. Do not edit, relocate, or delete source files unless the task explicitly requires it.
- `RUTILE_DATABASE_ROOT` overrides the source location and must be accessible to the server. The catalog scans `Useful` and `SinglePhase` subdirectories when present, otherwise the source root. A fresh checkout includes one assessed Al–Cu example. The external Windows collection may be unavailable on other machines.
- `RUTILE_WORKSPACE` overrides the default repository `workspace/` storage directory. Imports copy files into content-addressed folders; source collections remain read-only. Running calculations do not survive server shutdown, and the UI has no saved-run browser or JSON reimport control.
- Derived conversions must preserve the original and record the transformation.
- Keep large datasets, local catalogs, user workspaces, generated results, virtual environments, and API keys out of version control.
- Use environment variables or local configuration for credentials; never place keys in frontend code, logs, documentation, fixtures, or example configuration.
- Materials Project access is optional and uses `MP_API_KEY` or a key held in server memory for the session. Preserve loopback binding, host/origin checks, upload limits, and key privacy. Ordinary phase calculations must work without Materials Project access.
- Keep redistribution and access terms with imported datasets. NIST Alloy Data website access does not imply unrestricted API access.

## Verification and UX

- Run the existing suite with the environment's Python and `-m pytest` from the repository root. It covers database import/inspection, API errors and origin checks, mocked Materials Project access, input validation, duplicate phase handling, and synthetic miscibility-gap behavior.
- For changes to application startup or jobs, also verify a running server with a representative upload, completed calculation, and result retrieval. A server process or open port alone does not verify the worker workflow.
- For UI changes, exercise the affected controls, plot inspection, keyboard access, and mobile layout in a browser. `scripts/check_browser.py` requires Edge and uses the bundled Al–Cu assessment. `scripts/check_environment.py` imports research dependencies, including matminer, so it is not a base-install check.
- Test meaningful behavior: composition conversion, database suitability, phase mapping, scientific benchmark outputs, persistence, and error handling.
- Use small redistributable fixtures; avoid network calls in ordinary tests.
- Scientific regressions need documented tolerances and references, not exact floating-point equality.
- The current UI lets users select databases; it does not automatically establish assessment suitability or verify validity ranges. Explain source limitations, and preserve manual selection if adding reliable recommendations.
- Build accessible forms and keyboard navigation; label physical units and distinguish warnings from calculation failures.
- Do not display mock calculations as real results.
- Report what was implemented, what was checked, and remaining limitations. Do not claim planned integrations are operational.
