# Rutile3 development instructions

## Purpose and priorities

Develop the existing local materials modeling application toward property extrapolation from CALPHAD thermodynamic equilibrium: connect stable phases, their compositions, and molar amounts to supported property models, with explicit assumptions and validation. The equilibrium foundation currently uses a FastAPI/Python backend, pycalphad solver, and HTML/CSS/native JavaScript UI. Implemented features include thermodynamic database inspection and import, binary equilibrium phase maps at fixed pressure, Auto/Manual temperature limits, parallel CPU workers, live previews and counted progress, cancellation, point inspection, JSON export, and optional Materials Project reference lookups.

Property extrapolation, calibrated property prediction, solidification, precipitation, and alloy optimization remain planned. Published alloy benchmark validation is also outstanding; scientific regressions use synthetic regular-solution, ideal-melting, and order/disorder models. See `README.md` for usage, `docs/roadmap.md` before expanding scope, and `docs/phase-diagrams.md` for current methods and limits. Some older documentation still describes the initial scaffold; check the implementation before relying on those descriptions.

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
- Independent check rows, fallback mapping temperature batches, and single-phase coverage anchors use spawned worker processes with separate solver state and reusable models/phase records. `cpu_workers: 0` selects up to eight workers; explicit requests are limited to 16 and one fewer than the detected logical CPU count (at least one). Melting preflight and boundary continuation remain sequential; there is no GPU solver acceleration.
- Preserve cancellation of the entire job process tree, worker exit when the coordinator dies, and one native BLAS/OpenMP thread per process for application jobs. Progress should report real counts; adaptive mapping counts describe the current pass, not a known total for the whole calculation.
- Preserve the distinction between thermodynamic equilibrium, solidification history, microstructure evolution, and engineering property prediction.

## Scientific and data integrity

- Always make units, composition basis (mass/mole/atomic fraction), temperature scale, pressure, and phase-fraction basis explicit.
- Track source identifiers, checksums, solver versions, model parameters, processing history, and assumptions with each saved run.
- Never substitute zero for missing property data or present dummy volume parameters as measurements.
- Database element lists alone do not establish assessed interaction coverage or applicability.
- Do not concatenate TDB assessments automatically or choose them solely by age, number of phases, or existing quality labels.
- Check compatibility of phase models, reference states, and mobility/thermodynamic descriptions.
- Boundary mapping first attempts pycalphad `BinaryStrategy`; the fallback uses sampled energy hulls to seed global equilibrium solves with adaptive temperature refinement. Keep the selected method and fallback reason. Hull vertices are candidate seeds, not converged boundary endpoints; independent sample checks remain separate from boundary discovery.
- Preserve the bounded quarter/midpoint/three-quarter probes in candidate mixed fields and probes in narrow intervening single-phase intervals. Record probe counts and retries. Do not replace physical phase transitions with cosmetic smoothing or infer accuracy from a visually smooth diagram.
- Exclude an extra standalone disordered representation only after matching active constituents, site ratios, and symbolic Gibbs energy to an ordered model's linked disordered contribution. Do not infer equivalence from names or sampled energies. Preserve the source and record exclusions in provenance; ordered-model labels can cover both ordered and disordered states.
- Preserve valid map regions when individual boundary seeds remain unresolved after retries. Keep partial maps, unverified coverage, unresolved equilibria, near-boundary differences, and disagreements distinct. Completed independent checks do not establish complete boundary coverage or experimental validity. Retain stage timings, resolved worker settings, and raw differences in saved results.
- Materials Project currently provides supplementary reference candidates, not verified CALPHAD phase matches. Any future matching must consider structure as well as composition; record missing property coverage.
- Separate measured values, computed reference values, estimates, and calibrated predictions in results.
- Strength and hardness require material-condition information and validation; do not imply that a TDB alone provides them.

## Source files and secrets

- Treat `Y:\ThermodynamicDatabases` as an external source collection. Do not edit, relocate, or delete source files unless the task explicitly requires it.
- `RUTILE_DATABASE_ROOT` overrides the source location and must be accessible to the server. The catalog recursively scans that root, explicitly registered roots, and managed imports for `.tdb`/`.tbd` files; it does not restrict scanning to `Useful` or `SinglePhase`. A fresh checkout includes assessed Al–Cu and Re–W examples under `examples/`, with attribution, checksums, and redistribution terms in `examples/README.md`. The external Windows collection may be unavailable on other machines.
- `RUTILE_WORKSPACE` overrides the default repository `workspace/` storage directory. Imports copy files into content-addressed folders; source collections remain read-only. Running calculations do not survive server shutdown, and the UI has no saved-run browser or JSON reimport control.
- `RUTILE_CATALOG_PATH` overrides the catalog SQLite file. Its default is outside the repository under the user's local application-data directory, namespaced by workspace identity.
- Derived conversions must preserve the original and record the transformation.
- Keep large datasets, local catalogs, user workspaces, generated results, virtual environments, and API keys out of version control.
- Use environment variables or local configuration for credentials; never place keys in frontend code, logs, documentation, fixtures, or example configuration.
- Materials Project access is optional and uses `MP_API_KEY` or a key held in server memory for the session. Preserve loopback binding, host/origin checks, upload limits, and key privacy. Ordinary phase calculations must work without Materials Project access.
- Keep redistribution and access terms with imported datasets. NIST Alloy Data website access does not imply unrestricted API access.

## Verification and UX

- Run the existing suite with the environment's Python and `-m pytest` from the repository root. It covers database import/inspection, API errors and origin checks, mocked Materials Project access, input validation, exact disordered-model equivalence, analytical miscibility-gap and melting behavior, boundary-seed retries, serial/parallel consistency with spawned workers, and counted progress. See `backend/tests/README.md` for scientific tolerances and scope.
- For changes to application startup or jobs, also verify a running server with a representative upload, completed calculation, and result retrieval. A server process or open port alone does not verify the worker workflow.
- For UI changes, exercise the affected controls, plot inspection, keyboard access, and mobile layout in a browser. `scripts/check_browser.py` requires Edge and uses the bundled Al–Cu assessment. `scripts/check_environment.py` imports research dependencies, including matminer, so it is not a base-install check.
- Use `scripts/benchmark_diagram.py` for reproducible worker timing without a web server; it retains the source snapshot, settings, result, logs, and `benchmark.json` under the run directory. `scripts/check_phase_workflow.py` exercises a supplied assessment against a running server. Compare like-for-like settings and source checksums, and report unresolved coverage alongside performance; a fast completed job is not a validated phase diagram.
- Test meaningful behavior: composition conversion, database suitability, phase mapping, scientific benchmark outputs, persistence, and error handling.
- Use small redistributable fixtures; avoid network calls in ordinary tests.
- Scientific regressions need documented tolerances and references, not exact floating-point equality.
- The current UI lets users select databases; it does not automatically establish assessment suitability or verify validity ranges. Explain source limitations, and preserve manual selection if adding reliable recommendations.
- Build accessible forms and keyboard navigation; label physical units and distinguish warnings from calculation failures.
- Preserve reduced-motion behavior, smooth panel transitions, and counted stage fills. The inspector labels disagreements while keeping nearest-sample values available for other checks. Crystal-view changes must preserve sharp settled rendering on high-DPI desktop/mobile displays: use the wide lattice cache during the dive and rebuild visible layers at the settled view's pixel density. See `docs/ui-ux.md` for interface behavior.
- Do not display mock calculations as real results.
- Report what was implemented, what was checked, and remaining limitations. Do not claim planned integrations are operational.
