# Rutile3 development instructions

## Purpose and priorities

Build a materials property modeling application with an HTML/CSS/JavaScript UI and Python backend. Initial priorities are database management, phase diagram creation, and UI/UX. See `docs/roadmap.md` before expanding scope. This repository currently contains a scaffold, not a working solver or application.

## Environment and layout

- Run Python through `.venv/Scripts/python.exe` on Windows; use `.venv/bin/python` on other platforms. Initial interpreter: Python 3.12.
- Backend source belongs in `backend/src/rutile3`; frontend source belongs in `frontend/src`.
- Declare dependencies in the root `pyproject.toml`; install into the project environment, not the system interpreter.
- Keep documentation under `docs/` and update it when behavior or architectural decisions change.
- Use native JavaScript modules initially. Do not introduce a frontend framework or build system without a concrete feature need.

## Architecture

- Keep HTTP transport in `api/`, orchestration in `services/`, and scientific library adapters in `engines/`.
- Keep domain types and property calculations independent of HTTP and UI code.
- Put catalog/import/storage code in the backend `data/` package; put local datasets in the root `data/` directory.
- Scientific calculations must have explicit inputs and structured results; expose progress and cancellation through the job layer when long-running work is introduced.
- Avoid blocking HTTP request handlers with long CPU-bound calculations.
- Preserve the distinction between thermodynamic equilibrium, solidification history, microstructure evolution, and engineering property prediction.

## Scientific and data integrity

- Always make units, composition basis (mass/mole/atomic fraction), temperature scale, pressure, and phase-fraction basis explicit.
- Track source identifiers, checksums, solver versions, model parameters, processing history, and assumptions with each saved run.
- Never substitute zero for missing property data or present dummy volume parameters as measurements.
- Database element lists alone do not establish assessed interaction coverage or applicability.
- Do not concatenate TDB assessments automatically or choose them solely by age, number of phases, or existing quality labels.
- Check compatibility of phase models, reference states, and mobility/thermodynamic descriptions.
- Match Materials Project records by structure as well as composition; record missing property coverage.
- Separate measured values, computed reference values, estimates, and calibrated predictions in results.
- Strength and hardness require material-condition information and validation; do not imply that a TDB alone provides them.

## Source files and secrets

- Treat `Y:\ThermodynamicDatabases` as an external source collection. Do not edit, relocate, or delete source files unless the task explicitly requires it.
- Derived conversions must preserve the original and record the transformation.
- Keep large datasets, local catalogs, user workspaces, generated results, virtual environments, and API keys out of version control.
- Use environment variables or local configuration for credentials; never place keys in frontend code, logs, documentation, fixtures, or example configuration.
- Keep redistribution and access terms with imported datasets. NIST Alloy Data website access does not imply unrestricted API access.

## Verification and UX

- Test meaningful behavior: composition conversion, database suitability, phase mapping, scientific benchmark outputs, persistence, and error handling.
- Use small redistributable fixtures; avoid network calls in ordinary tests.
- Scientific regressions need documented tolerances and references, not exact floating-point equality.
- Keep database decisions automatic where reliable, explain selections, and expose manual overrides for advanced users.
- Build accessible forms and keyboard navigation; label physical units and distinguish warnings from calculation failures.
- Do not display mock calculations as real results.
- Report what was implemented, what was checked, and remaining limitations. Do not claim planned integrations are operational.
