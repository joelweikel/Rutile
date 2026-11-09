# Development roadmap

The binary workflow now includes traced boundaries, phase-fraction gradients,
independent sample checks, Auto/Manual temperature ranges, live previews,
cancellation, inspection, and structured export. Windows sharing-lock handling
and targeted equilibrium retries are implemented. Synthetic scientific
regressions and local Al–Cu, Ta–Zr, and Re–W browser checks cover numerical and
workflow behavior; published alloy benchmark validation remains outstanding.

The outlines below retain acceptance criteria for the broader project. They are
not all completed features. Material-point arc melting with equilibrium cooling and supplementary Kawin
tracer diffusion are implemented. Scheil solidification, precipitation kinetics,
calibrated property prediction, and optimization remain planned.

The following are local issue outlines; no external issue tracker tickets have been created.

## 1. Database management foundation

Implementation detail: [Automatic TDB catalog and selection plan](database-selection-plan.md).

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

The current interface has an animated intro, an interactive title screen, a tile menu, appearance settings, and the phase-diagram workspace. See the [interface guide](ui-ux.md) for screen behavior and styling.

The Alloy studio menu opens Optimize alloy with composition bounds, arc melting,
property goals/limits, and review, or Create alloy with exact composition amounts,
arc melting, and review. Both share Al/Fe/Ni families. Phase simulation uses pycalphad
initial/melt/cooling equilibria and compatible Kawin tracer diffusion, with explicit
assumptions and source transformations. Property optimization, precipitation time
integration, and persisted project browsing remain planned. See [processing](processing.md).

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
