# Mechanical properties

## Planned prediction for new alloys

Rutile will calculate a plastic flow curve from the processed microstructure.
The same constitutive model will supply yield strength, a hardness estimate,
and the tensile response up to the peak load. A fracture or damage model will
account for premature failure when it can limit that peak.

1. **Calculate phases.** Use an applicable CALPHAD assessment for the phase
   identities, compositions, and amounts at relevant processing stages. Keep
   the fraction basis explicit and use phase molar volumes when converting
   molar amounts to volume fractions.
2. **Calculate the processed state.** Use the thermal and deformation history
   to model the mechanisms relevant to the route. Solidification, grain
   growth and recrystallization, precipitation kinetics, and deformation and
   recovery can determine grain size, matrix solute content, precipitate size
   and spacing, phase morphology, texture, and dislocation density.
   [Kawin precipitation and strengthening example](https://kawin.org/docs/02-examples/strength/)
3. **Calculate the flow curve.** Use the matrix and second-phase state,
   elastic constants, slip geometry, and applicable strengthening mechanisms
   to establish the initial resistance to plastic flow. Evolve that resistance
   with a constitutive hardening law at the specified test temperature and
   strain rate. Reuse equations across alloy families where the same mechanisms
   apply. [Solid-solution strengthening in aluminum](https://doi.org/10.1038/nmat2813) · [Dislocation-based hardening in dilute alloys](https://link.springer.com/article/10.1007/s11661-024-07475-9)

### Yield, hardness, and tensile peak

- **Yield strength.** Use the modeled tensile response and the applicable
  yield definition, such as the 0.2% offset intersection for proof stress.
- **Vickers hardness.** In a suitable plastic indentation regime, estimate
  hardness from the true flow stress at a representative plastic strain.
  A Tabor-type estimate is `HV ≈ C × σ_flow(ε_rep) / 9.80665` with flow
  stress in MPa. Use a constraint factor `C` and representative strain
  `ε_rep` appropriate to the indentation and material response. Values near
  3 and 0.08 are approximations that require validation. [Representative strain in Vickers indentation](https://doi.org/10.1016/j.actamat.2010.08.010)
- **UTS when necking controls.** Calculate the peak engineering stress,
  `max(F / A₀)`, using the original cross-sectional area `A₀`. For
  approximately incompressible, rate-independent uniform tension, the
  Considère criterion identifies the peak when the true work-hardening rate
  falls to the true stress. [Maximum load in a tensile test](https://ocw.mit.edu/courses/3-11-mechanics-of-materials-fall-1999/d4ea545640f151bb66e6d8bc0ba55ed4_MIT3_11F99_ss.pdf)

### UTS estimated from measured hardness

Measured hardness can constrain one point on the flow curve. With an
independently established hardening law for the applicable alloy family and
condition, use that point to set the flow stress scale and calculate the
tensile peak. A published hardness-to-UTS conversion can also provide a
secondary estimate within its validated material, hardness scale, and range.
Record the test method and load, material condition, and conversion uncertainty.
A single hardness value leaves the hardening rate undetermined. When hardness
and UTS are both calculated from the same flow curve, agreement between them
is an internal consistency check. Independent validation requires a
measurement. [ISO 18265 hardness conversions](https://www.iso.org/standard/53810.html)

### Fracture-limited tensile peak

For a known crack under small-scale yielding, use crack size, geometry, and
condition-specific toughness to calculate the load for crack initiation. If
unstable fracture occurs while the tensile load is still rising, that failure
sets the specimen's peak load. With stable crack growth or substantial
plasticity, calculate the load history with an applicable elastic–plastic
fracture or ductile damage model, such as a void nucleation, growth, and
coalescence model. The peak can occur after damage begins. Keep the predicted
specimen peak load and fracture toughness as distinct outputs. [NASA fracture mechanics handbook](https://standards.nasa.gov/sites/default/files/standards/NASA/REVISION/0/2023-12-14-NASA-HDBK-5010-Vol-2-Rev-Final.pdf) · [Ductile tearing experiments and modeling](https://link.springer.com/article/10.1007/s10704-023-00701-2)

### Model inputs and experimental checks

Use published equations and applicable material parameters to build the
model. Use targeted experiments to calibrate physical parameters when needed.
First test the constitutive response with a measured microstructure. Then
test the full workflow using the calculated microstructure for the same
processing history. Compare grain size, phase fractions, and precipitate
sizes against microscopy or diffraction. Compare the flow curve against
tensile tests, hardness against matching indentation tests, and fracture
against tests with documented flaws or specimen geometry. Reserve independent
conditions, chemistries, or routes for testing transfer where relevant.
Record sources, validity ranges, and uncertainty. If a required mechanism or
input is missing, identify the affected output and the gap.

The existing **Estimate strength from composition** screen is a
nearest-neighbor prototype and is unsuitable for new-alloy design. Its
underlying tables can supply measured yield and UTS benchmarks when the
material and test conditions can be matched. [Aluminum table](https://data.mendeley.com/datasets/b6br4yk6r3/1) · [Steel table](https://data.mendeley.com/datasets/jmwb9ddd43/1)

## Analyze a tensile trace

The tensile-analysis API accepts a locally available reference specimen or a
single monotonic uniaxial tensile trace. The local reference
choices use the downloaded 6061-T651 bar, HCT590X sheet, and Inconel 625 specimens
under `workspace/reference-data/` (or the configured workspace). Uploads are available
for any alloy with an engineering tensile curve.

Use UTF-8 CSV or TSV with a header such as `engineering_strain,stress_MPa`.
Select fraction (mm/mm) or percent strain and enter the alloy and processing
condition. Keep the original test sequence. Optional test temperature and strain
rate are recorded as test conditions. A supplied Young’s modulus uses the strain
zero in the input file. Otherwise a linear regression estimates the modulus and
zero from the initial loading segment. Its result depends on the quality of the
strain measurement and the portion of the elastic range recorded. A supplied shear modulus enables isotropic
Poisson’s ratio from the two moduli. Alloy Studio’s equilibrium property results
also derive isotropic Poisson’s ratio from the Hill bulk and shear moduli when
both are available.

The first maximum engineering stress sets the end of the uniform-deformation
approximation. The maximum is labeled UTS when the trace shows a clear subsequent
load drop and a recorded peak otherwise. Proof stress is the interpolated 0.2%
offset intersection. The outputs are exploratory calculations from the test trace.

Through the peak, true stress is engineering stress times one plus engineering
strain. True plastic strain is log(1 + engineering strain) minus true stress
divided by Young’s modulus. The Voce saturation law is fit in the uniform plastic
range. The result includes its parameters, stress RMSE and fit range. Fitted UTS
is available when modeled engineering stress peaks inside that range.
Approximate Vickers hardness uses three times the fitted true flow stress at
0.08 true plastic strain divided by 9.80665, within the fit range. This conversion
needs comparison with condition-matched indentation measurements. The fit and
its residual describe the supplied test. Grain evolution and fracture require
additional models and data.
[Voce hardening](https://www.sandia.gov/files/sierra/SM_LAME_5_28/main/models/j2_plasticity.html)
· [Vickers representative strain](https://doi.org/10.1016/j.actamat.2010.08.010)

Each analysis saves the source bytes, SHA-256, material condition, fit settings
and versions with the calculation job. Export JSON preserves the trace,
derived metrics, model estimates, and warnings. The plot supports pointer
inspection and keyboard navigation with the arrow, Home and End keys.

The fitted engineering peak also gives a fitted uniform elongation. To report
measured permanent elongation after fracture, provide the original gauge length
and the gauge length measured after reassembling the fractured pieces.

## Aluminum mechanical workflow

Connect a precipitation result or imported Microstructure to **Aluminum
Mechanical Properties**. Use a process- and test-matched calibration and set
the validity ranges in the downloadable record. Each present particle population
requires a calibrated bypass spacing and coefficient. For measured or modeled
θ′ disks in binary Al–Cu, set its obstacle `model` to `theta_prime_plate` and
supply the sphere-equivalent radius, disk diameter-to-thickness ratio and volume
fraction in the microstructure. [Plate bypass model, equation 9](https://arxiv.org/abs/1804.09634)

The node calculates a necking-limited or pre-necking-rupture-limited tensile
peak from the calibrated response. Optional inputs add a sourced,
condition-calibrated particle transformation stress and a linear hardening
tail to the Voce law. If the response is still rising at the calibration limit,
the node reports the endpoint separately. With an independently determined mode-I
toughness and specified flaw geometry it also estimates critical remote stress
for crack initiation. [Aluminum coverage and validation](aluminum-family-modeling.md)
