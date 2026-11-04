# Rutile3

Rutile3 is a planned materials property modeling application with an HTML/CSS/JavaScript frontend and a Python backend. It will connect thermodynamic databases, phase diagrams, processing simulations, property models, and alloy optimization in one workflow.

## Current status

Project scaffold with its Python dependencies installed: the folder structure, Python package, virtual environment, and development documentation are established. There is no running web application or scientific engine integration yet. Installation checks do not replace scientific validation of each feature.

## First priorities

1. **Database management:** import and validate sources once, catalog their coverage, recommend suitable databases, and preserve reproducible selections without making users manage files for every calculation.
2. **Phase diagram creation:** start with validated binary equilibrium temperature-composition diagrams, then add isothermal sections and other calculations.
3. **UI/UX:** design a clear material-to-calculation-to-results workflow with useful progress, validation, and error messages.

See [the initial backlog](docs/roadmap.md) for acceptance criteria.

## Development environment

The initial environment uses Python 3.12.10 and lives in `.venv/`. In PowerShell, from the project root:

```powershell
.\.venv\Scripts\Activate.ps1
python --version
python -m pip install -c requirements-win-py312.txt -e ".[research]"
```

Activation is optional; this also works if PowerShell blocks activation scripts:

```powershell
.\.venv\Scripts\python.exe -m pip install -c requirements-win-py312.txt -e ".[research]"
```

To recreate the environment on another machine with Python 3.12:

```powershell
python -m venv .venv
```

The editable install makes the `rutile3` backend package importable. Core dependencies are declared in `pyproject.toml`; the `research` extra installs ESPEI and matminer. `requirements-win-py312.txt` records the resolved Windows/Python 3.12 dependency versions, excluding the local editable package. Omit `[research]` for a core-only installation. Other platforms need their own resolution and verification.

Verify the full environment without credentials or network access:

```powershell
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe scripts/check_environment.py
```

The check imports all discussed packages and exercises elemental data, composition conversion, numerical optimization, and a synthetic ideal-solution equilibrium calculation. It does not validate real alloy predictions or external API access. There is no frontend build step yet: use native JavaScript modules, HTML, and CSS initially.

## Layout

```text
Rutile3/
  .venv/                       Local Python environment (ignored)
  backend/
    src/rutile3/
      api/                     HTTP routes and request/response schemas
      domain/                  Shared material, composition, phase, and result types
      services/                Application workflows and orchestration
      engines/                 Scientific-library adapters
      properties/              Physical and mechanical property models
      optimization/            Composition and processing optimization
      data/                    Catalog, importers, repositories, and migrations
      jobs/                    Calculation execution, progress, cancellation
      core/                    Configuration, logging, and shared infrastructure
    tests/                     Unit, integration, and scientific regression checks
  frontend/
    src/
      js/                      UI modules, API client, views, and components
      styles/                  CSS foundations, layouts, and components
    public/                    Static assets
    tests/                     Browser and interaction checks
  data/                        Local imported datasets, catalog, and caches (ignored)
  workspace/                   User projects, calculation runs, and exports (ignored)
  examples/                    Small reproducible examples with redistributable inputs
  scripts/                     Developer and maintenance utilities
  docs/                        Architecture, data policy, UX, roadmap, and decisions
  pyproject.toml               Python packaging and dependency declarations
  AGENTS.md                    Repository development instructions
```

## Technical direction

- Python backend with a planned FastAPI HTTP boundary; keep scientific code independent of the web framework.
- HTML/CSS and native JavaScript modules for the frontend; introduce frontend tooling only when needed.
- A local database catalog, initially planned around SQLite, plus files for source datasets and calculation artifacts.
- pycalphad for equilibria, Scheil for solidification, and Kawin for diffusion/precipitation and supported strength contributions.
- mp-api/pymatgen and mendeleev for supplementary data; manually curated NIST imports with provenance.
- Calibrated property models and later pymoo optimization; ESPEI and matminer are optional extensions.

The libraries are installed, including optional ESPEI and matminer, but application integrations remain planned. FastAPI's [documentation](https://fastapi.tiangolo.com/) describes the proposed API framework.

## Existing thermodynamic sources

The existing collection is at `Y:\ThermodynamicDatabases`. Treat it as an external source library: do not move, rewrite, or bulk-copy it during setup. Future imports should record source paths, checksums, versions, coverage, and validation results. Paths must be configurable rather than embedded in scientific code.

## Documentation

Start with [the docs index](docs/README.md), [architecture](docs/architecture.md), [database management](docs/database-management.md), [phase diagrams](docs/phase-diagrams.md), and [UI/UX](docs/ui-ux.md).
