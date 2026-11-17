# Documentation

- [Architecture](architecture.md): component boundaries, subprocess jobs, previews, and storage.
- [Database management](database-management.md): catalog, suitability checks, provenance, and imports.
- [Automatic TDB selection plan](database-selection-plan.md): catalog workflow, system preferences, selection rules, and staged acceptance criteria.
- [Phase diagrams](phase-diagrams.md): Auto/Manual ranges, boundary tracing, gradients, independent checks, exports, and scientific limits.
- [Processing](processing.md): equilibrium arc melting, nominal compositions, MatCalc conversion, Kawin transport context, jobs, and limits.
- The planned Alloy Studio canvas, file sharing, and implementation milestones. [Alloy Studio workflow plan](alloy-studio-workflow-plan.md)
- Planned pin types, record fields, node inputs and outputs, and MatCalc file connections. [Alloy Studio node catalog](alloy-studio-node-catalog.md)
- Read the plan for microstructure-based plastic flow, hardness, tensile strength, and fracture, and the current tensile analysis instructions. [Mechanical properties](mechanical-properties.md)
- Screen navigation, Alloy Studio setup, result inspection, and accessibility. [UI/UX](ui-ux.md)
- [Roadmap](roadmap.md): implemented scope, outstanding validation, and later milestones.
- [Decisions](decisions/README.md): record consequential technical choices.

The interface, architecture, and current phase-diagram workflow describe the
implementation. Planning sections and later milestones remain prospective.
See the [verification guide](../backend/tests/README.md) and
[developer utilities](../scripts/README.md) for automated and browser checks.

- [Phase registry](phase-registry.md): resolution design, model constraints, property routing, and initial density-rule scope.
- [Density benchmarks](density-benchmarks.md): six common alloy comparisons, source references, constrained-FCC diagnostics and coverage failures.
- The bundled phase identity snapshot, attribution rules, and Alloy Studio integration. [MatCalc to Materials Project translation](matcalc-mp-translation-layer.md)
- Design notes for broader phase resolution and property coverage. [Phase translation plan](matcalc-materials-project-translation.md)
