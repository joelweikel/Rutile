# Architecture

## Boundaries

The browser owns presentation and user interaction. The FastAPI backend handles validation, source selection, scientific calculations, and persistence.

Request flow: frontend -> API -> application service -> scientific engine/property model -> structured result -> frontend.

Services use repositories for data access and subprocess jobs for long calculations. Scientific modules are callable outside HTTP for validation and batch work. Jobs retain request/source snapshots, status, structured results, and worker logs. Atomic preview snapshots contain partial boundary data and completed independent sample rows; `/api/jobs/{id}/preview` serves these separately from the compact status response. Previews are incomplete and are never treated as completed results. Cancellation terminates the subprocess; running calculations do not resume after restart.

## Module responsibilities

The frontend shell in `frontend/src/js/shell.js` owns navigation and browser-local appearance preferences. `rutile-scene.js` drives the camera and Canvas lattice. `gem-models.js` supplies shared geometry for the WebGL 2 gem renderer in `gem-optics.js` and the Canvas fallback. The decorative optics run independently of the scientific solver. `app.js` owns the phase-diagram form, staged workspace, job requests, and export. `phase-plot.js` renders vector boundary curves over phase-fraction shading, places labels, and handles pointer/keyboard inspection. Backend `engines/boundaries.py` isolates mapping, interpolation, and comparison. Switching screens keeps the same workspace and job state mounted in the browser.

| Backend package | Responsibility |
| --- | --- |
| `api` | HTTP endpoints, transport schemas, error translation |
| `domain` | Diagram inputs, source-selection types, units, and constraints |
| `services` | Database selection and calculation workflows |
| `engines` | pycalphad equilibrium, boundary mapping, and temperature estimation; later scientific adapters |
| `properties` | Reserved for future property calculations and calibrated models |
| `optimization` | Reserved for future objectives, constraints, and optimizer adapters |
| `data` | Catalog, source importers, repositories, migrations, and external-data clients |
| `jobs` | Execution, progress, cancellation, and artifact tracking |
| `core` | Configuration, logging, and infrastructure shared across the application |

Create more granular subpackages as concrete features need them, rather than creating speculative implementations.

## Storage

The local catalog uses SQLite metadata and file-backed datasets and results. Root `data/` is managed reference data. Root `workspace/` contains imports and runs. Version control includes only the directory documentation.

If the deployment uses a mapped/network drive, place the live SQLite catalog on a configurable local disk; validate locking and concurrency before supporting a shared catalog. Do not assume a database file on `Y:` is safe for concurrent writers.

Each run should pin source checksums, inputs, units, model and package versions, assumptions, and output artifacts. Store structured numerical outputs separately from plot presentation so users can replot without recalculating.

Job JSON writes use unique temporary files and bounded retries for Windows sharing
locks. API reads close their file handles before sending responses; previews are
loaded into memory rather than streamed from an open file. Failed progress or
preview publication is logged and retried on a later snapshot without aborting
the scientific calculation. Results and terminal status still use durable writes.
Status checks re-read after observing a worker exit to avoid confusing a concurrent
successful completion with a crash; a complete result can recover a missed final
status publication. Restarted incomplete jobs remain non-resumable.

Automatic temperature estimation is a worker preflight in `engines/temperature.py`.
It resolves limits before calling the binary mapper and updates preview settings
before any plot is drawn. Catalog selection defers only temperature applicability
for an Auto request; the worker enforces the selected source's documented limits
and stores both the original request and resolved inputs/probe provenance.

## Future capability boundaries

Equilibrium, solidification, diffusion, precipitation, and strength are separate models with explicit state-transfer steps. Scheil output requires an explicit interpretation before homogenization or aging calculations. Strength models require grain size, dislocation state, precipitate information, and calibration appropriate to the alloy family. Optimization must respect model validity ranges and expose uncertainty.
