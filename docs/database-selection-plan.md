# Automatic TDB catalog and selection plan

The local catalog, coverage API, selection policy, and binary-diagram source review are implemented. Coverage curation is manual and starts with an empty evidence store. Mobility and volume metadata support library inspection. The current calculation adapter handles binary thermodynamic equilibrium. See [Database management](database-management.md) for setup and use.

## Goal and scope

Users define a material system and calculation conditions. Rutile3 catalogs available TDB files, recommends an applicable database, explains its decision, and lets users persist a preferred source for each binary, ternary, or higher-order system.

The first version selects one coherent thermodynamic database per calculation. A preference for an interaction means a preferred source for calculations of that element system, not permission to extract and combine parameters from unrelated files. Al-Cu, Al-Mg, and Cu-Mg preferences do not together define an Al-Cu-Mg database. Automatic assessment merging is out of scope.

## Catalog and storage

1. Register configurable source directories, including `Y:\ThermodynamicDatabases`, and scan without editing, moving, or deleting originals.
2. Identify file content by checksum. Group identical copies while retaining their locations; keep changed content as a distinct version.
3. Parse each file independently. Record failures without excluding other valid files from the catalog.
4. Record elements, phases, phase models, parameter families, supported capabilities, citations, access/redistribution terms, and assessment or release year when documented. File modification time is not assessment year. Preserve unknown values explicitly.
5. Build coverage records for element systems and relevant phases. Keep documented assessed coverage, detected parameters, extrapolation, and unknown coverage distinct, with evidence attached. Element lists and successful parsing do not prove assessment quality or applicability.
6. Record documented composition, temperature, and pressure limits, including units and composition basis. Do not infer unrestricted applicability from missing limits.

Use SQLite for metadata on a configurable local disk, with file-backed datasets and run artifacts. Do not assume a live catalog on the mapped `Y:` drive supports concurrent writers. Catalogs, imported files, and user preferences stay out of version control.

Where access terms allow, retain immutable managed copies to support reproduction. Otherwise retain source identity and location, and report when pinned content is unavailable. Recheck checksums before execution; a changed file must not silently stand in for a saved version. Derived conversions preserve the original and record their transformation.

## Preferences

The default for each system is **Automatic**. Users can instead select a **Preferred database** pinned to an exact content version. Store element systems in a canonical order so Al-Cu and Cu-Al refer to the same preference.

Support a library preference and a project override. Resolve choices in this order: an existing saved project selection, an explicit project override, a library preference, then automatic selection. Changing a saved project selection is an explicit user action; new catalog imports never replace it silently.

Preferences apply to the exact system and calculation capability. A binary preference does not automatically apply to a ternary request. Optional applicability scopes may constrain composition and temperature; these scopes must state units and composition basis. Begin with exact-system preferences and add scoped preferences only when the UI can explain their precedence unambiguously.

Every requested source still undergoes suitability checks. An incompatible preferred source produces an actionable conflict and alternatives, rather than a silent fallback. Users can acknowledge scientifically uncertain coverage with a recorded assumption, but cannot override an unreadable file or unsupported solver model into executable status.

## Automatic selection policy

Use an ordered policy with visible reasons rather than a phase-count/year score that could outweigh incompatibility.

| Order | Check | Behavior |
| --- | --- | --- |
| 1 | Technical eligibility | Exclude unreadable sources, unsupported models, missing required components, and incompatible calculation capabilities. |
| 2 | Applicability | Check documented composition, temperature, pressure, phase models, and reference conventions. Exclude known out-of-scope candidates from automatic selection; distinguish unknown limits from confirmed coverage. |
| 3 | Explicit selection or preference | Use the pinned applicable source; surface conflicts or missing content. |
| 4 | Scientific suitability | Prefer documented assessment coverage and relevant validation evidence for the requested system and conditions. Existing quality labels alone are insufficient. |
| 5 | Relevant phases | Compare coverage of phases needed for the requested calculation. Total phases in the file are not a quality measure. Missing required phases exclude a candidate; uncertain phase coverage remains visible. |
| 6 | Recency | Use documented assessment/release year only to distinguish otherwise comparable candidates. Unknown year remains unknown. |

Automatically select only when the evidence supports a clear applicable choice. If coverage is uncertain or candidates have unresolved scientific tradeoffs, present a recommendation and request a choice before calculation. Stable display ordering must not masquerade as a scientific tie-breaker.

For a multicomponent request, evaluate the whole system, including known higher-order assessments and extrapolation assumptions. Do not treat the presence of all binary pairs as proof of assessed higher-order coverage. Keep thermodynamic, mobility, and volume capabilities separate; a thermodynamic selection does not establish diffusion, density, strength, or hardness support.

## User workflow

The library presents a searchable table of system, automatic recommendation, saved preference, coverage status, and selection reason. A detail view shows source identity, citation/year, relevant phases, assessment evidence, documented limits, and exclusions.

1. Register or rescan a source directory and review import findings.
2. Define elements, composition and basis, temperature scale/range, pressure, and calculation type.
3. Review the automatic selection and explanation, or choose and save a preference.
4. Resolve missing coverage, incompatible preferences, or ambiguous candidates before submitting a calculation.
5. Save the selected source and decision with the project/run.

Provide keyboard-accessible controls and labeled units. Distinguish import errors, incompatibility, scientific uncertainty, and calculation failures. Offer an explicit return to Automatic and an explicit review of newly available versions. Do not display proposed selections or mock calculations as completed scientific results.

Example: an Al-Cu request can use the user's pinned Al-Cu preference when applicable. An Al-Cu-Mg request is evaluated independently against whole-system candidates; the three binary preferences are not merged.

## Records and responsibilities

Minimum persistent records:

- Source version: checksum, locations, original/derived relationship, citations, terms, documented year, parser/version, findings, and capabilities.
- Coverage evidence: source version, element system, relevant phases, assessment status, evidence reference, limits with units/basis, and unknowns.
- Preference: exact system, capability, library/project scope, pinned source version, and any explicit applicability constraints.
- Selection decision: request, selected checksum, policy version, preference used, candidate reasons, unresolved warnings, and user acknowledgments.
- Saved run: selection decision, explicit inputs and units, composition and phase-fraction bases, solver/package versions, model parameters, processing history, assumptions, and result references.

Catalog scanning, imports, and repositories belong in backend `data/`; selection orchestration belongs in `services/`; parser and solver adapters belong in `engines/`; HTTP transport stays in `api/`. Keep request and suitability types independent of HTTP and UI. Use native JavaScript modules for the frontend. Long scans or calculations should expose progress and cancellation through the job layer without blocking request handlers.

## Delivery stages and acceptance

1. **Catalog foundation:** register sources, compute checksums, parse independently, persist findings, and distinguish capabilities. Verify duplicate detection, changed-file versioning, missing files, and partial scan failures with small redistributable fixtures.
2. **Coverage and suitability:** persist evidence and evaluate explicit requests. Verify that element presence does not imply assessment coverage, unsupported models are excluded, missing limits remain unknown, and extra irrelevant phases or a newer year cannot outweigh suitability.
3. **Preferences and selection:** persist exact-system choices, implement precedence, explain recommendations, and require a choice for unresolved ambiguity. Verify project overrides, incompatible preferences, stable saved selections after imports, and independent handling of multicomponent requests.
4. **UI and provenance:** provide the library table, candidate details, accessible controls, and saved decision records. Verify keyboard operation, clear error/warning states, checksum checks before execution, and round-trip persistence of source identity and assumptions.

Ordinary tests use local fixtures without network access. Selection tests establish policy behavior, not thermodynamic accuracy. When the binary phase-diagram adapter is implemented, validate calculations against documented scientific references and tolerances as required by the separate phase-diagram milestone.

## Limitations

Coverage and assessment dates may require curated metadata because TDB syntax alone does not establish them reliably. Unknown evidence remains visible. The initial implementation does not automatically merge assessments, calibrate scientific models, guarantee accuracy from metadata, or provide mechanical properties from a TDB alone.
