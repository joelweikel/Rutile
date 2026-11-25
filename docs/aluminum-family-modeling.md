# Aluminum alloy family modeling strategy

## Goal and scope

Develop reusable, mechanistic predictions for aluminum alloys across composition and processing conditions. Target strength, density, elastic moduli, polished color, microstructure, hardness, crack resistance, and elongation at break. The aim is to support alloy optimization without collecting a new property dataset for every small composition change.

The model architecture should cover the aluminum family; individual alloy systems and processing routes are validation cases, not separate product architectures. Coverage and accuracy must be established for a defined composition, process, and test-condition range before results are used for optimization.

## Shared modeling stages

1. **Thermodynamics and diffusion:** Calculate phase identities, compositions, and amounts using an applicable multicomponent assessment. Use compatible mobility data for diffusion and kinetics.
2. **Processing and microstructure:** Model the relevant solidification, segregation, grain evolution, precipitation, deformation, and recovery mechanisms for the actual processing history. Carry phase morphology, particle state, grain size, and defects forward when the applicable models and inputs are available.
3. **Density and elasticity:** Calculate phase volumes and elastic properties using applicable phase and constituent models, then combine phases on an explicit volume basis. Include porosity, texture, or other corrections when supported by the intended application.
4. **Strength and hardness:** Calculate a flow response from the processed state and relevant strengthening mechanisms. Derive yield and tensile strength from that response and estimate hardness using an applicable, validated indentation relationship.
5. **Crack resistance and elongation:** Couple deformation with applicable damage and fracture models. Define the requested fracture metric, loading, flaw or specimen geometry, and test conditions explicitly.
6. **Polished color:** Calculate phase spectra using applicable optical data or electronic-structure methods. Account for phase structure and composition, and model the combined surface appearance when multiple phases contribute.

These are development targets, not claims that the current application implements the complete pipeline. Equilibrium phases alone do not establish a processed microstructure or mechanical properties.

## Parameters and data

Reuse equations across alloy systems wherever the underlying mechanism applies. Element-, phase-, interaction-, and processing-specific parameters will still be required. Obtain them from compatible assessed multicomponent databases, physical calculations, experiments, and published measurements as appropriate; record their sources, units, validity ranges, and uncertainty.

Parameterize physically meaningful quantities rather than fitting a direct composition-to-property predictor. Identify missing or inapplicable inputs and affected outputs explicitly. Do not substitute a base-metal value or silently extrapolate to fill a gap.

## Validation and coverage

Validate the shared framework in stages, using condition-matched measurements of phase state and microstructure before testing complete property predictions. Exercise distinct aluminum alloy mechanisms with representative Al–Cu, Al–Mg–Si, Al–Zn–Mg–Cu, and cast Al–Si cases. Reserve compositions and processing conditions for independent transfer tests; a successful Al–Cu test alone does not establish family-wide validity.

Define the optimizer's supported composition, processing, and test-condition space. Measure both the fraction of that space for which a result is available and the fraction meeting an agreed error tolerance against independent benchmarks. The long-term 99% goal applies to a defined space and acceptance criteria, not to arbitrary aluminum alloys or a guarantee of accuracy merely because a number was produced. Expose gaps and uncertainty to the optimizer.

## Alloy Studio workflows

Open **Project → Al–Cu starter** and select **Run graph** for Al–4 wt% Cu.
The casting branch runs equilibrium, Scheil solidification, density and
elasticity, tracer diffusivity, and polished-section color using assigned phase
volumes. Near room temperature, the equilibrium FCC matrix uses published Al
stiffness as a zeroth-order estimate at up to 10 atomic ppm Cu.

The aging branch runs exploratory bulk θ′ precipitation at 453 K for 168 h
from the solutionized equilibrium. The default bulk-nucleation model predicts
no appreciable θ′ and omits the observed heterogeneous nucleation pathways.
The **AA168 microstructure (TEM)** input separately supplies the measured
plate population and inferred matrix composition for the **Microstructure Viewer**
and **Aluminum Mechanical Properties**. The bundled reduced flow calibration
uses the published simulated polycrystal curve, and the indentation factor is
calibrated to the published HV0.5 measurement. This produces a proof stress,
Vickers hardness, and a flow curve through the calibrated strain range. The
tensile peak, elongation at break, and crack initiation remain unavailable for
this example. The mechanical branch is independent of the Composition and
Precipitation Kinetics nodes: changing those inputs does not update or mark its
result stale. For other conditions, supply matched microstructure and calibration.
[AA168 microscopy and hardness](https://arxiv.org/abs/1804.09634) ·
[AA168 polycrystal simulation](https://arxiv.org/abs/2005.07426)

The **Composition** inspector accepts additional elements in the same basis as
the first addition. Enter `Mg 2.5, Cu 1.6` alongside 5.6 wt% Zn to model an
Al–Zn–Mg–Cu case. The base fills the balance.

| Property | Calculation and inputs | Current limits |
| --- | --- | --- |
| Microstructure | **Scheil Solidification** takes an aluminum equilibrium run with a verified arc melt. It saves the remaining liquid composition and the identities, amounts and compositions of solids deposited at each step. **Precipitation Kinetics** takes a solutionized phase set, compatible mobility and sourced phase and nucleation parameters. A solved disordered MatCalc `GP_MAT` starting state can use the linked `FCC_A1` matrix. Bulk-nucleated particles can use fixed sphere, plate or needle geometry. | Classic Scheil assumes complete liquid mixing and zero solid diffusion. The last balanced state is retained when an interval remains unresolved. Grain size, shrinkage porosity, quench kinetics, heterogeneous nucleation and recovery need separate inputs or models. |
| Density | **Density and Elasticity** combines atomic molar volumes from MatCalc DP and compatible crystal references. Offline estimates use θ-Al₂Cu, Mg₂Si and diamond-Si diffraction data and Al-rich FCC lattice changes of Cu, Mg, Si and Zn near 298 K. Optional bulk density uses a supplied pore volume fraction and source. | The FCC multicomponent approximation adds binary lattice changes inside the tabulated binary ranges and up to 5 at% total solute. Full density needs volume data for every present phase. |
| Elastic moduli | The same node calculates fully dense isotropic Voigt–Reuss–Hill bulk, shear and Young’s moduli and Poisson’s ratio. It includes room-temperature stiffness references for elemental Al, diamond Si and near-stoichiometric θ-Al₂Cu, temperature-dependent Mg₂Si moduli, and matched Phase Data. | Solute-dependent stiffness, pore geometry, texture and many intermetallic tensors need independent inputs. |
| Strength | **Aluminum Mechanical Properties** consumes the last sample of a precipitation result or imported Microstructure. Supply grain size, dislocation density, particle bypass parameters and a calibration matched to the matrix and test conditions. The model combines lattice friction, Labusch-type solute, Hall–Petch grain, Taylor dislocation and bypass contributions with Voce hardening. It computes 0.2% proof stress and the engineering tensile peak. | Particle cutting, brittle-phase load transfer and anisotropy need separate models. The coefficients and work hardening require calibration for the applicable condition. |
| Hardness | The mechanical node estimates Vickers hardness from flow stress using the supplied representative strain, constraint factor and test force. | Compare against independent Vickers tests at the same force, material condition and surface preparation. |
| Crack resistance | The mechanical node estimates critical remote stress for mode-I initiation from supplied condition-matched toughness, crack size, geometry factor, ligament and thickness. It checks yielding and a conservative size criterion. | Intrinsic toughness, stable tearing, fatigue growth and large-scale yielding need dedicated models and test data. |
| Elongation at break | The mechanical node can report uniform elongation and estimate in-test elongation at rupture when a calibrated critical plastic strain is reached before diffuse necking. **Analyze a tensile trace** can calculate measured permanent elongation from the original and reassembled fracture gauge lengths. | Post-necking rupture needs a localization and damage model with the specimen geometry. |
| Polished color | **Spectral Color** resolves reference and optional DFT spectra and accepts condition-matched measured reflectance. Exposed area fractions combine phase spectra in reflectance space before D65/2° colorimetry. | The area model assumes clean, optically independent polished patches. Oxide, scattering, orientation and roughness need matching data or a separate model. |

The mechanical and spectral nodes provide input templates. A particle-free
measured state uses an empty precipitate array. Results retain the inputs,
sources, ranges, calculation assumptions and coverage gaps.

[Processing methods](processing.md) · [Precipitation](precipitation.md) ·
[Spectral color](optical-colors.md) · [Mechanical properties](mechanical-properties.md)

## Benchmark sources

- **Al–Cu.** Published Al–4 wt% Cu TEM particle measurements and Vickers
  hardness before aging and after 18, 30, 120 and 168 h at 453 K exercise
  changes in the governing obstacle mechanism.
  [Rodríguez-Veiga et al.](https://arxiv.org/abs/1804.09634)
- **Al–Mg–Si.** 6061 thermal-cycle TEM/SANS and tensile results give a case
  for needle growth and strength validation. Hold out whole thermal histories.
  [6061 study](https://www.sciencedirect.com/science/article/pii/S135964541300726X)
- **Al–Zn–Mg–Cu.** AA7030/7050 aging measurements and 7075-T6 long-crack
  growth curves exercise separate precipitation and fatigue mechanisms.
  [Aging study](https://www.sciencedirect.com/science/article/abs/pii/S2589152922002411) ·
  [NASA fatigue tests](https://ntrs.nasa.gov/api/citations/20050215293/downloads/20050215293.pdf)
- **Cast Al–Si.** Directional-solidification experiments give cooling
  histories and segregation. Alloy 319 X-ray measurements span solid and
  liquid density.
  [Directional casting measurements](https://www.scielo.br/j/mr/a/znxhpVVybYS5j4R7TsTgG8H/?lang=en) ·
  [Alloy 319 density experiments](https://www.sciencedirect.com/science/article/abs/pii/S1359646299000433)

Report execution coverage, applicable-input coverage and independent
experimental error separately. The optimization domain and independent
property error tolerances remain to be established.

### Initial workflow checks

The pinned MatCalc Al assessment completed Scheil runs at 101325 Pa for
Al–4Cu, Al–1Mg–0.6Si, Al–7Si and Al–5.6Zn–2.5Mg–1.6Cu, all by mass percent.
The Al–Mg–Si calculation used a 5 K step after a 10 K run retained unresolved
liquid. The Al–7Si terminal bracket was 850.195–850.215 K, close to the published
binary eutectic near 850.2 K.
[Al–Si precipitation and eutectic data](https://www.sciencedirect.com/science/article/pii/S0921509307014244)

At 298.15 K and 101325 Pa, the four nominal equilibrium checks gave dense
estimates for Al–4Cu (2.776 g/cm³), Al–1Mg–0.6Si (2.683 g/cm³) and Al–7Si
(2.668 g/cm³). The Al–Zn–Mg–Cu case had 92.3 mol% density coverage. The
`LC14_ZN2MG` and `MGALCUZN_T` phases need applicable volumes and stiffness
for their distinct multicomponent compositions. These checks establish
which software paths and references resolve for the stated equilibrium cases.
