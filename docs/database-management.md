# Database management

The catalog records source identities, suitability evidence, and selection decisions.
See the [roadmap](roadmap.md) for remaining browser controls and validation.

The phase-diagram workspace takes one uploaded thermodynamic file and offers the
elements parsed from it. The calculation pins that file and records coverage
uncertainty in the selection provenance. Alloy Studio processing uses the named
family assessment and its mobility companion by default, with a manual TDB
option. Source registration, scanning, coverage curation, and saved preferences
are available through the API. [Processing methods](processing.md)

The catalog defaults to a per-workspace directory under `%LOCALAPPDATA%\Rutile3` on Windows and `~/.local/share/Rutile3` elsewhere. Set `RUTILE_CATALOG_PATH` to a SQLite file on a local disk to override it. Scan results, user preferences, and coverage evidence persist across restarts.

### Curating coverage

Use `PUT /api/databases/{sha256}/coverage` to record coverage for a specific version, exact element system, and calculation capability. The request accepts an assessment status (`assessed`, `extrapolated`, or `unknown`), an evidence reference, optional citation and terms, assessed phases, documented year, validation and reference compatibility, and applicability limits. Limits use `temperature_k`, `pressure_pa`, and per-element `composition_mole_fraction` bounds. The binary map checks the full composition interval. Evidence entry is available through the API. A fresh catalog has no curated evidence for the external collection.

The catalog groups and checksums the original bytes of browser imports. A run keeps a copy of a user-imported source or a source whose evidence records permission to retain it. For other external sources, it records the location and checksum and verifies the content again in the worker. Reproducing those runs requires access to matching source content.

## Source selection API

`POST /api/databases/selection` evaluates a system and reports eligible
candidates, documented limits, and coverage warnings. A pinned source with
unresolved coverage requires a recorded assumption. The resolver can apply
saved selections and preferences by project ID. The resolver checks a saved
project selection, an explicit database ID, a project preference, a library
preference, then automatic selection, in that order. Preferences apply to an
exact element system and capability. Uncertain pinned coverage requires a
recorded assumption; an ineligible source cannot be selected. Automatic
selection requires eligible candidates without coverage warnings, and can
remain unresolved when evidence or phase coverage does not distinguish them.
A searchable catalog and project preference controls in the browser are planned.

## Import and catalog

1. Register a source directory or import a selected file without changing the original.
2. Calculate a content checksum to identify duplicates and versions.
3. Parse metadata and validate syntax using the appropriate scientific adapter.
4. Record elements, phases, phase models, parameter families, source citation, license, and assessed limits where known.
5. Keep validation findings and compatibility status separate from scientific accuracy claims.
6. Make usable sources available to selection workflows; show actionable reasons for excluded sources.

The existing `Y:\ThermodynamicDatabases` inventory is useful input, but its quality labels are not a substitute for validation. Volume-only and mobility-only files can be valuable supporting datasets.

## Selection rules

Match requested elements, relevant phases, calculation capability, composition/temperature applicability, and compatible model/reference conventions. Unknown assessed limits remain unknown. Do not treat all listed element combinations as validated. Do not automatically merge unrelated binary assessments.

Record thermodynamic, mobility, molar-volume, and mechanical-property sources separately. A successful TDB parse does not prove density, diffusion, or strength support.

## Experimental imports

Manual NIST downloads and selected literature data should retain the original file and map into normalized records containing property, value, unit, composition and basis, phase, temperature, pressure, sample processing, measurement method, uncertainty, and citation. Preserve missing fields explicitly. Record redistribution terms and import transformations.

Materials Project is supplementary; cache selected records with retrieval date, record ID, structure, calculation metadata, and available properties. Credentials stay on the backend. NIST's public website is available without registration, while its documented API access is available upon request; no live NIST API integration is assumed.
