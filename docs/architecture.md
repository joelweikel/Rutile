# Architecture

## Boundaries

The browser owns presentation and user interaction. The FastAPI backend handles validation, source selection, scientific calculations, and persistence.

Request flow: frontend -> API -> application service -> scientific engine/property model -> structured result -> frontend.

Services use repositories for data access and job execution for long calculations. Scientific modules should also be callable outside HTTP for validation and batch work. Add process-based execution when real calculations are introduced; keep durable job IDs and explicit queued/running/completed/failed/cancelled states.

## Module responsibilities

| Backend package | Responsibility |
| --- | --- |
| `api` | Versioned endpoints, transport schemas, error translation |
| `domain` | Material definitions, composition bases, processing schedules, result contracts |
| `services` | Database selection and calculation workflows |
| `engines` | Adapters for pycalphad, Scheil, Kawin, and later engines |
| `properties` | Density, elasticity, strengthening, hardness, and model calibration |
| `optimization` | Objectives, constraints, candidate evaluation, and optimizer adapters |
| `data` | Catalog, source importers, repositories, migrations, and external-data clients |
| `jobs` | Execution, progress, cancellation, and artifact tracking |
| `core` | Configuration, logging, and infrastructure shared across the application |

Create more granular subpackages as concrete features need them, rather than creating speculative implementations.

## Storage

The local catalog uses SQLite metadata and file-backed datasets and results. Root `data/` is managed reference data. Root `workspace/` contains imports and runs. Version control includes only the directory documentation.

If the deployment uses a mapped/network drive, place the live SQLite catalog on a configurable local disk; validate locking and concurrency before supporting a shared catalog. Do not assume a database file on `Y:` is safe for concurrent writers.

Each run should pin source checksums, inputs, units, model and package versions, assumptions, and output artifacts. Store structured numerical outputs separately from plot presentation so users can replot without recalculating.

## Future capability boundaries

Equilibrium, solidification, diffusion, precipitation, and strength are separate models with explicit state-transfer steps. Scheil output requires an explicit interpretation before homogenization or aging calculations. Strength models require grain size, dislocation state, precipitate information, and calibration appropriate to the alloy family. Optimization must respect model validity ranges and expose uncertainty.
