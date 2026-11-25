# Development roadmap

Rutile already supports binary equilibrium maps and a node-based Alloy Studio
with material-point equilibrium, phase assignment, density and elasticity,
tracer diffusion, classic Scheil, scoped isothermal precipitation, spectral
color, and conditional aluminum mechanical calculations. See
[current capabilities](current-state.md) for the limits of each feature.
The items below are priorities, not claims of completed work.

## Near-term usability and integrity

1. Make the Al–Cu starter's measured AA168 microstructure and calibration
   visibly condition-specific. Warn when users change an independent composition
   or schedule and could mistake the fixed mechanical result for a prediction.
2. Make the guided Optimize alloy form's phase-simulation-only status clear, or
   replace it with an executable, bounded workflow when supported objectives exist.
3. Expose the measured tensile-analysis workflow through normal navigation and
   retain measured data and fitted calibration with their material conditions.
4. Add a saved-run browser and portable workflow/result exchange with source
   identity, missing-source recovery and redistribution restrictions. Currently
   the browser restores only its last graph and available local job results.
5. Surface catalog search, coverage evidence, and compatible source choices in
   the UI. Provide reusable, condition-scoped kinetic and mechanical parameter
   records alongside the existing phase-property research workflow.

## Validated processing and properties

- Extend solidification histories into explicitly defined cast microstructure
  states. Assess cases requiring back diffusion, segregation, porosity and grain
  evolution with applicable inputs and independent measurements.
- Extend precipitation beyond the current single isothermal bulk-nucleation
  model only where suitable mechanisms, parameters and validation exist.
  Address quench and heterogeneous nucleation where they control the result.
- Validate mechanical stages against condition-matched microstructure, flow and
  hardness measurements. Add particle cutting, damage or fracture models only
  where their required inputs and applicability are established.
- Develop composition and process sweeps and optimization only over supported
  models, validity ranges and explicit feasibility or unavailable states.
- Expand alloy-family and optical coverage with separately sourced parameters,
  provenance and independent transfer benchmarks.
- Improve phase-identity resolution using source-specific model signatures,
  ordering and structure evidence. Keep identity, property applicability,
  and unresolved or competing candidates separate; do not substitute an
  MP structure's stability for the CALPHAD equilibrium.
- Improve reference-research validation with a condition-matched Mo–Hf pilot
  and a redistributable multiphase fixture. A possible density-model source is
  [Bocklund et al., Eq. 23 and Table A.1](https://www.osti.gov/servlets/purl/2427484);
  assess its composition and temperature range before use.

The Al–Cu starter mechanical branch currently uses an imported AA168
microstructure and condition-specific calibration; its precipitation model is
a separate exploratory branch. Equilibrium and processed microstructure are
not interchangeable. [Aluminum modeling](aluminum-family-modeling.md)

## Database and phase-diagram validation

Catalog registration, checksums, source selection and manual coverage evidence
exist through the API; a searchable catalog and evidence editor in the browser
remain to be built. A source's declared elements do not establish assessed
interaction coverage. [Database management](database-management.md)

Binary mapping includes boundary tracing and fallback mapping, independent
sample checks, previews, cancellation, inspection and structured export.
Synthetic regular-solution, ideal-melting and order/disorder tests check
numerical behavior. Published alloy-diagram benchmark validation remains
outstanding; specify reference sources, comparison metrics and tolerances before
claiming experimental accuracy. [Phase-diagram methods](phase-diagrams.md)

These are local development priorities, not external issue-tracker tickets.
For future reusable material states, preserve the original phase amounts,
composition and source identity; label omitted phases and keep calculated,
measured and assumed inputs distinct. Comparisons and optimization must retain
units, conditions, applicability and missing-coverage reasons.
