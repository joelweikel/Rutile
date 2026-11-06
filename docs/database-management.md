# Database management

See the [automatic TDB catalog and selection plan](database-selection-plan.md) for the workflow, preference precedence, storage records, and implementation stages.

Open **Database library** in the phase-diagram workspace and choose **Scan source folders**. The scan reports progress and can be cancelled. Register additional absolute paths there, or import an individual file. Enter the elements and calculation conditions, then choose **Review database sources** to see the decision and candidate details. For uncertain coverage, select a candidate and record an assumption before running. A project ID is optional. Reusing it preserves the exact database version selected for a system.

The catalog defaults to a per-workspace directory under `%LOCALAPPDATA%\Rutile3` on Windows and `~/.local/share/Rutile3` elsewhere. Set `RUTILE_CATALOG_PATH` to a SQLite file on a local disk to override it. Scan results, user preferences, and coverage evidence persist across restarts.

### Curating coverage

Use `PUT /api/databases/{sha256}/coverage` to record coverage for a specific version, exact element system, and calculation capability. The request accepts an assessment status (`assessed`, `extrapolated`, or `unknown`), an evidence reference, optional citation and terms, assessed phases, documented year, validation and reference compatibility, and applicability limits. Limits use `temperature_k`, `pressure_pa`, and per-element `composition_mole_fraction` bounds. The binary map checks the full composition interval. Evidence entry is available through the API. A fresh catalog has no curated evidence for the external collection.

The catalog groups and checksums the original bytes of browser imports. A run keeps a copy of a user-imported source or a source whose evidence records permission to retain it. For other external sources, it records the location and checksum and verifies the content again in the worker. Reproducing those runs requires access to matching source content.

## User experience

Users define alloy elements, composition, conditions, and calculation type. The application selects or recommends compatible data and explains coverage gaps. Advanced users can inspect and override the choice. A saved project keeps its selection; new imports must not silently change old results.

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
