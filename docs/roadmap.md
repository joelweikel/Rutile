# Initial implementation backlog

The following are local issue outlines; no external issue tracker tickets have been created.

## 1. Database management foundation

Deliver a catalog, configurable source registration, checksum-based duplicate detection, TDB parsing/validation, coverage inspection, and persistent source selection.

Acceptance:
- Register the existing database collection without editing source files.
- Distinguish thermodynamic, mobility, and volume capabilities.
- Given a requested system, explain suitable candidates and missing coverage.
- Save a selection with immutable source identity for reproducible runs.
- Report parsing failures without preventing valid files from being cataloged.

## 2. Binary phase diagram workflow

Deliver the first pycalphad adapter, explicit composition/units validation, calculation job lifecycle, structured results, plotting, and export.

Acceptance:
- Reproduce a documented reference binary diagram within stated tolerances.
- Keep numerical results and provenance independent of the displayed plot.
- Explain invalid inputs, unsupported systems, and failed calculations.
- Keep the UI responsive during a calculation and expose job status.

## 3. UI/UX foundation

Deliver material/project navigation, composition forms, data-library inspection, a phase-diagram workspace, and shared UI styles/components.

Acceptance:
- A user can reach a diagram without manually choosing a TDB when a verified default is available.
- Ambiguous coverage prompts an understandable choice instead of silently selecting an arbitrary source.
- Forms are keyboard accessible and display units and composition basis.
- Loading, empty, success, and failure states are implemented.

## Later milestones

1. Curated property imports, phase-aware molar volume/density, and uncertainty metadata.
2. Scheil solidification and explicit transfer to processing simulations.
3. Compatible mobility sources, Kawin precipitation/diffusion, and experimental validation.
4. Calibrated strength/hardness models for a selected alloy family.
5. Composition/process optimization with validity constraints and uncertainty-aware comparison.
6. Additional alloy families and optional ESPEI/matminer integrations.
