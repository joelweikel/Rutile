# Phase diagram creation

## First deliverable

Implement a binary equilibrium temperature-composition diagram at fixed pressure, backed by a selected and validated pycalphad-compatible TDB. Make components, dependent component, composition basis, temperature range, pressure, phase selection, and resolution explicit.

The first UI should let users define the system and conditions, review automatic database selection, submit a job, inspect progress, and view/export results. Converting input mass fractions to the engine's required basis must be explicit and tested.

## Results and reproducibility

Return structured phase assemblages, compositions, fractions, calculation conditions, source checksums, solver version, warnings, and units. Plotting should preserve phase identities and explain failed or unresolved points rather than drawing fabricated boundaries through them.

Use a small redistributable binary assessment with a published reference diagram for acceptance. Verify characteristic phase regions and transition temperatures within documented tolerances; a plausible-looking image alone is insufficient.

## Later extensions

Add isothermal ternary sections, multicomponent sections, equilibrium property curves, and Scheil solidification paths. Clearly distinguish equilibrium diagrams from process-dependent predictions. Liquidus and solidus estimates must report the calculation method and assumptions.
