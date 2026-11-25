# Current capabilities and limits

Rutile is a local CALPHAD and materials-modeling application. The workflows
below describe what is available today; the [roadmap](roadmap.md) describes
remaining work. A completed calculation is not by itself experimental
validation or evidence that the selected assessment applies.

## Phase diagrams

The phase-diagram screen uploads one thermodynamic file and maps a binary
system at fixed pressure. It supports automatic or manual temperature limits,
live partial previews, cancellation, independent sample checks, interactive
inspection, and JSON export. Unresolved equilibria, unverified regions and
disagreements are reported separately. Published alloy-diagram validation is
still outstanding. There is no diagram saved-run browser or result import.
[Methods and limits](phase-diagrams.md)

## Alloy Studio

The native node editor runs connected calculations in separate jobs. It offers:

| Node or input | Available behavior | Main limits |
| --- | --- | --- |
| Composition, Processing Schedule and file inputs | Fixed composition in mass or atomic basis, ordered thermal events, and thermodynamic, mobility and physical-data selections. | Source element lists do not establish assessed interaction coverage or compatibility. |
| Equilibrium Along Schedule | Material-point equilibrium at thermal setpoints, including an optional fully liquid melt and sampled equilibrium cooling. | An equilibrium cooling or quench result is not a kinetic solidification or quench prediction. |
| Phase Assignment and Phase Viewer | Inspect phase amounts and compositions and attach screened references or local phase properties. Optional research can find missing density and elasticity evidence. | Identity and property applicability are separate; some phases lack usable properties. |
| Density and Elasticity | Phase-aware density and isotropic elastic estimates where required source data are available; optional user-supplied porosity. | Missing phase volumes or stiffness can prevent a full-alloy result. Solute, temperature, texture and porosity model coverage is limited. |
| Tracer Diffusivity | Kawin tracer coefficients using the final phase state and a compatible mobility file. | Availability depends on supported phases and mobility data; a reference-only fallback is labeled. |
| Scheil Solidification | Classic Al-family Scheil history, including phase and liquid compositions and amounts. | Assumes a mixed liquid and no solid diffusion. It does not produce grain size, porosity, or a complete cast microstructure. |
| Precipitation Kinetics | Kawin isothermal kinetics from a compatible solutionized phase state, an aging hold, mobility and supplied model parameters. | A homogeneous matrix, no initial precipitates, fixed shape and bulk nucleation are assumed. General quenching, heterogeneous nucleation and non-isothermal aging are not modeled. |
| Import Microstructure and Microstructure Viewer | Import measured or modeled microstructure records and inspect the samples with a schematic visualization. | Particle positions and section geometry are illustrative, not reconstructed microscopy. |
| Aluminum Mechanical Properties | Conditional flow, proof stress, hardness and other available metrics from a precipitation result or imported microstructure and a matched calibration. | Inputs and model validity are condition-specific. Grain state, particle mechanisms, hardening and fracture data may be missing; no general new-alloy prediction is established. |
| Phase Colors and Spectral Color | Assign reference swatches or calculate polished phase and surface color from supported spectra; optionally run local DFT for supported structures. | Spectrum and structure coverage is limited. Etched colors are assigned references, not predicted etching. |

The Al–Cu starter includes separate casting and aging branches. Its mechanical
node consumes the **AA168 microstructure (TEM)** input and bundled AA168
calibration; it is not connected to the Composition or Precipitation Kinetics
nodes. Changing the composition or schedule does not update that measured
microstructure or mark the mechanical branch stale. Use a condition-matched
microstructure and calibration for another case. The exploratory bulk θ′
precipitation run does not reproduce the observed heterogeneous nucleation.
[Aluminum workflow](aluminum-family-modeling.md) ·
[Processing](processing.md) · [Precipitation](precipitation.md) ·
[Spectral color](optical-colors.md)

## Guided setup and tensile analysis

**Project → Guided setup** offers Create alloy and Optimize alloy forms. They
can submit an equilibrium phase simulation using the specified composition or,
in Optimize alloy, a nominal composition. Optimize alloy does not run an optimizer or evaluate the entered objectives and property limits.
[Processing](processing.md)

A measured tensile-curve analysis and a composition-based strength prototype
exist in the backend and frontend, but the current interface has no navigation
entry for their screen. The composition prototype is unsuitable for new-alloy
design. [Mechanical methods](mechanical-properties.md)

## Sources, results and portability

The bundled MatCalc sources include Al, Fe, Mg, Mo, Ni and Ti assessments,
their named mobility companions, and physical density data. The bundled
Materials Project identity snapshot covers the pinned Al, Fe and Ni
assessments; provisional searches may support other compatible phases.
Identity is not proof that a property transfers to a particular composition
or condition. [Source and reference methods](processing.md)

The browser stores the last Alloy Studio graph and references to local
completed jobs. The `.rutile` export contains the workflow definition, not
the calculation results or uploaded thermodynamic, mobility, and physical-data files. On another installation,
use the same available sources or reselect the custom files and rerun. Result
JSON can be exported separately; there is no general result reimport or
saved-run browser. Interrupted jobs do not resume after server shutdown.
[Interface guide](ui-ux.md#alloy-studio-workflows)

Independent checks and documented synthetic tests establish selected numerical
and software behavior; independent, condition-matched experimental validation
and demonstrated transfer remain necessary for alloy design.
[Verification scope](../backend/tests/README.md)
